#!/usr/bin/env bash
set -Eeuo pipefail

release_die() {
  printf '{"status":"error","code":"%s"}\n' "$1" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || release_die "MISSING_COMMAND_$1"
}

require_regular_file() {
  local candidate=$1
  local code=$2
  [[ "$candidate" == /* && -f "$candidate" && ! -L "$candidate" ]] ||
    release_die "$code"
}

require_safe_directory() {
  local candidate=$1
  local code=$2
  require_command realpath
  [[ "$candidate" == /* && -d "$candidate" && ! -L "$candidate" ]] ||
    release_die "$code"
  [[ "$(realpath -e -- "$candidate")" != "/" ]] || release_die "$code"
}

configure_release_compose() {
  : "${COMPOSE_ENV_FILE:?COMPOSE_ENV_FILE is required}"
  : "${COMPOSE_FILE:?COMPOSE_FILE is required}"
  require_regular_file "$COMPOSE_ENV_FILE" "INVALID_COMPOSE_ENV_FILE"
  require_regular_file "$COMPOSE_FILE" "INVALID_COMPOSE_FILE"
  require_command docker
  require_command jq
  COMPOSE_ARGUMENTS=(--env-file "$COMPOSE_ENV_FILE" --file "$COMPOSE_FILE")
  docker compose "${COMPOSE_ARGUMENTS[@]}" config --quiet >/dev/null 2>&1 ||
    release_die "INVALID_COMPOSE_CONFIG"
  COMPOSE_PROJECT=$(
    docker compose "${COMPOSE_ARGUMENTS[@]}" config --format json |
      jq -er '.name | select(type == "string" and length > 0)'
  ) || release_die "INVALID_COMPOSE_PROJECT"
}

compose_release() {
  docker compose "${COMPOSE_ARGUMENTS[@]}" "$@"
}

validate_image_reference() {
  local reference=$1
  [[ -n "$reference" ]] || release_die "IMAGE_REFERENCE_EMPTY"
  [[ "$reference" != *replace-with* && "$reference" != *:latest ]] ||
    release_die "IMAGE_REFERENCE_NOT_FIXED"
  if [[ "$reference" == *@sha256:* ]]; then
    [[ "$reference" =~ @sha256:[0-9a-f]{64}$ ]] ||
      release_die "IMAGE_DIGEST_INVALID"
  else
    [[ "$reference" =~ :[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
      release_die "IMAGE_TAG_REQUIRED"
  fi
}

validate_all_images() {
  local compose_json
  compose_json=$(compose_release config --format json)
  jq -e '
    (.services | type == "object")
    and ([.services[] | has("build")] | all(. == false))
    and ([.services[] | .image | strings | length > 0] | all)
  ' <<<"$compose_json" >/dev/null || release_die "PRODUCTION_BUILD_OR_IMAGE_INVALID"
  while IFS= read -r image_reference; do
    validate_image_reference "$image_reference"
  done < <(jq -r '.services[].image' <<<"$compose_json" | LC_ALL=C sort -u)
}

load_latest_backup() {
  : "${BACKUP_OUTPUT_DIR:?BACKUP_OUTPUT_DIR is required}"
  require_safe_directory "$BACKUP_OUTPUT_DIR" "INVALID_BACKUP_OUTPUT_DIR"
  require_command date
  require_command sha256sum
  LATEST_BACKUP_EPOCH=0
  LATEST_BACKUP_METADATA=
  while IFS= read -r -d '' metadata_file; do
    local_created_at=$(jq -er '.created_at | strings' "$metadata_file" 2>/dev/null || true)
    [[ -n "$local_created_at" ]] || continue
    local_epoch=$(date -u -d "$local_created_at" +%s 2>/dev/null || true)
    [[ "$local_epoch" =~ ^[0-9]+$ ]] || continue
    if (( local_epoch > LATEST_BACKUP_EPOCH )); then
      LATEST_BACKUP_EPOCH=$local_epoch
      LATEST_BACKUP_METADATA=$metadata_file
    fi
  done < <(find "$BACKUP_OUTPUT_DIR" -maxdepth 1 -type f -name 'pnx-backup-*.meta.json' -print0)
  [[ -n "$LATEST_BACKUP_METADATA" ]] || release_die "BACKUP_MISSING"

  LATEST_BACKUP_ID=$(jq -er '.backup_id | strings | select(test("^pnx-backup-[0-9]{8}T[0-9]{6}Z-(daily|weekly)$"))' "$LATEST_BACKUP_METADATA") ||
    release_die "BACKUP_METADATA_INVALID"
  LATEST_BACKUP_ARCHIVE="$BACKUP_OUTPUT_DIR/$LATEST_BACKUP_ID.tar.gpg"
  LATEST_BACKUP_CHECKSUM="$LATEST_BACKUP_ARCHIVE.sha256"
  require_regular_file "$LATEST_BACKUP_ARCHIVE" "BACKUP_ARCHIVE_MISSING"
  require_regular_file "$LATEST_BACKUP_CHECKSUM" "BACKUP_CHECKSUM_MISSING"
  (
    cd -- "$BACKUP_OUTPUT_DIR"
    sha256sum --check --status "$(basename -- "$LATEST_BACKUP_CHECKSUM")"
  ) || release_die "BACKUP_CHECKSUM_INVALID"

  BACKUP_AGE_SECONDS=$(($(date -u +%s) - LATEST_BACKUP_EPOCH))
  (( BACKUP_AGE_SECONDS < 0 )) && BACKUP_AGE_SECONDS=0
  RELEASE_MAX_BACKUP_AGE_SECONDS=${RELEASE_MAX_BACKUP_AGE_SECONDS:-86400}
  [[ "$RELEASE_MAX_BACKUP_AGE_SECONDS" =~ ^[1-9][0-9]*$ ]] ||
    release_die "INVALID_BACKUP_AGE_LIMIT"
  (( BACKUP_AGE_SECONDS <= RELEASE_MAX_BACKUP_AGE_SECONDS )) ||
    release_die "BACKUP_TOO_OLD"
}

container_health() {
  local service=$1
  local row
  row=$(compose_release ps --format json "$service" 2>/dev/null | jq -sc '
    map(if type == "array" then .[] else . end) | first // {}
  ')
  jq -e '
    .State == "running"
    and ((.Health // "") == "healthy" or (.Health // "") == "")
  ' <<<"$row" >/dev/null
}

wait_for_services() {
  local timeout_seconds=$1
  shift
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    local all_healthy=YES
    local service
    for service in "$@"; do
      if ! container_health "$service"; then
        all_healthy=NO
        break
      fi
    done
    [[ "$all_healthy" == "YES" ]] && return 0
    sleep 5
  done
  return 1
}

configure_release_curl() {
  : "${RELEASE_HTTPS_URL:?RELEASE_HTTPS_URL is required}"
  [[ "$RELEASE_HTTPS_URL" == https://* && "$RELEASE_HTTPS_URL" != *[[:space:]]* ]] ||
    release_die "INVALID_RELEASE_HTTPS_URL"
  RELEASE_CURL_ARGUMENTS=(--silent --show-error --fail --max-time 15)
  if [[ -n "${RELEASE_CA_CERT_FILE:-}" ]]; then
    require_regular_file "$RELEASE_CA_CERT_FILE" "INVALID_CA_CERTIFICATE_FILE"
    RELEASE_CURL_ARGUMENTS+=(--cacert "$RELEASE_CA_CERT_FILE")
  fi
  if [[ -n "${RELEASE_RESOLVE:-}" ]]; then
    [[ "$RELEASE_RESOLVE" != *[[:space:]]* ]] || release_die "INVALID_RELEASE_RESOLVE"
    RELEASE_CURL_ARGUMENTS+=(--resolve "$RELEASE_RESOLVE")
  fi
}

release_https_smoke() {
  configure_release_curl
  local path
  for path in /login /health/live /health/ready /health/worker; do
    curl "${RELEASE_CURL_ARGUMENTS[@]}" --output /dev/null       "${RELEASE_HTTPS_URL%/}$path" 2>/dev/null ||
      release_die "HTTPS_SMOKE_FAILED"
  done
}
