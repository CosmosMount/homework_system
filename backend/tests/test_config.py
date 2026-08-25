from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

OUTBOX_TEST_KEY = urlsafe_b64encode(b"o" * 32).decode("ascii")


def production_values() -> dict[str, Any]:
    return {
        "app_env": "production",
        "app_base_url": "https://training.example.edu",
        "trusted_hosts": "training.example.edu,backend",
        "minio_public_base_url": "https://training.example.edu/storage",
        "session_cookie_secure": True,
        "session_current_secret": "s" * 32,
        "session_previous_secret": "p" * 32,
        "csrf_secret": "c" * 32,
        "team_invite_code_pepper": "t" * 32,
        "database_password": "d" * 32,
        "minio_access_key": "access-key-strong-123456",
        "minio_secret_key": "m" * 32,
        "outbox_encryption_key": OUTBOX_TEST_KEY,
        "smtp_host": "smtp.example.edu",
        "smtp_password": "smtp-password-strong",
    }


def test_database_pool_defaults_match_four_web_worker_capacity_budget() -> None:
    settings = Settings(app_env="test")

    assert settings.database_pool_size == 8
    assert settings.database_max_overflow == 4


def test_connect_campus_domain_is_fixed_and_old_domain_is_rejected() -> None:
    settings = Settings(app_env="test")

    assert settings.campus_email_domain == "connect.hkust-gz.edu.cn"
    for rejected_domain in ("hkust-gz.edu.cn", "example.edu.cn"):
        with pytest.raises(ValidationError):
            Settings(campus_email_domain=rejected_domain)


def test_production_requires_https_and_strong_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_rejects_development_placeholder_with_https() -> None:
    values = production_values()
    values["session_current_secret"] = "development-only-session-secret-at-least-32-bytes"
    with pytest.raises(ValidationError, match="SESSION_CURRENT_SECRET"):
        Settings(**values)


def test_production_accepts_https_and_independent_strong_secrets() -> None:
    settings = Settings(**production_values())

    assert settings.app_env == "production"
    assert settings.app_origin == "https://training.example.edu"


def test_production_rejects_non_same_origin_minio_and_duplicate_secrets() -> None:
    values = production_values()
    values["minio_public_base_url"] = "https://objects.example.edu/storage"
    with pytest.raises(ValidationError, match="MINIO_PUBLIC_BASE_URL"):
        Settings(**values)

    values = production_values()
    values["csrf_secret"] = "s" * 32
    with pytest.raises(ValidationError, match="independent"):
        Settings(**values)


def test_production_requires_internal_backend_trusted_host() -> None:
    values = production_values()
    values["trusted_hosts"] = "training.example.edu"

    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings(**values)


def test_secret_file_loading_and_direct_value_are_exclusive(tmp_path: Path) -> None:
    session_file = tmp_path / "session-secret"
    session_file.write_text("f" * 32 + "\n", encoding="utf-8")
    values = production_values()
    values.pop("session_current_secret")
    settings = Settings(
        **values,
        session_current_secret_file=str(session_file),
    )
    assert settings.session_current_secret.get_secret_value() == "f" * 32

    values = production_values()
    with pytest.raises(ValidationError, match="exclusive"):
        Settings(
            **values,
            session_current_secret_file=str(session_file),
        )


def test_missing_secret_file_fails_without_leaking_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing-secret"
    values = production_values()
    values.pop("session_current_secret")
    with pytest.raises(
        ValidationError,
        match="SESSION_CURRENT_SECRET_FILE cannot be read",
    ) as error:
        Settings(
            **values,
            session_current_secret_file=str(missing),
        )
    assert str(missing) not in str(error.value)
