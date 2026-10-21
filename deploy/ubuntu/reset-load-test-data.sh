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

python3 loadtest/seed_load_test.py \
  --confirm-loadtest-target \
  --env-file "${ENV_FILE}" \
  --citizens "${LOADTEST_CITIZENS}" \
  --auth-citizens "${LOADTEST_AUTH_CITIZENS}" \
  --pending-per-stage "${LOADTEST_PENDING_PER_STAGE}" \
  --registrations "${LOADTEST_REGISTRATIONS}" \
  --completed-documents "${LOADTEST_COMPLETED_DOCUMENTS}" \
  --otp-ttl-hours "${LOADTEST_OTP_TTL_HOURS}"

echo "Full load-test manifest has been written to loadtest/generated/accounts.json."
