#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Environment file tidak ditemukan: $ENV_FILE" >&2
    echo "Salin .env.production.example menjadi .env.production lalu isi semua secret." >&2
    exit 1
fi

env_value() {
    local key="$1"
    grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r'
}

require_real_value() {
    local key="$1"
    local value
    value="$(env_value "$key")"
    if [[ -z "$value" || "$value" == *replace* ]]; then
        echo "Nilai $key belum diisi dengan nilai production di $ENV_FILE." >&2
        exit 1
    fi
}

if [[ "${SKIP_ENV_PLACEHOLDER_CHECK:-0}" != "1" ]]; then
    for key in \
        SECRET_KEY INTERNAL_SERVICE_TOKEN REDIS_PASSWORD USER_DB_PASSWORD \
        DOCUMENT_DB_PASSWORD REPORTING_DB_PASSWORD EMAIL_HOST_USER \
        EMAIL_HOST_PASSWORD KEPALA_DESA_NAMA KEPALA_DESA_NIP
    do
        require_real_value "$key"
    done

    if [[ "$(env_value DOMAIN)" == "api.example.com" ]]; then
        echo "DOMAIN masih memakai contoh api.example.com di $ENV_FILE." >&2
        exit 1
    fi
    if [[ "$(env_value KEPALA_DESA_NAMA)" == "Nama Kepala Desa" ]]; then
        echo "KEPALA_DESA_NAMA masih memakai contoh di $ENV_FILE." >&2
        exit 1
    fi
    if [[ "$(env_value KEPALA_DESA_NIP)" == "1234567890" ]]; then
        echo "KEPALA_DESA_NIP masih memakai contoh di $ENV_FILE." >&2
        exit 1
    fi
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

cd "$ROOT_DIR"

echo "[1/4] Validasi konfigurasi Compose"
compose config --quiet

echo "[2/4] Build image"
compose build --pull

echo "[3/4] Jalankan database, migrasi, API, worker, dan gateway"
compose up -d --remove-orphans

echo "[4/4] Tunggu gateway sehat"
GATEWAY_BIND="$(compose port gateway 80)"
GATEWAY_HEALTH_HOST="${GATEWAY_BIND%:*}"
GATEWAY_HEALTH_PORT="${GATEWAY_BIND##*:}"
if [[ "$GATEWAY_HEALTH_HOST" == "0.0.0.0" || "$GATEWAY_HEALTH_HOST" == "::" || "$GATEWAY_HEALTH_HOST" == "[::]" ]]; then
    GATEWAY_HEALTH_HOST="127.0.0.1"
fi
GATEWAY_HEALTH_URL="http://${GATEWAY_HEALTH_HOST}:${GATEWAY_HEALTH_PORT}/health/"
for attempt in $(seq 1 60); do
    if curl --fail --silent --show-error "$GATEWAY_HEALTH_URL" >/dev/null; then
        compose ps
        echo "Deployment berhasil."
        exit 0
    fi
    sleep 2
done

compose ps
compose logs --tail=100 gateway user-api document-api approval-api reporting-api
echo "Gateway belum sehat setelah 120 detik." >&2
exit 1
