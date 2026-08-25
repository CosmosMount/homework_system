import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = ROOT / "infra/monitoring/check.sh"
ALERT_SCRIPT = ROOT / "infra/monitoring/evaluate-alerts.sh"
ALERT_RULES = ROOT / "infra/monitoring/alert-rules.json"


def _snapshot() -> dict[str, Any]:
    return {
        "status": "ok",
        "generated_at": "2026-08-25T08:00:00Z",
        "services": {
            "https_page": {"status": "ok", "status_code": 200},
            "frontend": {"status": "ok"},
            "backend_live": {"status": "ok", "status_code": 200},
            "backend_ready": {"status": "ok", "status_code": 200},
            "worker": {"status": "ok", "age_seconds": 30},
            "postgresql": {"status": "ok"},
            "minio": {"status": "ok"},
        },
        "containers": {
            service: {"state": "running", "health": "healthy"}
            for service in ("nginx", "frontend", "backend", "worker", "postgres", "minio")
        },
        "database": {
            "status": "ok",
            "outbox": {
                "pending": 0,
                "retry": 0,
                "processing": 0,
                "active_total": 0,
                "oldest_active_age_seconds": None,
                "dead": 0,
            },
            "uploads": {
                "rejected": 0,
                "aborted": 0,
                "expired": 0,
                "stale_sessions": 0,
                "orphaned_available": 0,
                "cleanup_due_available": 0,
            },
        },
        "backup": {"status": "present", "age_seconds": 3600},
        "tls": {"status": "ok", "days_remaining": 90},
        "disk": {"data_available_percent": 60, "backup_available_percent": 70},
        "http_metrics": {
            "window_seconds": 300,
            "sample_count": 100,
            "errors_5xx": 0,
            "error_rate": 0,
            "p95_ms": 120,
        },
    }


def _evaluate(tmp_path: Path, snapshot: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    snapshot_file = tmp_path / "snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")
    return subprocess.run(
        [str(ALERT_SCRIPT), str(snapshot_file), str(ALERT_RULES)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_monitoring_shell_scripts_are_valid_and_do_not_query_sensitive_fields() -> None:
    for script in (CHECK_SCRIPT, ALERT_SCRIPT):
        subprocess.run(["bash", "-n", str(script)], check=True)
    check_source = CHECK_SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "original_name",
        "email_normalized",
        "secret_payload_ciphertext",
        "minio_upload_id",
    ):
        assert forbidden not in check_source


def test_alert_evaluator_accepts_healthy_snapshot(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, _snapshot())

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "ok",
        "generated_at": "2026-08-25T08:00:00Z",
        "alert_count": 0,
        "alerts": [],
    }


def test_alert_evaluator_covers_all_required_thresholds(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["status"] = "error"
    services = snapshot["services"]
    services["worker"] = {"status": "error", "age_seconds": 301}
    services["postgresql"] = {"status": "error"}
    services["minio"] = {"status": "error"}
    database = snapshot["database"]
    database["outbox"]["oldest_active_age_seconds"] = 601
    database["outbox"]["dead"] = 1
    snapshot["backup"]["age_seconds"] = 86401
    snapshot["tls"]["days_remaining"] = 6
    snapshot["disk"] = {"data_available_percent": 9, "backup_available_percent": 19}
    snapshot["http_metrics"] = {
        "window_seconds": 300,
        "sample_count": 100,
        "errors_5xx": 6,
        "error_rate": 0.06,
        "p95_ms": 1001,
    }

    result = _evaluate(tmp_path, snapshot)

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "critical"
    codes = {alert["code"] for alert in payload["alerts"]}
    assert {
        "TLS_CERTIFICATE_EXPIRING",
        "WORKER_HEARTBEAT_STALE",
        "OUTBOX_OLDEST_EXCEEDED",
        "OUTBOX_DEAD_PRESENT",
        "BACKUP_STALE",
        "DISK_DATA_AVAILABLE_PERCENT_LOW",
        "DISK_BACKUP_AVAILABLE_PERCENT_LOW",
        "HTTP_5XX_RATE_HIGH",
        "HTTP_P95_HIGH",
        "SERVICE_POSTGRESQL_UNAVAILABLE",
        "SERVICE_MINIO_UNAVAILABLE",
    } <= codes
