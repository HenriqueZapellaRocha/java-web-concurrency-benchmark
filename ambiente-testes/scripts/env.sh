#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

usage() {
  printf '%s\n' \
    'Uso: ./scripts/env.sh up m1|m2|m3 [--skip-build]' \
    '     ./scripts/env.sh smoke m1|m2|m3' \
    '     ./scripts/env.sh cpu-pilot m1|m2|m3' \
    '     ./scripts/env.sh cpu-study --dry-run|--execute [opções]' \
    '     ./scripts/env.sh cpu-study --consolidate STUDY_ID' \
    '     ./scripts/env.sh io-pilot m1|m2|m3' \
    '     ./scripts/env.sh io-study --dry-run|--execute [opções]' \
    '     ./scripts/env.sh io-study --consolidate STUDY_ID' \
    '     ./scripts/env.sh mixed-pilot m1|m2|m3' \
    '     ./scripts/env.sh mixed-study --dry-run|--execute [opções]' \
    '     ./scripts/env.sh mixed-study --consolidate STUDY_ID' \
    '     ./scripts/env.sh logs m1|m2|m3' \
    '     ./scripts/env.sh capture m1|m2|m3' \
    '     ./scripts/env.sh check|status|stop' \
    'check confere ferramentas, configuração Compose e acesso ao Docker; não faz build.'
}

[[ $# -ge 1 ]] || { usage; exit 1; }
action="$1"
case "$action" in
  up)
    [[ $# -eq 2 || ( $# -eq 3 && "$3" == --skip-build ) ]] || { usage; exit 1; }
    model="$2"
    validate_model "$model"
    ;;
  smoke|cpu-pilot|io-pilot|mixed-pilot|logs|capture)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    model="$2"
    validate_model "$model"
    ;;
  cpu-study|io-study|mixed-study) [[ $# -ge 2 ]] || { usage; exit 1; } ;;
  check|status|stop) [[ $# -eq 1 ]] || { usage; exit 1; } ;;
  -h|--help) [[ $# -eq 1 ]] || { usage; exit 1; }; usage; exit 0 ;;
  *) usage; exit 1 ;;
esac

if [[ "$action" == check ]]; then
  require_command curl
  require_command python3
  require_command docker
  compose --profile m1 --profile m2 --profile m3 --profile tools --profile build --profile tests config --quiet
fi
if [[ "$action" == cpu-study ]]; then
  require_command python3
  exec python3 "$TCC_ROOT/scripts/lib/benchmark/cpu_study.py" "${@:2}"
fi
if [[ "$action" == io-study ]]; then
  require_command python3
  exec python3 "$TCC_ROOT/scripts/lib/benchmark/io_study.py" "${@:2}"
fi
if [[ "$action" == mixed-study ]]; then
  require_command python3
  exec python3 "$TCC_ROOT/scripts/lib/benchmark/mixed_study.py" "${@:2}"
fi
require_docker
case "$action" in
  check)
    printf '%s\n' 'Ferramentas e Compose disponíveis. Docker acessível; nenhum build executado.'
    docker version --format '{{.Server.Version}}'
    ;;
  up)
    require_command curl
    require_command python3
    if [[ "${3:-}" == --skip-build ]]; then
      app_dir="$(application_directory "$model")"
      jar="$app_dir/build/libs/${app_dir##*/}-app.jar"
      [[ -f "$jar" ]] || fail "jar ausente; execute ./scripts/build.sh antes de usar --skip-build"
    else
      "$TCC_ROOT/scripts/build.sh" "$model" bootJar
    fi
    compose --profile "$model" build "$model"
    # Escopo restrito aos protótipos do projeto tcc2. O banco e seu volume são mantidos.
    compose --profile m1 --profile m2 --profile m3 stop m1 m2 m3
    compose --profile "$model" up -d postgres "$model"
    url="$(application_url "$model")"
    ready=false
    for attempt in {1..30}; do
      if curl -fsS --max-time 2 "$url/actuator/health/readiness" >/dev/null 2>&1; then
        ready=true
        break
      fi
      sleep 2
    done
    if [[ "$ready" != true ]]; then
      compose logs --tail 40 "$model"
      fail "modelo $model não ficou pronto; verifique aplicação e conexão com PostgreSQL"
    fi
    printf 'Ambiente %s disponível em %s\n' "$model" "$url"
    curl -fsS "$url/environment" | python3 -m json.tool
    ;;
  smoke)
    mkdir -p "$TCC_ROOT/results/raw"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    compose --profile tools run --rm --no-deps \
      --user "$(id -u):$(id -g)" \
      -e BASE_URL="http://$model:8080" -e EXPECTED_MODEL="$model" \
      k6 run --summary-export "/results/$model-smoke-$stamp.json" /scripts/smoke.js
    ;;
  cpu-pilot)
    result_dir="${CPU_RESULT_DIR:-}"
    if [[ -n "$result_dir" ]]; then
      [[ "$result_dir" != /* && "$result_dir" != *..* && "$result_dir" =~ ^[A-Za-z0-9._/-]+$ ]] || \
        fail 'CPU_RESULT_DIR deve ser um caminho relativo seguro'
    fi
    host_result_dir="$TCC_ROOT/results/raw${result_dir:+/$result_dir}"
    container_result_dir="/results${result_dir:+/$result_dir}"
    mkdir -p "$host_result_dir"
    container_id="$(compose ps -q "$model")"
    [[ -n "$container_id" ]] || fail "modelo $model não está em execução; use ./scripts/env.sh up $model"
    expected_iterations="$(docker exec "$container_id" printenv CPU_ITERATIONS)"
    execution_mode=request-thread
    if [[ "$model" == m3 ]]; then
      execution_mode="$(docker exec "$container_id" printenv CPU_EXECUTION_MODE)"
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    prefix="${CPU_RUN_ID:-$model-cpu-pilot-$stamp}"
    k6_args=(run --summary-export "$container_result_dir/$prefix-summary.json")
    if [[ "${K6_CPU_WRITE_RAW:-true}" == true ]]; then
      k6_args+=(--out "json=$container_result_dir/$prefix-metrics.jsonl")
    fi
    k6_args+=(/scripts/cpu.js)
    compose --profile tools run --rm --no-deps \
      --user "$(id -u):$(id -g)" \
      -e BASE_URL="http://$model:8080" \
      -e EXPECTED_MODEL="$model" \
      -e EXPECTED_ITERATIONS="$expected_iterations" \
      -e EXECUTION_MODE="$execution_mode" \
      k6 "${k6_args[@]}"
    printf 'Resumo: results/raw%s/%s-summary.json\n' "${result_dir:+/$result_dir}" "$prefix"
    if [[ "${K6_CPU_WRITE_RAW:-true}" == true ]]; then
      printf 'Métricas brutas: results/raw%s/%s-metrics.jsonl\n' "${result_dir:+/$result_dir}" "$prefix"
    fi
    ;;
  io-pilot)
    require_command python3
    result_dir="${IO_RESULT_DIR:-}"
    if [[ -n "$result_dir" ]]; then
      [[ "$result_dir" != /* && "$result_dir" != *..* && "$result_dir" =~ ^[A-Za-z0-9._/-]+$ ]] || \
        fail 'IO_RESULT_DIR deve ser um caminho relativo seguro'
    fi
    host_result_dir="$TCC_ROOT/results/raw${result_dir:+/$result_dir}"
    container_result_dir="/results${result_dir:+/$result_dir}"
    mkdir -p "$host_result_dir"
    container_id="$(compose ps -q "$model")"
    [[ -n "$container_id" ]] || fail "modelo $model não está em execução; use ./scripts/env.sh up $model"
    run_uuid="${IO_RUN_UUID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    prefix="${IO_RUN_ID:-$model-io-pilot-$stamp}"
    k6_args=(run --summary-export "$container_result_dir/$prefix-summary.json")
    if [[ "${K6_IO_WRITE_RAW:-true}" == true ]]; then
      k6_args+=(--out "json=$container_result_dir/$prefix-metrics.jsonl")
    fi
    k6_args+=(/scripts/io.js)
    compose --profile tools run --rm --no-deps \
      --user "$(id -u):$(id -g)" \
      -e BASE_URL="http://$model:8080" -e EXPECTED_MODEL="$model" \
      -e RUN_ID="$run_uuid" -e ITEM_MIN_ID="${IO_ITEM_MIN_ID:-1}" -e ITEM_MAX_ID="${IO_ITEM_MAX_ID:-100000}" \
      -e ITEM_OFFSET="${IO_ITEM_OFFSET:-0}" \
      -e RATE="${K6_IO_RATE:-100}" -e WARMUP_RATE="${K6_IO_WARMUP_RATE:-100}" \
      -e TIME_UNIT="${K6_IO_TIME_UNIT:-1s}" -e WARMUP_DURATION="${K6_IO_WARMUP_DURATION:-30s}" \
      -e MEASUREMENT_DURATION="${K6_IO_MEASUREMENT_DURATION:-60s}" \
      -e PRE_ALLOCATED_VUS="${K6_IO_PRE_ALLOCATED_VUS:-100}" -e MAX_VUS="${K6_IO_MAX_VUS:-1000}" \
      -e REQUEST_TIMEOUT="${K6_IO_REQUEST_TIMEOUT:-15s}" \
      k6 "${k6_args[@]}"
    printf 'Run UUID: %s\nResumo: results/raw%s/%s-summary.json\n' "$run_uuid" "${result_dir:+/$result_dir}" "$prefix"
    if [[ "${K6_IO_WRITE_RAW:-true}" == true ]]; then
      printf 'Métricas brutas: results/raw%s/%s-metrics.jsonl\n' "${result_dir:+/$result_dir}" "$prefix"
    fi
    ;;
  mixed-pilot)
    require_command python3
    result_dir="${MIXED_RESULT_DIR:-}"
    if [[ -n "$result_dir" ]]; then
      [[ "$result_dir" != /* && "$result_dir" != *..* && "$result_dir" =~ ^[A-Za-z0-9._/-]+$ ]] || \
        fail 'MIXED_RESULT_DIR deve ser um caminho relativo seguro'
    fi
    host_result_dir="$TCC_ROOT/results/raw${result_dir:+/$result_dir}"
    container_result_dir="/results${result_dir:+/$result_dir}"
    mkdir -p "$host_result_dir"
    container_id="$(compose ps -q "$model")"
    [[ -n "$container_id" ]] || fail "modelo $model não está em execução; use ./scripts/env.sh up $model"
    expected_iterations="$(docker exec "$container_id" printenv MIXED_CPU_ITERATIONS)"
    execution_mode=request-thread
    if [[ "$model" == m3 ]]; then
      execution_mode="$(docker exec "$container_id" printenv MIXED_CPU_EXECUTION_MODE)"
    fi
    run_uuid="${IO_RUN_UUID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    prefix="${MIXED_RUN_ID:-$model-mixed-pilot-$stamp}"
    k6_args=(run --summary-export "$container_result_dir/$prefix-summary.json")
    if [[ "${K6_MIXED_WRITE_RAW:-true}" == true ]]; then
      k6_args+=(--out "json=$container_result_dir/$prefix-metrics.jsonl")
    fi
    k6_args+=(/scripts/mixed.js)
    compose --profile tools run --rm --no-deps \
      --user "$(id -u):$(id -g)" \
      -e BASE_URL="http://$model:8080" -e EXPECTED_MODEL="$model" \
      -e EXPECTED_ITERATIONS="$expected_iterations" -e EXECUTION_MODE="$execution_mode" \
      -e RUN_ID="$run_uuid" -e ITEM_MIN_ID="${IO_ITEM_MIN_ID:-1}" -e ITEM_MAX_ID="${IO_ITEM_MAX_ID:-100000}" \
      -e ITEM_OFFSET="${IO_ITEM_OFFSET:-0}" \
      -e RATE="${K6_MIXED_RATE:-100}" -e WARMUP_RATE="${K6_MIXED_WARMUP_RATE:-100}" \
      -e TIME_UNIT="${K6_MIXED_TIME_UNIT:-1s}" -e WARMUP_DURATION="${K6_MIXED_WARMUP_DURATION:-30s}" \
      -e MEASUREMENT_DURATION="${K6_MIXED_MEASUREMENT_DURATION:-60s}" \
      -e PRE_ALLOCATED_VUS="${K6_MIXED_PRE_ALLOCATED_VUS:-100}" -e MAX_VUS="${K6_MIXED_MAX_VUS:-1000}" \
      -e REQUEST_TIMEOUT="${K6_MIXED_REQUEST_TIMEOUT:-15s}" \
      k6 "${k6_args[@]}"
    printf 'Run UUID: %s\nResumo: results/raw%s/%s-summary.json\n' "$run_uuid" "${result_dir:+/$result_dir}" "$prefix"
    if [[ "${K6_MIXED_WRITE_RAW:-true}" == true ]]; then
      printf 'Métricas brutas: results/raw%s/%s-metrics.jsonl\n' "${result_dir:+/$result_dir}" "$prefix"
    fi
    ;;
  capture)
    require_command python3
    exec python3 "$TCC_ROOT/scripts/lib/environment/capture_environment.py" "$model" "$(application_url "$model")"
    ;;
  logs) compose logs --tail 100 "$model" ;;
  status) compose --profile m1 --profile m2 --profile m3 ps -a ;;
  stop) compose --profile m1 --profile m2 --profile m3 --profile tools --profile build --profile tests down ;;
esac
