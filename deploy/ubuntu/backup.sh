#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${1:-$ROOT_DIR/backups/$TIMESTAMP}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Environment file tidak ditemukan: $ENV_FILE" >&2
    exit 1
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

mkdir -p "$BACKUP_DIR"

echo "Backup PostgreSQL"
compose exec -T user-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$BACKUP_DIR/user_db.dump"
compose exec -T document-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$BACKUP_DIR/document_db.dump"
compose exec -T reporting-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$BACKUP_DIR/reporting_db.dump"

echo "Backup media"
compose exec -T user-api tar -C /app/media -czf - . >"$BACKUP_DIR/user_media.tar.gz"
compose exec -T document-api tar -C /app/media -czf - . >"$BACKUP_DIR/document_media.tar.gz"

sha256sum "$BACKUP_DIR"/* >"$BACKUP_DIR/SHA256SUMS"
echo "Backup selesai: $BACKUP_DIR"
