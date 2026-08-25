#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

[[ "${ROLLBACK_APPROVAL:-NO}" == "YES" ]] || release_die "ROLLBACK_APPROVAL_REQUIRED"
[[ "${ROLLBACK_RESTORE_BACKUP:-NO}" == "NO" ]] ||
  release_die "PRODUCTION_BACKUP_RESTORE_FORBIDDEN"
: "${RELEASE_STATE_DIR:?RELEASE_STATE_DIR is required}"
: "${ROLLBACK_MANIFEST:?ROLLBACK_MANIFEST is required}"
require_safe_directory "$RELEASE_STATE_DIR" "INVALID_RELEASE_STATE_DIR"
require_regular_file "$ROLLBACK_MANIFEST" "INVALID_ROLLBACK_MANIFEST"
for command_name in date docker flock jq realpath; do
  require_command "$command_name"
done
configure_release_compose

exec 9>"$RELEASE_STATE_DIR/.release.lock"
flock -n 9 || release_die "RELEASE_ALREADY_RUNNING"
jq -e '.version == 1 and .status == "deployed"' "$ROLLBACK_MANIFEST" >/dev/null ||
  release_die "ROLLBACK_MANIFEST_NOT_DEPLOYED"
MANIFEST_PROJECT=$(jq -er '.compose_project | strings' "$ROLLBACK_MANIFEST")
[[ "$MANIFEST_PROJECT" == "$COMPOSE_PROJECT" ]] ||
  release_die "ROLLBACK_PROJECT_MISMATCH"
RELEASE_ID=$(jq -er '.release_id | strings' "$ROLLBACK_MANIFEST")
PREVIOUS_BACKEND_IMAGE=$(jq -er '.previous_images.backend | strings' "$ROLLBACK_MANIFEST")
PREVIOUS_FRONTEND_IMAGE=$(jq -er '.previous_images.frontend | strings' "$ROLLBACK_MANIFEST")
[[ "$PREVIOUS_BACKEND_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  release_die "PREVIOUS_BACKEND_IMAGE_INVALID"
[[ "$PREVIOUS_FRONTEND_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  release_die "PREVIOUS_FRONTEND_IMAGE_INVALID"
docker image inspect "$PREVIOUS_BACKEND_IMAGE" "$PREVIOUS_FRONTEND_IMAGE" >/dev/null 2>&1 ||
  release_die "PREVIOUS_IMAGE_NOT_AVAILABLE"

MIGRATION_CHANGED=$(jq -r '.migration_changed // false' "$ROLLBACK_MANIFEST")
if [[ "$MIGRATION_CHANGED" == "true" && "${ROLLBACK_SCHEMA_COMPATIBLE:-NO}" != "YES" ]]; then
  release_die "SCHEMA_COMPATIBILITY_CONFIRMATION_REQUIRED"
fi

compose_previous() {
  BACKEND_IMAGE="$PREVIOUS_BACKEND_IMAGE"   FRONTEND_IMAGE="$PREVIOUS_FRONTEND_IMAGE"     docker compose "${COMPOSE_ARGUMENTS[@]}" "$@"
}

compose_previous up --detach --no-deps --force-recreate backend worker >/dev/null 2>&1 ||
  release_die "BACKEND_WORKER_ROLLBACK_FAILED"
wait_for_services "${RELEASE_HEALTH_TIMEOUT_SECONDS:-300}" backend worker ||
  release_die "BACKEND_WORKER_ROLLBACK_HEALTH_TIMEOUT"
compose_previous up --detach --no-deps --force-recreate frontend nginx >/dev/null 2>&1 ||
  release_die "FRONTEND_NGINX_ROLLBACK_FAILED"
wait_for_services "${RELEASE_HEALTH_TIMEOUT_SECONDS:-300}" frontend nginx ||
  release_die "FRONTEND_NGINX_ROLLBACK_HEALTH_TIMEOUT"
release_https_smoke

ROLLBACK_OVERRIDE="$RELEASE_STATE_DIR/$RELEASE_ID.rollback-images.env"
[[ ! -e "$ROLLBACK_OVERRIDE" ]] || release_die "ROLLBACK_OVERRIDE_ALREADY_EXISTS"
printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\n'   "$PREVIOUS_BACKEND_IMAGE" "$PREVIOUS_FRONTEND_IMAGE" >"$ROLLBACK_OVERRIDE"
chmod 0600 "$ROLLBACK_OVERRIDE"

ROLLBACK_TEMP=$(mktemp "$RELEASE_STATE_DIR/.rollback-state.XXXXXX")
trap 'rm -f -- "$ROLLBACK_TEMP"' EXIT
jq --arg rolled_back_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"   '.status = "rolled_back"
   | .rolled_back_at = $rolled_back_at
   | .database_restore_performed = false'   "$ROLLBACK_MANIFEST" >"$ROLLBACK_TEMP"
mv -- "$ROLLBACK_TEMP" "$ROLLBACK_MANIFEST"
trap - EXIT

jq -nc   --arg release_id "$RELEASE_ID"   --argjson migration_changed "$MIGRATION_CHANGED"   '{
    status:"ok",
    release_id:$release_id,
    images:"rolled_back",
    migration_changed:$migration_changed,
    database_restore_performed:false,
    https_smoke:"ok"
  }'
