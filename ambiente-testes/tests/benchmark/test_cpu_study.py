import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib" / "benchmark"))
import cpu_study


class CpuConcurrencyStudyTest(unittest.TestCase):
    def args(self, variants):
        return argparse.Namespace(
            variants=variants, rates=[75, 90], repetitions=1, seed=42,
            iterations=200000, warmup_rate=25, warmup_duration="10s",
            measurement_duration="15s", pre_allocated_vus=100, max_vus=1000,
            request_timeout="15s",
        )

    def variant(self, identifier):
        return next(item for item in cpu_study.VARIANTS if item["id"] == identifier)

    def test_official_default_variants_remain_unchanged(self):
        self.assertEqual(cpu_study.DEFAULT_VARIANT_IDS, (
            "m1-platform", "m2-virtual", "m3-event-loop", "m3-bounded-elastic",
        ))

    def test_tomcat_sweep_has_expected_caps_and_safe_minimums(self):
        expected = {"m1-platform-t2": 2, "m1-platform-t4": 4, "m1-platform-t8": 8,
                    "m1-platform-t16": 16, "m1-platform-t32": 32}
        for identifier, cap in expected.items():
            variant = self.variant(identifier)
            self.assertEqual(variant["tomcatMaxThreads"], cap)
            self.assertLessEqual(variant["tomcatMinSpareThreads"], cap)
            self.assertFalse(variant["primary"])

    def test_plan_includes_only_explicitly_selected_sensitivity_variants(self):
        selected = ["m1-platform", "m1-platform-t2", "m3-event-loop"]
        plan = cpu_study.make_plan(self.args(selected))
        self.assertEqual(len(plan), 6)
        self.assertEqual({run["id"] for run in plan}, set(selected))
        self.assertEqual({run["rate"] for run in plan}, {75, 90})

    def test_run_environment_applies_tomcat_cap_without_changing_pbkdf2(self):
        args = self.args(["m1-platform-t4"])
        run = {**self.variant("m1-platform-t4"), "rate": 75, "repetition": 1,
               "runId": "r01-m1-t4"}
        env = cpu_study.run_environment({}, run, args, "study")
        self.assertEqual(env["TOMCAT_MAX_THREADS"], "4")
        self.assertEqual(env["TOMCAT_MIN_SPARE_THREADS"], "4")
        self.assertEqual(env["CPU_ITERATIONS"], "200000")
        self.assertEqual(env["APP_CPUS"], "2.0")

    def test_runtime_configuration_proves_tomcat_limit_and_processor_count(self):
        run = {**self.variant("m1-platform-t2"), "rate": 90, "runId": "r"}
        container_env = [
            "POSTGRES_PASSWORD=must-not-be-recorded", "CPU_ITERATIONS=200000",
            "TOMCAT_MAX_THREADS=2", "TOMCAT_MIN_SPARE_THREADS=2",
            "JAVA_TOOL_OPTIONS=-Xmx512m",
        ]
        endpoint = {"model": "m1", "availableProcessors": 2}
        with patch.object(cpu_study, "output", return_value=__import__('json').dumps(container_env)), \
             patch.object(cpu_study, "http_json", return_value=endpoint):
            result = cpu_study.runtime_configuration("http://app", "container", run, {})
        selected = result["selectedContainerEnvironment"]
        self.assertEqual(selected["TOMCAT_MAX_THREADS"], "2")
        self.assertNotIn("POSTGRES_PASSWORD", selected)
        self.assertEqual(result["environmentEndpoint"]["availableProcessors"], 2)

    def test_runtime_configuration_rejects_a_limit_different_from_plan(self):
        run = {**self.variant("m1-platform-t2"), "rate": 90, "runId": "r"}
        with patch.object(cpu_study, "output", return_value='["TOMCAT_MAX_THREADS=200","TOMCAT_MIN_SPARE_THREADS=10"]'), \
             patch.object(cpu_study, "http_json", return_value={"availableProcessors": 2}):
            with self.assertRaisesRegex(RuntimeError, "diverge do plano"):
                cpu_study.runtime_configuration("http://app", "container", run, {})

    def test_csv_accepts_reference_and_tomcat_rows_with_different_fields(self):
        rows = [
            {"variant": "m2-virtual", "status": "completed"},
            {"variant": "m1-platform-t2", "status": "completed",
             "tomcatMaxThreads": 2, "tomcatMinSpareThreads": 2},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.csv"
            cpu_study.write_csv(path, rows)
            with path.open() as source:
                loaded = list(csv.DictReader(source))
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[1]["tomcatMaxThreads"], "2")
        self.assertEqual(loaded[0]["tomcatMaxThreads"], "")

    def test_resume_rejects_an_abbreviated_command_that_changes_the_matrix(self):
        saved = vars(self.args(["m1-platform-t2"]))
        current = dict(saved)
        current["rates"] = [25, 60, 75, 90]
        current["variants"] = list(cpu_study.DEFAULT_VARIANT_IDS)
        differences = cpu_study.resume_configuration_differences(saved, current)
        self.assertEqual(differences, ["rates", "variants"])

    def test_container_sampling_preserves_other_roles_when_k6_has_exited(self):
        payload = json.dumps({
            "CPUPerc": "12.5%", "MemPerc": "1%", "MemUsage": "1MiB / 2GiB",
            "NetIO": "1MB / 2MB", "BlockIO": "3MB / 4MB", "PIDs": "3",
        })

        def run(command, **kwargs):
            if command[-1] == "gone-k6":
                raise subprocess.CalledProcessError(1, command, stderr="No such container")
            return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

        with patch.object(cpu_study.subprocess, "run", side_effect=run):
            samples = cpu_study.sample_containers(
                {"application": "app", "database": "db", "loadGenerator": "gone-k6"},
                elapsed=45.1, warmup=15, measurement=30, env={},
            )

        self.assertEqual(samples["application"]["cpuPercent"], 12.5)
        self.assertEqual(samples["database"]["blockReadBytes"], 3_000_000)
        self.assertIn("No such container", samples["loadGenerator"]["error"])
        self.assertEqual(samples["loadGenerator"]["phase"], "graceful-stop")


if __name__ == "__main__":
    unittest.main()
