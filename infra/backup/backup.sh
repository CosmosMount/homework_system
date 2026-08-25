#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

: "${BACKUP_OUTPUT_DIR:?BACKUP_OUTPUT_DIR is required}"
: "${BACKUP_STATE_DIR:?BACKUP_STATE_DIR is required}"
: "${BACKUP_GPG_RECIPIENT:?BACKUP_GPG_RECIPIENT is required}"
: "${BACKUP_KIND:?BACKUP_KIND must be daily or weekly}"
: "${NGINX_CONFIG_FILE:?NGINX_CONFIG_FILE is required}"
BACKUP_WORK_ROOT=${BACKUP_WORK_ROOT:-/tmp}

[[ "$BACKUP_KIND" == "daily" || "$BACKUP_KIND" == "weekly" ]] ||
  backup_die "INVALID_BACKUP_KIND"
require_safe_directory "$BACKUP_OUTPUT_DIR" "INVALID_BACKUP_OUTPUT_DIR"
require_safe_directory "$BACKUP_STATE_DIR" "INVALID_BACKUP_STATE_DIR"
require_safe_directory "$BACKUP_WORK_ROOT" "INVALID_BACKUP_WORK_ROOT"
require_regular_file "$NGINX_CONFIG_FILE" "INVALID_NGINX_CONFIG_FILE"
for command_name in docker jq gpg tar sha256sum stat flock realpath install; do
  require_command "$command_name"
done

OUTPUT_DIRECTORY_RESOLVED=$(realpath -e -- "$BACKUP_OUTPUT_DIR")
STATE_DIRECTORY_RESOLVED=$(realpath -e -- "$BACKUP_STATE_DIR")
if [[ "$STATE_DIRECTORY_RESOLVED" == "$OUTPUT_DIRECTORY_RESOLVED" ||
  "$STATE_DIRECTORY_RESOLVED" == "$OUTPUT_DIRECTORY_RESOLVED/"* ||
  "$OUTPUT_DIRECTORY_RESOLVED" == "$STATE_DIRECTORY_RESOLVED/"* ]]; then
  backup_die "BACKUP_STATE_MUST_BE_LOCAL_AND_SEPARATE"
fi
STATE_DIRECTORY_MODE=$(stat -c %a "$STATE_DIRECTORY_RESOLVED")
(( (8#$STATE_DIRECTORY_MODE & 077) == 0 )) ||
  backup_die "INSECURE_BACKUP_STATE_PERMISSIONS"
configure_compose

RECIPIENT_FINGERPRINT=$(
  gpg --batch --with-colons --list-keys "$BACKUP_GPG_RECIPIENT" 2>/dev/null |
    awk -F: '$1 == "fpr" { print $10; exit }'
)
[[ "$RECIPIENT_FINGERPRINT" =~ ^[0-9A-Fa-f]{40,64}$ ]] ||
  backup_die "GPG_RECIPIENT_NOT_FOUND"

exec 8>"$BACKUP_STATE_DIR/.backup-state.lock"
flock -n 8 || backup_die "BACKUP_STATE_ALREADY_LOCKED"
exec 9>"$BACKUP_OUTPUT_DIR/.backup.lock"
flock -n 9 || backup_die "BACKUP_ALREADY_RUNNING"

BACKUP_STARTED_EPOCH=$(date +%s)
BACKUP_CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BACKUP_TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_ID="pnx-backup-$BACKUP_TIMESTAMP-$BACKUP_KIND"
FINAL_ARCHIVE="$BACKUP_OUTPUT_DIR/$BACKUP_ID.tar.gpg"
FINAL_CHECKSUM="$FINAL_ARCHIVE.sha256"
FINAL_METADATA="$BACKUP_OUTPUT_DIR/$BACKUP_ID.meta.json"
[[ ! -e "$FINAL_ARCHIVE" && ! -e "$FINAL_CHECKSUM" && ! -e "$FINAL_METADATA" ]] ||
  backup_die "BACKUP_ID_COLLISION"

WEEKLY_BASE_STATE="$BACKUP_STATE_DIR/minio-weekly-base-manifest.json"
OBJECT_BACKUP_MODE=full
OBJECT_BASE_BACKUP_ID=
if [[ "$BACKUP_KIND" == "daily" ]]; then
  require_regular_file "$WEEKLY_BASE_STATE" "MINIO_WEEKLY_BASE_STATE_MISSING"
  OBJECT_BASE_BACKUP_ID=$(jq -er '
    select(
      .version == 2
      and .mode == "full"
      and (.backup_id | type == "string")
      and (.backup_id | test("^pnx-backup-[0-9]{8}T[0-9]{6}Z-weekly$"))
    )
    | .backup_id
  ' "$WEEKLY_BASE_STATE") || backup_die "MINIO_WEEKLY_BASE_STATE_INVALID"
  require_regular_file \
    "$BACKUP_OUTPUT_DIR/$OBJECT_BASE_BACKUP_ID.tar.gpg" \
    "MINIO_WEEKLY_BASE_ARCHIVE_MISSING"
  require_regular_file \
    "$BACKUP_OUTPUT_DIR/$OBJECT_BASE_BACKUP_ID.tar.gpg.sha256" \
    "MINIO_WEEKLY_BASE_CHECKSUM_MISSING"
  require_regular_file \
    "$BACKUP_OUTPUT_DIR/$OBJECT_BASE_BACKUP_ID.meta.json" \
    "MINIO_WEEKLY_BASE_METADATA_MISSING"
  (
    cd -- "$BACKUP_OUTPUT_DIR"
    sha256sum --check --status "$OBJECT_BASE_BACKUP_ID.tar.gpg.sha256"
  ) || backup_die "MINIO_WEEKLY_BASE_CHECKSUM_FAILED"
  jq -e --arg backup_id "$OBJECT_BASE_BACKUP_ID" '
    .status == "ok"
    and .backup_id == $backup_id
    and .kind == "weekly"
    and .object_backup_mode == "full"
  ' "$BACKUP_OUTPUT_DIR/$OBJECT_BASE_BACKUP_ID.meta.json" >/dev/null ||
    backup_die "MINIO_WEEKLY_BASE_METADATA_INVALID"
  OBJECT_BACKUP_MODE=incremental
fi

STAGING_DIRECTORY=$(mktemp -d "$BACKUP_WORK_ROOT/pnx-backup.XXXXXX")
PLAIN_DIRECTORY="$STAGING_DIRECTORY/plain"
PARTIAL_ARCHIVE="$BACKUP_OUTPUT_DIR/.$BACKUP_ID.tar.gpg.partial"
PARTIAL_CHECKSUM="$BACKUP_OUTPUT_DIR/.$BACKUP_ID.tar.gpg.sha256.partial"
PARTIAL_METADATA="$BACKUP_OUTPUT_DIR/.$BACKUP_ID.meta.json.partial"
PARTIAL_BASE_STATE="$BACKUP_STATE_DIR/.$BACKUP_ID.minio-weekly-base.partial"
cleanup_backup() {
  rm -rf -- "$STAGING_DIRECTORY"
  rm -f -- \
    "$PARTIAL_ARCHIVE" \
    "$PARTIAL_CHECKSUM" \
    "$PARTIAL_METADATA" \
    "$PARTIAL_BASE_STATE"
}
trap cleanup_backup EXIT
install -d -m 0700 "$PLAIN_DIRECTORY/database" "$PLAIN_DIRECTORY/objects"
install -d -m 0700 "$PLAIN_DIRECTORY/config"
install -d -m 0770 "$PLAIN_DIRECTORY/object-transfer"

compose_run exec -T postgres sh -ceu \
  'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  >"$PLAIN_DIRECTORY/database/database.dump"
[[ -s "$PLAIN_DIRECTORY/database/database.dump" ]] ||
  backup_die "DATABASE_DUMP_EMPTY"

HOST_UID=$(id -u)
HOST_GID=$(id -g)
OBJECT_EXPORT_VOLUMES=(
  --volume "$PLAIN_DIRECTORY/object-transfer:/operations:rw"
)
OBJECT_EXPORT_ARGUMENTS=(
  python -m app.cli export-objects
  --output /operations/export
  --backup-id "$BACKUP_ID"
)
if [[ "$BACKUP_KIND" == "daily" ]]; then
  OBJECT_EXPORT_VOLUMES+=(--volume "$BACKUP_STATE_DIR:/backup-state:ro")
  OBJECT_EXPORT_ARGUMENTS+=(
    --base-manifest /backup-state/minio-weekly-base-manifest.json
  )
fi
compose_run run --rm --no-deps -T \
  --user "$HOST_UID:$HOST_GID" \
  "${OBJECT_EXPORT_VOLUMES[@]}" \
  backend \
  "${OBJECT_EXPORT_ARGUMENTS[@]}" \
  >"$PLAIN_DIRECTORY/objects/export-summary.json"
OBJECT_MANIFEST="$PLAIN_DIRECTORY/object-transfer/export/manifest.json"
[[ -s "$OBJECT_MANIFEST" ]] || backup_die "OBJECT_EXPORT_MANIFEST_MISSING"
if [[ "$BACKUP_KIND" == "weekly" ]]; then
  jq -e --arg backup_id "$BACKUP_ID" '
    .version == 2
    and .backup_id == $backup_id
    and .mode == "full"
    and .base_backup_id == null
    and .base_manifest_sha256 == null
  ' "$OBJECT_MANIFEST" >/dev/null || backup_die "OBJECT_FULL_MANIFEST_INVALID"
else
  jq -e \
    --arg backup_id "$BACKUP_ID" \
    --arg base_backup_id "$OBJECT_BASE_BACKUP_ID" '
      .version == 2
      and .backup_id == $backup_id
      and .mode == "incremental"
      and .base_backup_id == $base_backup_id
      and (.base_manifest_sha256 | test("^[0-9a-f]{64}$"))
    ' "$OBJECT_MANIFEST" >/dev/null || backup_die "OBJECT_INCREMENTAL_MANIFEST_INVALID"
fi
mv -- "$PLAIN_DIRECTORY/object-transfer/export" "$PLAIN_DIRECTORY/objects/export"
rmdir -- "$PLAIN_DIRECTORY/object-transfer"
OBJECT_MANIFEST="$PLAIN_DIRECTORY/objects/export/manifest.json"

compose_run run --rm --no-deps -T backend alembic current \
  >"$PLAIN_DIRECTORY/database/alembic-current.txt"
[[ -s "$PLAIN_DIRECTORY/database/alembic-current.txt" ]] ||
  backup_die "ALEMBIC_HEAD_MISSING"

cp -- "$COMPOSE_FILE" "$PLAIN_DIRECTORY/config/compose.production.yml"
cp -- "$NGINX_CONFIG_FILE" "$PLAIN_DIRECTORY/config/nginx.production.conf"
awk -F= '
  $1 ~ /^(COMPOSE_PROJECT_NAME|BACKEND_IMAGE|FRONTEND_IMAGE|APP_BASE_URL|TRUSTED_HOSTS|APP_TIMEZONE|CAMPUS_EMAIL_DOMAIN|LOG_LEVEL|MINIO_PUBLIC_BASE_URL|POSTGRES_DB|POSTGRES_USER|DATABASE_POOL_SIZE|DATABASE_MAX_OVERFLOW|MINIO_BUCKET|MINIO_REGION|SMTP_HOST|SMTP_PORT|SMTP_STARTTLS|MAIL_FROM|MAIL_REPLY_TO|GLOBAL_MAX_UPLOAD_BYTES|UPLOAD_PART_SIZE_BYTES|UPLOAD_SESSION_TTL_SECONDS|WORKER_NAME|WORKER_HEARTBEAT_INTERVAL_SECONDS|WORKER_STALE_AFTER_SECONDS|WORKER_POLL_INTERVAL_SECONDS|WORKER_LOCK_LEASE_SECONDS)$/ {
    print
  }
' "$COMPOSE_ENV_FILE" >"$PLAIN_DIRECTORY/config/non-secret.env"
compose_run config --images >"$PLAIN_DIRECTORY/config/images.txt"

OBJECT_COUNT=$(jq -er '.inventory | length' "$OBJECT_MANIFEST")
OBJECT_BYTES=$(jq -er '[.inventory[].size_bytes] | add // 0' "$OBJECT_MANIFEST")
OBJECT_PAYLOAD_COUNT=$(jq -er '.objects | length' "$OBJECT_MANIFEST")
OBJECT_PAYLOAD_BYTES=$(jq -er '[.objects[].size_bytes] | add // 0' "$OBJECT_MANIFEST")
OBJECT_DELETED_COUNT=$(jq -er '.deleted_object_keys | length' "$OBJECT_MANIFEST")
DATABASE_BYTES=$(stat -c %s "$PLAIN_DIRECTORY/database/database.dump")
ALEMBIC_HEAD=$(tr '\n' ' ' <"$PLAIN_DIRECTORY/database/alembic-current.txt" | sed 's/[[:space:]]*$//')
jq -n \
  --arg backup_id "$BACKUP_ID" \
  --arg kind "$BACKUP_KIND" \
  --arg created_at "$BACKUP_CREATED_AT" \
  --arg compose_project "$COMPOSE_PROJECT" \
  --arg alembic_head "$ALEMBIC_HEAD" \
  --arg object_backup_mode "$OBJECT_BACKUP_MODE" \
  --arg object_base_backup_id "$OBJECT_BASE_BACKUP_ID" \
  --argjson database_bytes "$DATABASE_BYTES" \
  --argjson object_count "$OBJECT_COUNT" \
  --argjson object_bytes "$OBJECT_BYTES" \
  --argjson object_payload_count "$OBJECT_PAYLOAD_COUNT" \
  --argjson object_payload_bytes "$OBJECT_PAYLOAD_BYTES" \
  --argjson object_deleted_count "$OBJECT_DELETED_COUNT" '
  {
    version: 2,
    backup_id: $backup_id,
    kind: $kind,
    created_at: $created_at,
    compose_project: $compose_project,
    alembic_head: $alembic_head,
    database_bytes: $database_bytes,
    object_backup_mode: $object_backup_mode,
    object_base_backup_id: (
      if $object_base_backup_id == "" then null else $object_base_backup_id end
    ),
    object_count: $object_count,
    object_bytes: $object_bytes,
    object_payload_count: $object_payload_count,
    object_payload_bytes: $object_payload_bytes,
    object_deleted_count: $object_deleted_count
  }
' >"$PLAIN_DIRECTORY/MANIFEST.json"

(
  cd -- "$PLAIN_DIRECTORY"
  find . -type f ! -name SHA256SUMS -print0 |
    LC_ALL=C sort -z |
    xargs -0 sha256sum >SHA256SUMS
)
tar --format=pax --sort=name -C "$PLAIN_DIRECTORY" \
  -cf "$STAGING_DIRECTORY/backup.tar" .
gpg --batch --yes --trust-model always \
  --recipient "$RECIPIENT_FINGERPRINT" \
  --output "$PARTIAL_ARCHIVE" \
  --encrypt "$STAGING_DIRECTORY/backup.tar"
[[ -s "$PARTIAL_ARCHIVE" ]] || backup_die "ENCRYPTED_BACKUP_EMPTY"

ARCHIVE_HASH=$(sha256sum "$PARTIAL_ARCHIVE" | awk '{print $1}')
printf '%s  %s\n' "$ARCHIVE_HASH" "$(basename "$FINAL_ARCHIVE")" \
  >"$PARTIAL_CHECKSUM"
ARCHIVE_BYTES=$(stat -c %s "$PARTIAL_ARCHIVE")
DURATION_SECONDS=$(( $(date +%s) - BACKUP_STARTED_EPOCH ))
jq -n \
  --arg backup_id "$BACKUP_ID" \
  --arg kind "$BACKUP_KIND" \
  --arg created_at "$BACKUP_CREATED_AT" \
  --arg recipient_fingerprint "$RECIPIENT_FINGERPRINT" \
  --arg object_backup_mode "$OBJECT_BACKUP_MODE" \
  --arg object_base_backup_id "$OBJECT_BASE_BACKUP_ID" \
  --argjson archive_bytes "$ARCHIVE_BYTES" \
  --argjson database_bytes "$DATABASE_BYTES" \
  --argjson object_count "$OBJECT_COUNT" \
  --argjson object_bytes "$OBJECT_BYTES" \
  --argjson object_payload_count "$OBJECT_PAYLOAD_COUNT" \
  --argjson object_payload_bytes "$OBJECT_PAYLOAD_BYTES" \
  --argjson object_deleted_count "$OBJECT_DELETED_COUNT" \
  --argjson duration_seconds "$DURATION_SECONDS" '
  {
    status: "ok",
    version: 2,
    backup_id: $backup_id,
    kind: $kind,
    created_at: $created_at,
    encryption: "openpgp",
    recipient_fingerprint: $recipient_fingerprint,
    archive_bytes: $archive_bytes,
    database_bytes: $database_bytes,
    object_backup_mode: $object_backup_mode,
    object_base_backup_id: (
      if $object_base_backup_id == "" then null else $object_base_backup_id end
    ),
    object_count: $object_count,
    object_bytes: $object_bytes,
    object_payload_count: $object_payload_count,
    object_payload_bytes: $object_payload_bytes,
    object_deleted_count: $object_deleted_count,
    duration_seconds: $duration_seconds
  }
' >"$PARTIAL_METADATA"

if [[ "$BACKUP_KIND" == "weekly" ]]; then
  install -m 0600 "$OBJECT_MANIFEST" "$PARTIAL_BASE_STATE"
fi
mv -- "$PARTIAL_ARCHIVE" "$FINAL_ARCHIVE"
mv -- "$PARTIAL_CHECKSUM" "$FINAL_CHECKSUM"
mv -- "$PARTIAL_METADATA" "$FINAL_METADATA"
if [[ "$BACKUP_KIND" == "weekly" ]]; then
  mv -- "$PARTIAL_BASE_STATE" "$WEEKLY_BASE_STATE"
fi
jq -c . "$FINAL_METADATA"
