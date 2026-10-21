#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
LOADTEST_COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f docker-compose.production.yml
  -f docker-compose.loadtest-target.yml
  -f docker-compose.monitoring.yml
)
PRODUCTION_COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f docker-compose.production.yml
)

"${LOADTEST_COMPOSE[@]}" down --remove-orphans
"${PRODUCTION_COMPOSE[@]}" up -d --build --remove-orphans
"${PRODUCTION_COMPOSE[@]}" ps

echo "Load-test mode nonaktif. OTP kembali dinamis dan email eksternal aktif."
