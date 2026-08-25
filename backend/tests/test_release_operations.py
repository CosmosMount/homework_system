import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIRECTORY = ROOT / "infra/release"
COMMON = RELEASE_DIRECTORY / "common.sh"
PREFLIGHT = RELEASE_DIRECTORY / "preflight.sh"
DEPLOY = RELEASE_DIRECTORY / "deploy.sh"
ROLLBACK = RELEASE_DIRECTORY / "rollback.sh"


def _validate_image(reference: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; validate_image_reference "$2"',
            "release-image-test",
            str(COMMON),
            reference,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_scripts_have_valid_shell_syntax() -> None:
    subprocess.run(
        ["bash", "-n", str(COMMON), str(PREFLIGHT), str(DEPLOY), str(ROLLBACK)],
        check=True,
    )
    for script in (PREFLIGHT, DEPLOY, ROLLBACK):
        assert script.stat().st_mode & 0o111


def test_fixed_image_validator_accepts_digest_or_explicit_tag() -> None:
    digest = "registry.example.edu/pnx/backend@sha256:" + "a" * 64

    assert _validate_image(digest).returncode == 0
    assert _validate_image("registry.example.edu/pnx/backend:2026.08.25").returncode == 0


def test_fixed_image_validator_rejects_latest_placeholder_and_unversioned_reference() -> None:
    for reference in (
        "registry.example.edu/pnx/backend:latest",
        "registry.example.edu/pnx/backend@sha256:replace-with-digest",
        "registry.example.edu/pnx/backend",
    ):
        result = _validate_image(reference)

        assert result.returncode == 2
        assert '"status":"error"' in result.stderr


def test_deploy_orders_backup_gate_migration_health_and_https_smoke() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    preflight = source.index('"$SCRIPT_DIRECTORY/preflight.sh"')
    migrate = source.index("compose_release run --rm --no-deps -T migrate")
    backend = source.index("force-recreate backend worker")
    frontend = source.index("force-recreate frontend nginx")
    smoke = source.index("release_https_smoke")
    assert preflight < migrate < backend < frontend < smoke
    assert "alembic downgrade" not in source
    assert "restore.sh" not in source


def test_preflight_requires_encrypted_backup_checksum_and_safe_topology() -> None:
    common = COMMON.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")

    assert "BACKUP_CHECKSUM_INVALID" in common
    assert "BACKUP_TOO_OLD" in common
    assert ".tar.gpg" in common
    assert "PRODUCTION_TOPOLOGY_INVALID" in preflight
    assert "SECRET_FILE_INVALID" in preflight
    assert "TLS_CERTIFICATE_TOO_CLOSE_TO_EXPIRY" in preflight


def test_rollback_only_changes_images_and_forbids_blind_database_restore() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "PRODUCTION_BACKUP_RESTORE_FORBIDDEN" in source
    assert "SCHEMA_COMPATIBILITY_CONFIRMATION_REQUIRED" in source
    assert "database_restore_performed:false" in source
    assert "alembic downgrade" not in source
    assert "restore.sh" not in source
    assert "compose_previous" in source
