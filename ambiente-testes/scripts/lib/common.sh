#!/usr/bin/env bash
# Biblioteca de comandos do workspace; não altera ferramentas globais.
set -euo pipefail
TCC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

fail() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "comando necessário não encontrado: $1"
}

compose() {
  local env_file="$TCC_ROOT/.env.example"
  if [[ -f "$TCC_ROOT/.env" ]]; then
    env_file="$TCC_ROOT/.env"
  fi
  docker compose --env-file "$env_file" -f "$TCC_ROOT/infra/compose.yaml" "$@"
}

postgres_psql() {
  compose exec -T postgres sh -c \
    'exec psql --no-psqlrc --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --set=ON_ERROR_STOP=1 "$@"' \
    sh "$@"
}

require_docker() {
  require_command docker
  local diagnostic
  if ! diagnostic="$(docker info --format '{{.ServerVersion}}' 2>&1)"; then
    if [[ "$diagnostic" == *"permission denied"* || "$diagnostic" == *"operation not permitted"* ]]; then
      fail "acesso ao Docker bloqueado nesta sessão. Execute no terminal local com acesso ao engine. Detalhe: $diagnostic"
    fi
    fail "Docker não está disponível. Inicie o Docker Desktop. Detalhe: $diagnostic"
  fi
}

validate_model() {
  case "$1" in m1|m2|m3) ;; *) fail "modelo inválido: $1 (use m1, m2 ou m3)" ;; esac
}

application_directory() {
  case "$1" in
    m1) printf '%s/apps/mvc' "$TCC_ROOT" ;;
    m2) printf '%s/apps/virtual-threads' "$TCC_ROOT" ;;
    m3) printf '%s/apps/reactive' "$TCC_ROOT" ;;
    *) fail "modelo inválido: $1 (use m1, m2 ou m3)" ;;
  esac
}

application_url() {
  local binding
  binding="$(compose port "$1" 8080)"
  [[ -n "$binding" ]] || fail "modelo $1 não está em execução"
  printf 'http://%s' "$binding"
}
