#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

usage() {
  printf '%s\n' \
    'Uso: ./scripts/database.sh apply-schema' \
    '     ./scripts/database.sh seed [opções do gerador/carregador]' \
    '     ./scripts/database.sh generate-data [opções]' \
    '     ./scripts/database.sh load-data [opções]' \
    'apply-schema cria as tabelas em public, em uma única transação.' \
    'Testes: ./scripts/test.sh schema ou ./scripts/test.sh seed.'
}

[[ $# -ge 1 ]] || { usage; exit 1; }
case "$1" in
  apply-schema) [[ $# -eq 1 ]] || { usage; exit 1; }; action="$1" ;;
  seed|generate-data|load-data) action="$1" ;;
  -h|--help) [[ $# -eq 1 ]] || { usage; exit 1; }; usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
shift

require_docker
if [[ "$action" != generate-data ]]; then
  compose up -d --wait --wait-timeout 45 postgres
fi

case "$action" in
  apply-schema)
    {
      printf 'SET LOCAL search_path TO public, pg_catalog;\n'
      cat "$TCC_ROOT/infra/postgres/001_create_io_schema.sql"
    } | postgres_psql --single-transaction --file=-
    printf '%s\n' 'Schema de /io aplicado em public. Nenhum dado foi carregado.'
    ;;
  seed|generate-data|load-data)
    mkdir -p "$TCC_ROOT/data/generated" "$TCC_ROOT/results/raw"
    compose --profile tools build seed
    seed_user="$(id -u):$(id -g)"
    case "$action" in
      seed) seed_action=prepare ;;
      generate-data) seed_action=generate ;;
      load-data) seed_action=load ;;
    esac
    compose --profile tools run --rm --no-deps --user "$seed_user" seed \
      python /workspace/scripts/lib/database/seed_data.py "$seed_action" "$@"
    ;;
esac
