#!/usr/bin/env python3
"""Deterministic catalog files and atomic, block-based PostgreSQL COPY loading."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
DDL = ROOT / "infra/postgres/001_create_io_schema.sql"
FORMAT_VERSION = 1
BLOCK_BYTES = 4 * 1024 * 1024
COLUMNS = {
    "category": ("id", "name", "slug", "description", "display_order", "active", "created_at", "updated_at"),
    "catalog_item": (
        "id", "category_id", "sku", "name", "description", "brand", "model",
        "price", "currency", "weight_grams", "status", "created_at", "updated_at",
    ),
}
TABLES = (*COLUMNS, "access_event")
# Drop references first; restore referenced keys before references.
BULK_DROP = (
    ("catalog_item", "catalog_item_category_fk"), ("access_event", "access_event_item_fk"),
    ("category", "category_slug_uk"), ("category", "category_pk"),
    ("catalog_item", "catalog_item_sku_uk"), ("catalog_item", "catalog_item_pk"),
)
BULK_RESTORE = (
    ("category", "category_pk"), ("category", "category_slug_uk"),
    ("catalog_item", "catalog_item_pk"), ("catalog_item", "catalog_item_sku_uk"),
    ("catalog_item", "catalog_item_category_fk"), ("access_event", "access_event_item_fk"),
)
FAMILIES = ("Wireless Mouse", "Mechanical Keyboard", "USB Hub", "Laptop Stand", "Webcam", "Headset", "Monitor", "Network Adapter")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class SeedConfig:
    items: int = 100_000
    categories: int = 100
    description_bytes: int = 1024
    seed: int = 42
    timestamp: str = "2026-01-01T00:00:00+00:00"

    def __post_init__(self):
        for name in ("items", "categories", "description_bytes", "seed"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} deve ser inteiro")
        if not 1 <= self.categories <= min(self.items, 2_147_483_647):
            raise ValueError("use 1 <= categories <= items, respeitando integer do PostgreSQL")
        if not 1 <= self.items <= 9_223_372_036_854_775_807:
            raise ValueError("items deve ser positivo e caber em bigint")
        if not 64 <= self.description_bytes <= 1_048_576:
            raise ValueError("description-bytes deve ficar entre 64 e 1048576")
        if not 0 <= self.seed <= 18_446_744_073_709_551_615:
            raise ValueError("seed deve ser um inteiro não negativo de até 64 bits")
        stamp = datetime.fromisoformat(self.timestamp)
        if stamp.tzinfo is None:
            raise ValueError("timestamp deve informar o fuso horário")
        object.__setattr__(self, "timestamp", stamp.astimezone(timezone.utc).isoformat())


def description(kind, row_id, seed, length):
    # ASCII and fixed length: no COPY escaping, locale or wall clock dependence.
    prefix = f"Synthetic {kind} {row_id}. "
    remaining = length - len(prefix)
    suffix = hashlib.shake_256(f"v{FORMAT_VERSION}:{seed}:{kind}:{row_id}".encode("ascii"))
    return prefix + suffix.hexdigest((remaining + 1) // 2)[:remaining]


def category_rows(config):
    stamp = config.timestamp
    for row_id in range(1, config.categories + 1):
        yield (f"{row_id}\tCategory {row_id:03d}\tcategory-{row_id:03d}\t"
               f"{description('category', row_id, config.seed, 256)}\t{row_id - 1}\ttrue\t{stamp}\t{stamp}\n").encode("ascii")


def item_rows(config):
    stamp = config.timestamp
    seed = config.seed
    category_count = config.categories
    size = config.description_bytes
    for row_id in range(1, config.items + 1):
        cents = (row_id * 7919 + seed) % 50_000_000
        yield (
            f"{row_id}\t{(row_id - 1) % category_count + 1}\tSKU-{row_id:012d}\t"
            f"{FAMILIES[(row_id + seed) % len(FAMILIES)]} {row_id}\t"
            f"{description('item', row_id, seed, size)}\tBrand {(row_id + seed) % 32 + 1:02d}\t"
            f"Model {row_id % 500:03d}\t{cents // 100}.{cents % 100:02d}\tBRL\t"
            f"{(row_id * 31 + seed) % 50_000 + 1}\tACTIVE\t{stamp}\t{stamp}\n"
        ).encode("ascii")


def write_rows(path, rows):
    digest = hashlib.sha256()
    buffer = bytearray()
    count = size = 0
    started = time.perf_counter()
    with path.open("wb", buffering=BLOCK_BYTES) as stream:
        for row in rows:
            buffer.extend(row)
            count += 1
            if len(buffer) >= BLOCK_BYTES:
                stream.write(buffer)
                digest.update(buffer)
                size += len(buffer)
                buffer.clear()
        if buffer:
            stream.write(buffer)
            digest.update(buffer)
            size += len(buffer)
    return {"file": path.name, "rows": count, "bytes": size, "sha256": digest.hexdigest(),
            "generationSeconds": round(time.perf_counter() - started, 6)}


def read_manifest(dataset):
    manifest = json.loads((dataset / "manifest.json").read_text())
    if manifest["formatVersion"] != FORMAT_VERSION:
        raise ValueError("versão do formato da massa incompatível")
    config = SeedConfig(**manifest["parameters"])
    if manifest["schemaSha256"] != sha256_file(DDL):
        raise ValueError("o schema SQL mudou desde a geração; gere outra massa")
    if set(manifest["tables"]) != set(COLUMNS):
        raise ValueError("tabelas do manifesto incompatíveis")
    for table, columns in COLUMNS.items():
        entry = manifest["tables"][table]
        expected_rows = config.categories if table == "category" else config.items
        if entry["file"] != f"{table}.tsv" or entry["columns"] != list(columns):
            raise ValueError(f"arquivo/colunas incompatíveis para {table}")
        if entry["rows"] != expected_rows or type(entry["bytes"]) is not int or entry["bytes"] <= 0:
            raise ValueError(f"quantidades inválidas para {table}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"hash inválido para {table}")
    return manifest, config


def generate_dataset(dataset, config):
    dataset = Path(dataset)
    if dataset.exists():
        manifest, existing = read_manifest(dataset)
        if existing != config:
            raise ValueError("pasta já contém outra configuração; use --dataset com outra pasta")
        return manifest, True
    dataset.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{dataset.name}-", dir=dataset.parent))
    try:
        manifest = {
            "formatVersion": FORMAT_VERSION, "parameters": asdict(config), "createdAt": utc_now(),
            "generatorSha256": sha256_file(Path(__file__)), "schemaSha256": sha256_file(DDL),
            "pythonVersion": platform.python_version(), "format": "PostgreSQL COPY text, UTF-8, tab-separated, no header",
            "tables": {}, "accessEventInitialRows": 0,
        }
        for table, rows in (("category", category_rows(config)), ("catalog_item", item_rows(config))):
            print(f"Gerando {table}...", flush=True)
            info = write_rows(temporary / f"{table}.tsv", rows)
            info["columns"] = list(COLUMNS[table])
            manifest["tables"][table] = info
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        temporary.rename(dataset)
        return manifest, False
    except BaseException:
        shutil.rmtree(temporary)
        raise


def connection_kwargs():
    return {
        "host": os.environ["DB_HOST"], "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"], "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"], "connect_timeout": 10,
        "application_name": "tcc2-seed",
    }


def snapshot_schema(cursor, schema):
    cursor.execute("""
        SELECT t.relname, c.conname, c.contype, c.convalidated, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = %s AND t.relname = ANY(%s) ORDER BY t.relname, c.conname
    """, (schema, list(TABLES)))
    constraints = cursor.fetchall()
    cursor.execute("""
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = %s AND tablename = ANY(%s) ORDER BY tablename, indexname
    """, (schema, list(TABLES)))
    return constraints, cursor.fetchall()


def validate_columns(cursor, schema):
    expected = {}
    for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", DDL.read_text(), re.S):
        expected[table] = [
            (name, kind.replace(" ", "").replace("varchar", "charactervarying"), name == "id" and table == "access_event")
            for name, kind in re.findall(
                r"^    (\w+)\s+(bigint|varchar\(\d+\)|numeric\(\d+,\s*\d+\)|integer|boolean|text|timestamptz|uuid)(?=\s|,|$)", body, re.M)
        ]
    for table in TABLES:
        cursor.execute("""
            SELECT a.attname, replace(format_type(a.atttypid, a.atttypmod), ' ', ''),
                   a.attidentity = 'a', a.attnotnull
            FROM pg_attribute a JOIN pg_class t ON t.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s AND t.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """, (schema, table))
        actual = cursor.fetchall()
        wanted = [(name, kind.replace("timestamptz", "timestampwithtimezone"), identity, True)
                  for name, kind, identity in expected[table]]
        if actual != wanted:
            raise ValueError(f"colunas, tipos, identidade ou nulabilidade divergentes em {schema}.{table}")


def load_dataset(dataset, *, schema="public", keep_indexes=False, maintenance_mb=256):
    import psycopg
    from psycopg import sql

    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
        raise ValueError("nome de schema inválido")
    if type(maintenance_mb) is not int or not 16 <= maintenance_mb <= 1024:
        raise ValueError("maintenance-work-mem-mb deve ficar entre 16 e 1024")
    dataset = Path(dataset)
    manifest, config = read_manifest(dataset)
    started = time.perf_counter()
    result = {"mode": "keep-indexes" if keep_indexes else "rebuild-indexes", "schema": schema,
              "dataset": str(dataset), "manifestSha256": sha256_file(dataset / "manifest.json"), "phases": {}}
    with psycopg.connect(**connection_kwargs(), autocommit=True) as connection:
        if connection.info.server_version != 160014:
            raise ValueError("o carregador exige a baseline PostgreSQL 16.14")
        result["postgresVersion"] = connection.info.server_version
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL timezone = 'UTC'")
                cursor.execute("SELECT set_config('maintenance_work_mem', %s, true)", (f"{maintenance_mb}MB",))
                # Serializes simultaneous seed attempts, including schema creation.
                cursor.execute("SELECT pg_advisory_xact_lock(6132026, hashtext(%s))", (schema,))
                cursor.execute("SELECT relname, relkind FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace WHERE n.nspname = %s AND relname = ANY(%s)", (schema, list(TABLES)))
                existing = dict(cursor.fetchall())
                if not existing:
                    cursor.execute(DDL.read_text(), prepare=False)
                    result["schemaCreated"] = True
                elif existing != {name: "r" for name in TABLES}:
                    raise ValueError("schema parcial ou tabelas incompatíveis; nenhuma substituição foi feita")
                else:
                    result["schemaCreated"] = False
                cursor.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                    sql.SQL(", ").join(sql.Identifier(schema, name) for name in TABLES)))
                for table in TABLES:
                    cursor.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(sql.Identifier(schema, table)))
                    if cursor.fetchone()[0]:
                        raise ValueError(f"{schema}.{table} contém dados; a carga aceita somente tabelas vazias")
                validate_columns(cursor, schema)
                before = snapshot_schema(cursor, schema)
                definitions = {(table, name): definition for table, name, kind, valid, definition in before[0] if valid}
                expected_constraints = {
                    (table, name)
                    for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", DDL.read_text(), re.S)
                    for name in re.findall(r"CONSTRAINT (\w+)", body)
                }
                if not expected_constraints.issubset(definitions):
                    raise ValueError("constraints obrigatórias ausentes ou não validadas")
                if not keep_indexes:
                    for table, name in BULK_DROP:
                        cursor.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(sql.Identifier(schema, table), sql.Identifier(name)))

                for table, columns in COLUMNS.items():
                    info = manifest["tables"][table]
                    digest = hashlib.sha256()
                    copied_bytes = 0
                    phase_started = time.perf_counter()
                    print(f"COPY {table}: {info['rows']:,} registros...", flush=True)
                    command = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT text, ENCODING 'UTF8')").format(
                        sql.Identifier(schema, table), sql.SQL(", ").join(map(sql.Identifier, columns)))
                    with (dataset / info["file"]).open("rb", buffering=BLOCK_BYTES) as stream, cursor.copy(command) as copy:
                        while block := stream.read(BLOCK_BYTES):
                            copy.write(block)
                            digest.update(block)
                            copied_bytes += len(block)
                    if digest.hexdigest() != info["sha256"] or copied_bytes != info["bytes"]:
                        raise ValueError(f"hash/tamanho divergente em {table}; a transação será desfeita")
                    seconds = time.perf_counter() - phase_started
                    result["phases"][f"copy_{table}"] = {"seconds": round(seconds, 6), "bytes": copied_bytes,
                        "rows": info["rows"], "mibPerSecond": round(copied_bytes / 1048576 / seconds, 3)}

                phase_started = time.perf_counter()
                if not keep_indexes:
                    for table, name in BULK_RESTORE:
                        cursor.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}").format(
                            sql.Identifier(schema, table), sql.Identifier(name), sql.SQL(definitions[(table, name)])))
                if snapshot_schema(cursor, schema) != before:
                    raise ValueError("constraints/índices não foram restaurados de forma idêntica; use --keep-indexes para índices customizados")
                result["phases"]["restore_constraints"] = {"seconds": round(time.perf_counter() - phase_started, 6)}

                phase_started = time.perf_counter()
                cursor.execute(sql.SQL("SELECT count(*), min(id), max(id) FROM {}").format(sql.Identifier(schema, "category")))
                if cursor.fetchone() != (config.categories, 1, config.categories):
                    raise ValueError("quantidade/IDs de categorias divergentes")
                cursor.execute(sql.SQL("SELECT count(*), min(id), max(id), min(octet_length(description)), max(octet_length(description)) FROM {}").format(sql.Identifier(schema, "catalog_item")))
                if cursor.fetchone() != (config.items, 1, config.items, config.description_bytes, config.description_bytes):
                    raise ValueError("quantidade/IDs/tamanho das descrições de produtos divergentes")
                cursor.execute(sql.SQL("SELECT category_id, count(*) FROM {} GROUP BY category_id ORDER BY category_id").format(sql.Identifier(schema, "catalog_item")))
                expected = [(i, config.items // config.categories + (i <= config.items % config.categories)) for i in range(1, config.categories + 1)]
                if cursor.fetchall() != expected:
                    raise ValueError("distribuição de produtos por categoria divergente")
                cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, "access_event")))
                if cursor.fetchone()[0] != 0:
                    raise ValueError("access_event deve permanecer vazia")
                result["phases"]["validation"] = {"seconds": round(time.perf_counter() - phase_started, 6)}

                phase_started = time.perf_counter()
                for table in TABLES:
                    cursor.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(schema, table)))
                result["phases"]["analyze"] = {"seconds": round(time.perf_counter() - phase_started, 6)}
        # The successful transaction context has committed, including DDL.
        result["committed"] = True
    result["totalSeconds"] = round(time.perf_counter() - started, 6)
    result["rows"] = {"category": config.categories, "catalog_item": config.items, "access_event": 0}
    result["itemsPerSecond"] = round(config.items / result["totalSeconds"], 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("generate", "load", "prepare"):
        command = commands.add_parser(action)
        command.add_argument("--dataset", type=Path, default=Path("/data/io-v1"))
        command.add_argument("--report", type=Path)
        if action in ("generate", "prepare"):
            command.add_argument("--items", type=int, default=100_000)
            command.add_argument("--categories", type=int, default=100)
            command.add_argument("--description-bytes", type=int, default=1024)
            command.add_argument("--seed", type=int, default=42)
            command.add_argument("--timestamp", default="2026-01-01T00:00:00+00:00")
        if action in ("load", "prepare"):
            command.add_argument("--keep-indexes", action="store_true")
            command.add_argument("--maintenance-work-mem-mb", type=int, default=256)
    args = parser.parse_args(argv)
    if not Path("/.dockerenv").is_file():
        parser.error("execute pelo scripts/database.sh, sempre em Docker")
    report_path = args.report or Path("/results") / f"seed-{args.action}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    report = {"purpose": "catalog-data-preparation", "performanceResults": False, "startedAt": utc_now(),
              "action": args.action, "status": "running", "pythonVersion": platform.python_version()}
    exit_code = 0
    try:
        if args.action in ("generate", "prepare"):
            config = SeedConfig(args.items, args.categories, args.description_bytes, args.seed, args.timestamp)
            started = time.perf_counter()
            manifest, reused = generate_dataset(args.dataset, config)
            report["generation"] = {"reused": reused, "seconds": round(time.perf_counter() - started, 6),
                                    "parameters": manifest["parameters"], "manifest": str(args.dataset / "manifest.json")}
        if args.action in ("load", "prepare"):
            report["load"] = load_dataset(args.dataset, keep_indexes=args.keep_indexes, maintenance_mb=args.maintenance_work_mem_mb)
        else:
            # A generate-only invocation verifies cached files too.
            manifest, _ = read_manifest(args.dataset)
            for info in manifest["tables"].values():
                path = args.dataset / info["file"]
                if path.stat().st_size != info["bytes"] or sha256_file(path) != info["sha256"]:
                    raise ValueError(f"arquivo gerado/cached divergente: {info['file']}")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        exit_code = 1
    report["finishedAt"] = utc_now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    print(f"Relatório: {report_path}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
