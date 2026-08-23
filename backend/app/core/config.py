from functools import lru_cache
from typing import Literal, Self
from urllib.parse import quote_plus

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "PNX Training Hub API"
    app_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    app_timezone: str = "Asia/Shanghai"
    trusted_hosts: str = "localhost,127.0.0.1,backend"
    campus_email_domain: str = "hkust-gz.edu.cn"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    session_current_secret: SecretStr = SecretStr("development-session-secret-change-me-32-bytes")
    session_previous_secret: SecretStr | None = None
    csrf_secret: SecretStr = SecretStr("development-csrf-secret-change-me-32-bytes")

    database_host: str = "postgres"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "pnx_training"
    database_user: str = "pnx"
    database_password: SecretStr = SecretStr("pnx_dev_password")
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)

    minio_internal_endpoint: str = "http://minio:9000"
    minio_public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080/storage")
    minio_bucket: str = "pnx-training"
    minio_access_key: SecretStr = SecretStr("pnx_dev_access")
    minio_secret_key: SecretStr = SecretStr("pnx_dev_secret_change_me")
    minio_region: str = "us-east-1"

    smtp_host: str = "localhost"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    mail_from: str = "no-reply@hkust-gz.edu.cn"
    mail_reply_to: str = "no-reply@hkust-gz.edu.cn"

    global_max_upload_bytes: int = Field(default=2_147_483_648, ge=1)
    upload_part_size_bytes: int = Field(default=16_777_216, ge=5_242_880)
    upload_session_ttl_seconds: int = Field(default=86_400, ge=300)

    worker_name: str = "primary"
    worker_heartbeat_interval_seconds: int = Field(default=60, ge=5, le=300)
    worker_stale_after_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("campus_email_domain")
    @classmethod
    def validate_campus_email_domain(cls, value: str) -> str:
        normalized = value.strip().lower().lstrip("@")
        if normalized != "hkust-gz.edu.cn":
            raise ValueError("CAMPUS_EMAIL_DOMAIN must be hkust-gz.edu.cn")
        return normalized

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value != "Asia/Shanghai":
            raise ValueError("APP_TIMEZONE must be Asia/Shanghai")
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.global_max_upload_bytes > 2_147_483_648:
            raise ValueError("GLOBAL_MAX_UPLOAD_BYTES cannot exceed 2 GiB")
        if self.app_env != "production":
            return self

        if self.app_base_url.scheme != "https":
            raise ValueError("APP_BASE_URL must use HTTPS in production")
        secrets_to_validate = [
            ("SESSION_CURRENT_SECRET", self.session_current_secret),
            ("CSRF_SECRET", self.csrf_secret),
            ("DATABASE_PASSWORD", self.database_password),
            ("MINIO_SECRET_KEY", self.minio_secret_key),
        ]
        if self.session_previous_secret is not None:
            secrets_to_validate.append(("SESSION_PREVIOUS_SECRET", self.session_previous_secret))

        weak_markers = ("change_me", "change-me", "development", "pnx_dev")
        for name, secret in secrets_to_validate:
            value = secret.get_secret_value()
            normalized = value.lower()
            if len(value) < 32 or any(marker in normalized for marker in weak_markers):
                raise ValueError(f"{name} must be a strong production secret")
        return self

    @property
    def database_url(self) -> str:
        password = quote_plus(self.database_password.get_secret_value())
        return (
            "postgresql+asyncpg://"
            f"{quote_plus(self.database_user)}:{password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
