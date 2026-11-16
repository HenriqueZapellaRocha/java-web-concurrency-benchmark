#!/usr/bin/env python3
"""Registra metadados de desenvolvimento sem coletar senhas/env dos containers."""
import datetime
import json
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / (".env" if (ROOT / ".env").is_file() else ".env.example")
COMPOSE = ("docker", "compose", "--env-file", str(ENV_FILE), "-f", "infra/compose.yaml",
           "--profile", "m1", "--profile", "m2", "--profile", "m3")


def command(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"Falha ao executar {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def container_metadata(service):
    identifier = command(*COMPOSE, "ps", "-q", service)
    if not identifier:
        raise RuntimeError(f"Container {service} não está em execução")
    template = ('{"image":{{json .Config.Image}},"imageId":{{json .Image}},'
                '"memoryBytes":{{.HostConfig.Memory}},"nanoCpus":{{.HostConfig.NanoCpus}}}')
    return json.loads(command("docker", "inspect", "--format", template, identifier))


def container_env(service, name):
    identifier = command(*COMPOSE, "ps", "-q", service)
    if not identifier:
        raise RuntimeError(f"Container {service} não está em execução")
    return command("docker", "exec", identifier, "printenv", name)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {"m1", "m2", "m3"}:
        raise SystemExit("Uso: capture_environment.py m1|m2|m3 http://127.0.0.1:PORT")
    model, base_url = sys.argv[1:]
    with urllib.request.urlopen(base_url + "/environment", timeout=10) as response:
        runtime = json.load(response)
    if runtime.get("model") != model:
        raise RuntimeError("O modelo em execução não corresponde ao modelo informado")
    with urllib.request.urlopen(base_url + "/actuator/health/readiness", timeout=10) as response:
        readiness = json.load(response)
    now = datetime.datetime.now(datetime.timezone.utc)
    snapshot = {
        "recordedAt": now.isoformat(),
        "purpose": "environment-validation",
        "model": model,
        "runtime": runtime,
        "readiness": readiness,
        "dockerVersion": command("docker", "version", "--format", "{{.Server.Version}}"),
        "composeVersion": command("docker", "compose", "version", "--short"),
        "application": container_metadata(model),
        "postgres": container_metadata("postgres"),
        "cpuWorkload": {
            "iterations": int(container_env(model, "CPU_ITERATIONS")),
            "executionMode": (container_env(model, "CPU_EXECUTION_MODE")
                              if model == "m3" else "request-thread"),
        },
    }
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    snapshot["gitCommit"] = revision.stdout.strip() if revision.returncode == 0 else None
    output = ROOT / "results" / "raw" / f"{model}-environment-{now:%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    print(output)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from error
