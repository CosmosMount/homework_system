from base64 import urlsafe_b64encode
from pathlib import Path

import pytest

from app.audit.models import AuditLog
from app.core.config import Settings
from app.operations.synthetic_seed import (
    SYNTHETIC_ADMIN_EMAIL,
    SYNTHETIC_STUDENT_EMAIL,
    SyntheticSeedError,
    SyntheticUserSeeder,
    read_password_file,
)
from app.users.models import User


class FakeSyntheticSeedRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.audit_logs: list[AuditLog] = []
        self.commits = 0

    async def get_user_by_email(self, email: str) -> User | None:
        return self.users.get(email)

    def add_user_with_audit(self, user: User, audit_log: AuditLog) -> None:
        self.users[user.email_normalized] = user
        self.audit_logs.append(audit_log)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_synthetic_user_seed_is_nonproduction_and_idempotent() -> None:
    repository = FakeSyntheticSeedRepository()
    seeder = SyntheticUserSeeder(repository, Settings(app_env="test"))

    first = await seeder.seed(password="Correct-Horse-Battery-Staple-2026!")
    second = await seeder.seed(password="Correct-Horse-Battery-Staple-2026!")

    assert first == {"created": 2, "existing": 0, "total": 2}
    assert second == {"created": 0, "existing": 2, "total": 2}
    assert set(repository.users) == {
        SYNTHETIC_ADMIN_EMAIL,
        SYNTHETIC_STUDENT_EMAIL,
    }
    assert repository.users[SYNTHETIC_ADMIN_EMAIL].role == "admin"
    assert repository.users[SYNTHETIC_STUDENT_EMAIL].role == "student"
    assert all(user.status == "active" for user in repository.users.values())
    assert all(user.email_verified_at is not None for user in repository.users.values())
    assert len(repository.audit_logs) == 2
    assert repository.commits == 2


@pytest.mark.asyncio
async def test_synthetic_user_seed_refuses_production() -> None:
    repository = FakeSyntheticSeedRepository()
    seeder = SyntheticUserSeeder(
        repository,
        Settings(
            app_env="production",
            app_base_url="https://training.example.edu",
            trusted_hosts="training.example.edu,backend",
            session_cookie_secure=True,
            session_current_secret="a" * 32,
            csrf_secret="b" * 32,
            team_invite_code_pepper="c" * 32,
            outbox_encryption_key=urlsafe_b64encode(b"f" * 32).decode("ascii"),
            smtp_host="smtp.example.edu",
            smtp_password="smtp-secret",
            minio_public_base_url="https://training.example.edu/storage",
            minio_access_key="production-access-key",
            minio_secret_key="d" * 32,
            database_password="e" * 32,
        ),
    )

    with pytest.raises(SyntheticSeedError) as captured:
        await seeder.seed(password="Correct-Horse-Battery-Staple-2026!")

    assert captured.value.code == "SYNTHETIC_SEED_FORBIDDEN_IN_PRODUCTION"
    assert repository.users == {}


def test_synthetic_password_requires_absolute_regular_non_symlink_file(
    tmp_path: Path,
) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("Correct-Horse-Battery-Staple-2026!\n", encoding="utf-8")

    assert read_password_file(password_file) == "Correct-Horse-Battery-Staple-2026!"

    relative = Path("password")
    with pytest.raises(SyntheticSeedError):
        read_password_file(relative)
    symlink = tmp_path / "password-link"
    symlink.symlink_to(password_file)
    with pytest.raises(SyntheticSeedError):
        read_password_file(symlink)
