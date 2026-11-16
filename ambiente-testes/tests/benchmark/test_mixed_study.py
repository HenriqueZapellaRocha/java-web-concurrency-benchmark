import argparse
import json
import sys
import unittest
from pathlib import Path


BENCHMARK = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "benchmark"
sys.path.insert(0, str(BENCHMARK))

import io_study
import mixed_study


class MixedStudyTest(unittest.TestCase):
    def args(self, **changes):
        values = {
            "variants": list(mixed_study.DEFAULT_VARIANT_IDS),
            "rates": [100, 300], "repetitions": 2, "seed": 42,
            "database_delay": "100ms", "database_delays": ["100ms"],
            "mixed_cpu_iterations": 25000,
            "warmup_rate": 50, "warmup_duration": "10s",
            "measurement_duration": "15s", "request_timeout": "15s",
            "pre_allocated_vus": 100, "max_vus": 1000,
            "db_pool_size": 250, "postgres_max_connections": 300,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def setUp(self):
        self.original_variants = io_study.VARIANTS
        io_study.VARIANTS = mixed_study.VARIANTS

    def tearDown(self):
        io_study.VARIANTS = self.original_variants

    def test_default_plan_compares_three_models_without_bounded_elastic(self):
        args = self.args()
        plan = mixed_study.make_plan(args, "mixed-default")
        self.assertEqual(len(plan), 12)
        self.assertEqual({run["id"] for run in plan}, set(mixed_study.DEFAULT_VARIANT_IDS))
        self.assertNotIn("m3-bounded-elastic", {run["id"] for run in plan})
        self.assertEqual({run["mixedCpuIterations"] for run in plan}, {25000})
        self.assertEqual(len({run["databaseRunId"] for run in plan}), len(plan))

    def test_reactive_execution_modes_are_explicit_sensitivity_variants(self):
        args = self.args(variants=["m3-event-loop", "m3-bounded-elastic"],
                         rates=[100], repetitions=1)
        plan = mixed_study.make_plan(args, "mixed-reactive-modes")
        self.assertEqual(
            {run["id"]: run["executionMode"] for run in plan},
            {"m3-event-loop": "event-loop", "m3-bounded-elastic": "bounded-elastic"},
        )

    def test_environment_configures_cpu_io_and_reactive_mode(self):
        args = self.args(variants=["m3-bounded-elastic"], rates=[100], repetitions=1)
        run = mixed_study.make_plan(args, "mixed-environment")[0]
        catalog = {"items": 3_000_000, "itemMin": 1, "itemMax": 3_000_000}
        environment = io_study.run_environment({}, run, args, "mixed-environment", catalog)
        self.assertEqual(environment["MIXED_CPU_ITERATIONS"], "25000")
        self.assertEqual(environment["MIXED_CPU_EXECUTION_MODE"], "bounded-elastic")
        self.assertEqual(environment["IO_DATABASE_DELAY"], "100ms")
        self.assertEqual(environment["DB_POOL_MAX_SIZE"], "250")
        self.assertEqual(environment["K6_MIXED_RATE"], "100")
        self.assertEqual(environment["MIXED_RESULT_DIR"],
                         f"mixed-environment/{run['runId']}")

    def test_internal_paths_can_be_recorded_in_json_manifest_configuration(self):
        args = self.args()
        args.k6_script = mixed_study.MIXED_SCRIPT
        args.study_script = Path(mixed_study.__file__).resolve()
        configuration = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        }
        encoded = json.dumps(configuration)
        self.assertIn("mixed.js", encoded)


if __name__ == "__main__":
    unittest.main()
