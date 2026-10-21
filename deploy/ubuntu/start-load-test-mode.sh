#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
LOADTEST_CITIZENS="${LOADTEST_CITIZENS:-60}"
LOADTEST_AUTH_CITIZENS="${LOADTEST_AUTH_CITIZENS:-500}"
LOADTEST_PENDING_PER_STAGE="${LOADTEST_PENDING_PER_STAGE:-5000}"
LOADTEST_REGISTRATIONS="${LOADTEST_REGISTRATIONS:-25000}"
LOADTEST_COMPLETED_DOCUMENTS="${LOADTEST_COMPLETED_DOCUMENTS:-2500}"
LOADTEST_OTP_TTL_HOURS="${LOADTEST_OTP_TTL_HOURS:-12}"
export GATEWAY_BIND_ADDRESS="${GATEWAY_BIND_ADDRESS:-0.0.0.0}"
COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f docker-compose.production.yml
  -f docker-compose.loadtest-target.yml
  -f docker-compose.monitoring.yml
)

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" up -d --build --remove-orphans
"${COMPOSE[@]}" ps

python3 loadtest/seed_load_test.py \
  --confirm-loadtest-target \
  --env-file "${ENV_FILE}" \
  --citizens "${LOADTEST_CITIZENS}" \
  --auth-citizens "${LOADTEST_AUTH_CITIZENS}" \
  --pending-per-stage "${LOADTEST_PENDING_PER_STAGE}" \
  --registrations "${LOADTEST_REGISTRATIONS}" \
  --completed-documents "${LOADTEST_COMPLETED_DOCUMENTS}" \
  --otp-ttl-hours "${LOADTEST_OTP_TTL_HOURS}"

echo "Load-test mode aktif."
echo "OTP tetap: 246810, TTL: ${LOADTEST_OTP_TTL_HOURS} jam"
echo "Prepared full load-test manifest: loadtest/generated/accounts.json"
echo "Prepared ${LOADTEST_REGISTRATIONS} pending registration candidates."
echo "Prepared $((LOADTEST_PENDING_PER_STAGE * 4)) approval/application candidates."
echo "Prepared ${LOADTEST_COMPLETED_DOCUMENTS} final document tokens."
echo "Gateway: ${GATEWAY_BIND_ADDRESS}:${GATEWAY_PORT:-8080}"
echo "Prometheus: 127.0.0.1:${PROMETHEUS_PORT:-9090}"
