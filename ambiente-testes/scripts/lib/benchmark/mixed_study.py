#!/usr/bin/env python3
"""Orquestra pilotos e campanhas reproduzíveis do workload POST /mixed."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import cpu_study as common
import io_study as study


MIXED_SCRIPT = common.ROOT / "tests" / "k6" / "mixed.js"
DEFAULT_VARIANT_IDS = ("m1-platform", "m2-virtual", "m3-event-loop")
VARIANTS = (
    {"id": "m1-platform", "model": "m1", "executionMode": "request-thread",
     "tomcatMaxThreads": 200, "tomcatMinSpareThreads": 10},
    {"id": "m2-virtual", "model": "m2", "executionMode": "request-thread"},
    {"id": "m3-event-loop", "model": "m3", "executionMode": "event-loop"},
    {"id": "m3-bounded-elastic", "model": "m3", "executionMode": "bounded-elastic"},
)


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
        description="Executa e consolida o experimento configurável de POST /mixed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="mostra o plano sem usar Docker")
    action.add_argument("--execute", action="store_true", help="executa a campanha")
    action.add_argument("--consolidate", metavar="STUDY_ID", help="regera CSVs existentes")
    parser.add_argument("--rates", type=common.rates, default=common.rates("100,300,600"))
    parser.add_argument("--variants", type=variant_ids, default=list(DEFAULT_VARIANT_IDS))
    parser.add_argument("--repetitions", type=common.positive_int, default=1)
    parser.add_argument("--cpu-iterations", dest="mixed_cpu_iterations",
                        type=common.positive_int, default=10000,
                        help="iterações SHA-256 executadas antes da operação de I/O")
    parser.add_argument("--warmup-rate", type=common.positive_int, default=100)
    parser.add_argument("--warmup-duration", default="15s")
    parser.add_argument("--measurement-duration", default="30s")
    parser.add_argument("--cooldown", default=10, type=int)
    parser.add_argument("--pre-allocated-vus", type=common.positive_int, default=100)
    parser.add_argument("--max-vus", type=common.positive_int, default=1000)
    parser.add_argument("--request-timeout", default="15s")
    parser.add_argument("--db-pool-size", type=common.positive_int, default=250)
    parser.add_argument("--database-delay", type=study.controlled_delay, default="100ms",
                        help="pg_sleep executado dentro da transação de /mixed")
    parser.add_argument("--postgres-max-connections", type=common.positive_int, default=300)
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
    if common.duration_seconds(args.request_timeout) <= common.duration_seconds(args.database_delay):
        parser.error("--request-timeout deve ser maior que a latência controlada")
    if args.study_id and not re.fullmatch(r"[A-Za-z0-9._-]+", args.study_id):
        parser.error("--study-id aceita somente letras, números, ponto, hífen e sublinhado")
    args.database_delays = [args.database_delay]
    args.metric_prefix = "mixed"
    args.pilot_action = "mixed-pilot"
    args.study_action = "mixed-study"
    args.purpose = "tcc2-mixed-workload-comparison"
    args.k6_script = MIXED_SCRIPT
    args.study_script = Path(__file__).resolve()
    return args


def display_plan(args: argparse.Namespace, plan: list[dict]) -> None:
    seconds = common.duration_seconds(args.warmup_duration) + common.duration_seconds(
        args.measurement_duration
    ) + args.cooldown
    print("Experimento mixed do TCC 2")
    print(
        f"Rodadas: {len(plan)} ({len(args.variants)} variantes × {len(args.rates)} taxas × "
        f"{args.repetitions} repetições)"
    )
    print(f"Variantes: {', '.join(args.variants)}")
    print(f"Taxas: {', '.join(map(str, args.rates))} req/s")
    print(f"CPU por requisição: {args.mixed_cpu_iterations} iterações SHA-256")
    print(f"Latência PostgreSQL controlada: {args.database_delay}")
    print(f"Pool PostgreSQL por aplicação: {args.db_pool_size}")
    print(f"Aquecimento: {args.warmup_rate} req/s por {args.warmup_duration}")
    print(f"Medição: {args.measurement_duration}; cooldown: {args.cooldown}s")
    print(f"VUs: {args.pre_allocated_vus} pré-alocados, máximo {args.max_vus}")
    print(f"Duração mínima estimada: {len(plan) * seconds / 3600:.2f} h, mais reinícios e limpeza")
    print("Ordem determinística:")
    for index, run in enumerate(plan, 1):
        print(f"  {index:02d}. {run['runId']}")


def make_plan(args: argparse.Namespace, study_id: str) -> list[dict]:
    study.VARIANTS = VARIANTS
    plan = study.make_plan(args, study_id)
    for run in plan:
        run["mixedCpuIterations"] = args.mixed_cpu_iterations
    return plan


def main() -> int:
    args = arguments()
    study.VARIANTS = VARIANTS
    if args.consolidate:
        return study.consolidate(args.consolidate)
    study_id = args.study_id or (
        f"mixed-study-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"
    )
    plan = make_plan(args, study_id)
    display_plan(args, plan)
    return 0 if args.dry_run else study.execute(args, study_id, plan)


if __name__ == "__main__":
    raise SystemExit(main())
