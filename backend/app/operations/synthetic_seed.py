from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.audit.models import AuditLog
from app.core.config import Settings
from app.core.identifiers import uuid7
from app.core.security import get_password_manager, validate_password
from app.users.models import User

SYNTHETIC_ADMIN_EMAIL = "e2e-admin@connect.hkust-gz.edu.cn"
SYNTHETIC_STUDENT_EMAIL = "e2e-student@connect.hkust-gz.edu.cn"


class SyntheticSeedError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SyntheticSeedRepositoryProtocol(Protocol):
    async def get_user_by_email(self, email: str) -> User | None: ...

    def add_user_with_audit(self, user: User, audit_log: AuditLog) -> None: ...

    async def commit(self) -> None: ...


def read_password_file(path: Path) -> str:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise SyntheticSeedError("INVALID_PASSWORD_FILE")
    if path.stat().st_size > 4096:
        raise SyntheticSeedError("INVALID_PASSWORD_FILE")
    try:
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as exc:
        raise SyntheticSeedError("INVALID_PASSWORD_FILE") from exc
    if not password:
        raise SyntheticSeedError("INVALID_PASSWORD_FILE")
    return password


class SyntheticUserSeeder:
    def __init__(
        self,
        repository: SyntheticSeedRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def seed(self, *, password: str) -> dict[str, int | str]:
        if self._settings.app_env == "production":
            raise SyntheticSeedError("SYNTHETIC_SEED_FORBIDDEN_IN_PRODUCTION")

        definitions = (
            {
                "email": SYNTHETIC_ADMIN_EMAIL,
                "student_number": "E2E-ADMIN-001",
                "full_name": "虚构测试管理员",
                "role": "admin",
            },
            {
                "email": SYNTHETIC_STUDENT_EMAIL,
                "student_number": "E2E-STUDENT-001",
                "full_name": "虚构测试学生",
                "role": "student",
            },
        )
        created = 0
        existing = 0
        now = datetime.now(UTC)
        password_manager = get_password_manager()
        for definition in definitions:
            email = definition["email"]
            student_number = definition["student_number"]
            validate_password(password, email=email, student_number=student_number)
            current = await self._repository.get_user_by_email(email)
            if current is not None:
                if (
                    current.student_number != student_number
                    or current.role != definition["role"]
                    or current.status != "active"
                ):
                    raise SyntheticSeedError("SYNTHETIC_ACCOUNT_CONFLICT")
                existing += 1
                continue
            user = User(
                id=uuid7(),
                email=email,
                email_normalized=email,
                student_number=student_number,
                full_name=definition["full_name"],
                password_hash=password_manager.hash(password),
                role=definition["role"],
                status="active",
                cohort_id=None,
                direction_id=None,
                email_verified_at=now,
                disabled_at=None,
                disabled_by=None,
                disabled_reason=None,
                password_changed_at=now,
            )
            self._repository.add_user_with_audit(
                user,
                AuditLog(
                    id=uuid7(),
                    actor_user_id=None,
                    action="test_data.seed_user",
                    target_type="user",
                    target_id=user.id,
                    request_id="synthetic-seed",
                    ip_prefix="local",
                    result="success",
                    change_summary={"synthetic": True, "role": definition["role"]},
                    created_at=now,
                ),
            )
            created += 1
        await self._repository.commit()
        return {
            "created": created,
            "existing": existing,
            "total": len(definitions),
        }
