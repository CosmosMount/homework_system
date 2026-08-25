#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

: "${BACKUP_OUTPUT_DIR:?BACKUP_OUTPUT_DIR is required}"
DAILY_KEEP=${DAILY_KEEP:-14}
WEEKLY_KEEP=${WEEKLY_KEEP:-8}
RETENTION_APPLY=${RETENTION_APPLY:-NO}

for command_name in find jq realpath; do
  require_command "$command_name"
done
require_safe_directory "$BACKUP_OUTPUT_DIR" "INVALID_BACKUP_OUTPUT_DIR"
[[ "$DAILY_KEEP" =~ ^[0-9]+$ && "$WEEKLY_KEEP" =~ ^[0-9]+$ ]] ||
  backup_die "INVALID_RETENTION_COUNT"
[[ "$RETENTION_APPLY" == "NO" || "$RETENTION_APPLY" == "YES" ]] ||
  backup_die "INVALID_RETENTION_MODE"

mapfile -t DAILY_FILES < <(
  find "$BACKUP_OUTPUT_DIR" -maxdepth 1 -type f \
    -name 'pnx-backup-????????T??????Z-daily.tar.gpg' -printf '%f\n' |
    LC_ALL=C sort -r
)
mapfile -t WEEKLY_FILES < <(
  find "$BACKUP_OUTPUT_DIR" -maxdepth 1 -type f \
    -name 'pnx-backup-????????T??????Z-weekly.tar.gpg' -printf '%f\n' |
    LC_ALL=C sort -r
)

declare -A PROTECTED_WEEKLY_BASES=()
RETAINED_DAILY_COUNT=$DAILY_KEEP
(( RETAINED_DAILY_COUNT > ${#DAILY_FILES[@]} )) &&
  RETAINED_DAILY_COUNT=${#DAILY_FILES[@]}
for (( index=0; index<RETAINED_DAILY_COUNT; index++ )); do
  daily_name=${DAILY_FILES[$index]%.tar.gpg}
  daily_metadata="$BACKUP_OUTPUT_DIR/$daily_name.meta.json"
  require_regular_file "$daily_metadata" "RETENTION_DAILY_METADATA_MISSING"
  jq -e . "$daily_metadata" >/dev/null || backup_die "RETENTION_DAILY_METADATA_INVALID"
  base_backup_id=$(jq -r '.object_base_backup_id // empty' "$daily_metadata")
  if [[ -n "$base_backup_id" ]]; then
    [[ "$base_backup_id" =~ ^pnx-backup-[0-9]{8}T[0-9]{6}Z-weekly$ ]] ||
      backup_die "RETENTION_BASE_BACKUP_ID_INVALID"
    PROTECTED_WEEKLY_BASES["$base_backup_id"]=1
  fi
done

REMOVED_COUNT=0
PROTECTED_WEEKLY_COUNT=0
remove_backup_set() {
  local file_name=$1
  [[ "$file_name" =~ ^pnx-backup-[0-9]{8}T[0-9]{6}Z-(daily|weekly)\.tar\.gpg$ ]] ||
    backup_die "UNSAFE_RETENTION_FILENAME"
  local archive="$BACKUP_OUTPUT_DIR/$file_name"
  local checksum="$archive.sha256"
  local metadata="$BACKUP_OUTPUT_DIR/${file_name%.tar.gpg}.meta.json"
  [[ -f "$archive" && ! -L "$archive" ]] || backup_die "UNSAFE_RETENTION_TARGET"
  if [[ "$RETENTION_APPLY" == "YES" ]]; then
    rm -- "$archive"
    [[ ! -e "$checksum" ]] || rm -- "$checksum"
    [[ ! -e "$metadata" ]] || rm -- "$metadata"
  fi
  REMOVED_COUNT=$((REMOVED_COUNT + 1))
}

for (( index=DAILY_KEEP; index<${#DAILY_FILES[@]}; index++ )); do
  remove_backup_set "${DAILY_FILES[$index]}"
done
for (( index=WEEKLY_KEEP; index<${#WEEKLY_FILES[@]}; index++ )); do
  weekly_name=${WEEKLY_FILES[$index]%.tar.gpg}
  if [[ -n "${PROTECTED_WEEKLY_BASES[$weekly_name]:-}" ]]; then
    PROTECTED_WEEKLY_COUNT=$((PROTECTED_WEEKLY_COUNT + 1))
    continue
  fi
  remove_backup_set "${WEEKLY_FILES[$index]}"
done

jq -n \
  --arg mode "$RETENTION_APPLY" \
  --argjson daily_seen "${#DAILY_FILES[@]}" \
  --argjson weekly_seen "${#WEEKLY_FILES[@]}" \
  --argjson selected_count "$REMOVED_COUNT" \
  --argjson protected_weekly_count "$PROTECTED_WEEKLY_COUNT" '
  {
    status: "ok",
    mode: (if $mode == "YES" then "apply" else "dry-run" end),
    daily_seen: $daily_seen,
    weekly_seen: $weekly_seen,
    selected_count: $selected_count,
    protected_weekly_count: $protected_weekly_count
  }
'
