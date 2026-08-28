from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.models import OneTimeToken
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticationService
from app.core.config import Settings
from app.core.security import sha256_hexdigest
from app.users.models import User
from app.users.repository import UserRepository


def make_pending_user(now: datetime) -> User:
    return User(
        id=uuid4(),
        email="first@connect.hkust-gz.edu.cn",
        email_normalized="first@connect.hkust-gz.edu.cn",
        student_number="bootstrap-001",
        full_name="初始用户",
        password_hash="not-a-real-password-hash",
        role="student",
        status="pending_email",
        cohort_id=None,
        direction_id=None,
        email_verified_at=None,
        disabled_at=None,
        disabled_by=None,
        disabled_reason=None,
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_verification_token(user: User, now: datetime, raw_token: str) -> OneTimeToken:
    return OneTimeToken(
        id=uuid4(),
        user_id=user.id,
        purpose="email_verification",
        token_hash=sha256_hexdigest(raw_token),
        expires_at=now + timedelta(hours=1),
        used_at=None,
        created_at=now,
    )


def build_service(
    *,
    user: User,
    token: OneTimeToken,
    now: datetime,
    has_active_user: bool,
) -> tuple[AuthenticationService, AsyncMock, AsyncMock, AsyncMock, Mock]:
    commit = AsyncMock()
    rollback = AsyncMock()
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=commit, rollback=rollback),
    )
    service = AuthenticationService(
        session,
        Settings(app_env="test"),
        clock=lambda: now,
    )
    acquire_lock = AsyncMock()
    invalidate_tokens = AsyncMock()
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            get_one_time_token_for_update=AsyncMock(return_value=token),
            acquire_initial_admin_bootstrap_lock=acquire_lock,
            has_active_user=AsyncMock(return_value=has_active_user),
            invalidate_tokens=invalidate_tokens,
        ),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(get_by_id=AsyncMock(return_value=user)),
    )
    audit_add = Mock()
    service._audit = cast(AuditRepository, SimpleNamespace(add=audit_add))
    return service, commit, acquire_lock, invalidate_tokens, audit_add


@pytest.mark.asyncio
async def test_first_verified_user_becomes_audited_initial_admin() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    raw_token = "first-verification-token"
    user = make_pending_user(now)
    token = make_verification_token(user, now, raw_token)
    service, commit, acquire_lock, invalidate_tokens, audit_add = build_service(
        user=user,
        token=token,
        now=now,
        has_active_user=False,
    )
    lock_order: list[str] = []
    acquire_lock.side_effect = lambda: lock_order.append("advisory")
    get_token = cast(AsyncMock, service._auth.get_one_time_token_for_update)

    def lock_token(_token_hash: str) -> OneTimeToken:
        lock_order.append("one_time_token")
        return token

    get_token.side_effect = lock_token
    add_assignment_audiences = AsyncMock(return_value=0)
    service._assignments = cast(
        AssignmentRepository,
        SimpleNamespace(
            add_open_assignment_audiences_for_student=add_assignment_audiences,
        ),
    )

    response = await service.confirm_email(
        raw_token,
        request_id="bootstrap-request",
        ip_prefix="192.0.2.0/24",
    )

    assert response.status == "active"
    assert user.status == "active"
    assert user.role == "admin"
    assert user.email_verified_at == now
    assert user.revision == 2
    assert token.used_at == now
    assert lock_order[:2] == ["advisory", "one_time_token"]
    acquire_lock.assert_awaited_once()
    invalidate_tokens.assert_awaited_once_with(
        user_id=user.id,
        purpose="email_verification",
        now=now,
        exclude_id=token.id,
    )
    add_assignment_audiences.assert_not_awaited()
    commit.assert_awaited_once()
    audit = audit_add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.action == "user.initial_admin_granted"
    assert audit.actor_user_id == user.id
    assert audit.request_id == "bootstrap-request"
    assert audit.ip_prefix == "192.0.2.0/24"
    assert audit.change_summary == {
        "from": "student",
        "to": "admin",
        "reason": "first_verified_user",
    }


@pytest.mark.asyncio
async def test_later_verified_user_remains_student_without_bootstrap_audit() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    raw_token = "later-verification-token"
    user = make_pending_user(now)
    token = make_verification_token(user, now, raw_token)
    service, commit, acquire_lock, _, audit_add = build_service(
        user=user,
        token=token,
        now=now,
        has_active_user=True,
    )
    add_assignment_audiences = AsyncMock(return_value=1)
    service._assignments = cast(
        AssignmentRepository,
        SimpleNamespace(
            add_open_assignment_audiences_for_student=add_assignment_audiences,
        ),
    )

    await service.confirm_email(
        raw_token,
        request_id="later-request",
        ip_prefix="198.51.100.0/24",
    )

    assert user.status == "active"
    assert user.role == "student"
    add_assignment_audiences.assert_awaited_once_with(user=user, created_at=now)
    acquire_lock.assert_awaited_once()
    commit.assert_awaited_once()
    audit_add.assert_not_called()
