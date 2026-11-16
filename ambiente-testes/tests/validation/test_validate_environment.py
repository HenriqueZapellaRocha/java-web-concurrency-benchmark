import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("validate_environment", ROOT / "scripts/lib/environment/validate_environment.py")
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


def snapshot(model):
    indicator = "r2dbc" if model == "m3" else "db"
    return {
        "runtime": {
            "model": model,
            "webStack": "spring-webflux/netty" if model == "m3" else "spring-mvc/tomcat",
            "javaVersion": "21.0.11+10-LTS",
            "javaVendor": "Eclipse Adoptium",
            "springBootVersion": "3.5.6",
            "virtual": model == "m2",
            "nonBlocking": model == "m3",
        },
        "readiness": {"status": "UP", "components": {indicator: {"status": "UP"}}},
    }


def write_test_reports(root, skipped=0):
    for module, classes in validation.EXPECTED_TESTS.items():
        target = root / "apps" / module / "build/test-results/test"
        target.mkdir(parents=True)
        for name in classes:
            (target / f"TEST-{name}.xml").write_text(
                f'<testsuite name="{name}" tests="1" failures="0" errors="0" skipped="{skipped}"/>')


class EvidenceValidationTest(unittest.TestCase):
    def test_missing_http_execution_is_not_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Relatório HTTP ausente"):
                validation.validate_test_reports(Path(directory))

    def test_skipped_http_tests_are_not_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_test_reports(root, skipped=1)
            with self.assertRaisesRegex(ValueError, "Teste HTTP sem aprovação"):
                validation.validate_test_reports(root)

    def test_all_three_http_reports_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_test_reports(root)
            self.assertEqual(len(validation.validate_test_reports(root)), 3)
            (root / "apps/reactive/build/test-results/test/TEST-br.pucrs.tcc2.reactive.M3HttpEnvironmentTest.xml").unlink()
            with self.assertRaisesRegex(ValueError, "Relatório HTTP ausente"):
                validation.validate_test_reports(root)

    def test_m2_report_in_mvc_project_does_not_replace_independent_m2_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_test_reports(root)
            independent = root / "apps/virtual-threads/build/test-results/test/TEST-br.pucrs.tcc2.virtualthreads.M2HttpEnvironmentTest.xml"
            former = root / "apps/mvc/build/test-results/test/TEST-br.pucrs.tcc2.mvc.M2HttpEnvironmentTest.xml"
            independent.rename(former)
            with self.assertRaisesRegex(ValueError, "apps/virtual-threads/"):
                validation.validate_test_reports(root)

    def test_virtual_threads_requires_its_own_executable_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for app, filename, entrypoint in (
                ("mvc", "mvc-app.jar", "br/pucrs/tcc2/mvc/MvcApplication.class"),
                ("virtual-threads", "virtual-threads-app.jar", "br/pucrs/tcc2/virtualthreads/VirtualThreadsApplication.class"),
                ("reactive", "reactive-app.jar", "br/pucrs/tcc2/reactive/ReactiveApplication.class"),
            ):
                target = root / "apps" / app / "build/libs" / filename
                target.parent.mkdir(parents=True)
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("META-INF/MANIFEST.MF", "Main-Class: org.springframework.boot.loader.launch.JarLauncher\n")
                    archive.writestr("BOOT-INF/classes/" + entrypoint, b"")
            self.assertEqual(len(validation.validate_jars(root)), 3)
            (root / "apps/virtual-threads/build/libs/virtual-threads-app.jar").unlink()
            with self.assertRaisesRegex(ValueError, "apps/virtual-threads/"):
                validation.validate_jars(root)

    def test_virtual_thread_claim_must_match_m2(self):
        evidence = snapshot("m2")
        evidence["runtime"]["virtual"] = False
        with self.assertRaisesRegex(ValueError, "campo virtual"):
            validation.validate_snapshot(evidence, "m2")

    def test_global_health_up_does_not_prove_database_connection(self):
        evidence = snapshot("m3")
        evidence["readiness"]["components"].clear()
        with self.assertRaisesRegex(ValueError, "PostgreSQL não foi comprovada"):
            validation.validate_snapshot(evidence, "m3")

    def test_m3_requires_a_non_blocking_thread_marker(self):
        evidence = snapshot("m3")
        evidence["runtime"]["nonBlocking"] = False
        with self.assertRaisesRegex(ValueError, "campo nonBlocking"):
            validation.validate_snapshot(evidence, "m3")

    def test_evidence_for_correct_stack_and_database_is_accepted(self):
        for model in ("m1", "m2", "m3"):
            validation.validate_snapshot(snapshot(model), model)

    def test_permission_denials_preserve_logs_and_prevent_model_startup(self):
        executed = []

        def run_command(args, stdout, **kwargs):
            executed.append(args)
            if args[:2] == ["docker", "version"]:
                stdout.write("permission denied while trying to connect to the docker API\n")
                return subprocess.CompletedProcess(args, 1)
            if "scripts/build.sh" in args:
                stdout.write("FileLockContentionHandler: Operation not permitted\n")
                return subprocess.CompletedProcess(args, 1)
            return subprocess.CompletedProcess(args, 0)

        with tempfile.TemporaryDirectory() as directory, patch.object(validation.subprocess, "run", side_effect=run_command):
            with contextlib.redirect_stdout(io.StringIO()):
                run = validation.ValidationRun(Path(directory))
                code = run.execute()
            report = json.loads((run.directory / "report.json").read_text())
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(all(model["status"] == "not_run" for model in report["models"].values()))
            self.assertFalse(any("scripts/env.sh" in command for command in executed))
            self.assertFalse(any("scripts/build.sh" in command for command in executed))
            self.assertFalse((run.directory / "gradle_build_and_http_tests.log").exists())
            self.assertTrue((run.directory / "docker_service.log").is_file())

    def test_invalid_compose_prevents_build_and_model_startup(self):
        executed = []

        def run_command(args, **kwargs):
            executed.append(args)
            return subprocess.CompletedProcess(args, 1 if "config" in args else 0)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(validation.subprocess, "run", side_effect=run_command):
                with contextlib.redirect_stdout(io.StringIO()):
                    run = validation.ValidationRun(Path(directory))
                    self.assertEqual(run.execute(), 1)
            self.assertEqual(run.report["status"], "failed")
            self.assertFalse(any("scripts/build.sh" in command or "scripts/env.sh" in command for command in executed))

    def test_docker_toolchain_failure_prevents_build_and_model_startup(self):
        executed = []

        def run_command(args, **kwargs):
            executed.append(args)
            return subprocess.CompletedProcess(args, 1 if "scripts/build.sh" in args else 0)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(validation.subprocess, "run", side_effect=run_command):
                with contextlib.redirect_stdout(io.StringIO()):
                    run = validation.ValidationRun(Path(directory))
                    self.assertEqual(run.execute(), 1)
            self.assertEqual(run.report["status"], "failed")
            self.assertEqual([args for args in executed if "scripts/build.sh" in args],
                             [["bash", "scripts/build.sh", "--version"]])
            self.assertNotIn("gradle_build_and_http_tests", run.report["steps"])
            self.assertFalse(any("scripts/env.sh" in command for command in executed))

    def test_successful_exit_without_http_reports_does_not_start_containers(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(validation.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
                with contextlib.redirect_stdout(io.StringIO()):
                    run = validation.ValidationRun(Path(directory))
                    self.assertEqual(run.execute(), 1)
            self.assertEqual(run.report["steps"]["build_artifacts"]["status"], "failed")
            self.assertTrue(all(model["status"] == "not_run" for model in run.report["models"].values()))


if __name__ == "__main__":
    unittest.main()
