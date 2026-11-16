import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib" / "benchmark"))
import io_study


class IoStudyTest(unittest.TestCase):
    def args(self, **overrides):
        values = {
            "variants": list(io_study.DEFAULT_VARIANT_IDS),
            "rates": [100, 300], "repetitions": 2, "seed": 42,
            "measurement_duration": "10s", "database_delay": "0ms",
            "postgres_max_connections": 100,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_controlled_database_delay_has_a_safe_upper_bound(self):
        self.assertEqual(io_study.controlled_delay("100ms"), "100ms")
        self.assertEqual(io_study.controlled_delay("0ms"), "0ms")
        self.assertEqual(io_study.controlled_delays("50ms,100ms,50ms"),
                         ["50ms", "100ms"])
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "0ms e 30s"):
            io_study.controlled_delay("31s")

    def test_k6_wall_limit_allows_normal_shutdown_but_rejects_long_host_pauses(self):
        args = self.args(
            warmup_duration="30s", measurement_duration="60s", request_timeout="15s"
        )
        self.assertEqual(io_study.k6_wall_limit(args), 125)

    def test_plan_is_deterministic_complete_and_uses_unique_database_uuids(self):
        first = io_study.make_plan(self.args(), "study-a")
        second = io_study.make_plan(self.args(), "study-a")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 12)
        self.assertEqual(len({run["databaseRunId"] for run in first}), 12)
        combinations = {(run["repetition"], run["id"], run["rate"]) for run in first}
        self.assertEqual(len(combinations), 12)
        changed = io_study.make_plan(self.args(), "study-b")
        self.assertNotEqual(first[0]["databaseRunId"], changed[0]["databaseRunId"])

    def test_delay_matrix_is_complete_and_encoded_in_run_ids(self):
        args = self.args(
            variants=["m1-platform", "m2-virtual", "m3-reactive"], rates=[1000],
            repetitions=2, database_delays=["50ms", "100ms", "200ms"],
        )
        plan = io_study.make_plan(args, "delay-matrix")
        self.assertEqual(len(plan), 18)
        combinations = {
            (run["repetition"], run["id"], run["rate"], run["databaseDelay"])
            for run in plan
        }
        self.assertEqual(len(combinations), 18)
        self.assertTrue(all(f"-d{run['databaseDelay']}" in run["runId"] for run in plan))

    def test_each_run_gets_a_reproducible_catalog_offset(self):
        catalog = {"items": 3_000_000, "itemMin": 1, "itemMax": 3_000_000}
        run = io_study.make_plan(self.args(repetitions=1), "large-catalog")[0]
        offset = io_study.item_offset(run, catalog)
        self.assertGreaterEqual(offset, 0)
        self.assertLess(offset, catalog["items"])
        self.assertEqual(offset, io_study.item_offset(run, catalog))

        args = self.args(
            warmup_rate=100, warmup_duration="15s", pre_allocated_vus=100,
            max_vus=1000, request_timeout="15s", db_pool_size=10,
        )
        environment = io_study.run_environment({}, run, args, "large-catalog", catalog)
        self.assertEqual(environment["IO_ITEM_OFFSET"], str(offset))
        self.assertEqual(environment["IO_DATABASE_DELAY"], "0ms")
        self.assertEqual(environment["POSTGRES_MAX_CONNECTIONS"], "100")

    def test_t250_sensitivity_changes_only_the_m1_tomcat_ceiling(self):
        args = self.args(
            variants=["m1-platform", "m1-platform-t250"], rates=[2100], repetitions=1,
            warmup_rate=500, warmup_duration="30s", pre_allocated_vus=500,
            max_vus=5000, request_timeout="15s", db_pool_size=250,
            database_delay="100ms", postgres_max_connections=300,
        )
        plan = io_study.make_plan(args, "io-thread-sensitivity")
        self.assertEqual({run["id"] for run in plan},
                         {"m1-platform", "m1-platform-t250"})
        selected = next(run for run in plan if run["id"] == "m1-platform-t250")
        self.assertEqual(selected["tomcatMaxThreads"], 250)
        self.assertEqual(selected["tomcatMinSpareThreads"], 10)

        catalog = {"items": 3_000_000, "itemMin": 1, "itemMax": 3_000_000}
        environment = io_study.run_environment(
            {}, selected, args, "io-thread-sensitivity", catalog
        )
        self.assertEqual(environment["TOMCAT_MAX_THREADS"], "250")
        self.assertEqual(environment["TOMCAT_MIN_SPARE_THREADS"], "10")

    def test_summary_separates_successes_in_window_and_database_resources(self):
        summary = {"metrics": {
            "io_measurement_requests": {"count": 1000},
            "io_measurement_completions_in_window": {"count": 1000},
            "io_measurement_successes_in_window": {"count": 1000},
            "io_measurement_failures_in_window": {"count": 0},
            "io_measurement_completions_after_window": {"count": 0},
            "io_measurement_failures_after_window": {"count": 0},
            "io_measurement_failures": {"passes": 0},
            "io_total_valid_responses": {"count": 1100},
            "io_measurement_http_req_duration": {
                "avg": 8.0, "med": 7.0, "p(95)": 12.0, "p(99)": 20.0, "max": 25.0,
            },
            "dropped_iterations": {"count": 0}, "vus": {"max": 12},
        }}
        run = {"runId": "r", "databaseRunId": "d", "repetition": 1,
               "id": "m1-platform", "model": "m1", "rate": 100}
        samples = [
            {"phase": "measurement", "elapsedSeconds": 1, "cpuPercent": 10,
             "memoryUsageBytes": 100, "pids": 2, "networkReceivedBytes": 10,
             "networkSentBytes": 20, "blockReadBytes": 1, "blockWrittenBytes": 2},
            {"phase": "measurement", "elapsedSeconds": 9, "cpuPercent": 20,
             "memoryUsageBytes": 120, "pids": 3, "networkReceivedBytes": 110,
             "networkSentBytes": 220, "blockReadBytes": 11, "blockWrittenBytes": 22},
        ]
        diagnostics_before = {"cpuStat": {"usage_usec": 1_000_000, "throttled_usec": 0}}
        diagnostics_after = {"cpuStat": {"usage_usec": 3_000_000, "throttled_usec": 1000},
                             "memoryPeakBytes": 130}
        row = io_study.parse_run_summary(
            summary, run, self.args(measurement_duration="10s"), samples, samples, samples,
            [{"phase": "measurement", "active": 8, "idle": 2, "allocated": 10,
              "pending": 3, "configuredMax": 10}],
            diagnostics_before, diagnostics_after, diagnostics_before, diagnostics_after,
            None, None, {"xactCommit": 5, "tupInserted": 2},
            {"xactCommit": 1007, "tupInserted": 1002, "connections": 11, "eventBytes": 4096},
            1100,
        )
        self.assertEqual(row["classification"], "sustained")
        self.assertEqual(row["successfulRps"], 100)
        self.assertEqual(row["persistedEventsBeforeCleanup"], 1100)
        self.assertEqual(row["databaseNetworkReceivedBytes"], 100)
        self.assertEqual(row["postgresXactCommit"], 1002)
        self.assertEqual(row["postgresTupInserted"], 1000)
        self.assertEqual(row["databasePoolActiveMax"], 8)
        self.assertEqual(row["databasePoolPendingMax"], 3)

    def test_cleanup_deletes_only_the_selected_run_id(self):
        run_id = "76ca367c-f087-4de1-bd2e-c4fe459699da"
        with patch.object(io_study, "psql", side_effect=["42", "", "0"]) as mocked:
            self.assertEqual(io_study.cleanup_run_events(run_id, {}), 42)
        statements = [call.args[0] for call in mocked.call_args_list]
        self.assertIn(f"run_id = '{run_id}'::uuid", statements[0])
        self.assertIn("VACUUM (ANALYZE) public.access_event", statements[1])
        self.assertIn(f"run_id = '{run_id}'::uuid", statements[2])
        self.assertNotIn("TRUNCATE", " ".join(statements).upper())

    def test_catalog_must_have_contiguous_positive_item_ids(self):
        snapshot = {"categories": 2, "items": 2, "itemMin": 1, "itemMax": 3,
                    "events": 0, "catalogBytes": 1, "categoryBytes": 1, "eventBytes": 1,
                    "maxConnections": 100}
        with patch.object(io_study, "psql", return_value=json.dumps(snapshot)):
            with self.assertRaisesRegex(RuntimeError, "contíguos"):
                io_study.catalog_snapshot({})

    def test_partial_csv_accepts_failed_and_completed_rows_with_different_fields(self):
        failed = {"status": "failed", "variant": "m1-platform", "targetRateRps": 100,
                  "error": "startup"}
        completed = {"status": "completed", "variant": "m2-virtual", "targetRateRps": 100,
                     "classification": "sustained", "successfulRps": 100.0}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            io_study.write_outputs(target, [failed, completed])
            content = (target / "runs.csv").read_text()
            self.assertIn("error", content)
            self.assertIn("successfulRps", content)
            self.assertTrue((target / "summary.csv").is_file())


if __name__ == "__main__":
    unittest.main()
