#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"

python3 loadtest/seed_load_test.py \
  --confirm-loadtest-target \
  --env-file "${ENV_FILE}" \
  --purge-only
