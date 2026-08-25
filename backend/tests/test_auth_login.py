from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.security import PasswordManager, PasswordVerification
from app.users.models import User
from app.users.repository import UserRepository


def make_user(*, status: str) -> User:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    return User(
        id=uuid4(),
        email="student@connect.hkust-gz.edu.cn",
        email_normalized="student@connect.hkust-gz.edu.cn",
        student_number="login-test-001",
        full_name="登录测试用户",
        password_hash="test-password-hash",
        role="student",
        status=status,
        cohort_id=None,
        direction_id=None,
        email_verified_at=now if status == "active" else None,
        disabled_at=None,
        disabled_by=None,
        disabled_reason=None,
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def build_service(
    user: User,
) -> tuple[AuthenticationService, AsyncMock, AsyncMock, Mock, AsyncMock]:
    commit = AsyncMock()
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=commit, rollback=AsyncMock()),
    )
    password_manager = cast(
        PasswordManager,
        SimpleNamespace(
            verify=Mock(return_value=PasswordVerification(valid=True)),
            hash=Mock(return_value="rehash-not-needed"),
            consume_dummy_verification=Mock(),
        ),
    )
    service = AuthenticationService(
        session,
        Settings(app_env="test"),
        clock=lambda: datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
        password_manager=password_manager,
    )
    get_by_email = AsyncMock(return_value=user)
    has_other_accounts = AsyncMock(return_value=True)
    service._users = cast(
        UserRepository,
        SimpleNamespace(
            get_by_email=get_by_email,
            get_by_id=AsyncMock(return_value=user),
            has_other_accounts=has_other_accounts,
        ),
    )
    count_security_events = AsyncMock(return_value=0)
    add_session = Mock()
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            count_security_events=count_security_events,
            add_security_event=Mock(),
            add_session=add_session,
            acquire_initial_admin_bootstrap_lock=AsyncMock(),
            revoke_all_sessions=AsyncMock(),
        ),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    return service, get_by_email, count_security_events, add_session, commit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    ["student", " Student@CONNECT.HKUST-GZ.EDU.CN "],
)
async def test_active_connect_user_can_login_with_username_or_email(
    identifier: str,
) -> None:
    user = make_user(status="active")
    service, get_by_email, count_security_events, add_session, commit = build_service(user)

    result = await service.login(
        identifier=identifier,
        password="correct-password",
        ip_prefix="192.0.2.0/24",
        user_agent_summary="Test / Test",
    )

    assert result.user.id == user.id
    assert result.user.role == "student"
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    assert (
        count_security_events.await_args_list[0].kwargs["email_normalized"]
        == "student@connect.hkust-gz.edu.cn"
    )
    add_session.assert_called_once()
    cast(AsyncMock, service._users.has_other_accounts).assert_awaited_once_with(user.id)
    cast(AsyncMock, service._auth.revoke_all_sessions).assert_not_awaited()
    cast(Mock, service._audit.add).assert_not_called()
    commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending_email", "disabled"])
async def test_inactive_user_cannot_bypass_status_with_username(status: str) -> None:
    service, get_by_email, _, add_session, commit = build_service(make_user(status=status))

    with pytest.raises(ApplicationError) as caught:
        await service.login(
            identifier="student",
            password="correct-password",
            ip_prefix="198.51.100.0/24",
            user_agent_summary="Test / Test",
        )

    assert caught.value.status_code == 401
    assert caught.value.code == "INVALID_CREDENTIALS"
    assert (
        caught.value.message == "登录失败。请检查用户名或邮箱与密码；新注册账号需先完成邮箱验证。"
    )
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    add_session.assert_not_called()
    cast(AsyncMock, service._auth.acquire_initial_admin_bootstrap_lock).assert_not_awaited()
    cast(AsyncMock, service._users.has_other_accounts).assert_not_awaited()
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_only_active_account_is_promoted_to_audited_admin_on_login() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    user = make_user(status="active")
    service, _, _, add_session, commit = build_service(user)
    has_other_accounts = cast(AsyncMock, service._users.has_other_accounts)
    has_other_accounts.return_value = False
    acquire_lock = cast(
        AsyncMock,
        service._auth.acquire_initial_admin_bootstrap_lock,
    )
    revoke_all_sessions = cast(AsyncMock, service._auth.revoke_all_sessions)
    audit_add = cast(Mock, service._audit.add)

    result = await service.login(
        identifier="student",
        password="correct-password",
        ip_prefix="192.0.2.0/24",
        user_agent_summary="Test / Test",
        request_id="single-account-login",
    )

    assert user.role == "admin"
    assert user.revision == 2
    assert result.user.role == "admin"
    has_other_accounts.assert_awaited_once_with(user.id)
    acquire_lock.assert_awaited_once()
    revoke_all_sessions.assert_awaited_once_with(user.id, now)
    session_record = add_session.call_args.args[0]
    assert session_record.idle_expires_at == now + timedelta(hours=4)
    audit = audit_add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.action == "user.single_account_admin_granted"
    assert audit.actor_user_id == user.id
    assert audit.request_id == "single-account-login"
    assert audit.ip_prefix == "192.0.2.0/24"
    assert audit.change_summary == {
        "from": "student",
        "to": "admin",
        "reason": "single_verified_account",
    }
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_session_list_returns_active_user_metadata() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    admin = make_user(status="active")
    admin.role = "admin"
    current_session = SimpleNamespace(
        id=uuid4(),
        created_at=now - timedelta(hours=1),
        last_seen_at=now,
        idle_expires_at=now + timedelta(hours=4),
        absolute_expires_at=now + timedelta(days=10),
        ip_prefix="192.0.2.0/24",
        user_agent_summary="Browser / Linux",
    )
    context = SimpleNamespace(user=admin, session=current_session)
    service = AuthenticationService(
        cast(AsyncSession, SimpleNamespace()),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    list_active_sessions = AsyncMock(return_value=[(current_session, admin)])
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(list_active_sessions=list_active_sessions),
    )

    result = await service.list_admin_sessions(context)

    list_active_sessions.assert_awaited_once_with(now=now)
    assert len(result) == 1
    assert result[0].user_id == admin.id
    assert result[0].user_role == "admin"
    assert result[0].is_current is True
    assert not hasattr(result[0], "token_hash")
