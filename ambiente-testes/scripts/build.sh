#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"
target=all
case "${1:-}" in
  m1|m2|m3|all) target="$1"; shift ;;
  -h|--help)
    printf '%s\n' 'Uso: ./scripts/build.sh [m1|m2|m3|all] [tarefas/opções Gradle]' \
      'Padrão: todos os projetos, tarefa verifyEnvironment. Execução sempre em Docker.'
    exit 0
    ;;
esac
[[ $# -gt 0 ]] || set -- verifyEnvironment
require_docker
for model in m1 m2 m3; do
  [[ "$target" == all || "$target" == "$model" ]] || continue
  app_dir="$(application_directory "$model")"
  mkdir -p "$app_dir/.cache/gradle"
  printf '\nBuild de %s (%s)\n' "$model" "${app_dir##*/}"
  compose --profile build run --rm --no-deps --user "$(id -u):$(id -g)" "build-$model" "$@"
done
