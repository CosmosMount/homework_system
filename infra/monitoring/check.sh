#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

operations_die() {
  printf '{"status":"error","code":"%s"}\n' "$1" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || operations_die "MISSING_COMMAND_$1"
}

require_regular_file() {
  local candidate=$1
  local code=$2
  [[ "$candidate" == /* && -f "$candidate" ]] || operations_die "$code"
}

require_directory() {
  local candidate=$1
  local code=$2
  [[ "$candidate" == /* && -d "$candidate" ]] || operations_die "$code"
  [[ "$(realpath -e -- "$candidate")" != "/" ]] || operations_die "$code"
}

for command_name in awk curl date df docker find jq openssl realpath; do
  require_command "$command_name"
done

: "${COMPOSE_ENV_FILE:?COMPOSE_ENV_FILE is required}"
: "${COMPOSE_FILE:?COMPOSE_FILE is required}"
: "${OPERATIONS_HTTPS_URL:?OPERATIONS_HTTPS_URL is required}"
: "${OPERATIONS_TLS_CERTIFICATE_FILE:?OPERATIONS_TLS_CERTIFICATE_FILE is required}"
: "${OPERATIONS_DATA_DISK_PATH:?OPERATIONS_DATA_DISK_PATH is required}"
: "${BACKUP_OUTPUT_DIR:?BACKUP_OUTPUT_DIR is required}"
OPERATIONS_LOG_WINDOW_SECONDS=${OPERATIONS_LOG_WINDOW_SECONDS:-300}

require_regular_file "$COMPOSE_ENV_FILE" "INVALID_COMPOSE_ENV_FILE"
require_regular_file "$COMPOSE_FILE" "INVALID_COMPOSE_FILE"
require_regular_file "$OPERATIONS_TLS_CERTIFICATE_FILE" "INVALID_TLS_CERTIFICATE_FILE"
require_directory "$OPERATIONS_DATA_DISK_PATH" "INVALID_DATA_DISK_PATH"
require_directory "$BACKUP_OUTPUT_DIR" "INVALID_BACKUP_OUTPUT_DIR"
[[ "$OPERATIONS_HTTPS_URL" == https://* && "$OPERATIONS_HTTPS_URL" != *[[:space:]]* ]] ||
  operations_die "INVALID_HTTPS_URL"
[[ "$OPERATIONS_LOG_WINDOW_SECONDS" =~ ^[1-9][0-9]*$ ]] ||
  operations_die "INVALID_LOG_WINDOW"

CURL_TLS_ARGUMENTS=()
if [[ -n "${OPERATIONS_CA_CERT_FILE:-}" ]]; then
  require_regular_file "$OPERATIONS_CA_CERT_FILE" "INVALID_CA_CERTIFICATE_FILE"
  CURL_TLS_ARGUMENTS+=(--cacert "$OPERATIONS_CA_CERT_FILE")
fi
if [[ -n "${OPERATIONS_RESOLVE:-}" ]]; then
  [[ "$OPERATIONS_RESOLVE" != *[[:space:]]* ]] || operations_die "INVALID_RESOLVE"
  CURL_TLS_ARGUMENTS+=(--resolve "$OPERATIONS_RESOLVE")
fi

COMPOSE_ARGUMENTS=(--env-file "$COMPOSE_ENV_FILE" --file "$COMPOSE_FILE")
compose() {
  docker compose "${COMPOSE_ARGUMENTS[@]}" "$@"
}
compose config --quiet >/dev/null 2>&1 || operations_die "INVALID_COMPOSE_CONFIG"

http_status() {
  local path=$1
  local expected=$2
  local code=000
  local status=error
  if code=$(
    curl "${CURL_TLS_ARGUMENTS[@]}" --silent --output /dev/null --max-time 10       --write-out '%{http_code}' "${OPERATIONS_HTTPS_URL%/}$path" 2>/dev/null
  ); then
    [[ "$code" == "$expected" ]] && status=ok
  fi
  [[ "$code" =~ ^[0-9]{3}$ ]] || code=000
  jq -nc --arg status "$status" --argjson status_code "$((10#$code))"     '{status:$status,status_code:$status_code}'
}

HTTPS_PAGE=$(http_status "/login" "200")
BACKEND_LIVE=$(http_status "/health/live" "200")
BACKEND_READY=$(http_status "/health/ready" "200")

WORKER_BODY=
WORKER_STATUS=error
WORKER_AGE=null
if WORKER_BODY=$(
  curl "${CURL_TLS_ARGUMENTS[@]}" --silent --fail --max-time 10     "${OPERATIONS_HTTPS_URL%/}/health/worker" 2>/dev/null
); then
  if WORKER_AGE=$(jq -er '.age_seconds | numbers' <<<"$WORKER_BODY" 2>/dev/null); then
    WORKER_STATUS=ok
  else
    WORKER_AGE=null
  fi
fi
WORKER=$(
  jq -nc --arg status "$WORKER_STATUS" --argjson age_seconds "$WORKER_AGE"     '{status:$status,age_seconds:$age_seconds}'
)

FRONTEND_STATUS=error
if compose exec -T frontend node -e   "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"   >/dev/null 2>&1; then
  FRONTEND_STATUS=ok
fi
POSTGRES_STATUS=error
if compose exec -T postgres sh -ceu   'pg_isready --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'   >/dev/null 2>&1; then
  POSTGRES_STATUS=ok
fi
MINIO_STATUS=error
if compose exec -T minio mc ready local >/dev/null 2>&1; then
  MINIO_STATUS=ok
fi

SERVICES=$(
  jq -nc     --argjson https_page "$HTTPS_PAGE"     --arg frontend "$FRONTEND_STATUS"     --argjson backend_live "$BACKEND_LIVE"     --argjson backend_ready "$BACKEND_READY"     --argjson worker "$WORKER"     --arg postgresql "$POSTGRES_STATUS"     --arg minio "$MINIO_STATUS"     '{
      https_page:$https_page,
      frontend:{status:$frontend},
      backend_live:$backend_live,
      backend_ready:$backend_ready,
      worker:$worker,
      postgresql:{status:$postgresql},
      minio:{status:$minio}
    }'
)

DATABASE_SNAPSHOT='{"status":"error","code":"OPERATIONS_SNAPSHOT_UNAVAILABLE"}'
if candidate=$(
  compose exec -T backend python -m app.cli operations-snapshot 2>/dev/null
); then
  if jq -e '.status == "ok"' <<<"$candidate" >/dev/null 2>&1; then
    DATABASE_SNAPSHOT=$candidate
  fi
fi

CONTAINER_LINES=$(compose ps --format json 2>/dev/null || true)
CONTAINERS=$(
  jq -sc '
    map(if type == "array" then .[] else . end) as $rows |
    reduce ["nginx","frontend","backend","worker","postgres","minio"][] as $service ({};
      ($rows | map(select(.Service == $service)) | first) as $row |
      .[$service] = if $row == null then
        {state:"missing",health:"missing"}
      else
        {
          state:($row.State // "unknown"),
          health:(if ($row.Health // "") == "" then "none" else $row.Health end)
        }
      end
    )
  ' <<<"$CONTAINER_LINES"
)

LATEST_BACKUP_EPOCH=0
while IFS= read -r -d '' metadata_file; do
  created_at=$(jq -er '.created_at | strings' "$metadata_file" 2>/dev/null || true)
  [[ -n "$created_at" ]] || continue
  created_epoch=$(date -u -d "$created_at" +%s 2>/dev/null || true)
  [[ "$created_epoch" =~ ^[0-9]+$ ]] || continue
  if (( created_epoch > LATEST_BACKUP_EPOCH )); then
    LATEST_BACKUP_EPOCH=$created_epoch
  fi
done < <(find "$BACKUP_OUTPUT_DIR" -maxdepth 1 -type f -name 'pnx-backup-*.meta.json' -print0)

NOW_EPOCH=$(date -u +%s)
if (( LATEST_BACKUP_EPOCH > 0 )); then
  BACKUP_AGE=$((NOW_EPOCH - LATEST_BACKUP_EPOCH))
  (( BACKUP_AGE < 0 )) && BACKUP_AGE=0
  BACKUP=$(jq -nc --argjson age_seconds "$BACKUP_AGE" '{status:"present",age_seconds:$age_seconds}')
else
  BACKUP='{"status":"missing","age_seconds":null}'
fi

TLS_DAYS=null
TLS_STATUS=error
TLS_END_DATE=$(
  openssl x509 -in "$OPERATIONS_TLS_CERTIFICATE_FILE" -noout -enddate 2>/dev/null || true
)
if [[ "$TLS_END_DATE" == notAfter=* ]]; then
  TLS_END_EPOCH=$(date -u -d "${TLS_END_DATE#notAfter=}" +%s 2>/dev/null || true)
  if [[ "$TLS_END_EPOCH" =~ ^[0-9]+$ ]]; then
    TLS_DAYS=$(((TLS_END_EPOCH - NOW_EPOCH) / 86400))
    TLS_STATUS=ok
  fi
fi
TLS=$(
  jq -nc --arg status "$TLS_STATUS" --argjson days_remaining "$TLS_DAYS"     '{status:$status,days_remaining:$days_remaining}'
)

available_percent() {
  local target=$1
  local used_percent
  used_percent=$(df -P -- "$target" 2>/dev/null | awk 'NR == 2 {gsub(/%/,"",$5); print $5}')
  if [[ "$used_percent" =~ ^[0-9]+$ ]]; then
    printf '%d' "$((100 - used_percent))"
  else
    printf 'null'
  fi
}
DATA_AVAILABLE_PERCENT=$(available_percent "$OPERATIONS_DATA_DISK_PATH")
BACKUP_AVAILABLE_PERCENT=$(available_percent "$BACKUP_OUTPUT_DIR")
DISK=$(
  jq -nc     --argjson data_available_percent "$DATA_AVAILABLE_PERCENT"     --argjson backup_available_percent "$BACKUP_AVAILABLE_PERCENT"     '{data_available_percent:$data_available_percent,backup_available_percent:$backup_available_percent}'
)

BACKEND_LOGS=$(
  compose logs --no-color --no-log-prefix --since "${OPERATIONS_LOG_WINDOW_SECONDS}s"     backend 2>/dev/null || true
)
HTTP_METRICS=$(
  jq -Rsc --argjson window_seconds "$OPERATIONS_LOG_WINDOW_SECONDS" '
    [split("\n")[] | fromjson? | select(.event == "request_completed")] as $requests |
    [$requests[].duration_ms | numbers] | sort as $durations |
    ($requests | length) as $count |
    ([$requests[] | select((.status_code | numbers) >= 500)] | length) as $errors |
    {
      window_seconds:$window_seconds,
      sample_count:$count,
      errors_5xx:$errors,
      error_rate:(if $count == 0 then null else ($errors / $count) end),
      p95_ms:(
        if ($durations | length) == 0 then null
        else $durations[(((($durations | length) * 0.95) | ceil) - 1)]
        end
      )
    }
  ' <<<"$BACKEND_LOGS"
)

PAYLOAD=$(
  jq -nc     --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"     --argjson services "$SERVICES"     --argjson containers "$CONTAINERS"     --argjson database "$DATABASE_SNAPSHOT"     --argjson backup "$BACKUP"     --argjson tls "$TLS"     --argjson disk "$DISK"     --argjson http_metrics "$HTTP_METRICS"     '{
      generated_at:$generated_at,
      services:$services,
      containers:$containers,
      database:$database,
      backup:$backup,
      tls:$tls,
      disk:$disk,
      http_metrics:$http_metrics
    }
    | .status = (
        if (
          ([.services[] | .status] | all(. == "ok"))
          and .database.status == "ok"
          and ([.containers[] | .state] | all(. == "running"))
          and ([.containers[] | .health] | all(. == "healthy" or . == "none"))
          and .tls.status == "ok"
          and .backup.status == "present"
          and .disk.data_available_percent != null
          and .disk.backup_available_percent != null
        ) then "ok" else "error" end
      )'
)
jq -c . <<<"$PAYLOAD"
[[ $(jq -r '.status' <<<"$PAYLOAD") == "ok" ]]
