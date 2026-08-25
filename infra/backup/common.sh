#!/usr/bin/env bash
set -Eeuo pipefail

backup_die() {
  printf '{"status":"error","code":"%s"}\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || backup_die "MISSING_COMMAND_$1"
}

require_regular_file() {
  local candidate=$1
  local code=$2
  [[ "$candidate" == /* ]] || backup_die "$code"
  [[ -f "$candidate" && ! -L "$candidate" ]] || backup_die "$code"
}

require_safe_directory() {
  local candidate=$1
  local code=$2
  require_command realpath
  [[ "$candidate" == /* ]] || backup_die "$code"
  [[ -d "$candidate" && ! -L "$candidate" ]] || backup_die "$code"
  local resolved
  resolved=$(realpath -e -- "$candidate")
  [[ "$resolved" != "/" ]] || backup_die "$code"
}

configure_compose() {
  : "${COMPOSE_ENV_FILE:?COMPOSE_ENV_FILE is required}"
  : "${COMPOSE_FILE:?COMPOSE_FILE is required}"
  require_regular_file "$COMPOSE_ENV_FILE" "INVALID_COMPOSE_ENV_FILE"
  require_regular_file "$COMPOSE_FILE" "INVALID_COMPOSE_FILE"
  require_command docker
  require_command jq
  COMPOSE_ARGUMENTS=(
    --env-file "$COMPOSE_ENV_FILE"
    --file "$COMPOSE_FILE"
  )
  docker compose "${COMPOSE_ARGUMENTS[@]}" config --quiet
  COMPOSE_PROJECT=$(
    docker compose "${COMPOSE_ARGUMENTS[@]}" config --format json |
      jq -er '.name | select(type == "string" and length > 0)'
  )
}

compose_run() {
  docker compose "${COMPOSE_ARGUMENTS[@]}" "$@"
}
