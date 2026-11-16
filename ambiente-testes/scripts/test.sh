#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

usage() {
  printf '%s\n' \
    'Uso: ./scripts/test.sh apps|mvc-io|virtual-threads-io|reactive-io|schema|seed|validation|benchmark|environment|all' \
    '  apps        Testes HTTP dos três modelos e geração dos jars em Docker.' \
    '  mvc-io      Integração de /io no MVC com HTTP e PostgreSQL Docker.' \
    '  virtual-threads-io  Integração de /io em virtual threads com HTTP e PostgreSQL Docker.' \
    '  reactive-io Integração de /io no WebFlux/R2DBC com HTTP e PostgreSQL Docker.' \
    '  schema      Integridade do DDL em uma cópia isolada no PostgreSQL Docker.' \
    '  seed        Gerador e integração da carga em Docker, com dados isolados.' \
    '  validation  Testes do automatizador em Docker, sem iniciar os modelos.' \
    '  benchmark   Testes dos orquestradores de experimentos, sem iniciar os modelos.' \
    '  environment Build, banco e smoke/captura dos três modelos; deixa M3 ativo.' \
    '  all         Apps, validation, benchmark, integrações /io dos três modelos, schema e seed; sem environment ou carga da massa.'
}

[[ $# -eq 1 ]] || { usage; exit 1; }
case "$1" in
  -h|--help) usage; exit 0 ;;
  apps|mvc-io|virtual-threads-io|reactive-io|schema|seed|validation|benchmark|environment|all) target="$1" ;;
  *) usage; exit 1 ;;
esac

run_group() {
  printf '\nExecutando grupo: %s\n' "$1"
  case "$1" in
    apps) "$TCC_ROOT/scripts/build.sh" verifyEnvironment --rerun-tasks ;;
    mvc-io|virtual-threads-io|reactive-io)
      require_docker
      compose --profile tests up -d --wait --wait-timeout 45 postgres
      compose --profile tests run --rm --no-deps --user "$(id -u):$(id -g)" "$1-test"
      ;;
    schema)
      require_docker
      compose up -d --wait --wait-timeout 45 postgres
      # Cópia transacional: fixtures, índices e sequência são removidos no rollback.
      check_schema="tcc2_schema_check_$$"
      {
        printf 'BEGIN;\nCREATE SCHEMA %s;\nSET LOCAL search_path TO %s, pg_catalog;\n' \
          "$check_schema" "$check_schema"
        cat "$TCC_ROOT/infra/postgres/001_create_io_schema.sql" "$TCC_ROOT/tests/database/check_io_schema.sql"
        printf 'ROLLBACK;\n'
      } | postgres_psql --file=-
      printf '%s\n' 'Verificação aprovada; a cópia e os dados de teste foram desfeitos.'
      ;;
    seed|validation|benchmark)
      require_docker
      seed_integration=0
      if [[ "$1" == seed ]]; then
        compose up -d --wait --wait-timeout 45 postgres
        seed_integration=1
      fi
      mkdir -p "$TCC_ROOT/data/generated" "$TCC_ROOT/results/raw"
      compose --profile tools build seed
      compose --profile tools run --rm --no-deps --user "$(id -u):$(id -g)" \
        -e "TCC_SEED_INTEGRATION=$seed_integration" \
        seed python -m unittest discover -s "/workspace/tests/$1" -v
      ;;
    environment)
      require_command python3
      exec python3 "$TCC_ROOT/scripts/lib/environment/validate_environment.py"
      ;;
  esac
}

if [[ "$target" == all ]]; then
  for group in apps validation benchmark mvc-io virtual-threads-io reactive-io schema seed; do
    run_group "$group"
  done
else
  run_group "$target"
fi
