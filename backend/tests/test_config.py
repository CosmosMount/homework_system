import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_wrong_campus_domain_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(campus_email_domain="example.edu.cn")


def test_production_requires_https_and_strong_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_rejects_development_placeholder_with_https() -> None:
    strong_secret = "s" * 32
    with pytest.raises(ValidationError, match="SESSION_CURRENT_SECRET"):
        Settings(
            app_env="production",
            app_base_url="https://training.example.edu",
            session_current_secret="development-only-session-secret-at-least-32-bytes",
            csrf_secret=strong_secret,
            database_password=strong_secret,
            minio_secret_key=strong_secret,
        )


def test_production_accepts_https_and_independent_strong_secrets() -> None:
    settings = Settings(
        app_env="production",
        app_base_url="https://training.example.edu",
        session_current_secret="s" * 32,
        session_previous_secret="p" * 32,
        csrf_secret="c" * 32,
        database_password="d" * 32,
        minio_secret_key="m" * 32,
    )

    assert settings.app_env == "production"
