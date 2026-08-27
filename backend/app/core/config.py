from base64 import urlsafe_b64decode
from functools import lru_cache
from pathlib import Path
from re import fullmatch
from typing import Literal, Self
from urllib.parse import quote_plus, urlsplit

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
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
    campus_email_domain: str = "connect.hkust-gz.edu.cn"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    session_current_secret: SecretStr = SecretStr("development-session-secret-change-me-32-bytes")
    session_previous_secret: SecretStr | None = None
    csrf_secret: SecretStr = SecretStr("development-csrf-secret-change-me-32-bytes")
    session_cookie_secure: bool = False
    session_current_secret_file: str | None = None
    session_previous_secret_file: str | None = None
    csrf_secret_file: str | None = None
    team_invite_code_pepper_file: str | None = None
    outbox_encryption_key_file: str | None = None
    database_password_file: str | None = None
    minio_access_key_file: str | None = None
    minio_secret_key_file: str | None = None
    smtp_password_file: str | None = None
    feishu_app_secret_file: str | None = None
    team_invite_code_pepper: SecretStr = SecretStr("development-team-invite-pepper-32-bytes")
    outbox_encryption_key: SecretStr = SecretStr("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    database_host: str = "postgres"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "pnx_training"
    database_user: str = "pnx"
    database_password: SecretStr = SecretStr("pnx_dev_password")
    database_pool_size: int = Field(default=8, ge=1, le=100)
    database_max_overflow: int = Field(default=4, ge=0, le=100)

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
    mail_from: str = "no-reply@connect.hkust-gz.edu.cn"
    mail_reply_to: str = "no-reply@connect.hkust-gz.edu.cn"

    feishu_app_id: str = ""
    feishu_app_secret: SecretStr = SecretStr("")
    feishu_wiki_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "feishu_wiki_url", "FEISHU_WIKI_URL", "FEISHU_KNOWLEDGE_SOURCE_URL"
        ),
    )
    feishu_knowledge_max_documents: int = Field(default=500, ge=1, le=5_000)
    feishu_knowledge_max_assets: int = Field(default=2_000, ge=1, le=10_000)
    feishu_knowledge_max_asset_bytes: int = Field(default=52_428_800, ge=1, le=209_715_200)

    global_max_upload_bytes: int = Field(default=2_147_483_648, ge=1)
    upload_part_size_bytes: int = Field(default=16_777_216, ge=5_242_880)
    upload_session_ttl_seconds: int = Field(default=86_400, ge=300)

    worker_name: str = "primary"
    worker_heartbeat_interval_seconds: int = Field(default=60, ge=5, le=300)
    worker_stale_after_seconds: int = Field(default=300, ge=30, le=3600)
    worker_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    worker_lock_lease_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("session_previous_secret", mode="before")
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="before")
    @classmethod
    def load_secret_files(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values
        resolved = dict(values)
        secret_files = (
            ("session_current_secret", "session_current_secret_file"),
            ("session_previous_secret", "session_previous_secret_file"),
            ("csrf_secret", "csrf_secret_file"),
            ("team_invite_code_pepper", "team_invite_code_pepper_file"),
            ("outbox_encryption_key", "outbox_encryption_key_file"),
            ("database_password", "database_password_file"),
            ("minio_access_key", "minio_access_key_file"),
            ("minio_secret_key", "minio_secret_key_file"),
            ("smtp_password", "smtp_password_file"),
            ("feishu_app_secret", "feishu_app_secret_file"),
        )
        for value_name, file_name in secret_files:
            file_value = resolved.get(file_name)
            if file_value in (None, ""):
                continue
            if resolved.get(value_name) not in (None, ""):
                raise ValueError(f"{value_name.upper()} and {file_name.upper()} are exclusive")
            try:
                secret = Path(str(file_value)).read_text(encoding="utf-8").rstrip("\r\n")
            except OSError as exc:
                raise ValueError(f"{file_name.upper()} cannot be read") from exc
            if not secret:
                raise ValueError(f"{file_name.upper()} cannot be empty")
            resolved[value_name] = secret
        return resolved

    @field_validator("outbox_encryption_key")
    @classmethod
    def validate_outbox_encryption_key(cls, value: SecretStr) -> SecretStr:
        try:
            decoded = urlsafe_b64decode(value.get_secret_value().encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise ValueError("OUTBOX_ENCRYPTION_KEY must be URL-safe base64") from exc
        if len(decoded) != 32:
            raise ValueError("OUTBOX_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return value

    @field_validator("campus_email_domain")
    @classmethod
    def validate_campus_email_domain(cls, value: str) -> str:
        normalized = value.strip().lower().lstrip("@")
        if normalized != "connect.hkust-gz.edu.cn":
            raise ValueError("CAMPUS_EMAIL_DOMAIN must be connect.hkust-gz.edu.cn")
        return normalized

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value != "Asia/Shanghai":
            raise ValueError("APP_TIMEZONE must be Asia/Shanghai")
        return value

    @field_validator("feishu_wiki_url")
    @classmethod
    def validate_feishu_wiki_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is None:
            return None
        parts = urlsplit(str(value))
        hostname = (parts.hostname or "").lower()
        if parts.scheme != "https" or not (
            hostname.endswith(".feishu.cn") or hostname.endswith(".larksuite.com")
        ):
            raise ValueError("FEISHU_WIKI_URL must be an HTTPS Feishu or Lark URL")
        if parts.username or parts.password or parts.port not in (None, 443) or parts.fragment:
            raise ValueError("FEISHU_WIKI_URL contains unsupported URL components")
        path = parts.path.rstrip("/")
        if not (fullmatch(r"/wiki/space/[0-9]+", path) or fullmatch(r"/wiki/[A-Za-z0-9_-]+", path)):
            raise ValueError(
                "FEISHU_WIKI_URL must use /wiki/space/{space_id} or /wiki/{node_token}"
            )
        return value

    @model_validator(mode="after")
    def validate_feishu_configuration(self) -> Self:
        values = (
            self.feishu_app_id.strip(),
            self.feishu_app_secret.get_secret_value().strip(),
            self.feishu_wiki_url,
        )
        if any(values) and not all(values):
            raise ValueError(
                "FEISHU_APP_ID, FEISHU_APP_SECRET and FEISHU_WIKI_URL must be configured together"
            )
        return self

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.global_max_upload_bytes > 2_147_483_648:
            raise ValueError("GLOBAL_MAX_UPLOAD_BYTES cannot exceed 2 GiB")
        if self.app_env != "production":
            return self

        if self.app_base_url.scheme != "https":
            raise ValueError("APP_BASE_URL must use HTTPS in production")
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        app_parts = urlsplit(str(self.app_base_url))
        minio_parts = urlsplit(str(self.minio_public_base_url))
        if (
            minio_parts.scheme != "https"
            or minio_parts.netloc != app_parts.netloc
            or minio_parts.path.rstrip("/") != "/storage"
        ):
            raise ValueError("MINIO_PUBLIC_BASE_URL must be the application HTTPS /storage path")
        if (
            app_parts.hostname is None
            or app_parts.hostname not in self.trusted_host_list
            or "backend" not in self.trusted_host_list
            or "*" in self.trusted_host_list
        ):
            raise ValueError("TRUSTED_HOSTS must contain the production hostname and backend")
        if self.smtp_host in {"", "localhost", "smtp.example.invalid"}:
            raise ValueError("SMTP_HOST must be configured in production")
        if not self.smtp_password.get_secret_value():
            raise ValueError("SMTP_PASSWORD must be configured in production")
        secrets_to_validate = [
            ("SESSION_CURRENT_SECRET", self.session_current_secret),
            ("CSRF_SECRET", self.csrf_secret),
            ("TEAM_INVITE_CODE_PEPPER", self.team_invite_code_pepper),
            ("DATABASE_PASSWORD", self.database_password),
            ("MINIO_SECRET_KEY", self.minio_secret_key),
            ("OUTBOX_ENCRYPTION_KEY", self.outbox_encryption_key),
        ]
        if self.session_previous_secret is not None:
            secrets_to_validate.append(("SESSION_PREVIOUS_SECRET", self.session_previous_secret))

        weak_markers = ("change_me", "change-me", "development", "pnx_dev")
        for name, secret in secrets_to_validate:
            value = secret.get_secret_value()
            normalized = value.lower()
            if len(value) < 32 or any(marker in normalized for marker in weak_markers):
                raise ValueError(f"{name} must be a strong production secret")
        access_key = self.minio_access_key.get_secret_value()
        if len(access_key) < 16 or any(marker in access_key.lower() for marker in weak_markers):
            raise ValueError("MINIO_ACCESS_KEY must be a strong production credential")
        secret_values = [secret.get_secret_value() for _, secret in secrets_to_validate]
        secret_values.extend([access_key, self.smtp_password.get_secret_value()])
        if len(secret_values) != len(set(secret_values)):
            raise ValueError("production secrets must be independent")
        if self.outbox_encryption_key.get_secret_value() == (
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        ):
            raise ValueError("OUTBOX_ENCRYPTION_KEY must be a strong production secret")
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

    @property
    def app_origin(self) -> str:
        parts = urlsplit(str(self.app_base_url))
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def session_cookie_name(self) -> str:
        return "__Host-pnx_session" if self.session_cookie_secure else "pnx_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-pnx_csrf" if self.session_cookie_secure else "pnx_csrf"

    @property
    def feishu_knowledge_configured(self) -> bool:
        return bool(
            self.feishu_app_id.strip()
            and self.feishu_app_secret.get_secret_value().strip()
            and self.feishu_wiki_url is not None
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
