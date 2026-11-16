"""Run inside the seed container; database cases use private, disposable schemas."""
from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/lib/database"))
import seed_data as seed


class GeneratorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = seed.SeedConfig(items=11, categories=3, description_bytes=64)

    def test_exact_bytes_counts_distribution_and_price(self):
        rows = [row.decode("ascii").rstrip("\n").split("\t") for row in seed.item_rows(self.config)]
        self.assertEqual(len(rows), 11)
        self.assertTrue(all(len(row) == len(seed.COLUMNS["catalog_item"]) for row in rows))
        self.assertTrue(all(len(row[4].encode("utf8")) == 64 for row in rows))
        self.assertEqual(Counter(int(row[1]) for row in rows), {1: 4, 2: 4, 3: 3})
        self.assertTrue(all(row[8] == "BRL" and row[10] == "ACTIVE" for row in rows))
        self.assertTrue(all("\\" not in field and "\r" not in field for row in rows for field in row))
        self.assertEqual(rows[0][7], "79.61")

    def test_same_parameters_produce_identical_files(self):
        first, _ = seed.generate_dataset(self.root / "first", self.config)
        second, _ = seed.generate_dataset(self.root / "second", self.config)
        for table in seed.COLUMNS:
            self.assertEqual(first["tables"][table]["sha256"], second["tables"][table]["sha256"])
            data = (self.root / "first" / f"{table}.tsv").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), first["tables"][table]["sha256"])
            self.assertEqual(len(data), first["tables"][table]["bytes"])

    def test_seed_changes_content_without_changing_shape(self):
        first = list(seed.item_rows(self.config))
        second = list(seed.item_rows(replace(self.config, seed=43)))
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), len(second))

    def test_utc_timestamp_is_normalized(self):
        config = replace(self.config, timestamp="2025-12-31T21:00:00-03:00")
        self.assertEqual(config.timestamp, "2026-01-01T00:00:00+00:00")

    def test_invalid_configuration_is_rejected(self):
        for change in ({"items": 0}, {"categories": 0}, {"categories": 12}, {"seed": -1},
                       {"description_bytes": 63}, {"timestamp": "2026-01-01T00:00:00"}, {"items": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.config, **change)

    def test_existing_dataset_is_reused_but_never_overwritten(self):
        dataset = self.root / "data"
        first, reused = seed.generate_dataset(dataset, self.config)
        self.assertFalse(reused)
        second, reused = seed.generate_dataset(dataset, self.config)
        self.assertTrue(reused)
        self.assertEqual(first, second)
        with self.assertRaises(ValueError):
            seed.generate_dataset(dataset, replace(self.config, seed=43))

    def test_manifest_cannot_redirect_to_another_file(self):
        dataset = self.root / "data"
        manifest, _ = seed.generate_dataset(dataset, self.config)
        manifest["tables"]["category"]["file"] = "../other.tsv"
        (dataset / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            seed.read_manifest(dataset)


@unittest.skipUnless(os.environ.get("TCC_SEED_INTEGRATION") == "1", "execute scripts/test.sh seed em Docker")
class CopyIntegrationTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.sql = sql
        self.connection = psycopg.connect(**seed.connection_kwargs(), autocommit=True)
        self.addCleanup(self.connection.close)
        self.schema = "seed_test_" + uuid.uuid4().hex
        self.connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: self.connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dataset = Path(self.temporary.name) / "data"
        self.config = seed.SeedConfig(items=11, categories=3, description_bytes=64)
        seed.generate_dataset(self.dataset, self.config)

    def create_empty_schema(self):
        with self.connection.transaction():
            self.connection.execute(self.sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(self.sql.Identifier(self.schema)))
            self.connection.execute(seed.DDL.read_text(), prepare=False)

    def schema_snapshot(self):
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(self.sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(self.sql.Identifier(self.schema)))
            return seed.snapshot_schema(cursor, self.schema)

    def test_bulk_copy_restores_schema_and_refuses_second_load(self):
        self.create_empty_schema()
        before = self.schema_snapshot()
        result = seed.load_dataset(self.dataset, schema=self.schema)
        self.assertTrue(result["committed"])
        self.assertEqual(result["rows"], {"category": 3, "catalog_item": 11, "access_event": 0})
        self.assertEqual(before, self.schema_snapshot())
        with self.assertRaisesRegex(ValueError, "contém dados"):
            seed.load_dataset(self.dataset, schema=self.schema)
        count = self.connection.execute(self.sql.SQL("SELECT count(*) FROM {}.catalog_item").format(self.sql.Identifier(self.schema))).fetchone()[0]
        self.assertEqual(count, 11)

    def test_keep_indexes_and_create_missing_tables(self):
        result = seed.load_dataset(self.dataset, schema=self.schema, keep_indexes=True)
        self.assertTrue(result["schemaCreated"])
        self.assertEqual(result["rows"]["catalog_item"], 11)

    def test_failed_foreign_key_validation_rolls_back_data_and_ddl(self):
        import psycopg
        self.create_empty_schema()
        before = self.schema_snapshot()
        path = self.dataset / "catalog_item.tsv"
        fields = path.read_text().splitlines()
        row = fields[0].split("\t")
        row[1] = "999"
        fields[0] = "\t".join(row)
        path.write_text("\n".join(fields) + "\n")
        manifest = json.loads((self.dataset / "manifest.json").read_text())
        manifest["tables"]["catalog_item"]["sha256"] = seed.sha256_file(path)
        manifest["tables"]["catalog_item"]["bytes"] = path.stat().st_size
        (self.dataset / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            seed.load_dataset(self.dataset, schema=self.schema)
        self.assertEqual(before, self.schema_snapshot())
        count = self.connection.execute(self.sql.SQL("SELECT count(*) FROM {}.category").format(self.sql.Identifier(self.schema))).fetchone()[0]
        self.assertEqual(count, 0)

    def test_hash_mismatch_rolls_back_initial_schema_creation(self):
        # Valid COPY data but a different hash must abort the entire transaction.
        path = self.dataset / "catalog_item.tsv"
        original = path.read_bytes()
        content = original.replace(b"Brand 12", b"Brand 13", 1)
        self.assertNotEqual(original, content)
        path.write_bytes(content)
        with self.assertRaisesRegex(ValueError, "hash/tamanho"):
            seed.load_dataset(self.dataset, schema=self.schema)
        rows = self.connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", (self.schema,)).fetchall()
        self.assertEqual(rows, [])
