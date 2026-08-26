from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserRoleRequest
from app.users.service import AuditContext, UserAdministrationService


def make_active_admin() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="admin@connect.hkust-gz.edu.cn",
        email_normalized="admin@connect.hkust-gz.edu.cn",
        student_number="admin-test",
        full_name="测试管理员",
        password_hash="not-a-real-password-hash",
        role="admin",
        status="active",
        cohort_id=None,
        direction_id=None,
        email_verified_at=now,
        disabled_at=None,
        disabled_by=None,
        disabled_reason=None,
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def build_last_admin_service(
    user: User,
) -> tuple[UserAdministrationService, AsyncMock, Mock]:
    commit = AsyncMock()
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=commit, rollback=AsyncMock()),
    )
    service = UserAdministrationService(session, Settings(app_env="test"))
    service._users = cast(
        UserRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=user),
            active_admin_count=AsyncMock(return_value=1),
        ),
    )
    audit_add = Mock()
    service._audit = cast(AuditRepository, SimpleNamespace(add=audit_add))
    return service, commit, audit_add


def audit_context(user: User) -> AuditContext:
    actor = cast(AuthenticatedContext, SimpleNamespace(user=user))
    return AuditContext(actor=actor, request_id="test-request", ip_prefix="192.0.2.0/24")


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_disabled_and_denial_is_audited() -> None:
    user = make_active_admin()
    service, commit, audit_add = build_last_admin_service(user)

    with pytest.raises(ApplicationError) as caught:
        await service.disable_user(
            user.id,
            reason="安全回归测试",
            audit=audit_context(user),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "STATE_CONFLICT"
    assert user.status == "active"
    commit.assert_awaited_once()
    audit = audit_add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.action == "user.disable"
    assert audit.result == "denied"
    assert audit.change_summary["blocked"] == "last_active_admin"


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_demoted_and_denial_is_audited() -> None:
    user = make_active_admin()
    service, commit, audit_add = build_last_admin_service(user)

    with pytest.raises(ApplicationError) as caught:
        await service.change_role(
            user.id,
            UserRoleRequest(role="student", reason="安全回归测试"),
            audit=audit_context(user),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "STATE_CONFLICT"
    assert user.role == "admin"
    assert user.revision == 1
    commit.assert_awaited_once()
    audit = audit_add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.action == "user.role_change"
    assert audit.result == "denied"
    assert audit.change_summary["blocked"] == "last_active_admin"


@pytest.mark.asyncio
async def test_demoting_another_admin_revokes_every_session() -> None:
    target = make_active_admin()
    service, commit, audit_add = build_last_admin_service(target)
    cast(AsyncMock, service._users.active_admin_count).return_value = 2
    revoke_all_sessions = AsyncMock()
    cast(Any, service._auth).revoke_all_sessions_for_user = revoke_all_sessions

    result = await service.change_role(
        target.id,
        UserRoleRequest(role="student", reason="安全回归测试"),
        audit=audit_context(make_active_admin()),
    )

    assert result.role == "student"
    assert target.role == "student"
    revoke_all_sessions.assert_awaited_once_with(target.id)
    commit.assert_awaited_once()
    audit = audit_add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.result == "success"
    assert audit.change_summary == {
        "from": "admin",
        "to": "student",
        "reason": "安全回归测试",
    }
