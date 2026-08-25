#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

: "${RESTORE_ARTIFACT:?RESTORE_ARTIFACT is required}"
: "${RESTORE_CONFIRM_PROJECT:?RESTORE_CONFIRM_PROJECT is required}"
RESTORE_WORK_ROOT=${RESTORE_WORK_ROOT:-/tmp}

require_regular_file "$RESTORE_ARTIFACT" "INVALID_RESTORE_ARTIFACT"
require_regular_file "$RESTORE_ARTIFACT.sha256" "RESTORE_CHECKSUM_MISSING"
require_safe_directory "$RESTORE_WORK_ROOT" "INVALID_RESTORE_WORK_ROOT"
ARTIFACT_DIRECTORY=$(dirname -- "$RESTORE_ARTIFACT")
require_safe_directory "$ARTIFACT_DIRECTORY" "INVALID_RESTORE_ARTIFACT_DIRECTORY"
for command_name in docker jq gpg tar sha256sum awk realpath date install; do
  require_command "$command_name"
done
configure_compose
[[ "$COMPOSE_PROJECT" == "$RESTORE_CONFIRM_PROJECT" ]] ||
  backup_die "RESTORE_PROJECT_CONFIRMATION_MISMATCH"
[[ "$COMPOSE_PROJECT" =~ ^pnx-restore-[a-z0-9][a-z0-9_-]*$ ]] ||
  backup_die "UNSAFE_RESTORE_PROJECT"

RESTORE_STARTED_EPOCH=$(date +%s)
STAGING_DIRECTORY=$(mktemp -d "$RESTORE_WORK_ROOT/pnx-restore.XXXXXX")
cleanup_restore() {
  rm -rf -- "$STAGING_DIRECTORY"
}
trap cleanup_restore EXIT

extract_backup_artifact() {
  local artifact=$1
  local destination=$2
  local error_prefix=$3
  require_regular_file "$artifact" "${error_prefix}_ARTIFACT_MISSING"
  require_regular_file "$artifact.sha256" "${error_prefix}_CHECKSUM_MISSING"
  local artifact_directory
  local artifact_name
  artifact_directory=$(dirname -- "$artifact")
  artifact_name=$(basename -- "$artifact")
  (
    cd -- "$artifact_directory"
    sha256sum --check --status "$artifact_name.sha256"
  ) || backup_die "${error_prefix}_CHECKSUM_FAILED"

  install -d -m 0700 "$destination"
  gpg --batch --yes --output "$destination/backup.tar" \
    --decrypt "$artifact" >/dev/null 2>&1 ||
    backup_die "${error_prefix}_DECRYPTION_FAILED"
  tar -tf "$destination/backup.tar" |
    awk '
      /^\// { bad = 1 }
      /(^|\/)\.\.($|\/)/ { bad = 1 }
      END { exit bad }
    ' || backup_die "${error_prefix}_ARCHIVE_UNSAFE"
  install -d -m 0700 "$destination/extracted"
  tar -C "$destination/extracted" -xf "$destination/backup.tar"
  require_regular_file \
    "$destination/extracted/MANIFEST.json" \
    "${error_prefix}_MANIFEST_MISSING"
  require_regular_file \
    "$destination/extracted/SHA256SUMS" \
    "${error_prefix}_CONTENT_CHECKSUM_MANIFEST_MISSING"
  (
    cd -- "$destination/extracted"
    sha256sum --check --status SHA256SUMS
  ) || backup_die "${error_prefix}_CONTENT_CHECKSUM_FAILED"
}

extract_backup_artifact "$RESTORE_ARTIFACT" "$STAGING_DIRECTORY/target" RESTORE
PLAIN_DIRECTORY="$STAGING_DIRECTORY/target/extracted"
TARGET_MANIFEST="$PLAIN_DIRECTORY/MANIFEST.json"
BACKUP_ID=$(jq -er '.backup_id | strings | select(length > 0)' "$TARGET_MANIFEST")
BACKUP_CREATED_AT=$(jq -er '.created_at | strings | select(length > 0)' "$TARGET_MANIFEST")
OBJECT_BACKUP_MODE=$(jq -er '.object_backup_mode // "full"' "$TARGET_MANIFEST")
OBJECT_BASE_BACKUP_ID=$(jq -r '.object_base_backup_id // empty' "$TARGET_MANIFEST")
[[ "$OBJECT_BACKUP_MODE" == "full" || "$OBJECT_BACKUP_MODE" == "incremental" ]] ||
  backup_die "RESTORE_OBJECT_BACKUP_MODE_INVALID"

BASE_PLAIN_DIRECTORY=
if [[ "$OBJECT_BACKUP_MODE" == "incremental" ]]; then
  [[ "$OBJECT_BASE_BACKUP_ID" =~ ^pnx-backup-[0-9]{8}T[0-9]{6}Z-weekly$ ]] ||
    backup_die "RESTORE_INCREMENTAL_BASE_ID_INVALID"
  BASE_ARTIFACT="$ARTIFACT_DIRECTORY/$OBJECT_BASE_BACKUP_ID.tar.gpg"
  extract_backup_artifact \
    "$BASE_ARTIFACT" \
    "$STAGING_DIRECTORY/base" \
    RESTORE_BASE
  BASE_PLAIN_DIRECTORY="$STAGING_DIRECTORY/base/extracted"
  jq -e --arg backup_id "$OBJECT_BASE_BACKUP_ID" '
    .backup_id == $backup_id
    and .kind == "weekly"
    and .object_backup_mode == "full"
    and .object_base_backup_id == null
  ' "$BASE_PLAIN_DIRECTORY/MANIFEST.json" >/dev/null ||
    backup_die "RESTORE_INCREMENTAL_BASE_MANIFEST_INVALID"
else
  [[ -z "$OBJECT_BASE_BACKUP_ID" ]] ||
    backup_die "RESTORE_FULL_BACKUP_HAS_BASE"
fi

compose_run up --detach --wait --wait-timeout 180 postgres minio
TABLE_COUNT=$(
  compose_run exec -T postgres sh -ceu \
    'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only --no-align --command "SELECT count(*) FROM pg_tables WHERE schemaname = '\''public'\'';"'
)
[[ "$TABLE_COUNT" == "0" ]] || backup_die "RESTORE_DATABASE_NOT_EMPTY"

compose_run exec -T postgres sh -ceu \
  'pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-owner --no-acl --exit-on-error' \
  <"$PLAIN_DIRECTORY/database/database.dump"

HOST_UID=$(id -u)
HOST_GID=$(id -g)
if [[ "$OBJECT_BACKUP_MODE" == "full" ]]; then
  compose_run run --rm --no-deps -T \
    --user "$HOST_UID:$HOST_GID" \
    --volume "$PLAIN_DIRECTORY/objects:/operations:ro" \
    backend \
    python -m app.cli import-objects \
    --input /operations/export \
    --require-empty-bucket \
    >"$STAGING_DIRECTORY/import-summary.json"
else
  compose_run run --rm --no-deps -T \
    --user "$HOST_UID:$HOST_GID" \
    --volume "$BASE_PLAIN_DIRECTORY/objects:/operations:ro" \
    backend \
    python -m app.cli import-objects \
    --input /operations/export \
    --require-empty-bucket \
    >"$STAGING_DIRECTORY/base-import-summary.json"
  compose_run run --rm --no-deps -T \
    --user "$HOST_UID:$HOST_GID" \
    --volume "$PLAIN_DIRECTORY/objects:/incremental:ro" \
    --volume "$BASE_PLAIN_DIRECTORY/objects:/base:ro" \
    backend \
    python -m app.cli import-objects \
    --input /incremental/export \
    --base-manifest /base/export/manifest.json \
    --apply-incremental \
    >"$STAGING_DIRECTORY/import-summary.json"
fi

compose_run run --rm --no-deps -T backend alembic current \
  >"$STAGING_DIRECTORY/alembic-current.txt"
EXPECTED_HEAD=$(jq -er '.alembic_head' "$TARGET_MANIFEST")
grep -Fqx "$EXPECTED_HEAD" "$STAGING_DIRECTORY/alembic-current.txt" ||
  backup_die "RESTORED_ALEMBIC_HEAD_MISMATCH"

compose_run run --rm --no-deps -T backend \
  python -m app.cli reconcile-storage \
  >"$STAGING_DIRECTORY/reconciliation.json"
jq -e '.status == "ok"' "$STAGING_DIRECTORY/reconciliation.json" >/dev/null ||
  backup_die "RESTORED_STORAGE_INCONSISTENT"

RESTORE_DURATION_SECONDS=$(( $(date +%s) - RESTORE_STARTED_EPOCH ))
BACKUP_EPOCH=$(date -d "$BACKUP_CREATED_AT" +%s)
RPO_SECONDS=$(( RESTORE_STARTED_EPOCH - BACKUP_EPOCH ))
(( RPO_SECONDS >= 0 )) || RPO_SECONDS=0
jq -n \
  --arg backup_id "$BACKUP_ID" \
  --arg target_project "$COMPOSE_PROJECT" \
  --arg backup_created_at "$BACKUP_CREATED_AT" \
  --arg object_backup_mode "$OBJECT_BACKUP_MODE" \
  --arg object_base_backup_id "$OBJECT_BASE_BACKUP_ID" \
  --argjson rpo_seconds "$RPO_SECONDS" \
  --argjson rto_seconds "$RESTORE_DURATION_SECONDS" \
  --argjson object_count "$(jq -er '.object_count' "$STAGING_DIRECTORY/import-summary.json")" '
  {
    status: "ok",
    backup_id: $backup_id,
    target_project: $target_project,
    backup_created_at: $backup_created_at,
    object_backup_mode: $object_backup_mode,
    object_base_backup_id: (
      if $object_base_backup_id == "" then null else $object_base_backup_id end
    ),
    rpo_seconds: $rpo_seconds,
    rto_seconds: $rto_seconds,
    object_count: $object_count
  }
'
