#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

for command_name in date docker find jq openssl realpath sha256sum; do
  require_command "$command_name"
done
configure_release_compose
validate_all_images
load_latest_backup

COMPOSE_JSON=$(compose_release config --format json)
jq -e '
  ([.services | to_entries[] | select(.key != "nginx") | .value.ports? // empty] | length) == 0
  and ((.services.nginx.ports // []) | length == 2)
  and .networks.data_net.internal == true
' <<<"$COMPOSE_JSON" >/dev/null || release_die "PRODUCTION_TOPOLOGY_INVALID"

while IFS= read -r secret_file; do
  require_regular_file "$secret_file" "SECRET_FILE_INVALID"
done < <(jq -r '.secrets[].file' <<<"$COMPOSE_JSON")

: "${RELEASE_TLS_CERTIFICATE_FILE:?RELEASE_TLS_CERTIFICATE_FILE is required}"
require_regular_file "$RELEASE_TLS_CERTIFICATE_FILE" "INVALID_TLS_CERTIFICATE_FILE"
RELEASE_TLS_MIN_DAYS=${RELEASE_TLS_MIN_DAYS:-30}
[[ "$RELEASE_TLS_MIN_DAYS" =~ ^[0-9]+$ ]] || release_die "INVALID_TLS_MIN_DAYS"
TLS_END_DATE=$(openssl x509 -in "$RELEASE_TLS_CERTIFICATE_FILE" -noout -enddate 2>/dev/null) ||
  release_die "TLS_CERTIFICATE_INVALID"
[[ "$TLS_END_DATE" == notAfter=* ]] || release_die "TLS_CERTIFICATE_INVALID"
TLS_END_EPOCH=$(date -u -d "${TLS_END_DATE#notAfter=}" +%s 2>/dev/null) ||
  release_die "TLS_CERTIFICATE_INVALID"
TLS_DAYS_REMAINING=$(((TLS_END_EPOCH - $(date -u +%s)) / 86400))
(( TLS_DAYS_REMAINING >= RELEASE_TLS_MIN_DAYS )) ||
  release_die "TLS_CERTIFICATE_TOO_CLOSE_TO_EXPIRY"

compose_release exec -T postgres sh -ceu   'pg_isready --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'   >/dev/null 2>&1 || release_die "POSTGRESQL_NOT_READY"
compose_release exec -T minio mc ready local >/dev/null 2>&1 ||
  release_die "MINIO_NOT_READY"

IMAGE_COUNT=$(jq '[.services[].image] | unique | length' <<<"$COMPOSE_JSON")
jq -nc   --argjson image_count "$IMAGE_COUNT"   --argjson backup_age_seconds "$BACKUP_AGE_SECONDS"   --argjson tls_days_remaining "$TLS_DAYS_REMAINING"   '{
    status:"ok",
    fixed_image_count:$image_count,
    backup_age_seconds:$backup_age_seconds,
    tls_days_remaining:$tls_days_remaining,
    postgresql:"ready",
    minio:"ready"
  }'
