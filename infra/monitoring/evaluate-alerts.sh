#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

alert_die() {
  printf '{"status":"error","code":"%s","alerts":[]}\n' "$1" >&2
  exit 2
}

command -v jq >/dev/null 2>&1 || alert_die "MISSING_COMMAND_jq"
[[ $# -ge 1 && $# -le 2 ]] || alert_die "USAGE"
SNAPSHOT_FILE=$1
SCRIPT_DIRECTORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
RULES_FILE=${2:-"$SCRIPT_DIRECTORY/alert-rules.json"}
[[ "$SNAPSHOT_FILE" == /* && -f "$SNAPSHOT_FILE" && ! -L "$SNAPSHOT_FILE" ]] ||
  alert_die "INVALID_SNAPSHOT_FILE"
[[ "$RULES_FILE" == /* && -f "$RULES_FILE" && ! -L "$RULES_FILE" ]] ||
  alert_die "INVALID_RULES_FILE"
jq -e '.status | strings' "$SNAPSHOT_FILE" >/dev/null 2>&1 ||
  alert_die "INVALID_SNAPSHOT"
jq -e '.version == 1 and (.thresholds | type == "object")' "$RULES_FILE" >/dev/null 2>&1 ||
  alert_die "INVALID_RULES"

RESULT=$(
  jq -n --slurpfile snapshot "$SNAPSHOT_FILE" --slurpfile rules "$RULES_FILE" '
    $snapshot[0] as $s |
    $rules[0].thresholds as $t |
    def alert($code;$severity;$value;$threshold):
      {code:$code,severity:$severity,value:$value,threshold:$threshold};
    [
      if $s.status != "ok" then alert("OPERATIONS_CHECK_FAILED";"critical";null;null) else empty end,
      (
        $s.services
        | to_entries[]
        | select(.value.status != "ok")
        | alert(("SERVICE_" + (.key | ascii_upcase) + "_UNAVAILABLE");"critical";null;null)
      ),
      if ($s.tls.days_remaining // -1) < 0 then
        alert("TLS_CERTIFICATE_UNKNOWN";"critical";$s.tls.days_remaining;$t.tls_warning_days)
      elif $s.tls.days_remaining <= $t.tls_critical_days then
        alert("TLS_CERTIFICATE_EXPIRING";"critical";$s.tls.days_remaining;$t.tls_critical_days)
      elif $s.tls.days_remaining <= $t.tls_warning_days then
        alert("TLS_CERTIFICATE_EXPIRING";"warning";$s.tls.days_remaining;$t.tls_warning_days)
      else empty end,
      if ($s.services.worker.age_seconds // -1) < 0 then
        alert("WORKER_HEARTBEAT_UNKNOWN";"critical";$s.services.worker.age_seconds;$t.worker_stale_seconds)
      elif $s.services.worker.age_seconds > $t.worker_stale_seconds then
        alert("WORKER_HEARTBEAT_STALE";"critical";$s.services.worker.age_seconds;$t.worker_stale_seconds)
      else empty end,
      if ($s.database.outbox.oldest_active_age_seconds // 0) > $t.outbox_oldest_seconds then
        alert("OUTBOX_OLDEST_EXCEEDED";"critical";$s.database.outbox.oldest_active_age_seconds;$t.outbox_oldest_seconds)
      else empty end,
      if ($s.database.outbox.dead // 0) > 0 then
        alert("OUTBOX_DEAD_PRESENT";"critical";$s.database.outbox.dead;0)
      else empty end,
      if ($s.backup.age_seconds // -1) < 0 then
        alert("BACKUP_MISSING";"critical";$s.backup.age_seconds;$t.backup_max_age_seconds)
      elif $s.backup.age_seconds > $t.backup_max_age_seconds then
        alert("BACKUP_STALE";"critical";$s.backup.age_seconds;$t.backup_max_age_seconds)
      else empty end,
      (
        $s.disk
        | to_entries[]
        | select(.key | endswith("_available_percent"))
        | if (.value // -1) < 0 then
            alert(("DISK_" + (.key | ascii_upcase) + "_UNKNOWN");"critical";.value;$t.disk_warning_available_percent)
          elif .value < $t.disk_critical_available_percent then
            alert(("DISK_" + (.key | ascii_upcase) + "_LOW");"critical";.value;$t.disk_critical_available_percent)
          elif .value < $t.disk_warning_available_percent then
            alert(("DISK_" + (.key | ascii_upcase) + "_LOW");"warning";.value;$t.disk_warning_available_percent)
          else empty end
      ),
      if ($s.http_metrics.sample_count // 0) > 0 then
        if $s.http_metrics.error_rate >= $t.http_5xx_critical_rate then
          alert("HTTP_5XX_RATE_HIGH";"critical";$s.http_metrics.error_rate;$t.http_5xx_critical_rate)
        elif $s.http_metrics.error_rate >= $t.http_5xx_warning_rate then
          alert("HTTP_5XX_RATE_HIGH";"warning";$s.http_metrics.error_rate;$t.http_5xx_warning_rate)
        else empty end,
        if $s.http_metrics.p95_ms >= $t.http_p95_critical_ms then
          alert("HTTP_P95_HIGH";"critical";$s.http_metrics.p95_ms;$t.http_p95_critical_ms)
        elif $s.http_metrics.p95_ms >= $t.http_p95_warning_ms then
          alert("HTTP_P95_HIGH";"warning";$s.http_metrics.p95_ms;$t.http_p95_warning_ms)
        else empty end
      else empty end
    ] as $alerts |
    {
      status:(
        if any($alerts[]; .severity == "critical") then "critical"
        elif any($alerts[]; .severity == "warning") then "warning"
        else "ok" end
      ),
      generated_at:($s.generated_at // null),
      alert_count:($alerts | length),
      alerts:$alerts
    }
  '
)
jq -c . <<<"$RESULT"
case $(jq -r '.status' <<<"$RESULT") in
  ok) exit 0 ;;
  warning) exit 1 ;;
  *) exit 2 ;;
esac
