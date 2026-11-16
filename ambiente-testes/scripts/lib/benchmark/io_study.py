#!/usr/bin/env python3
"""Orquestra pilotos e campanhas reproduzíveis do workload POST /io."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
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
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cpu_study as common


ROOT = common.ROOT
RAW_ROOT = common.RAW_ROOT
PROCESSED_ROOT = common.PROCESSED_ROOT
ENV_SCRIPT = common.ENV_SCRIPT
BUILD_SCRIPT = common.BUILD_SCRIPT
IO_SCRIPT = ROOT / "tests" / "k6" / "io.js"
DEFAULT_VARIANT_IDS = ("m1-platform", "m2-virtual", "m3-reactive")
VARIANTS = (
    {"id": "m1-platform", "model": "m1",
     "tomcatMaxThreads": 200, "tomcatMinSpareThreads": 10},
    {"id": "m2-virtual", "model": "m2"},
    {"id": "m3-reactive", "model": "m3"},
    {"id": "m1-platform-t250", "model": "m1",
     "tomcatMaxThreads": 250, "tomcatMinSpareThreads": 10},
)
POOL_METRICS = (
    "hikaricp.connections.active", "hikaricp.connections.idle",
    "hikaricp.connections.pending", "hikaricp.connections.max", "hikaricp.connections",
    "r2dbc.pool.acquired", "r2dbc.pool.allocated", "r2dbc.pool.idle",
    "r2dbc.pool.max.allocated", "r2dbc.pool.pending",
)
IO_METRICS = common.METRIC_NAMES + POOL_METRICS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def controlled_delay(value: str) -> str:
    seconds = common.duration_seconds(value)
    if seconds > 30:
        raise argparse.ArgumentTypeError("--database-delay deve ficar entre 0ms e 30s")
    return value


def controlled_delays(value: str) -> list[str]:
    result = [controlled_delay(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise argparse.ArgumentTypeError("informe ao menos uma latência controlada")
    return list(dict.fromkeys(result))


def delay_token(value: str) -> str:
    return value.replace(".", "p")


def k6_wall_limit(args: argparse.Namespace) -> float:
    """Rejects host suspension and other pauses that invalidate an open-load run."""
    expected = common.duration_seconds(args.warmup_duration) \
        + common.duration_seconds(args.measurement_duration) + 5
    tolerance = max(30.0, 2 * common.duration_seconds(args.request_timeout))
    return expected + tolerance


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa e consolida o experimento configurável de POST /io.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="mostra o plano sem usar Docker")
    action.add_argument("--execute", action="store_true", help="executa a campanha")
    action.add_argument("--consolidate", metavar="STUDY_ID", help="regera CSVs existentes")
    parser.add_argument("--rates", type=common.rates, default=common.rates("100,300,600"))
    parser.add_argument("--variants", type=variant_ids, default=list(DEFAULT_VARIANT_IDS))
    parser.add_argument("--repetitions", type=common.positive_int, default=1)
    parser.add_argument("--warmup-rate", type=common.positive_int, default=100)
    parser.add_argument("--warmup-duration", default="30s")
    parser.add_argument("--measurement-duration", default="60s")
    parser.add_argument("--cooldown", default=20, type=int)
    parser.add_argument("--pre-allocated-vus", type=common.positive_int, default=100)
    parser.add_argument("--max-vus", type=common.positive_int, default=1000)
    parser.add_argument("--request-timeout", default="15s")
    parser.add_argument("--db-pool-size", type=common.positive_int, default=10)
    delay = parser.add_mutually_exclusive_group()
    delay.add_argument("--database-delay", type=controlled_delay, default="0ms",
                       help="pg_sleep executado dentro da transação de /io")
    delay.add_argument("--database-delays", type=controlled_delays,
                       help="lista de pg_sleep para uma análise randomizada, por exemplo 50ms,100ms,200ms")
    parser.add_argument("--postgres-max-connections", type=common.positive_int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--study-id", help="identificador seguro; permite retomar a campanha")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--allow-existing-events", action="store_true",
                        help="permite baseline não vazio; nunca remove eventos externos")
    args = parser.parse_args()
    for duration in (args.warmup_duration, args.measurement_duration, args.request_timeout):
        common.duration_seconds(duration)
    if args.cooldown < 0:
        parser.error("--cooldown não pode ser negativo")
    if args.max_vus < args.pre_allocated_vus:
        parser.error("--max-vus deve ser maior ou igual a --pre-allocated-vus")
    if args.postgres_max_connections < args.db_pool_size + 10:
        parser.error("--postgres-max-connections deve reservar ao menos 10 conexões além do pool")
    args.database_delays = args.database_delays or [args.database_delay]
    if common.duration_seconds(args.request_timeout) <= max(
            common.duration_seconds(value) for value in args.database_delays):
        parser.error("--request-timeout deve ser maior que todas as latências controladas")
    if args.study_id and not re.fullmatch(r"[A-Za-z0-9._-]+", args.study_id):
        parser.error("--study-id aceita somente letras, números, ponto, hífen e sublinhado")
    return args


def make_plan(args: argparse.Namespace, study_id: str = "io-plan") -> list[dict[str, Any]]:
    selected = [variant for variant in VARIANTS if variant["id"] in args.variants]
    delays = getattr(args, "database_delays", None) or [args.database_delay]
    plan: list[dict[str, Any]] = []
    for repetition in range(1, args.repetitions + 1):
        block = [{**variant, "rate": rate, "databaseDelay": database_delay,
                  "repetition": repetition}
                 for variant in selected for rate in args.rates for database_delay in delays]
        random.Random(args.seed + repetition).shuffle(block)
        for position, run in enumerate(block, 1):
            delay_suffix = f"-d{delay_token(run['databaseDelay'])}" if len(delays) > 1 else ""
            run["runId"] = (
                f"r{repetition:02d}-{position:02d}-{run['id']}-{run['rate']:04d}rps"
                f"{delay_suffix}"
            )
            run["databaseRunId"] = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"urn:tcc2:{study_id}:{run['runId']}"
            ))
            plan.append(run)
    return plan


def display_plan(args: argparse.Namespace, plan: list[dict[str, Any]]) -> None:
    seconds = common.duration_seconds(args.warmup_duration) + common.duration_seconds(
        args.measurement_duration
    ) + args.cooldown
    print("Experimento I/O-bound do TCC 2")
    print(
        f"Rodadas: {len(plan)} ({len(args.variants)} variantes × {len(args.rates)} taxas × "
        f"{len(args.database_delays)} latências × {args.repetitions} repetições)"
    )
    print(f"Variantes: {', '.join(args.variants)}")
    print(f"Taxas: {', '.join(map(str, args.rates))} req/s")
    print(f"Aquecimento: {args.warmup_rate} req/s por {args.warmup_duration}")
    print(f"Medição: {args.measurement_duration}; cooldown: {args.cooldown}s")
    print(f"Pool PostgreSQL por aplicação: {args.db_pool_size}")
    print(f"Latências PostgreSQL controladas: {', '.join(args.database_delays)}")
    print(f"PostgreSQL max_connections: {args.postgres_max_connections}")
    print(f"VUs: {args.pre_allocated_vus} pré-alocados, máximo {args.max_vus}")
    print(f"Duração mínima estimada: {len(plan) * seconds / 3600:.2f} h, mais reinícios e limpeza")
    print("Ordem determinística:")
    for index, run in enumerate(plan, 1):
        print(f"  {index:02d}. {run['runId']}")


def psql(sql: str, env: dict[str, str]) -> str:
    command = common.compose_command(
        "exec", "-T", "postgres", "sh", "-c",
        'exec psql --no-psqlrc --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" '
        '--set=ON_ERROR_STOP=1 "$@"',
        "sh", "--tuples-only", "--no-align", "--command", sql,
    )
    return common.output(command, env)


def catalog_snapshot(env: dict[str, str]) -> dict[str, Any]:
    value = psql("""
SELECT json_build_object(
  'categories', (SELECT count(*) FROM public.category),
  'items', (SELECT count(*) FROM public.catalog_item),
  'itemMin', (SELECT min(id) FROM public.catalog_item),
  'itemMax', (SELECT max(id) FROM public.catalog_item),
  'events', (SELECT count(*) FROM public.access_event),
  'catalogBytes', pg_total_relation_size('public.catalog_item'),
  'categoryBytes', pg_total_relation_size('public.category'),
  'eventBytes', pg_total_relation_size('public.access_event'),
  'maxConnections', current_setting('max_connections')::integer
)::text;
""", env)
    snapshot = json.loads(value)
    if not snapshot["items"] or not snapshot["categories"]:
        raise RuntimeError("catálogo vazio; execute ./scripts/database.sh seed")
    if snapshot["itemMin"] <= 0 or snapshot["itemMax"] - snapshot["itemMin"] + 1 != snapshot["items"]:
        raise RuntimeError("o estudo exige IDs de produtos positivos e contíguos")
    return snapshot


def item_offset(run: dict[str, Any], catalog: dict[str, Any]) -> int:
    """Selects an auditable, reproducible catalog position for each run."""
    return uuid.UUID(run["databaseRunId"]).int % int(catalog["items"])


def warm_catalog(env: dict[str, str]) -> dict[str, int]:
    raw = psql("""
SELECT json_build_object(
  'items', count(*),
  'descriptionBytes', sum(octet_length(description)),
  'nameBytes', sum(octet_length(name))
)::text FROM public.catalog_item;
""", env)
    return json.loads(raw)


def database_snapshot(env: dict[str, str]) -> dict[str, Any]:
    raw = psql("""
SELECT json_build_object(
  'capturedAt', clock_timestamp(),
  'xactCommit', xact_commit, 'xactRollback', xact_rollback,
  'blksRead', blks_read, 'blksHit', blks_hit,
  'tupReturned', tup_returned, 'tupFetched', tup_fetched,
  'tupInserted', tup_inserted, 'tupUpdated', tup_updated, 'tupDeleted', tup_deleted,
  'tempFiles', temp_files, 'tempBytes', temp_bytes, 'deadlocks', deadlocks,
  'sessions', sessions,
  'connections', (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()),
  'events', (SELECT count(*) FROM public.access_event),
  'eventBytes', pg_total_relation_size('public.access_event')
)::text FROM pg_stat_database WHERE datname = current_database();
""", env)
    return json.loads(raw)


def database_delta(before: dict[str, Any] | None, after: dict[str, Any] | None,
                   key: str) -> float | None:
    if not before or not after or not isinstance(before.get(key), (int, float)) \
            or not isinstance(after.get(key), (int, float)):
        return None
    return max(0.0, float(after[key]) - float(before[key]))


def count_run_events(run_uuid: str, env: dict[str, str]) -> int:
    return int(psql(
        f"SELECT count(*) FROM public.access_event WHERE run_id = '{uuid.UUID(run_uuid)}'::uuid;",
        env,
    ))


def cleanup_run_events(run_uuid: str, env: dict[str, str]) -> int:
    safe_uuid = uuid.UUID(run_uuid)
    deleted = int(psql(
        f"WITH deleted AS (DELETE FROM public.access_event WHERE run_id = '{safe_uuid}'::uuid RETURNING 1) SELECT count(*) FROM deleted;",
        env,
    ))
    psql("VACUUM (ANALYZE) public.access_event;", env)
    remaining = count_run_events(str(safe_uuid), env)
    if remaining:
        raise RuntimeError(f"limpeza incompleta de {safe_uuid}: {remaining} eventos restantes")
    return deleted


def actuator_snapshot(base_url: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"capturedAt": utc_now(), "metrics": {}}
    def read(name: str) -> tuple[str, Any]:
        try:
            return name, common.http_json(f"{base_url}/actuator/metrics/{name}")
        except (OSError, ValueError, urllib.error.URLError) as error:
            return name, {"error": str(error)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for name, value in executor.map(read, IO_METRICS):
            snapshot["metrics"][name] = value
    return snapshot


def pool_snapshot(base_url: str, model: str, elapsed: float,
                  warmup: float, measurement: float) -> dict[str, Any]:
    names = {
        "m1": ("hikaricp.connections.active", "hikaricp.connections.idle",
               "hikaricp.connections.pending", "hikaricp.connections.max",
               "hikaricp.connections"),
        "m2": ("hikaricp.connections.active", "hikaricp.connections.idle",
               "hikaricp.connections.pending", "hikaricp.connections.max",
               "hikaricp.connections"),
        "m3": ("r2dbc.pool.acquired", "r2dbc.pool.idle",
               "r2dbc.pool.pending", "r2dbc.pool.max.allocated", "r2dbc.pool.allocated"),
    }[model]

    def read(name: str) -> tuple[str, Any]:
        try:
            return name, common.http_json(f"{base_url}/actuator/metrics/{name}")
        except (OSError, ValueError, urllib.error.URLError) as error:
            return name, {"error": str(error)}

    metrics: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(names)) as executor:
        for name, value in executor.map(read, names):
            metrics[name] = value

    def value(name: str) -> float | None:
        return common.actuator_measurement({"metrics": metrics}, name, "VALUE")

    active_name, idle_name, pending_name, max_name = names[:4]
    active, idle = value(active_name), value(idle_name)
    allocated = value(names[4])
    return {
        "capturedAt": utc_now(), "elapsedSeconds": round(elapsed, 3),
        "phase": common.phase_at(elapsed, warmup, measurement),
        "active": active, "idle": idle, "allocated": allocated,
        "pending": value(pending_name), "configuredMax": value(max_name),
    }


def pool_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [sample for sample in samples if sample.get("phase") == "measurement"]
    result: dict[str, Any] = {}
    for name in ("active", "idle", "allocated", "pending"):
        values = [float(sample[name]) for sample in measured
                  if isinstance(sample.get(name), (int, float))]
        result[f"databasePool{name[0].upper()}{name[1:]}Avg"] = (
            statistics.fmean(values) if values else None
        )
        result[f"databasePool{name[0].upper()}{name[1:]}Max"] = max(values) if values else None
    configured = [float(sample["configuredMax"]) for sample in measured
                  if isinstance(sample.get("configuredMax"), (int, float))]
    result["databasePoolConfiguredMax"] = configured[-1] if configured else None
    return result


def code_identity(k6_script: Path = IO_SCRIPT, study_script: Path | None = None,
                  workload: str = "io") -> dict[str, Any]:
    study_script = study_script or Path(__file__).resolve()
    files = {
        f"k6{workload.title()}Script": k6_script,
        f"{workload}Study": study_script,
        "compose": common.COMPOSE_FILE,
        "schema": ROOT / "infra" / "postgres" / "001_create_io_schema.sql",
        "m1Jar": ROOT / "apps" / "mvc" / "build" / "libs" / "mvc-app.jar",
        "m2Jar": ROOT / "apps" / "virtual-threads" / "build" / "libs" / "virtual-threads-app.jar",
        "m3Jar": ROOT / "apps" / "reactive" / "build" / "libs" / "reactive-app.jar",
    }
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": common.sha256(path)}
            for name, path in files.items()}


def resource_metrics(prefix: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    cpu_avg, cpu_max = common.summarize_stats(samples, "cpuPercent")
    memory_avg, memory_max = common.summarize_stats(samples, "memoryUsageBytes")
    pids_avg, pids_max = common.summarize_stats(samples, "pids")
    return {
        f"{prefix}CpuAvgPercent": cpu_avg, f"{prefix}CpuMaxPercent": cpu_max,
        f"{prefix}MemoryAvgBytes": memory_avg, f"{prefix}MemoryMaxBytes": memory_max,
        f"{prefix}PidsAvg": pids_avg, f"{prefix}PidsMax": pids_max,
        f"{prefix}NetworkReceivedBytes": common.measurement_delta(samples, "networkReceivedBytes"),
        f"{prefix}NetworkSentBytes": common.measurement_delta(samples, "networkSentBytes"),
        f"{prefix}BlockReadBytes": common.measurement_delta(samples, "blockReadBytes"),
        f"{prefix}BlockWrittenBytes": common.measurement_delta(samples, "blockWrittenBytes"),
    }


def parse_run_summary(summary: dict[str, Any], run: dict[str, Any], args: argparse.Namespace,
                      app_samples: list[dict[str, Any]], db_samples: list[dict[str, Any]],
                      load_samples: list[dict[str, Any]], pool_samples: list[dict[str, Any]],
                      app_before: dict[str, Any] | None,
                      app_after: dict[str, Any] | None, db_before_diag: dict[str, Any] | None,
                      db_after_diag: dict[str, Any] | None, actuator_before: dict[str, Any] | None,
                      actuator_after: dict[str, Any] | None, pg_before: dict[str, Any] | None,
                      pg_after: dict[str, Any] | None, persisted_events: int | None) -> dict[str, Any]:
    seconds = common.duration_seconds(args.measurement_duration)
    expected = run["rate"] * seconds
    metric_prefix = getattr(args, "metric_prefix", "io")
    metric = lambda suffix: f"{metric_prefix}_{suffix}"
    requests = common.metric_value(summary, metric("measurement_requests"), "count", 0) or 0
    completed = common.metric_value(summary, metric("measurement_completions_in_window"), "count", requests)
    successes = common.metric_value(summary, metric("measurement_successes_in_window"), "count", 0) or 0
    failures_window = common.metric_value(summary, metric("measurement_failures_in_window"), "count", 0) or 0
    completions_after = common.metric_value(summary, metric("measurement_completions_after_window"), "count", 0) or 0
    failures_after = common.metric_value(summary, metric("measurement_failures_after_window"), "count", 0) or 0
    failures = common.metric_value(summary, metric("measurement_failures"), "passes", 0) or 0
    total_valid = common.metric_value(summary, metric("total_valid_responses"), "count", 0) or 0
    ratio = successes / expected if expected else 0
    classification = "saturated-with-errors" if failures else "saturated" if ratio < .99 else "sustained"
    result = {
        "runId": run["runId"], "databaseRunId": run["databaseRunId"],
        "repetition": run["repetition"], "variant": run["id"], "model": run["model"],
        "targetRateRps": run["rate"], "expectedRequests": int(expected),
        "completedRequests": int(requests), "completedInMeasurementWindow": int(completed),
        "successfulInMeasurementWindow": int(successes),
        "failedInMeasurementWindow": int(failures_window),
        "completedDuringGracefulStop": int(completions_after),
        "failedDuringGracefulStop": int(failures_after),
        "completionRps": completed / seconds, "successfulRps": successes / seconds,
        "completionRatio": completed / expected if expected else 0, "successRatio": ratio,
        "measurementShortfallRequests": max(0, int(expected - completed)),
        "successfulShortfallRequests": max(0, int(expected - successes)),
        "failedRequests": int(failures), "totalValidResponses": int(total_valid),
        "persistedEventsBeforeCleanup": persisted_events,
        "totalDroppedIterations": int(common.metric_value(summary, "dropped_iterations", "count", 0) or 0),
        "maxObservedVUs": common.metric_value(summary, "vus", "max"),
        "latencyAvgMs": common.metric_value(summary, metric("measurement_http_req_duration"), "avg"),
        "latencyP50Ms": common.metric_value(summary, metric("measurement_http_req_duration"), "med"),
        "latencyP95Ms": common.metric_value(summary, metric("measurement_http_req_duration"), "p(95)"),
        "latencyP99Ms": common.metric_value(summary, metric("measurement_http_req_duration"), "p(99)"),
        "latencyMaxMs": common.metric_value(summary, metric("measurement_http_req_duration"), "max"),
        "tomcatConfiguredMaxThreads": common.actuator_measurement(
            actuator_after, "tomcat.threads.config.max", "VALUE"
        ),
        "tomcatThreadsCurrentAfter": common.actuator_measurement(
            actuator_after, "tomcat.threads.current", "VALUE"
        ),
        "tomcatThreadsBusyAfter": common.actuator_measurement(
            actuator_after, "tomcat.threads.busy", "VALUE"
        ),
        "classification": classification,
    }
    result.update(resource_metrics("app", app_samples))
    result.update(resource_metrics("database", db_samples))
    result.update(resource_metrics("loadGenerator", load_samples))
    result.update(pool_metrics(pool_samples))
    result.update({
        "appCpuUsageSeconds": common.diagnostics_delta(app_before, app_after, "cpuStat", "usage_usec", 1e6),
        "appCpuThrottledSeconds": common.diagnostics_delta(app_before, app_after, "cpuStat", "throttled_usec", 1e6),
        "appMemoryPeakBytes": common.nested_number(app_after, "memoryPeakBytes"),
        "databaseCpuUsageSeconds": common.diagnostics_delta(db_before_diag, db_after_diag, "cpuStat", "usage_usec", 1e6),
        "databaseCpuThrottledSeconds": common.diagnostics_delta(db_before_diag, db_after_diag, "cpuStat", "throttled_usec", 1e6),
        "databaseMemoryPeakBytes": common.nested_number(db_after_diag, "memoryPeakBytes"),
        "jvmProcessCpuTimeSeconds": common.actuator_delta(actuator_before, actuator_after, "process.cpu.time", "TOTAL", 1e9),
        "jvmGcPauseCount": common.actuator_delta(actuator_before, actuator_after, "jvm.gc.pause", "COUNT"),
        "jvmGcPauseSeconds": common.actuator_delta(actuator_before, actuator_after, "jvm.gc.pause", "TOTAL_TIME"),
        "jvmAllocatedBytes": common.actuator_delta(actuator_before, actuator_after, "jvm.gc.memory.allocated", "COUNT"),
    })
    for field in ("xactCommit", "xactRollback", "blksRead", "blksHit", "tupReturned",
                  "tupFetched", "tupInserted", "tupUpdated", "tupDeleted", "tempFiles",
                  "tempBytes", "deadlocks", "sessions"):
        result[f"postgres{field[0].upper()}{field[1:]}"] = database_delta(pg_before, pg_after, field)
    result["postgresConnectionsAfter"] = (pg_after or {}).get("connections")
    result["postgresEventBytesAfter"] = (pg_after or {}).get("eventBytes")
    return result


AGGREGATE_METRICS = (
    "completionRps", "successfulRps", "completionRatio", "successRatio",
    "completedInMeasurementWindow", "successfulInMeasurementWindow", "failedInMeasurementWindow",
    "completedDuringGracefulStop", "failedDuringGracefulStop", "measurementShortfallRequests",
    "successfulShortfallRequests", "failedRequests", "totalValidResponses",
    "persistedEventsBeforeCleanup", "totalDroppedIterations", "maxObservedVUs",
    "latencyAvgMs", "latencyP50Ms", "latencyP95Ms", "latencyP99Ms", "latencyMaxMs",
    "appCpuAvgPercent", "appCpuMaxPercent", "appMemoryAvgBytes", "appMemoryMaxBytes",
    "appPidsAvg", "appPidsMax", "appNetworkReceivedBytes", "appNetworkSentBytes",
    "appBlockReadBytes", "appBlockWrittenBytes", "databaseCpuAvgPercent",
    "databaseCpuMaxPercent", "databaseMemoryAvgBytes", "databaseMemoryMaxBytes",
    "databasePidsAvg", "databasePidsMax", "databaseNetworkReceivedBytes",
    "databaseNetworkSentBytes", "databaseBlockReadBytes", "databaseBlockWrittenBytes",
    "databasePoolActiveAvg", "databasePoolActiveMax", "databasePoolIdleAvg",
    "databasePoolIdleMax", "databasePoolAllocatedAvg", "databasePoolAllocatedMax",
    "databasePoolPendingAvg", "databasePoolPendingMax", "databasePoolConfiguredMax",
    "loadGeneratorCpuAvgPercent", "loadGeneratorCpuMaxPercent", "loadGeneratorMemoryAvgBytes",
    "loadGeneratorMemoryMaxBytes", "loadGeneratorPidsAvg", "loadGeneratorPidsMax",
    "appCpuUsageSeconds", "appCpuThrottledSeconds", "appMemoryPeakBytes",
    "databaseCpuUsageSeconds", "databaseCpuThrottledSeconds", "databaseMemoryPeakBytes",
    "jvmProcessCpuTimeSeconds", "jvmGcPauseCount", "jvmGcPauseSeconds", "jvmAllocatedBytes",
    "tomcatConfiguredMaxThreads", "tomcatThreadsCurrentAfter", "tomcatThreadsBusyAfter",
    "postgresXactCommit", "postgresXactRollback", "postgresBlksRead", "postgresBlksHit",
    "postgresTupReturned", "postgresTupFetched", "postgresTupInserted", "postgresTupUpdated",
    "postgresTupDeleted", "postgresTempFiles", "postgresTempBytes", "postgresDeadlocks",
    "postgresSessions", "postgresConnectionsAfter", "postgresEventBytesAfter",
)


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "completed":
            groups[(row["variant"], row["targetRateRps"],
                    row.get("databaseDelay", "unspecified"))].append(row)
    result: list[dict[str, Any]] = []
    for (variant, rate, database_delay), group in sorted(groups.items()):
        item: dict[str, Any] = {
            "variant": variant, "targetRateRps": rate, "databaseDelay": database_delay,
            "completedRuns": len(group),
            "sustainedRuns": sum(row["classification"] == "sustained" for row in group),
            "saturatedRuns": sum(row["classification"] == "saturated" for row in group),
            "runsWithErrors": sum(row["classification"] == "saturated-with-errors" for row in group),
        }
        for metric in AGGREGATE_METRICS:
            values = [float(row[metric]) for row in group if row.get(metric) is not None]
            item[f"{metric}Mean"] = statistics.mean(values) if values else None
            item[f"{metric}StdDev"] = statistics.stdev(values) if len(values) > 1 else 0 if values else None
        result.append(item)
    return result


def write_outputs(processed_dir: Path, rows: list[dict[str, Any]]) -> None:
    runs_path = processed_dir / "runs.csv"
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        with runs_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        runs_path.write_text("", encoding="utf-8")
    common.write_csv(processed_dir / "summary.csv", aggregate(rows))


def run_environment(base: dict[str, str], run: dict[str, Any], args: argparse.Namespace,
                    study_id: str, catalog: dict[str, Any]) -> dict[str, str]:
    env = dict(base)
    env.update({
        "APP_CPUS": "2.0", "APP_MEMORY": "2g", "POSTGRES_CPUS": "2.0",
        "POSTGRES_MEMORY": "2g", "POSTGRES_MAX_CONNECTIONS": str(args.postgres_max_connections),
        "JVM_HEAP": "512m", "DB_POOL_MAX_SIZE": str(args.db_pool_size),
        "TOMCAT_MAX_THREADS": str(run.get("tomcatMaxThreads", 200)),
        "TOMCAT_MIN_SPARE_THREADS": str(run.get("tomcatMinSpareThreads", 10)),
        "IO_DATABASE_DELAY": run["databaseDelay"],
        "K6_IO_RATE": str(run["rate"]), "K6_IO_WARMUP_RATE": str(args.warmup_rate),
        "K6_IO_WARMUP_DURATION": args.warmup_duration,
        "K6_IO_MEASUREMENT_DURATION": args.measurement_duration,
        "K6_IO_PRE_ALLOCATED_VUS": str(args.pre_allocated_vus),
        "K6_IO_MAX_VUS": str(args.max_vus), "K6_IO_REQUEST_TIMEOUT": args.request_timeout,
        "K6_IO_WRITE_RAW": "false", "IO_ITEM_MIN_ID": str(catalog["itemMin"]),
        "IO_ITEM_MAX_ID": str(catalog["itemMax"]),
        "IO_ITEM_OFFSET": str(item_offset(run, catalog)), "IO_RUN_UUID": run["databaseRunId"],
        "IO_RESULT_DIR": f"{study_id}/{run['runId']}", "IO_RUN_ID": run["runId"],
    })
    if hasattr(args, "mixed_cpu_iterations"):
        env.update({
            "MIXED_CPU_ITERATIONS": str(args.mixed_cpu_iterations),
            "MIXED_CPU_EXECUTION_MODE": run.get("executionMode", "event-loop"),
            "K6_MIXED_RATE": str(run["rate"]),
            "K6_MIXED_WARMUP_RATE": str(args.warmup_rate),
            "K6_MIXED_WARMUP_DURATION": args.warmup_duration,
            "K6_MIXED_MEASUREMENT_DURATION": args.measurement_duration,
            "K6_MIXED_PRE_ALLOCATED_VUS": str(args.pre_allocated_vus),
            "K6_MIXED_MAX_VUS": str(args.max_vus),
            "K6_MIXED_REQUEST_TIMEOUT": args.request_timeout,
            "K6_MIXED_WRITE_RAW": "false",
            "MIXED_RESULT_DIR": f"{study_id}/{run['runId']}",
            "MIXED_RUN_ID": run["runId"],
        })
    return env


def execute_run(study_id: str, run: dict[str, Any], args: argparse.Namespace,
                base_env: dict[str, str], catalog: dict[str, Any]) -> dict[str, Any]:
    run_dir = RAW_ROOT / study_id / run["runId"]
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "run.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        if previous.get("status") == "completed":
            print(f"  já concluída; pulando {run['runId']}", flush=True)
            return previous
    env = run_environment(base_env, run, args, study_id, catalog)
    record: dict[str, Any] = {
        **run, "itemOffset": item_offset(run, catalog),
        "databaseDelay": run["databaseDelay"], "databasePoolSize": args.db_pool_size,
        "postgresMaxConnections": args.postgres_max_connections,
        "status": "running", "startedAt": utc_now(),
    }
    if hasattr(args, "mixed_cpu_iterations"):
        record["mixedCpuIterations"] = args.mixed_cpu_iterations
        record["mixedCpuExecutionMode"] = run.get("executionMode", "request-thread")
    common.write_json(result_path, record)
    app_samples: list[dict[str, Any]] = []
    db_samples: list[dict[str, Any]] = []
    load_samples: list[dict[str, Any]] = []
    pool_samples: list[dict[str, Any]] = []
    app_id = db_id = ""
    actuator_before = actuator_after = None
    app_diag_before = app_diag_after = None
    db_diag_before = db_diag_after = None
    pg_before = pg_after = None
    cleanup_deleted: int | None = None
    try:
        cleanup_run_events(run["databaseRunId"], env)
        common.run_logged([str(ENV_SCRIPT), "up", run["model"], "--skip-build"], run_dir / "startup.log", env)
        base_url = common.application_url(run["model"], env)
        record["catalogWarmup"] = warm_catalog(env)
        actuator_before = actuator_snapshot(base_url)
        common.write_json(run_dir / "actuator-before.json", actuator_before)
        app_id = common.output(common.compose_command("ps", "-q", run["model"]), env)
        db_id = common.output(common.compose_command("ps", "-q", "postgres"), env)
        if not app_id or not db_id:
            raise RuntimeError("container da aplicação ou PostgreSQL não encontrado")
        runtime_configuration = common.runtime_configuration(base_url, app_id, run, env)
        common.write_json(run_dir / "runtime-configuration.json", runtime_configuration)
        app_diag_before = common.container_diagnostics(app_id, env)
        db_diag_before = common.container_diagnostics(db_id, env)
        pg_before = database_snapshot(env)
        common.write_json(run_dir / "app-container-before.json", app_diag_before)
        common.write_json(run_dir / "database-container-before.json", db_diag_before)
        common.write_json(run_dir / "postgres-before.json", pg_before)
        duration_exceeded = False
        with (run_dir / "k6.log").open("w", encoding="utf-8") as log:
            pilot_action = getattr(args, "pilot_action", "io-pilot")
            process = subprocess.Popen([str(ENV_SCRIPT), pilot_action, run["model"]], cwd=ROOT,
                                       env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
            started = time.monotonic()
            warmup = common.duration_seconds(args.warmup_duration)
            measurement = common.duration_seconds(args.measurement_duration)
            k6_id: str | None = None
            next_sample = started
            next_pool_sample = started
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > k6_wall_limit(args):
                    duration_exceeded = True
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    break
                try:
                    if not k6_id:
                        k6_id = common.find_k6_container(env)
                    ids = {"application": app_id, "database": db_id}
                    if k6_id:
                        ids["loadGenerator"] = k6_id
                    captured = common.sample_containers(ids, elapsed, warmup, measurement, env)
                    app_samples.append(captured["application"])
                    db_samples.append(captured["database"])
                    if "loadGenerator" in captured:
                        load_samples.append(captured["loadGenerator"])
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    app_samples.append({"capturedAt": utc_now(), "elapsedSeconds": elapsed, "error": str(error)})
                if time.monotonic() >= next_pool_sample:
                    pool_samples.append(pool_snapshot(base_url, run["model"], elapsed, warmup, measurement))
                    next_pool_sample += 5
                next_sample += 1
                remaining = next_sample - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            k6_exit = process.returncode
            k6_wall_seconds = time.monotonic() - started
        for filename, values in (("app-docker-stats.jsonl", app_samples),
                                 ("database-docker-stats.jsonl", db_samples),
                                 ("load-generator-stats.jsonl", load_samples),
                                 ("database-pool-stats.jsonl", pool_samples)):
            with (run_dir / filename).open("w", encoding="utf-8") as target:
                for sample in values:
                    target.write(json.dumps(sample, ensure_ascii=False) + "\n")
        record.update({
            "k6ExitCode": k6_exit, "k6WallSeconds": round(k6_wall_seconds, 3),
            "k6WallLimitSeconds": k6_wall_limit(args),
        })
        if duration_exceeded or k6_wall_seconds > k6_wall_limit(args):
            raise RuntimeError(
                "duração do k6 incompatível com o protocolo; possível suspensão do host: "
                f"{k6_wall_seconds:.1f}s observados, limite {k6_wall_limit(args):.1f}s"
            )
        pg_after = database_snapshot(env)
        persisted = count_run_events(run["databaseRunId"], env)
        app_diag_after = common.container_diagnostics(app_id, env)
        db_diag_after = common.container_diagnostics(db_id, env)
        actuator_after = actuator_snapshot(base_url)
        common.write_json(run_dir / "postgres-after.json", pg_after)
        common.write_json(run_dir / "app-container-after.json", app_diag_after)
        common.write_json(run_dir / "database-container-after.json", db_diag_after)
        common.write_json(run_dir / "actuator-after.json", actuator_after)
        summary_path = run_dir / f"{run['runId']}-summary.json"
        if not summary_path.exists():
            raise RuntimeError("k6 não gerou o resumo esperado")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        record.update(parse_run_summary(
            summary, run, args, app_samples, db_samples, load_samples, pool_samples,
            app_diag_before, app_diag_after, db_diag_before, db_diag_after,
            actuator_before, actuator_after, pg_before, pg_after, persisted,
        ))
        record.update({"status": "completed"})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record.update({"status": "failed", "error": str(error)})
    finally:
        try:
            cleanup_deleted = cleanup_run_events(run["databaseRunId"], env)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as cleanup_error:
            record.update({"status": "failed", "cleanupError": str(cleanup_error)})
        record["cleanupDeletedEvents"] = cleanup_deleted
        record["finishedAt"] = utc_now()
        common.write_json(result_path, record)
        subprocess.run(common.compose_command("stop", run["model"]), cwd=ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return record


def consolidate(study_id: str) -> int:
    raw_dir, processed_dir = RAW_ROOT / study_id, PROCESSED_ROOT / study_id
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Campanha não encontrada: {study_id}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    for run in manifest["plan"]:
        path = raw_dir / run["runId"] / "run.json"
        if path.exists():
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    write_outputs(processed_dir, rows)
    report = {
        "studyId": study_id,
        "status": "complete" if len(rows) == len(manifest["plan"]) and all(r.get("status") == "completed" for r in rows) else "partial",
        "consolidatedAt": utc_now(), "plannedRuns": len(manifest["plan"]),
        "completedRuns": sum(r.get("status") == "completed" for r in rows),
        "failedRuns": sum(r.get("status") == "failed" for r in rows),
        "rawDirectory": str(raw_dir.relative_to(ROOT)),
        "processedDirectory": str(processed_dir.relative_to(ROOT)),
    }
    common.write_json(processed_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" else 2


def execute(args: argparse.Namespace, study_id: str, plan: list[dict[str, Any]]) -> int:
    raw_dir, processed_dir = RAW_ROOT / study_id, PROCESSED_ROOT / study_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    base_env = dict(os.environ)
    base_env["POSTGRES_MAX_CONNECTIONS"] = str(args.postgres_max_connections)
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if not args.skip_build:
            print("Compilando e validando os três modelos...", flush=True)
            common.run_logged([str(BUILD_SCRIPT), "all"], raw_dir / "build.log", base_env)
        subprocess.run(common.compose_command("up", "-d", "--wait", "--wait-timeout", "45", "postgres"),
                       cwd=ROOT, env=base_env, check=True)
        catalog = catalog_snapshot(base_env)
        if catalog["maxConnections"] != args.postgres_max_connections:
            raise RuntimeError(
                "PostgreSQL max_connections diverge do protocolo: "
                f"esperado {args.postgres_max_connections}, observado {catalog['maxConnections']}"
            )
        if catalog["events"] and not args.allow_existing_events:
            raise RuntimeError(
                f"public.access_event contém {catalog['events']} registros; limpe conscientemente ou use --allow-existing-events"
            )
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Erro de preparação: {error}", file=sys.stderr)
        return 1
    configuration = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    manifest = {
        "studyId": study_id,
        "purpose": getattr(args, "purpose", "tcc2-io-bound-comparison"),
        "createdAt": utc_now(),
        "configuration": configuration, "catalogBaseline": catalog,
        "resourceLimits": {"applicationCpus": 2.0, "applicationMemory": "2g",
                           "postgresCpus": 2.0, "postgresMemory": "2g", "jvmHeap": "512m",
                           "databasePoolSize": args.db_pool_size,
                           "databaseDelays": args.database_delays,
                           "postgresMaxConnections": args.postgres_max_connections},
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "python": platform.python_version()},
        "variants": list(VARIANTS), "plan": plan,
        "codeIdentity": code_identity(
            getattr(args, "k6_script", IO_SCRIPT),
            getattr(args, "study_script", Path(__file__).resolve()),
            getattr(args, "metric_prefix", "io"),
        ),
        "dockerVersion": common.output(["docker", "version", "--format", "{{.Server.Version}}"], base_env),
    }
    common.write_json(raw_dir / "manifest.json", manifest)
    rows: list[dict[str, Any]] = []
    interrupted = False
    try:
        for index, run in enumerate(plan, 1):
            print(f"[{index}/{len(plan)}] {run['runId']}", flush=True)
            result = execute_run(study_id, run, args, base_env, catalog)
            rows.append(result)
            write_outputs(processed_dir, rows)
            print(f"  resultado: {result['status']} ({result.get('classification', 'sem classificação')})", flush=True)
            if index < len(plan) and args.cooldown:
                print(f"  cooldown de {args.cooldown}s", flush=True)
                time.sleep(args.cooldown)
    except KeyboardInterrupt:
        interrupted = True
        print("\nCampanha interrompida; resultados parciais foram preservados.", file=sys.stderr)
    completed_runs = sum(r.get("status") == "completed" for r in rows)
    failed_runs = sum(r.get("status") == "failed" for r in rows)
    status = "interrupted" if interrupted else "complete" if completed_runs == len(plan) and not failed_runs else "failed"
    report = {
        "studyId": study_id, "status": status,
        "finishedAt": utc_now(), "plannedRuns": len(plan),
        "completedRuns": completed_runs, "failedRuns": failed_runs,
        "rawDirectory": str(raw_dir.relative_to(ROOT)),
        "processedDirectory": str(processed_dir.relative_to(ROOT)),
    }
    common.write_json(processed_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "complete":
        action = getattr(args, "study_action", "io-study")
        print(f"Retome com: ./scripts/env.sh {action} --execute --study-id {study_id}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    args = arguments()
    if args.consolidate:
        return consolidate(args.consolidate)
    study_id = args.study_id or f"io-study-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"
    plan = make_plan(args, study_id)
    display_plan(args, plan)
    return 0 if args.dry_run else execute(args, study_id, plan)


if __name__ == "__main__":
    raise SystemExit(main())
