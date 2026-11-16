#!/usr/bin/env bash
set -euo pipefail
# Each Gradle project owns a lockfile, including the application assembly project.
for lock in gradle.lockfile contract/gradle.lockfile domain/gradle.lockfile infrastructure/gradle.lockfile; do
  if [[ ! -f "$lock" ]]; then
    printf '%s\n' 'Os lockfiles WebFlux serão gerados na resolução das dependências de cada módulo.' >&2
    set -- "$@" --write-locks
    break
  fi
done
exec bash ./gradlew --no-daemon "$@"
