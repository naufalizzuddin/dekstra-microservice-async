#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  exit 1
fi

docker compose --env-file "${ENV_FILE}" \
  -f docker-compose.production.yml \
  -f docker-compose.loadtest-target.yml \
  -f docker-compose.monitoring.yml \
  down --remove-orphans

echo "Microservice stopped. Database, Redis, media, static, and Prometheus volumes were preserved."
