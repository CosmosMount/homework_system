#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$SCRIPT_DIRECTORY/common.sh"

[[ "${RELEASE_APPROVAL:-NO}" == "YES" ]] || release_die "RELEASE_APPROVAL_REQUIRED"
RELEASE_PULL=${RELEASE_PULL:-YES}
[[ "$RELEASE_PULL" == "YES" || "$RELEASE_PULL" == "NO" ]] ||
  release_die "INVALID_RELEASE_PULL_MODE"
: "${RELEASE_STATE_DIR:?RELEASE_STATE_DIR is required}"
require_safe_directory "$RELEASE_STATE_DIR" "INVALID_RELEASE_STATE_DIR"
for command_name in date docker flock jq realpath; do
  require_command "$command_name"
done

configure_release_compose
exec 9>"$RELEASE_STATE_DIR/.release.lock"
flock -n 9 || release_die "RELEASE_ALREADY_RUNNING"

STATE_FILE=
STATE_TEMP=
release_cleanup() {
  local exit_code=$?
  if [[ -n "$STATE_TEMP" && -e "$STATE_TEMP" ]]; then
    rm -f -- "$STATE_TEMP"
  fi
  if (( exit_code != 0 )) && [[ -n "$STATE_FILE" && -f "$STATE_FILE" ]]; then
    local failed_temp
    failed_temp=$(mktemp "$RELEASE_STATE_DIR/.release-failed.XXXXXX")
    jq --arg failed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"       '.status = "failed" | .failed_at = $failed_at'       "$STATE_FILE" >"$failed_temp" 2>/dev/null || true
    if [[ -s "$failed_temp" ]]; then
      mv -- "$failed_temp" "$STATE_FILE"
    else
      rm -f -- "$failed_temp"
    fi
  fi
  return "$exit_code"
}
trap release_cleanup EXIT

"$SCRIPT_DIRECTORY/preflight.sh" >/dev/null
load_latest_backup

BACKEND_CONTAINER=$(compose_release ps -q backend)
FRONTEND_CONTAINER=$(compose_release ps -q frontend)
[[ -n "$BACKEND_CONTAINER" && -n "$FRONTEND_CONTAINER" ]] ||
  release_die "CURRENT_RELEASE_CONTAINERS_MISSING"
PREVIOUS_BACKEND_IMAGE=$(docker inspect --format '{{.Image}}' "$BACKEND_CONTAINER")
PREVIOUS_FRONTEND_IMAGE=$(docker inspect --format '{{.Image}}' "$FRONTEND_CONTAINER")
[[ "$PREVIOUS_BACKEND_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  release_die "PREVIOUS_BACKEND_IMAGE_INVALID"
[[ "$PREVIOUS_FRONTEND_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  release_die "PREVIOUS_FRONTEND_IMAGE_INVALID"

COMPOSE_JSON=$(compose_release config --format json)
TARGET_BACKEND_IMAGE=$(jq -er '.services.backend.image | strings' <<<"$COMPOSE_JSON")
TARGET_FRONTEND_IMAGE=$(jq -er '.services.frontend.image | strings' <<<"$COMPOSE_JSON")
SCHEMA_BEFORE=$(
  compose_release exec -T backend alembic current 2>/dev/null |
    awk 'NF {print $1; exit}'
)
[[ "$SCHEMA_BEFORE" =~ ^[0-9A-Za-z_]+$ ]] || release_die "SCHEMA_BEFORE_UNKNOWN"

RELEASE_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RELEASE_ID="pnx-release-$(date -u +%Y%m%dT%H%M%SZ)"
STATE_FILE="$RELEASE_STATE_DIR/$RELEASE_ID.json"
[[ ! -e "$STATE_FILE" ]] || release_die "RELEASE_ID_COLLISION"
STATE_TEMP=$(mktemp "$RELEASE_STATE_DIR/.release-state.XXXXXX")
jq -n   --arg release_id "$RELEASE_ID"   --arg project "$COMPOSE_PROJECT"   --arg started_at "$RELEASE_STARTED_AT"   --arg backup_id "$LATEST_BACKUP_ID"   --arg schema_before "$SCHEMA_BEFORE"   --arg previous_backend "$PREVIOUS_BACKEND_IMAGE"   --arg previous_frontend "$PREVIOUS_FRONTEND_IMAGE"   --arg target_backend "$TARGET_BACKEND_IMAGE"   --arg target_frontend "$TARGET_FRONTEND_IMAGE"   '{
    version:1,
    release_id:$release_id,
    compose_project:$project,
    status:"started",
    started_at:$started_at,
    backup_id:$backup_id,
    schema_before:$schema_before,
    previous_images:{backend:$previous_backend,frontend:$previous_frontend},
    target_images:{backend:$target_backend,frontend:$target_frontend}
  }' >"$STATE_TEMP"
mv -- "$STATE_TEMP" "$STATE_FILE"
STATE_TEMP=

if [[ "$RELEASE_PULL" == "YES" ]]; then
  compose_release pull migrate backend worker frontend >/dev/null 2>&1 ||
    release_die "IMAGE_PULL_FAILED"
fi
compose_release run --rm --no-deps -T migrate >/dev/null 2>&1 ||
  release_die "MIGRATION_FAILED"
SCHEMA_AFTER=$(
  compose_release run --rm --no-deps -T migrate alembic current 2>/dev/null |
    awk 'NF {print $1; exit}'
)
[[ "$SCHEMA_AFTER" =~ ^[0-9A-Za-z_]+$ ]] || release_die "SCHEMA_AFTER_UNKNOWN"

compose_release up --detach --no-deps --force-recreate backend worker >/dev/null 2>&1 ||
  release_die "BACKEND_WORKER_UPDATE_FAILED"
wait_for_services "${RELEASE_HEALTH_TIMEOUT_SECONDS:-300}" backend worker ||
  release_die "BACKEND_WORKER_HEALTH_TIMEOUT"
compose_release up --detach --no-deps --force-recreate frontend nginx >/dev/null 2>&1 ||
  release_die "FRONTEND_NGINX_UPDATE_FAILED"
wait_for_services "${RELEASE_HEALTH_TIMEOUT_SECONDS:-300}" frontend nginx ||
  release_die "FRONTEND_NGINX_HEALTH_TIMEOUT"
release_https_smoke

STATE_TEMP=$(mktemp "$RELEASE_STATE_DIR/.release-state.XXXXXX")
jq   --arg completed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"   --arg schema_after "$SCHEMA_AFTER"   '.status = "deployed"
   | .completed_at = $completed_at
   | .schema_after = $schema_after
   | .migration_changed = (.schema_before != $schema_after)'   "$STATE_FILE" >"$STATE_TEMP"
mv -- "$STATE_TEMP" "$STATE_FILE"
STATE_TEMP=

jq -nc   --arg release_id "$RELEASE_ID"   --arg schema_before "$SCHEMA_BEFORE"   --arg schema_after "$SCHEMA_AFTER"   --argjson migration_changed "$([[ "$SCHEMA_BEFORE" != "$SCHEMA_AFTER" ]] && printf true || printf false)"   '{
    status:"ok",
    release_id:$release_id,
    schema_before:$schema_before,
    schema_after:$schema_after,
    migration_changed:$migration_changed,
    https_smoke:"ok"
  }'
