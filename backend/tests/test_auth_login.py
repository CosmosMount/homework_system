from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.dependencies import require_admin
from app.auth.models import Session
from app.auth.repository import AuthRepository
from app.auth.schemas import RegisterRequest
from app.auth.service import AuthenticatedContext, AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError, ErrorDetail
from app.core.security import PasswordManager, PasswordVerification
from app.users.models import User
from app.users.repository import UserRepository


class _UniqueViolationError(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__("duplicate key")
        self.constraint_name = constraint_name


def nested_unique_violation(constraint_name: str) -> IntegrityError:
    driver_error = _UniqueViolationError(constraint_name)
    adapter_error = Exception("asyncpg adapter error")
    adapter_error.__cause__ = driver_error
    return IntegrityError("INSERT INTO users", {}, adapter_error)


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
        last_active_at=None,
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
    touch_activity = AsyncMock()
    service._users = cast(
        UserRepository,
        SimpleNamespace(
            get_by_email=get_by_email,
            get_by_id=AsyncMock(return_value=user),
            has_other_accounts=has_other_accounts,
            touch_activity=touch_activity,
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
            lock_sessions_for_user=AsyncMock(),
            revoke_all_sessions=AsyncMock(),
        ),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    return service, get_by_email, count_security_events, add_session, commit


def build_authenticate_service(
    user: User,
    session_record: Session,
    *,
    now: datetime,
) -> tuple[AuthenticationService, AsyncMock, AsyncMock, AsyncMock]:
    commit = AsyncMock()
    rollback = AsyncMock()
    service = AuthenticationService(
        cast(
            AsyncSession,
            SimpleNamespace(commit=commit, rollback=rollback),
        ),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    find_session = AsyncMock(return_value=(session_record, user))
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(find_session_with_user=find_session),
    )
    touch_activity = AsyncMock()
    service._users = cast(
        UserRepository,
        SimpleNamespace(touch_activity=touch_activity),
    )
    service._sessions = cast(
        Any,
        SimpleNamespace(
            candidate_hashes=Mock(return_value=("candidate-hash",)),
            current_hash=Mock(return_value=session_record.token_hash),
        ),
    )
    return service, touch_activity, commit, rollback


def make_session(user: User, *, now: datetime, last_seen_at: datetime) -> Session:
    return Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="current-hash",
        csrf_secret_hash="csrf-hash",
        created_at=last_seen_at,
        last_seen_at=last_seen_at,
        idle_expires_at=now + timedelta(hours=1),
        absolute_expires_at=now + timedelta(days=1),
        revoked_at=None,
        student_view=False,
        ip_prefix="192.0.2.0/24",
        user_agent_summary="Test / Test",
    )


@pytest.mark.asyncio
async def test_registration_has_no_persistent_application_rate_limit() -> None:
    service, _, count_security_events, _, commit = build_service(make_user(status="active"))
    count_security_events.return_value = 30

    with pytest.raises(ApplicationError) as caught:
        await service.register(
            RegisterRequest(
                full_name="校外测试用户",
                student_number="registration-window-test",
                email="student@example.com",
                password="Correct-Horse-Battery-Staple-2026!",
            ),
            ip_prefix="198.51.100.0/24",
        )

    assert caught.value.status_code == 400
    assert caught.value.details[0].reason == "INVALID_CAMPUS_EMAIL"
    count_security_events.assert_not_awaited()
    cast(Mock, service._auth.add_security_event).assert_called_once()
    commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint_name", "field", "reason"),
    [
        ("uq_users_email_normalized", "email", "EMAIL_ALREADY_REGISTERED"),
        (
            "uq_users_student_number",
            "student_number",
            "STUDENT_NUMBER_ALREADY_REGISTERED",
        ),
    ],
)
async def test_registration_maps_nested_asyncpg_unique_violation(
    constraint_name: str,
    field: str,
    reason: str,
) -> None:
    service, _, _, _, commit = build_service(make_user(status="active"))
    commit.side_effect = [None, nested_unique_violation(constraint_name)]
    service._users = cast(UserRepository, SimpleNamespace(add=Mock()))
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            add_security_event=Mock(),
            invalidate_tokens=AsyncMock(),
            add_one_time_token=Mock(),
        ),
    )
    service._outbox = cast(Any, SimpleNamespace(add=Mock()))

    with pytest.raises(ApplicationError) as caught:
        await service.register(
            RegisterRequest(
                full_name="注册测试用户",
                student_number="registration-unique-test",
                email="registration.test@connect.hkust-gz.edu.cn",
                password="Correct-Horse-Battery-Staple-2026!",
            ),
            ip_prefix="198.51.100.0/24",
        )

    assert caught.value.status_code == 400
    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.details == [ErrorDetail(field=field, reason=reason)]
    cast(AsyncMock, service._session.rollback).assert_awaited_once()


@pytest.mark.asyncio
async def test_registration_does_not_misclassify_unknown_integrity_constraint() -> None:
    service, _, _, _, commit = build_service(make_user(status="active"))
    integrity_error = nested_unique_violation("uq_unrelated_constraint")
    commit.side_effect = [None, integrity_error]
    service._users = cast(UserRepository, SimpleNamespace(add=Mock()))
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            add_security_event=Mock(),
            invalidate_tokens=AsyncMock(),
            add_one_time_token=Mock(),
        ),
    )
    service._outbox = cast(Any, SimpleNamespace(add=Mock()))

    with pytest.raises(IntegrityError) as caught:
        await service.register(
            RegisterRequest(
                full_name="注册测试用户",
                student_number="registration-unknown-constraint",
                email="unknown.constraint@connect.hkust-gz.edu.cn",
                password="Correct-Horse-Battery-Staple-2026!",
            ),
            ip_prefix="198.51.100.0/24",
        )

    assert caught.value is integrity_error
    cast(AsyncMock, service._session.rollback).assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_resend_has_no_persistent_application_rate_limit() -> None:
    service, get_by_email, count_security_events, _, commit = build_service(
        make_user(status="active")
    )
    get_by_email.return_value = None
    count_security_events.return_value = 30

    await service.resend_verification(
        "student@connect.hkust-gz.edu.cn",
        ip_prefix="198.51.100.0/24",
    )

    count_security_events.assert_not_awaited()
    cast(Mock, service._auth.add_security_event).assert_called_once()
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    assert commit.await_count == 2


@pytest.mark.asyncio
async def test_password_reset_request_has_no_persistent_application_rate_limit() -> None:
    service, get_by_email, count_security_events, _, commit = build_service(
        make_user(status="active")
    )
    get_by_email.return_value = None
    count_security_events.return_value = 30

    await service.request_password_reset(
        "student@connect.hkust-gz.edu.cn",
        ip_prefix="198.51.100.0/24",
    )

    count_security_events.assert_not_awaited()
    cast(Mock, service._auth.add_security_event).assert_called_once()
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    assert commit.await_count == 2


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
    count_security_events.assert_not_awaited()
    add_session.assert_called_once()
    cast(AsyncMock, service._users.has_other_accounts).assert_awaited_once_with(user.id)
    cast(AsyncMock, service._auth.lock_sessions_for_user).assert_awaited_once_with(user.id)
    cast(AsyncMock, service._auth.revoke_all_sessions).assert_not_awaited()
    cast(AsyncMock, service._users.touch_activity).assert_awaited_once_with(
        user,
        at=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
    )
    cast(Mock, service._audit.add).assert_not_called()
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_correct_real_argon2id_password_is_not_blocked_by_prior_failures() -> None:
    password = "Correct-Horse-Battery-Staple-2026!"
    password_manager = PasswordManager()
    password_hash = password_manager.hash(password)
    user = make_user(status="active")
    user.password_hash = password_hash
    service, get_by_email, count_security_events, add_session, commit = build_service(user)
    service._passwords = password_manager
    count_security_events.return_value = 30

    result = await service.login(
        identifier="student",
        password=password,
        ip_prefix="192.0.2.0/24",
        user_agent_summary="Test / Test",
    )

    assert result.user.id == user.id
    assert user.password_hash == password_hash
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    count_security_events.assert_not_awaited()
    add_session.assert_called_once()
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_password_is_verified_before_existing_failure_limit_is_applied() -> None:
    user = make_user(status="active")
    service, get_by_email, count_security_events, add_session, commit = build_service(user)
    password_verify = cast(Mock, service._passwords.verify)
    password_verify.return_value = PasswordVerification(valid=False)
    count_security_events.side_effect = [5, 0]

    with pytest.raises(ApplicationError) as caught:
        await service.login(
            identifier=" Student@CONNECT.HKUST-GZ.EDU.CN ",
            password="wrong-password",
            ip_prefix="198.51.100.0/24",
            user_agent_summary="Test / Test",
        )

    assert caught.value.status_code == 429
    assert caught.value.code == "RATE_LIMITED"
    assert caught.value.headers == {"Retry-After": "600"}
    get_by_email.assert_awaited_once_with("student@connect.hkust-gz.edu.cn")
    password_verify.assert_called_once_with(user.password_hash, "wrong-password")
    assert (
        count_security_events.await_args_list[0].kwargs["email_normalized"]
        == "student@connect.hkust-gz.edu.cn"
    )
    add_session.assert_not_called()
    cast(Mock, service._auth.add_security_event).assert_not_called()
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_account_uses_dummy_password_check_before_ip_limit() -> None:
    service, get_by_email, count_security_events, add_session, commit = build_service(
        make_user(status="active")
    )
    get_by_email.return_value = None
    dummy_verification = cast(Mock, service._passwords.consume_dummy_verification)
    count_security_events.side_effect = [0, 30]

    with pytest.raises(ApplicationError) as caught:
        await service.login(
            identifier="unknown",
            password="wrong-password",
            ip_prefix="198.51.100.0/24",
            user_agent_summary="Test / Test",
        )

    assert caught.value.status_code == 429
    assert caught.value.code == "RATE_LIMITED"
    assert caught.value.headers == {"Retry-After": "600"}
    get_by_email.assert_awaited_once_with("unknown@connect.hkust-gz.edu.cn")
    dummy_verification.assert_called_once_with("wrong-password")
    assert (
        count_security_events.await_args_list[0].kwargs["email_normalized"]
        == "unknown@connect.hkust-gz.edu.cn"
    )
    add_session.assert_not_called()
    cast(Mock, service._auth.add_security_event).assert_not_called()
    commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    ["student", " Student@CONNECT.HKUST-GZ.EDU.CN "],
)
async def test_failed_connect_identifiers_share_normalized_email_limit(
    identifier: str,
) -> None:
    service, _, count_security_events, add_session, commit = build_service(
        make_user(status="active")
    )
    cast(Mock, service._passwords.verify).return_value = PasswordVerification(valid=False)

    with pytest.raises(ApplicationError):
        await service.login(
            identifier=identifier,
            password="wrong-password",
            ip_prefix="198.51.100.0/24",
            user_agent_summary="Test / Test",
        )

    assert (
        count_security_events.await_args_list[0].kwargs["email_normalized"]
        == "student@connect.hkust-gz.edu.cn"
    )
    add_session.assert_not_called()
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
    cast(AsyncMock, service._auth.lock_sessions_for_user).assert_not_awaited()
    cast(AsyncMock, service._users.has_other_accounts).assert_not_awaited()
    cast(AsyncMock, service._users.touch_activity).assert_not_awaited()
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
    cast(AsyncMock, service._auth.lock_sessions_for_user).assert_awaited_once_with(user.id)
    revoke_all_sessions.assert_awaited_once_with(user.id, now)
    cast(AsyncMock, service._users.touch_activity).assert_awaited_once_with(
        user,
        at=now,
    )
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
async def test_authenticated_request_refreshes_activity_at_five_minute_boundary() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    user = make_user(status="active")
    user.last_active_at = now - timedelta(minutes=5)
    session_record = make_session(
        user,
        now=now,
        last_seen_at=now - timedelta(minutes=5),
    )
    service, touch_activity, commit, rollback = build_authenticate_service(
        user,
        session_record,
        now=now,
    )

    context = await service.authenticate("raw-session-token")

    assert context.user is user
    assert context.session is session_record
    assert session_record.last_seen_at == now
    assert session_record.idle_expires_at == now + timedelta(hours=12)
    touch_activity.assert_awaited_once_with(user, at=now)
    commit.assert_awaited_once()
    rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticated_request_within_throttle_does_not_write_activity() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    user = make_user(status="active")
    last_seen_at = now - timedelta(minutes=4)
    user.last_active_at = last_seen_at
    session_record = make_session(user, now=now, last_seen_at=last_seen_at)
    service, touch_activity, commit, rollback = build_authenticate_service(
        user,
        session_record,
        now=now,
    )

    await service.authenticate("raw-session-token")

    assert session_record.last_seen_at == last_seen_at
    touch_activity.assert_not_awaited()
    commit.assert_not_awaited()
    rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticated_request_repairs_missing_account_activity() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    user = make_user(status="active")
    user.last_active_at = None
    session_record = make_session(
        user,
        now=now,
        last_seen_at=now - timedelta(minutes=1),
    )
    service, touch_activity, commit, _ = build_authenticate_service(
        user,
        session_record,
        now=now,
    )

    await service.authenticate("raw-session-token")

    touch_activity.assert_awaited_once_with(user, at=now)
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_session_does_not_update_account_activity() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    user = make_user(status="active")
    user.status = "disabled"
    user.last_active_at = now - timedelta(days=20)
    session_record = make_session(
        user,
        now=now,
        last_seen_at=now - timedelta(minutes=10),
    )
    service, touch_activity, commit, rollback = build_authenticate_service(
        user,
        session_record,
        now=now,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.authenticate("raw-session-token")

    assert caught.value.status_code == 401
    assert session_record.revoked_at == now
    touch_activity.assert_not_awaited()
    commit.assert_awaited_once()
    rollback.assert_not_awaited()


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
    context = cast(AuthenticatedContext, SimpleNamespace(user=admin, session=current_session))
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


@pytest.mark.asyncio
async def test_admin_can_toggle_student_view_without_changing_real_role() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    admin = make_user(status="active")
    admin.role = "admin"
    session_record = SimpleNamespace(id=uuid4(), student_view=False)
    context = AuthenticatedContext(
        user=admin,
        session=cast(Session, session_record),
    )
    commit = AsyncMock()
    service = AuthenticationService(
        cast(AsyncSession, SimpleNamespace(commit=commit)),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))

    enabled = await service.set_student_view(
        context,
        enabled=True,
        request_id="student-view-on",
        ip_prefix="192.0.2.0/24",
    )

    assert enabled.role == "admin"
    assert enabled.student_view is True
    assert context.effective_role == "student"
    assert context.is_admin is False
    with pytest.raises(ApplicationError) as admin_guard:
        require_admin(context)
    assert admin_guard.value.status_code == 403
    assert admin.role == "admin"
    assert session_record.student_view is True
    first_audit = cast(Mock, service._audit.add).call_args.args[0]
    assert isinstance(first_audit, AuditLog)
    assert first_audit.action == "auth.student_view.enable"

    disabled = await service.set_student_view(
        context,
        enabled=False,
        request_id="student-view-off",
        ip_prefix="192.0.2.0/24",
    )

    assert disabled.role == "admin"
    assert disabled.student_view is False
    assert context.effective_role == "admin"
    assert context.is_admin is True
    assert session_record.student_view is False
    assert [call.args[0].action for call in cast(Mock, service._audit.add).call_args_list] == [
        "auth.student_view.enable",
        "auth.student_view.disable",
    ]


@pytest.mark.asyncio
async def test_student_cannot_enable_student_view() -> None:
    user = make_user(status="active")
    session_record = SimpleNamespace(id=uuid4(), student_view=False)
    context = AuthenticatedContext(
        user=user,
        session=cast(Session, session_record),
    )
    commit = AsyncMock()
    service = AuthenticationService(
        cast(AsyncSession, SimpleNamespace(commit=commit)),
        Settings(app_env="test"),
    )

    with pytest.raises(ApplicationError) as caught:
        await service.set_student_view(
            context,
            enabled=True,
            request_id="student-view-denied",
            ip_prefix="192.0.2.0/24",
        )

    assert caught.value.status_code == 403
    assert session_record.student_view is False
    commit.assert_not_awaited()
