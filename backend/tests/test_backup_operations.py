import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIRECTORY = ROOT / "infra/backup"
COMMON = BACKUP_DIRECTORY / "common.sh"
BACKUP = BACKUP_DIRECTORY / "backup.sh"
RESTORE = BACKUP_DIRECTORY / "restore.sh"
RETENTION = BACKUP_DIRECTORY / "retention.sh"


def test_backup_chain_scripts_are_valid_and_executable() -> None:
    subprocess.run(
        ["bash", "-n", str(COMMON), str(BACKUP), str(RESTORE), str(RETENTION)],
        check=True,
    )
    for script in (COMMON, BACKUP, RESTORE, RETENTION):
        assert script.stat().st_mode & 0o111


def test_daily_backup_requires_verified_weekly_base_and_records_delta() -> None:
    source = BACKUP.read_text(encoding="utf-8")

    assert "BACKUP_STATE_DIR" in source
    assert "BACKUP_STATE_MUST_BE_LOCAL_AND_SEPARATE" in source
    assert "INSECURE_BACKUP_STATE_PERMISSIONS" in source
    assert "MINIO_WEEKLY_BASE_STATE_MISSING" in source
    assert "MINIO_WEEKLY_BASE_CHECKSUM_FAILED" in source
    assert "--base-manifest /backup-state/minio-weekly-base-manifest.json" in source
    assert "OBJECT_BACKUP_MODE=incremental" in source
    assert "object_payload_count" in source
    assert "object_deleted_count" in source
    assert source.index("gpg --batch --yes --trust-model always") < source.index(
        'mv -- "$PARTIAL_BASE_STATE" "$WEEKLY_BASE_STATE"'
    )


def test_incremental_restore_imports_base_then_delta_before_reconciliation() -> None:
    source = RESTORE.read_text(encoding="utf-8")

    extract_base = source.index('extract_backup_artifact \\\n    "$BASE_ARTIFACT"')
    import_base = source.index('--volume "$BASE_PLAIN_DIRECTORY/objects:/operations:ro"')
    apply_delta = source.index("--apply-incremental")
    reconcile = source.index("python -m app.cli reconcile-storage")
    assert extract_base < import_base < apply_delta < reconcile
    assert "RESTORE_INCREMENTAL_BASE_MANIFEST_INVALID" in source
    assert "RESTORE_OBJECT_BACKUP_MODE_INVALID" in source
    assert "untracked_object_count" in source
    assert "jq -e '.status == \"ok\"'" not in source
    assert "(.missing_objects | length) == 0" in source
    assert "RECONCILIATION_EXIT == 4" in source


def _create_backup_set(directory: Path, backup_id: str, metadata: dict[str, object]) -> None:
    (directory / f"{backup_id}.tar.gpg").write_bytes(b"encrypted")
    (directory / f"{backup_id}.tar.gpg.sha256").write_text("unused\n", encoding="utf-8")
    (directory / f"{backup_id}.meta.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )


def test_retention_protects_weekly_base_of_retained_daily(tmp_path: Path) -> None:
    weekly_old = "pnx-backup-20260801T000000Z-weekly"
    weekly_removed = "pnx-backup-20260808T000000Z-weekly"
    weekly_protected = "pnx-backup-20260815T000000Z-weekly"
    daily_removed = "pnx-backup-20260809T000000Z-daily"
    daily_retained = "pnx-backup-20260816T000000Z-daily"
    for weekly in (weekly_old, weekly_removed, weekly_protected):
        _create_backup_set(tmp_path, weekly, {"status": "ok"})
    _create_backup_set(
        tmp_path,
        daily_removed,
        {"status": "ok", "object_base_backup_id": weekly_removed},
    )
    _create_backup_set(
        tmp_path,
        daily_retained,
        {"status": "ok", "object_base_backup_id": weekly_protected},
    )
    environment = {
        **os.environ,
        "BACKUP_OUTPUT_DIR": str(tmp_path),
        "DAILY_KEEP": "1",
        "WEEKLY_KEEP": "0",
        "RETENTION_APPLY": "YES",
    }

    result = subprocess.run(
        [str(RETENTION)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    payload = json.loads(result.stdout)
    assert payload["selected_count"] == 3
    assert payload["protected_weekly_count"] == 1
    assert (tmp_path / f"{daily_retained}.tar.gpg").exists()
    assert (tmp_path / f"{weekly_protected}.tar.gpg").exists()
    assert not (tmp_path / f"{daily_removed}.tar.gpg").exists()
    assert not (tmp_path / f"{weekly_removed}.tar.gpg").exists()
    assert not (tmp_path / f"{weekly_old}.tar.gpg").exists()
