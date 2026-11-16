#!/usr/bin/env python3
"""Orquestra a campanha reproduzível do workload CPU do TCC 2."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import platform
import random
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = ROOT / "results" / "raw"
PROCESSED_ROOT = ROOT / "results" / "processed"
ENV_SCRIPT = ROOT / "scripts" / "env.sh"
BUILD_SCRIPT = ROOT / "scripts" / "build.sh"
COMPOSE_FILE = ROOT / "infra" / "compose.yaml"
CPU_SCRIPT = ROOT / "tests" / "k6" / "cpu.js"
METRIC_NAMES = (
    "process.cpu.usage",
    "process.cpu.time",
    "process.uptime",
    "system.cpu.usage",
    "system.load.average.1m",
    "jvm.memory.used",
    "jvm.memory.committed",
    "jvm.memory.max",
    "jvm.buffer.memory.used",
    "jvm.buffer.count",
    "jvm.threads.live",
    "jvm.threads.daemon",
    "jvm.threads.peak",
    "jvm.threads.states",
    "jvm.gc.pause",
    "jvm.gc.memory.allocated",
    "jvm.gc.memory.promoted",
    "jvm.gc.live.data.size",
    "jvm.classes.loaded",
    "jvm.compilation.time",
    "process.files.open",
    "process.files.max",
    "http.server.requests",
    "tomcat.threads.config.max",
    "tomcat.threads.current",
    "tomcat.threads.busy",
)
DEFAULT_VARIANT_IDS = (
    "m1-platform", "m2-virtual", "m3-event-loop", "m3-bounded-elastic",
)
VARIANTS = (
    {"id": "m1-platform", "model": "m1", "mode": "request-thread", "primary": True,
     "tomcatMaxThreads": 200, "tomcatMinSpareThreads": 10},
    {"id": "m2-virtual", "model": "m2", "mode": "request-thread", "primary": True},
    {"id": "m3-event-loop", "model": "m3", "mode": "event-loop", "primary": True},
    {"id": "m3-bounded-elastic", "model": "m3", "mode": "bounded-elastic", "primary": False},
    {"id": "m1-platform-t2", "model": "m1", "mode": "request-thread", "primary": False,
     "tomcatMaxThreads": 2, "tomcatMinSpareThreads": 2},
    {"id": "m1-platform-t4", "model": "m1", "mode": "request-thread", "primary": False,
     "tomcatMaxThreads": 4, "tomcatMinSpareThreads": 4},
    {"id": "m1-platform-t8", "model": "m1", "mode": "request-thread", "primary": False,
     "tomcatMaxThreads": 8, "tomcatMinSpareThreads": 8},
    {"id": "m1-platform-t16", "model": "m1", "mode": "request-thread", "primary": False,
     "tomcatMaxThreads": 16, "tomcatMinSpareThreads": 10},
    {"id": "m1-platform-t32", "model": "m1", "mode": "request-thread", "primary": False,
     "tomcatMaxThreads": 32, "tomcatMinSpareThreads": 10},
)
RESUME_CONFIGURATION_KEYS = (
    "rates", "variants", "repetitions", "iterations", "warmup_rate",
    "warmup_duration", "measurement_duration", "cooldown",
    "pre_allocated_vus", "max_vus", "request_timeout", "seed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_seconds(value: str) -> float:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"duração inválida: {value}")
    amount = float(match.group(1))
    return amount * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[match.group(2)]


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("o valor deve ser positivo")
    return parsed


def rates(value: str) -> list[int]:
    result = [positive_int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise argparse.ArgumentTypeError("informe ao menos uma taxa")
    return result


def variant_ids(value: str) -> list[str]:
    available = {variant["id"] for variant in VARIANTS}
    result = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(result) - available)
    if not result:
        raise argparse.ArgumentTypeError("informe ao menos uma variante")
    if invalid:
        raise argparse.ArgumentTypeError(
            f"variantes inválidas: {', '.join(invalid)}; use {', '.join(sorted(available))}"
        )
    return list(dict.fromkeys(result))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa e consolida o experimento configurável de POST /cpu.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="mostra o plano sem usar Docker")
    action.add_argument("--execute", action="store_true", help="executa a campanha")
    action.add_argument("--consolidate", metavar="STUDY_ID", help="regera CSVs de uma campanha existente")
    parser.add_argument("--rates", type=rates, default=rates("25,60,75,90"))
    parser.add_argument("--variants", type=variant_ids,
                        default=list(DEFAULT_VARIANT_IDS),
                        help="IDs separados por vírgula")
    parser.add_argument("--repetitions", type=positive_int, default=5)
    parser.add_argument("--iterations", type=positive_int, default=200000)
    parser.add_argument("--warmup-rate", type=positive_int, default=25)
    parser.add_argument("--warmup-duration", default="30s", type=str)
    parser.add_argument("--measurement-duration", default="60s", type=str)
    parser.add_argument("--cooldown", default=20, type=int, help="segundos entre rodadas")
    parser.add_argument("--pre-allocated-vus", type=positive_int, default=100)
    parser.add_argument("--max-vus", type=positive_int, default=1000)
    parser.add_argument("--request-timeout", default="15s")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--study-id", help="identificador seguro; permite retomar uma campanha")
    parser.add_argument("--skip-build", action="store_true", help="reutiliza os jars existentes")
    args = parser.parse_args()
    duration_seconds(args.warmup_duration)
    duration_seconds(args.measurement_duration)
    duration_seconds(args.request_timeout)
    if args.cooldown < 0:
        parser.error("--cooldown não pode ser negativo")
    if args.max_vus < args.pre_allocated_vus:
        parser.error("--max-vus deve ser maior ou igual a --pre-allocated-vus")
    if args.study_id and not re.fullmatch(r"[A-Za-z0-9._-]+", args.study_id):
        parser.error("--study-id aceita somente letras, números, ponto, hífen e sublinhado")
    return args


def make_plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    selected = [variant for variant in VARIANTS if variant["id"] in args.variants]
    for repetition in range(1, args.repetitions + 1):
        block = [
            {**variant, "rate": rate, "repetition": repetition}
            for variant in selected
            for rate in args.rates
        ]
        random.Random(args.seed + repetition).shuffle(block)
        for position, run in enumerate(block, 1):
            run["runId"] = (
                f"r{repetition:02d}-{position:02d}-{run['id']}-{run['rate']:04d}rps"
            )
            plan.append(run)
    return plan


def display_plan(args: argparse.Namespace, plan: list[dict[str, Any]]) -> None:
    per_run = (
        duration_seconds(args.warmup_duration)
        + duration_seconds(args.measurement_duration)
        + args.cooldown
    )
    print("Experimento CPU-bound do TCC 2")
    print(f"Rodadas: {len(plan)} ({len(args.variants)} variantes × {len(args.rates)} taxas × {args.repetitions} repetições)")
    print(f"Variantes: {', '.join(args.variants)}")
    print(f"Taxas de medição: {', '.join(map(str, args.rates))} req/s")
    print(f"Aquecimento: {args.warmup_rate} req/s por {args.warmup_duration}")
    print(f"Medição: {args.measurement_duration}; cooldown: {args.cooldown}s")
    print(f"VUs: {args.pre_allocated_vus} pré-alocados, máximo {args.max_vus}")
    print(f"Duração mínima estimada: {len(plan) * per_run / 3600:.2f} h, mais reinícios")
    print("Ordem determinística:")
    for index, run in enumerate(plan, 1):
        qualifier = "principal" if run["primary"] else "sensibilidade"
        print(f"  {index:02d}. {run['runId']} ({qualifier})")


def resume_configuration_differences(saved: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [key for key in RESUME_CONFIGURATION_KEYS if saved.get(key) != current.get(key)]


def env_file() -> Path:
    configured = ROOT / ".env"
    return configured if configured.exists() else ROOT / ".env.example"


def compose_command(*parts: str) -> list[str]:
    return [
        "docker", "compose", "--env-file", str(env_file()),
        "-f", str(COMPOSE_FILE), *parts,
    ]


def run_logged(command: list[str], log_path: Path, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True
        )
    if check and process.returncode != 0:
        raise RuntimeError(f"comando falhou ({process.returncode}); consulte {log_path}")
    return process


def output(command: list[str], env: dict[str, str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, env=env, text=True).strip()


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_identity() -> dict[str, Any]:
    files = {
        "k6CpuScript": CPU_SCRIPT,
        "compose": COMPOSE_FILE,
        "cpuStudy": Path(__file__).resolve(),
        "m1Jar": ROOT / "apps" / "mvc" / "build" / "libs" / "mvc-app.jar",
        "m2Jar": ROOT / "apps" / "virtual-threads" / "build" / "libs" / "virtual-threads-app.jar",
        "m3Jar": ROOT / "apps" / "reactive" / "build" / "libs" / "reactive-app.jar",
    }
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for name, path in files.items()}


def application_url(model: str, env: dict[str, str]) -> str:
    binding = output(compose_command("port", model, "8080"), env)
    if not binding:
        raise RuntimeError(f"porta do modelo {model} não encontrada")
    return f"http://{binding}"


def runtime_configuration(base_url: str, container_id: str, run: dict[str, Any],
                          env: dict[str, str]) -> dict[str, Any]:
    raw_environment = json.loads(output([
        "docker", "inspect", "--format", "{{json .Config.Env}}", container_id
    ], env))
    environment = {}
    allowed = {
        "CPU_ITERATIONS", "CPU_EXECUTION_MODE", "JAVA_TOOL_OPTIONS",
        "MIXED_CPU_ITERATIONS", "MIXED_CPU_EXECUTION_MODE",
        "DB_POOL_MAX_SIZE", "IO_DATABASE_DELAY",
        "TOMCAT_MAX_THREADS", "TOMCAT_MIN_SPARE_THREADS",
    }
    for entry in raw_environment:
        key, separator, value = entry.partition("=")
        if separator and key in allowed:
            environment[key] = value
    snapshot = http_json(f"{base_url}/environment")
    processors = snapshot.get("availableProcessors")
    if processors != 2:
        raise RuntimeError(f"JVM percebeu {processors} processadores; o protocolo exige 2")
    if run["model"] == "m1":
        expected_max = str(run.get("tomcatMaxThreads", 200))
        expected_min = str(run.get("tomcatMinSpareThreads", 10))
        if environment.get("TOMCAT_MAX_THREADS") != expected_max \
                or environment.get("TOMCAT_MIN_SPARE_THREADS") != expected_min:
            raise RuntimeError(
                "limite Tomcat aplicado diverge do plano: "
                f"esperado {expected_max}/{expected_min}, observado "
                f"{environment.get('TOMCAT_MAX_THREADS')}/{environment.get('TOMCAT_MIN_SPARE_THREADS')}"
            )
    if "mixedCpuIterations" in run:
        expected_iterations = str(run["mixedCpuIterations"])
        expected_mode = run.get("executionMode", "request-thread")
        if environment.get("MIXED_CPU_ITERATIONS") != expected_iterations:
            raise RuntimeError(
                "iterações mixed aplicadas divergem do plano: "
                f"esperado {expected_iterations}, observado "
                f"{environment.get('MIXED_CPU_ITERATIONS')}"
            )
        if run["model"] == "m3" and environment.get("MIXED_CPU_EXECUTION_MODE") != expected_mode:
            raise RuntimeError(
                "modo mixed aplicado diverge do plano: "
                f"esperado {expected_mode}, observado "
                f"{environment.get('MIXED_CPU_EXECUTION_MODE')}"
            )
    return {"capturedAt": utc_now(), "environmentEndpoint": snapshot,
            "selectedContainerEnvironment": environment}


def http_json(url: str, timeout: float = 5) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def actuator_snapshot(base_url: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"capturedAt": utc_now(), "metrics": {}}
    def read_metric(name: str) -> tuple[str, Any]:
        try:
            return name, http_json(f"{base_url}/actuator/metrics/{name}")
        except (OSError, ValueError, urllib.error.URLError) as error:
            return name, {"error": str(error)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for name, value in executor.map(read_metric, METRIC_NAMES):
            snapshot["metrics"][name] = value
    return snapshot


def percentage(value: str | None) -> float | None:
    if not value or value == "--":
        return None
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


def byte_size(value: str | None) -> int | None:
    if not value or value == "--":
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)\s*", value, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    factors = {
        "b": 1,
        "kb": 1000,
        "mb": 1000 ** 2,
        "gb": 1000 ** 3,
        "tb": 1000 ** 4,
        "kib": 1024,
        "mib": 1024 ** 2,
        "gib": 1024 ** 3,
        "tib": 1024 ** 4,
    }
    return round(amount * factors[unit])


def byte_pair(value: str | None) -> tuple[int | None, int | None]:
    if not value or " / " not in value:
        return None, None
    left, right = value.split(" / ", 1)
    return byte_size(left), byte_size(right)


def phase_at(elapsed: float, warmup: float, measurement: float) -> str:
    return "warmup" if elapsed < warmup else "measurement" if elapsed < warmup + measurement else "graceful-stop"


def container_sample(data: dict[str, Any], elapsed: float, warmup: float, measurement: float) -> dict[str, Any]:
    memory_usage, memory_limit = byte_pair(data.get("MemUsage"))
    network_received, network_sent = byte_pair(data.get("NetIO"))
    block_read, block_written = byte_pair(data.get("BlockIO"))
    return {
        "capturedAt": utc_now(),
        "elapsedSeconds": round(elapsed, 3),
        "phase": phase_at(elapsed, warmup, measurement),
        "cpuPercent": percentage(data.get("CPUPerc")),
        "memoryPercent": percentage(data.get("MemPerc")),
        "memoryUsage": data.get("MemUsage"),
        "memoryUsageBytes": memory_usage,
        "memoryLimitBytes": memory_limit,
        "networkIo": data.get("NetIO"),
        "networkReceivedBytes": network_received,
        "networkSentBytes": network_sent,
        "blockIo": data.get("BlockIO"),
        "blockReadBytes": block_read,
        "blockWrittenBytes": block_written,
        "pids": int(data["PIDs"]) if str(data.get("PIDs", "")).isdigit() else None,
    }


def sample_containers(container_ids: dict[str, str], elapsed: float, warmup: float,
                      measurement: float, env: dict[str, str]) -> dict[str, dict[str, Any]]:
    def read_container(item: tuple[str, str]) -> tuple[str, dict[str, Any]]:
        role, container_id = item
        try:
            process = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_id],
                cwd=ROOT, env=env, text=True, capture_output=True, check=True,
            )
            return role, container_sample(
                json.loads(process.stdout.strip()), elapsed, warmup, measurement
            )
        except (subprocess.SubprocessError, ValueError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            return role, {
                "capturedAt": utc_now(), "elapsedSeconds": round(elapsed, 3),
                "phase": phase_at(elapsed, warmup, measurement),
                "error": str(detail).strip(),
            }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(container_ids)) as executor:
        return dict(executor.map(read_container, container_ids.items()))


def find_k6_container(env: dict[str, str]) -> str | None:
    identifiers = output([
        "docker", "ps",
        "--filter", "label=com.docker.compose.project=tcc2",
        "--filter", "label=com.docker.compose.service=k6",
        "--format", "{{.ID}}",
    ], env).splitlines()
    return identifiers[0] if identifiers else None


def key_values(raw: str, separator: str | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        if separator and separator in line:
            key, value = line.split(separator, 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts
        value = value.strip()
        values[key.strip()] = int(value) if value.isdigit() else value
    return values


def container_diagnostics(container_id: str, env: dict[str, str]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"capturedAt": utc_now()}
    inspect_format = (
        '{"image":{{json .Config.Image}},"imageId":{{json .Image}},'
        '"memoryLimitBytes":{{.HostConfig.Memory}},"nanoCpus":{{.HostConfig.NanoCpus}},'
        '"pidsLimit":{{json .HostConfig.PidsLimit}},"startedAt":{{json .State.StartedAt}}}'
    )
    try:
        diagnostics["container"] = json.loads(output([
            "docker", "inspect", "--format", inspect_format, container_id
        ], env))
    except (subprocess.SubprocessError, ValueError) as error:
        diagnostics["container"] = {"error": str(error)}
    files = {
        "cpuStat": ("/sys/fs/cgroup/cpu.stat", None),
        "memoryEvents": ("/sys/fs/cgroup/memory.events", None),
        "processStatus": ("/proc/1/status", ":"),
    }
    for name, (path, separator) in files.items():
        try:
            diagnostics[name] = key_values(output(["docker", "exec", container_id, "cat", path], env), separator)
        except subprocess.SubprocessError as error:
            diagnostics[name] = {"error": str(error)}
    context_switch_command = (
        "awk '/^voluntary_ctxt_switches|^nonvoluntary_ctxt_switches/ "
        "{gsub(\":\", \"\", $1); sum[$1]+=$2} "
        "END {for (key in sum) print key, sum[key]}' /proc/1/task/*/status"
    )
    try:
        diagnostics["threadContextSwitches"] = key_values(output([
            "docker", "exec", container_id, "sh", "-c", context_switch_command
        ], env))
    except subprocess.SubprocessError as error:
        diagnostics["threadContextSwitches"] = {"error": str(error)}
    for name, path in {
        "memoryCurrentBytes": "/sys/fs/cgroup/memory.current",
        "memoryPeakBytes": "/sys/fs/cgroup/memory.peak",
    }.items():
        try:
            diagnostics[name] = int(output(["docker", "exec", container_id, "cat", path], env))
        except (subprocess.SubprocessError, ValueError) as error:
            diagnostics[name] = {"error": str(error)}
    return diagnostics


def metric_value(summary: dict[str, Any], metric: str, value: str, default: Any = None) -> Any:
    data = summary.get("metrics", {}).get(metric)
    if not data:
        return default
    # k6 1.8 exporta os campos diretamente; versões anteriores usam "values".
    return data.get("values", data).get(value, default)


def summarize_stats(samples: list[dict[str, Any]], field: str) -> tuple[float | None, float | None]:
    values = [float(sample[field]) for sample in samples if sample.get("phase") == "measurement" and sample.get(field) is not None]
    return (statistics.mean(values), max(values)) if values else (None, None)


def measurement_delta(samples: list[dict[str, Any]], field: str) -> float | None:
    values = [
        (float(sample["elapsedSeconds"]), float(sample[field]))
        for sample in samples
        if sample.get("phase") == "measurement" and sample.get(field) is not None
    ]
    if len(values) < 2:
        return None
    values.sort()
    return max(0.0, values[-1][1] - values[0][1])


def nested_number(value: dict[str, Any] | None, *path: str) -> float | None:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return float(current) if isinstance(current, (int, float)) else None


def diagnostics_delta(before: dict[str, Any] | None, after: dict[str, Any] | None,
                      section: str, key: str, divisor: float = 1.0) -> float | None:
    first = nested_number(before, section, key)
    last = nested_number(after, section, key)
    return max(0.0, last - first) / divisor if first is not None and last is not None else None


def actuator_measurement(snapshot: dict[str, Any] | None, metric: str, statistic: str) -> float | None:
    if not snapshot:
        return None
    data = snapshot.get("metrics", {}).get(metric, {})
    for measurement in data.get("measurements", []):
        if measurement.get("statistic") == statistic:
            value = measurement.get("value")
            return float(value) if isinstance(value, (int, float)) else None
    measurements = data.get("measurements", [])
    if len(measurements) == 1:
        value = measurements[0].get("value")
        return float(value) if isinstance(value, (int, float)) else None
    return None


def actuator_delta(before: dict[str, Any] | None, after: dict[str, Any] | None,
                   metric: str, statistic: str, divisor: float = 1.0) -> float | None:
    first = actuator_measurement(before, metric, statistic)
    last = actuator_measurement(after, metric, statistic)
    before_metric = (before or {}).get("metrics", {}).get(metric, {})
    if first is None and str(before_metric.get("error", "")).startswith("HTTP Error 404"):
        first = 0.0
    return max(0.0, last - first) / divisor if first is not None and last is not None else None


def parse_run_summary(summary: dict[str, Any], run: dict[str, Any], args: argparse.Namespace,
                      samples: list[dict[str, Any]], load_samples: list[dict[str, Any]] | None = None,
                      diagnostics_before: dict[str, Any] | None = None,
                      diagnostics_after: dict[str, Any] | None = None,
                      actuator_before: dict[str, Any] | None = None,
                      actuator_after: dict[str, Any] | None = None) -> dict[str, Any]:
    load_samples = load_samples or []
    measurement_seconds = duration_seconds(args.measurement_duration)
    expected = run["rate"] * measurement_seconds
    requests = metric_value(summary, "cpu_measurement_requests", "count", 0) or 0
    strict_requests = metric_value(summary, "cpu_measurement_completions_in_window", "count", None)
    strict_metric_available = strict_requests is not None
    if strict_requests is None:
        # Compatibilidade apenas para consolidar pilotos anteriores à métrica.
        strict_requests = requests
    successful_requests = metric_value(summary, "cpu_measurement_successes_in_window", "count", None)
    success_metric_available = successful_requests is not None
    failures_in_window = metric_value(summary, "cpu_measurement_failures_in_window", "count", None)
    completions_after_window = metric_value(
        summary, "cpu_measurement_completions_after_window", "count", None
    )
    failures_after_window = metric_value(
        summary, "cpu_measurement_failures_after_window", "count", None
    )
    # Em uma métrica Rate, "passes" conta os valores true. O script adiciona
    # true somente quando a validação da resposta falha.
    failures = metric_value(summary, "cpu_measurement_failures", "passes", 0) or 0
    if completions_after_window is None:
        completions_after_window = max(0, requests - strict_requests)
    if success_metric_available:
        failures_in_window = failures_in_window or 0
        failures_after_window = failures_after_window or 0
        achieved_requests = successful_requests
    else:
        # Campanhas legadas não permitem localizar os erros no tempo. Mantemos
        # a taxa de conclusões original, explicitamente marcada como legada.
        achieved_requests = strict_requests
    cpu_avg, cpu_max = summarize_stats(samples, "cpuPercent")
    memory_avg, memory_max = summarize_stats(samples, "memoryPercent")
    memory_bytes_avg, memory_bytes_max = summarize_stats(samples, "memoryUsageBytes")
    pids_avg, pids_max = summarize_stats(samples, "pids")
    load_cpu_avg, load_cpu_max = summarize_stats(load_samples, "cpuPercent")
    load_memory_avg, load_memory_max = summarize_stats(load_samples, "memoryUsageBytes")
    load_pids_avg, load_pids_max = summarize_stats(load_samples, "pids")
    completion = strict_requests / expected if expected else 0
    success_ratio = achieved_requests / expected if expected else 0
    if failures:
        classification = "saturated-with-errors"
    elif success_ratio < 0.99:
        classification = "saturated"
    else:
        classification = "sustained"
    return {
        "runId": run["runId"],
        "repetition": run["repetition"],
        "variant": run["id"],
        "model": run["model"],
        "executionMode": run["mode"],
        "primaryComparison": run["primary"],
        "targetRateRps": run["rate"],
        "expectedRequests": int(expected),
        "completedRequests": int(requests),
        "completedInMeasurementWindow": int(strict_requests),
        "completedDuringGracefulStop": int(completions_after_window),
        "strictWindowMetricAvailable": strict_metric_available,
        "successfulWindowMetricAvailable": success_metric_available,
        "successfulInMeasurementWindow": int(successful_requests) if success_metric_available else None,
        "failedInMeasurementWindow": int(failures_in_window) if success_metric_available else None,
        "failedDuringGracefulStop": int(failures_after_window) if success_metric_available else None,
        "completionRps": strict_requests / measurement_seconds,
        "successfulRps": successful_requests / measurement_seconds if success_metric_available else None,
        "achievedRps": achieved_requests / measurement_seconds,
        "achievedRpsDefinition": "successful" if success_metric_available else "completed-legacy",
        "completionRatio": completion,
        "successRatio": success_ratio if success_metric_available else None,
        "measurementShortfallRequests": max(0, int(expected - strict_requests)),
        "successfulShortfallRequests": (
            max(0, int(expected - successful_requests)) if success_metric_available else None
        ),
        "latencyAvgMs": metric_value(summary, "cpu_measurement_http_req_duration", "avg"),
        "latencyP50Ms": metric_value(summary, "cpu_measurement_http_req_duration", "med"),
        "latencyP95Ms": metric_value(summary, "cpu_measurement_http_req_duration", "p(95)"),
        "latencyP99Ms": metric_value(summary, "cpu_measurement_http_req_duration", "p(99)"),
        "latencyMaxMs": metric_value(summary, "cpu_measurement_http_req_duration", "max"),
        "failedRequests": int(failures),
        "totalDroppedIterations": int(metric_value(summary, "dropped_iterations", "count", 0) or 0),
        "maxObservedVUs": metric_value(summary, "vus", "max"),
        "appCpuAvgPercent": cpu_avg,
        "appCpuMaxPercent": cpu_max,
        "appMemoryAvgPercent": memory_avg,
        "appMemoryMaxPercent": memory_max,
        "appMemoryAvgBytes": memory_bytes_avg,
        "appMemoryMaxBytes": memory_bytes_max,
        "appPidsAvg": pids_avg,
        "appPidsMax": pids_max,
        "appNetworkReceivedBytes": measurement_delta(samples, "networkReceivedBytes"),
        "appNetworkSentBytes": measurement_delta(samples, "networkSentBytes"),
        "appBlockReadBytes": measurement_delta(samples, "blockReadBytes"),
        "appBlockWrittenBytes": measurement_delta(samples, "blockWrittenBytes"),
        "loadGeneratorCpuAvgPercent": load_cpu_avg,
        "loadGeneratorCpuMaxPercent": load_cpu_max,
        "loadGeneratorMemoryAvgBytes": load_memory_avg,
        "loadGeneratorMemoryMaxBytes": load_memory_max,
        "loadGeneratorPidsAvg": load_pids_avg,
        "loadGeneratorPidsMax": load_pids_max,
        "containerCpuUsageSeconds": diagnostics_delta(
            diagnostics_before, diagnostics_after, "cpuStat", "usage_usec", 1_000_000
        ),
        "containerCpuThrottledSeconds": diagnostics_delta(
            diagnostics_before, diagnostics_after, "cpuStat", "throttled_usec", 1_000_000
        ),
        "containerCpuThrottledPeriods": diagnostics_delta(
            diagnostics_before, diagnostics_after, "cpuStat", "nr_throttled"
        ),
        "containerMemoryPeakBytes": nested_number(diagnostics_after, "memoryPeakBytes"),
        "voluntaryContextSwitches": diagnostics_delta(
            diagnostics_before, diagnostics_after, "threadContextSwitches", "voluntary_ctxt_switches"
        ),
        "nonVoluntaryContextSwitches": diagnostics_delta(
            diagnostics_before, diagnostics_after, "threadContextSwitches", "nonvoluntary_ctxt_switches"
        ),
        "jvmProcessCpuTimeSeconds": actuator_delta(
            actuator_before, actuator_after, "process.cpu.time", "TOTAL", 1_000_000_000
        ),
        "jvmGcPauseCount": actuator_delta(
            actuator_before, actuator_after, "jvm.gc.pause", "COUNT"
        ),
        "jvmGcPauseSeconds": actuator_delta(
            actuator_before, actuator_after, "jvm.gc.pause", "TOTAL_TIME"
        ),
        "jvmAllocatedBytes": actuator_delta(
            actuator_before, actuator_after, "jvm.gc.memory.allocated", "COUNT"
        ),
        "jvmPromotedBytes": actuator_delta(
            actuator_before, actuator_after, "jvm.gc.memory.promoted", "COUNT"
        ),
        "jvmThreadsLiveAfter": actuator_measurement(actuator_after, "jvm.threads.live", "VALUE"),
        "jvmThreadsPeakAfter": actuator_measurement(actuator_after, "jvm.threads.peak", "VALUE"),
        "tomcatConfiguredMaxThreads": actuator_measurement(
            actuator_after, "tomcat.threads.config.max", "VALUE"
        ),
        "tomcatThreadsCurrentAfter": actuator_measurement(
            actuator_after, "tomcat.threads.current", "VALUE"
        ),
        "tomcatThreadsBusyAfter": actuator_measurement(
            actuator_after, "tomcat.threads.busy", "VALUE"
        ),
        "classification": classification,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json_if_present(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # Variantes de sensibilidade podem acrescentar metadados próprios (por
    # exemplo, limites Tomcat) que não existem na primeira linha do estudo.
    # O cabeçalho precisa representar a união estável de todos os registros.
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "completed":
            groups[(row["variant"], row["targetRateRps"])].append(row)
    aggregated: list[dict[str, Any]] = []
    metrics = (
        "achievedRps", "completionRps", "successfulRps", "completionRatio", "successRatio",
        "completedInMeasurementWindow", "successfulInMeasurementWindow",
        "failedInMeasurementWindow", "failedDuringGracefulStop",
        "completedDuringGracefulStop", "measurementShortfallRequests",
        "successfulShortfallRequests", "failedRequests",
        "totalDroppedIterations", "latencyAvgMs", "latencyP50Ms", "latencyP95Ms",
        "latencyP99Ms", "latencyMaxMs", "maxObservedVUs", "appCpuAvgPercent",
        "appCpuMaxPercent", "appMemoryAvgPercent", "appMemoryMaxPercent",
        "appMemoryAvgBytes", "appMemoryMaxBytes", "appPidsAvg", "appPidsMax",
        "appNetworkReceivedBytes", "appNetworkSentBytes", "appBlockReadBytes",
        "appBlockWrittenBytes", "loadGeneratorCpuAvgPercent", "loadGeneratorCpuMaxPercent",
        "loadGeneratorMemoryAvgBytes", "loadGeneratorMemoryMaxBytes", "loadGeneratorPidsAvg",
        "loadGeneratorPidsMax", "containerCpuUsageSeconds", "containerCpuThrottledSeconds",
        "containerCpuThrottledPeriods", "containerMemoryPeakBytes", "voluntaryContextSwitches",
        "nonVoluntaryContextSwitches", "jvmProcessCpuTimeSeconds", "jvmGcPauseCount",
        "jvmGcPauseSeconds", "jvmAllocatedBytes", "jvmPromotedBytes", "jvmThreadsLiveAfter",
        "jvmThreadsPeakAfter", "tomcatConfiguredMaxThreads", "tomcatThreadsCurrentAfter",
        "tomcatThreadsBusyAfter",
    )
    for (variant, rate), group in sorted(groups.items()):
        item: dict[str, Any] = {
            "variant": variant,
            "targetRateRps": rate,
            "completedRuns": len(group),
            "sustainedRuns": sum(row["classification"] == "sustained" for row in group),
            "saturatedRuns": sum(row["classification"] == "saturated" for row in group),
            "runsWithErrors": sum(row["classification"] == "saturated-with-errors" for row in group),
        }
        for metric in metrics:
            values = [float(row[metric]) for row in group if row.get(metric) is not None]
            item[f"{metric}Mean"] = statistics.mean(values) if values else None
            item[f"{metric}StdDev"] = statistics.stdev(values) if len(values) > 1 else 0 if values else None
        aggregated.append(item)
    return aggregated


def consolidate(study_id: str) -> int:
    raw_dir = RAW_ROOT / study_id
    processed_dir = PROCESSED_ROOT / study_id
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Campanha não encontrada: {study_id}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    saved = manifest["configuration"]
    saved.setdefault("consolidate", None)
    saved.setdefault("variants", [variant["id"] for variant in VARIANTS])
    args = argparse.Namespace(**saved)
    rows: list[dict[str, Any]] = []
    for run in manifest["plan"]:
        run_dir = raw_dir / run["runId"]
        result_path = run_dir / "run.json"
        summary_path = run_dir / f"{run['runId']}-summary.json"
        if not result_path.exists() or not summary_path.exists():
            continue
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        stats_path = run_dir / "docker-stats.jsonl"
        samples = []
        if stats_path.exists():
            samples = [json.loads(line) for line in stats_path.read_text(encoding="utf-8").splitlines() if line]
        load_stats_path = run_dir / "load-generator-stats.jsonl"
        load_samples = []
        if load_stats_path.exists():
            load_samples = [
                json.loads(line) for line in load_stats_path.read_text(encoding="utf-8").splitlines() if line
            ]
        rebuilt = {**previous, **parse_run_summary(
            summary, run, args, samples, load_samples,
            read_json_if_present(run_dir / "container-before.json"),
            read_json_if_present(run_dir / "container-after.json"),
            read_json_if_present(run_dir / "actuator-before.json"),
            read_json_if_present(run_dir / "actuator-after.json"),
        )}
        rebuilt.pop("droppedIterations", None)  # nome usado antes da consolidação final
        rebuilt["status"] = "completed"
        write_json(result_path, rebuilt)
        rows.append(rebuilt)
    write_csv(processed_dir / "runs.csv", rows)
    write_csv(processed_dir / "summary.csv", aggregate(rows))
    report = {
        "studyId": study_id,
        "status": "complete" if len(rows) == len(manifest["plan"]) else "partial",
        "consolidatedAt": utc_now(),
        "plannedRuns": len(manifest["plan"]),
        "completedRuns": sum(row.get("status") == "completed" for row in rows),
        "failedRuns": sum(row.get("status") == "failed" for row in rows),
        "rawDirectory": str(raw_dir.relative_to(ROOT)),
        "processedDirectory": str(processed_dir.relative_to(ROOT)),
    }
    write_json(processed_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" and report["failedRuns"] == 0 else 2


def run_environment(base: dict[str, str], run: dict[str, Any], args: argparse.Namespace, study_id: str) -> dict[str, str]:
    env = dict(base)
    env.update({
        "APP_CPUS": "2.0",
        "APP_MEMORY": "2g",
        "JVM_HEAP": "512m",
        "CPU_ITERATIONS": str(args.iterations),
        "TOMCAT_MAX_THREADS": str(run.get("tomcatMaxThreads", 200)),
        "TOMCAT_MIN_SPARE_THREADS": str(run.get("tomcatMinSpareThreads", 10)),
        "CPU_EXECUTION_MODE": run["mode"] if run["model"] == "m3" else "event-loop",
        "K6_CPU_RATE": str(run["rate"]),
        "K6_CPU_WARMUP_RATE": str(args.warmup_rate),
        "K6_CPU_WARMUP_DURATION": args.warmup_duration,
        "K6_CPU_MEASUREMENT_DURATION": args.measurement_duration,
        "K6_CPU_PRE_ALLOCATED_VUS": str(args.pre_allocated_vus),
        "K6_CPU_MAX_VUS": str(args.max_vus),
        "K6_CPU_REQUEST_TIMEOUT": args.request_timeout,
        "K6_CPU_WRITE_RAW": "false",
        "CPU_RESULT_DIR": f"{study_id}/{run['runId']}",
        "CPU_RUN_ID": run["runId"],
    })
    return env


def execute_run(study_id: str, run: dict[str, Any], args: argparse.Namespace, base_env: dict[str, str]) -> dict[str, Any]:
    run_dir = RAW_ROOT / study_id / run["runId"]
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "run.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        if previous.get("status") == "completed":
            print(f"  já concluída; pulando {run['runId']}", flush=True)
            return previous

    env = run_environment(base_env, run, args, study_id)
    started = utc_now()
    record: dict[str, Any] = {**run, "status": "running", "startedAt": started}
    write_json(result_path, record)
    samples: list[dict[str, Any]] = []
    load_samples: list[dict[str, Any]] = []
    actuator_before: dict[str, Any] | None = None
    actuator_after: dict[str, Any] | None = None
    diagnostics_before: dict[str, Any] | None = None
    diagnostics_after: dict[str, Any] | None = None
    try:
        run_logged([str(ENV_SCRIPT), "up", run["model"], "--skip-build"], run_dir / "startup.log", env)
        base_url = application_url(run["model"], env)
        actuator_before = actuator_snapshot(base_url)
        write_json(run_dir / "actuator-before.json", actuator_before)
        container_id = output(compose_command("ps", "-q", run["model"]), env)
        if not container_id:
            raise RuntimeError("container da aplicação não encontrado")
        runtime = runtime_configuration(base_url, container_id, run, env)
        record["runtimeConfiguration"] = runtime
        write_json(run_dir / "runtime-configuration.json", runtime)
        diagnostics_before = container_diagnostics(container_id, env)
        write_json(run_dir / "container-before.json", diagnostics_before)

        with (run_dir / "k6.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(ENV_SCRIPT), "cpu-pilot", run["model"]],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            monotonic_start = time.monotonic()
            warmup = duration_seconds(args.warmup_duration)
            measurement = duration_seconds(args.measurement_duration)
            k6_container_id: str | None = None
            next_sample_at = monotonic_start
            while process.poll() is None:
                elapsed = time.monotonic() - monotonic_start
                try:
                    if not k6_container_id:
                        k6_container_id = find_k6_container(env)
                    container_ids = {"application": container_id}
                    if k6_container_id:
                        container_ids["loadGenerator"] = k6_container_id
                    captured = sample_containers(container_ids, elapsed, warmup, measurement, env)
                    samples.append(captured["application"])
                    if "loadGenerator" in captured:
                        load_samples.append(captured["loadGenerator"])
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    samples.append({"capturedAt": utc_now(), "elapsedSeconds": round(elapsed, 3), "error": str(error)})
                next_sample_at += 1
                remaining = next_sample_at - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            k6_exit = process.returncode

        with (run_dir / "docker-stats.jsonl").open("w", encoding="utf-8") as target:
            for sample in samples:
                target.write(json.dumps(sample, ensure_ascii=False) + "\n")
        with (run_dir / "load-generator-stats.jsonl").open("w", encoding="utf-8") as target:
            for sample in load_samples:
                target.write(json.dumps(sample, ensure_ascii=False) + "\n")
        diagnostics_after = container_diagnostics(container_id, env)
        write_json(run_dir / "container-after.json", diagnostics_after)
        actuator_after = actuator_snapshot(base_url)
        write_json(run_dir / "actuator-after.json", actuator_after)
        summary_path = run_dir / f"{run['runId']}-summary.json"
        if not summary_path.exists():
            raise RuntimeError("k6 não gerou o resumo esperado")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        record.update(parse_run_summary(
            summary, run, args, samples, load_samples,
            diagnostics_before, diagnostics_after, actuator_before, actuator_after,
        ))
        # Um threshold do k6 pode falhar justamente por saturação/timeouts. Isso
        # é resultado experimental válido; falha estrutural é registrada abaixo.
        record.update({"status": "completed", "k6ExitCode": k6_exit})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record.update({"status": "failed", "error": str(error)})
    finally:
        record["finishedAt"] = utc_now()
        write_json(result_path, record)
        subprocess.run(compose_command("stop", run["model"]), cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return record


def execute(args: argparse.Namespace, plan: list[dict[str, Any]]) -> int:
    study_id = args.study_id or f"cpu-study-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"
    raw_dir = RAW_ROOT / study_id
    processed_dir = PROCESSED_ROOT / study_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    base_env = dict(os.environ)
    manifest_path = raw_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        differences = resume_configuration_differences(manifest["configuration"], vars(args))
        saved_run_ids = [run["runId"] for run in manifest.get("plan", [])]
        current_run_ids = [run["runId"] for run in plan]
        if differences or saved_run_ids != current_run_ids:
            detail = ", ".join(differences) or "ordem/plano de rodadas"
            print(
                f"Erro de retomada: a configuração diverge do manifesto em: {detail}. "
                "Repita o comando completo original.", file=sys.stderr,
            )
            return 1
        manifest.setdefault("resumedAt", []).append(utc_now())
        write_json(manifest_path, manifest)
    else:
        manifest = {
            "studyId": study_id,
            "purpose": "tcc2-cpu-bound-comparison",
            "createdAt": utc_now(),
            "configuration": vars(args),
            "resourceLimits": {"applicationCpus": 2.0, "applicationMemory": "2g", "jvmHeap": "512m"},
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "variants": list(VARIANTS),
            "plan": plan,
            "codeIdentity": code_identity(),
        }
        write_json(manifest_path, manifest)

    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        manifest["dockerVersion"] = output(["docker", "version", "--format", "{{.Server.Version}}"], base_env)
        manifest["dockerHost"] = json.loads(output([
            "docker", "info", "--format",
            ('{"cpus":{{.NCPU}},"memoryBytes":{{.MemTotal}},"driver":{{json .Driver}},'
             '"operatingSystem":{{json .OperatingSystem}},"architecture":{{json .Architecture}},'
             '"kernelVersion":{{json .KernelVersion}}}')
        ], base_env))
        if not args.skip_build:
            print("Compilando e validando os três modelos...", flush=True)
            run_logged([str(BUILD_SCRIPT), "all"], raw_dir / "build.log", base_env)
            manifest["codeIdentity"] = code_identity()
            write_json(raw_dir / "manifest.json", manifest)
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Erro de preparação: {error}", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    interrupted = False
    try:
        for index, run in enumerate(plan, 1):
            print(f"[{index}/{len(plan)}] {run['runId']}", flush=True)
            existing_path = raw_dir / run["runId"] / "run.json"
            already_completed = False
            if existing_path.exists():
                already_completed = json.loads(existing_path.read_text(encoding="utf-8")).get("status") == "completed"
            result = execute_run(study_id, run, args, base_env)
            rows.append(result)
            write_csv(processed_dir / "runs.csv", rows)
            write_csv(processed_dir / "summary.csv", aggregate(rows))
            print(f"  resultado: {result['status']} ({result.get('classification', 'sem classificação')})", flush=True)
            if index < len(plan) and args.cooldown and not already_completed:
                print(f"  cooldown de {args.cooldown}s", flush=True)
                time.sleep(args.cooldown)
    except KeyboardInterrupt:
        interrupted = True
        print("\nCampanha interrompida; resultados parciais foram preservados.", file=sys.stderr)

    report = {
        "studyId": study_id,
        "status": "interrupted" if interrupted else "complete",
        "finishedAt": utc_now(),
        "plannedRuns": len(plan),
        "completedRuns": sum(row.get("status") == "completed" for row in rows),
        "failedRuns": sum(row.get("status") == "failed" for row in rows),
        "rawDirectory": str(raw_dir.relative_to(ROOT)),
        "processedDirectory": str(processed_dir.relative_to(ROOT)),
    }
    write_json(processed_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if interrupted or report["failedRuns"]:
        print("Retome repetindo o mesmo comando completo usado para iniciar esta campanha.", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    args = arguments()
    if args.consolidate:
        return consolidate(args.consolidate)
    plan = make_plan(args)
    display_plan(args, plan)
    return 0 if args.dry_run else execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
