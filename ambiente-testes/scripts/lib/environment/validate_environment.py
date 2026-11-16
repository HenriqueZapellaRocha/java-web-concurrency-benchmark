#!/usr/bin/env python3
"""Validação sequencial do ambiente, com evidências e aprovação somente após todos os checks."""
import datetime
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODELS = ("m1", "m2", "m3")
EXPECTED_TESTS = {
    "mvc": ("br.pucrs.tcc2.mvc.M1HttpEnvironmentTest",),
    "virtual-threads": ("br.pucrs.tcc2.virtualthreads.M2HttpEnvironmentTest",),
    "reactive": ("br.pucrs.tcc2.reactive.M3HttpEnvironmentTest",),
}


def validate_test_reports(root):
    summaries = []
    for module, classes in EXPECTED_TESTS.items():
        directory = root / "apps" / module / "build" / "test-results" / "test"
        for name in classes:
            path = directory / f"TEST-{name}.xml"
            if not path.is_file():
                raise ValueError(f"Relatório HTTP ausente: {path.relative_to(root)}")
            suite = ET.parse(path).getroot()
            tests = int(suite.get("tests", "0"))
            failures = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
            skipped = int(suite.get("skipped", "0"))
            if tests < 1 or failures or skipped:
                raise ValueError(f"Teste HTTP sem aprovação: {name} (tests={tests}, failures={failures}, skipped={skipped})")
            summaries.append({"class": name, "tests": tests, "report": str(path.relative_to(root))})
    return summaries


def validate_jars(root):
    jars = []
    for module, filename, entrypoint in (
        ("mvc", "mvc-app.jar", "br/pucrs/tcc2/mvc/MvcApplication.class"),
        ("virtual-threads", "virtual-threads-app.jar", "br/pucrs/tcc2/virtualthreads/VirtualThreadsApplication.class"),
        ("reactive", "reactive-app.jar", "br/pucrs/tcc2/reactive/ReactiveApplication.class"),
    ):
        path = root / "apps" / module / "build" / "libs" / filename
        if not path.is_file():
            raise ValueError(f"Jar executável ausente: {path.relative_to(root)}")
        with zipfile.ZipFile(path) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode()
            if "Main-Class: org.springframework.boot.loader.launch.JarLauncher" not in manifest:
                raise ValueError(f"Jar sem launcher Spring Boot: {filename}")
            if "BOOT-INF/classes/" + entrypoint not in archive.namelist():
                raise ValueError(f"Classe da aplicação ausente: {filename}")
        jars.append(str(path.relative_to(root)))
    return jars


def validate_snapshot(snapshot, model):
    runtime = snapshot.get("runtime", {})
    expected_stack = "spring-webflux/netty" if model == "m3" else "spring-mvc/tomcat"
    expected = {
        "model": model,
        "webStack": expected_stack,
        "javaVersion": "21.0.11+10-LTS",
        "javaVendor": "Eclipse Adoptium",
        "springBootVersion": "3.5.6",
        "virtual": model == "m2",
        "nonBlocking": model == "m3",
    }
    for key, value in expected.items():
        if runtime.get(key) != value or (key in {"virtual", "nonBlocking"} and not isinstance(runtime.get(key), bool)):
            raise ValueError(f"Runtime de {model} não corresponde à baseline: campo {key}")
    readiness = snapshot.get("readiness", {})
    indicator = "r2dbc" if model == "m3" else "db"
    database = readiness.get("components", {}).get(indicator, {})
    if readiness.get("status") != "UP" or database.get("status") != "UP":
        raise ValueError(f"Conexão da aplicação {model} com PostgreSQL não foi comprovada")


class ValidationRun:
    def __init__(self, root=ROOT):
        self.root = root
        now = datetime.datetime.now(datetime.timezone.utc)
        self.directory = root / "results" / "raw" / f"validation-{now:%Y%m%dT%H%M%S.%fZ}"
        self.directory.mkdir(parents=True)
        self.report = {
            "startedAt": now.isoformat(),
            "purpose": "functional-environment-validation",
            "performanceResults": False,
            "status": "running",
            "steps": {},
            "models": {model: {"status": "not_run"} for model in MODELS},
        }
        self.save()

    def save(self):
        destination = self.directory / "report.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(destination)

    def run_step(self, name, args, timeout=120):
        print(f"Executando: {name}", flush=True)
        log = self.directory / f"{name}.log"
        try:
            with log.open("w") as output:
                result = subprocess.run(args, cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                                        text=True, timeout=timeout)
            text = log.read_text(errors="replace")
            restricted = any(message in text.lower() for message in (
                "operation not permitted", "cannot connect to the docker daemon",
                "failed to connect to the docker api", "docker não está disponível",
                "permission denied while trying to connect", "acesso ao docker bloqueado",
            ))
            status = "passed" if result.returncode == 0 else ("blocked" if restricted else "failed")
            record = {"status": status, "exitCode": result.returncode,
                      "log": str(log.relative_to(self.root))}
        except (OSError, subprocess.TimeoutExpired) as error:
            record = {"status": "failed", "error": str(error), "log": str(log.relative_to(self.root))}
        self.report["steps"][name] = record
        self.save()
        print(f"  {record['status']}: {record['log']}", flush=True)
        return record["status"] == "passed"

    def finish(self):
        all_models = all(model["status"] == "passed" for model in self.report["models"].values())
        all_steps = all(step["status"] == "passed" for step in self.report["steps"].values())
        if all_steps and all_models:
            status = "passed"
        else:
            statuses = [step["status"] for step in self.report["steps"].values()]
            statuses.extend(model["status"] for model in self.report["models"].values())
            status = "failed" if "failed" in statuses else ("blocked" if "blocked" in statuses else "failed")
        self.report["status"] = status
        self.report["finishedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.save()
        print(f"\nResultado: {status}\nRelatório: {self.directory / 'report.json'}", flush=True)
        return 0 if status == "passed" else 1

    def execute(self):
        env_file = self.root / (".env" if (self.root / ".env").is_file() else ".env.example")
        compose = ["docker", "compose", "--env-file", str(env_file), "-f", "infra/compose.yaml"]
        compose_ok = self.run_step("compose_configuration", [*compose, "--profile", "m1", "--profile", "m2",
                                                              "--profile", "m3", "--profile", "tools",
                                                              "--profile", "build", "--profile", "tests", "config", "--quiet"])
        docker_ok = self.run_step("docker_service", ["docker", "version", "--format", "{{.Server.Version}}"])
        if not (compose_ok and docker_ok):
            self.report["modelsNotRunReason"] = "Configuração Compose ou serviço Docker indisponível; build e modelos não executados."
            return self.finish()
        toolchain_ok = self.run_step("toolchain", ["bash", "scripts/build.sh", "--version"], timeout=600)
        build_ok = False
        if toolchain_ok:
            build_ok = self.run_step("gradle_build_and_http_tests", ["bash", "scripts/build.sh", "verifyEnvironment",
                                                                    "--rerun-tasks"], timeout=1800)
        if build_ok:
            try:
                self.report["httpTests"] = validate_test_reports(self.root)
                self.report["jars"] = validate_jars(self.root)
            except (ValueError, OSError, ET.ParseError, zipfile.BadZipFile, KeyError) as error:
                self.report["steps"]["build_artifacts"] = {"status": "failed", "error": str(error)}
                build_ok = False
        if not (compose_ok and docker_ok and build_ok):
            self.report["modelsNotRunReason"] = "Pré-requisitos de Compose, serviço Docker ou build/testes não passaram."
            return self.finish()

        postgres_started = self.run_step("postgres_start", [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "postgres"], timeout=180)
        if not postgres_started:
            self.report["modelsNotRunReason"] = "O PostgreSQL não iniciou com sucesso."
            return self.finish()
        postgres_ok = self.run_step("postgres_query", [*compose, "exec", "-T", "postgres", "sh", "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc "SELECT current_database(), current_user, version();"'])
        if not postgres_ok:
            self.report["modelsNotRunReason"] = "A consulta de verificação do PostgreSQL falhou."
            return self.finish()

        for model in MODELS:
            result = self.report["models"][model]
            result["status"] = "running"
            self.save()
            started = self.run_step(f"{model}_startup", ["bash", "scripts/env.sh", "up", model, "--skip-build"], timeout=600)
            smoke_ok = started and self.run_step(f"{model}_k6_smoke", ["bash", "scripts/env.sh", "smoke", model], timeout=300)
            capture_ok = started and self.run_step(f"{model}_capture", ["bash", "scripts/env.sh", "capture", model])
            result["status"] = "failed"
            if capture_ok:
                try:
                    log = self.directory / f"{model}_capture.log"
                    snapshot_path = pathlib.Path(log.read_text().strip().splitlines()[-1]).resolve()
                    snapshot_path.relative_to((self.root / "results" / "raw").resolve())
                    snapshot = json.loads(snapshot_path.read_text())
                    validate_snapshot(snapshot, model)
                    result["snapshot"] = str(snapshot_path.relative_to(self.root))
                    result["runtime"] = snapshot["runtime"]
                    result["databaseConnection"] = "passed"
                    result["status"] = "passed" if smoke_ok else "failed"
                except (ValueError, OSError, IndexError) as error:
                    result["error"] = str(error)
            if any(self.report["steps"].get(f"{model}_{step}", {}).get("status") == "blocked"
                   for step in ("startup", "k6_smoke", "capture")):
                result["status"] = "blocked"
            self.save()
        return self.finish()


if __name__ == "__main__":
    raise SystemExit(ValidationRun().execute())
