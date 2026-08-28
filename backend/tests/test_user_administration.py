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
from app.auth.service import AuthenticatedContext, AuthenticationService
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
        last_active_at=now,
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
    cast(Any, service._auth).acquire_admin_lifecycle_lock = AsyncMock()
    cast(Any, service._auth).lock_sessions_for_user = AsyncMock()
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


def make_account(
    *,
    now: datetime,
    role: str = "student",
    status: str = "active",
    created_at: datetime | None = None,
    email_verified_at: datetime | None = None,
    last_active_at: datetime | None = None,
) -> User:
    return User(
        id=uuid4(),
        email="account@connect.hkust-gz.edu.cn",
        email_normalized="account@connect.hkust-gz.edu.cn",
        student_number="account-test",
        full_name="账号测试用户",
        password_hash="not-a-real-password-hash",
        role=role,
        status=status,
        cohort_id=None,
        direction_id=None,
        email_verified_at=(
            email_verified_at if email_verified_at is not None else now - timedelta(days=30)
        ),
        last_active_at=last_active_at,
        disabled_at=now if status == "disabled" else None,
        disabled_by=None,
        disabled_reason="测试禁用" if status == "disabled" else None,
        password_changed_at=now - timedelta(days=30),
        created_at=created_at or now - timedelta(days=30),
        updated_at=now,
        revision=1,
    )


def build_activity_service(
    *,
    now: datetime,
    users: list[User],
    total: int | None = None,
) -> tuple[UserAdministrationService, AsyncMock]:
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock()),
    )
    service = UserAdministrationService(
        session,
        Settings(app_env="test"),
        clock=lambda: now,
    )
    list_users = AsyncMock(return_value=(users, len(users) if total is None else total))
    service._users = cast(
        UserRepository,
        SimpleNamespace(list_users=list_users),
    )
    return service, list_users


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


@pytest.mark.asyncio
async def test_activity_response_uses_strict_ten_day_active_only_boundary() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    exact_boundary = make_account(
        now=now,
        last_active_at=now - timedelta(days=10),
    )
    over_boundary = make_account(
        now=now,
        last_active_at=now - timedelta(days=10, seconds=1),
    )
    disabled_old = make_account(
        now=now,
        status="disabled",
        last_active_at=now - timedelta(days=20),
    )
    never_entered_recently_verified = make_account(
        now=now,
        created_at=now - timedelta(days=40),
        email_verified_at=now - timedelta(days=9),
        last_active_at=None,
    )
    never_entered_old_verification = make_account(
        now=now,
        created_at=now - timedelta(days=40),
        email_verified_at=now - timedelta(days=11),
        last_active_at=None,
    )
    accounts = [
        exact_boundary,
        over_boundary,
        disabled_old,
        never_entered_recently_verified,
        never_entered_old_verification,
    ]
    service, _ = build_activity_service(now=now, users=accounts)

    page = await service.list_users(
        page=1,
        page_size=20,
        status=None,
        role=None,
        cohort_id=None,
        direction_id=None,
        search=None,
        activity=None,
    )

    responses = {item.id: item for item in page.items}
    assert responses[exact_boundary.id].is_inactive is False
    assert responses[exact_boundary.id].inactive_days == 10
    assert responses[over_boundary.id].is_inactive is True
    assert responses[over_boundary.id].inactive_days == 10
    assert responses[disabled_old.id].is_inactive is False
    assert responses[disabled_old.id].inactive_days == 20
    assert responses[never_entered_recently_verified.id].last_active_at is None
    assert responses[never_entered_recently_verified.id].is_inactive is False
    assert responses[never_entered_recently_verified.id].inactive_days == 9
    assert responses[never_entered_old_verification.id].last_active_at is None
    assert responses[never_entered_old_verification.id].is_inactive is True
    assert responses[never_entered_old_verification.id].inactive_days == 11


@pytest.mark.asyncio
async def test_inactive_filter_preserves_repository_total_and_page_contract() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    inactive = make_account(
        now=now,
        last_active_at=now - timedelta(days=11),
    )
    service, list_users = build_activity_service(
        now=now,
        users=[inactive],
        total=26,
    )

    page = await service.list_users(
        page=3,
        page_size=5,
        status=None,
        role="student",
        cohort_id=None,
        direction_id=None,
        search="account",
        activity="inactive",
    )

    assert page.page == 3
    assert page.page_size == 5
    assert page.total == 26
    assert [item.id for item in page.items] == [inactive.id]
    list_users.assert_awaited_once_with(
        page=3,
        page_size=5,
        status=None,
        role="student",
        cohort_id=None,
        direction_id=None,
        search="account",
        activity="inactive",
        inactive_before=now - timedelta(days=10),
    )


def build_delete_service(
    *,
    now: datetime,
    target: User,
    latest_session_activity: datetime | None = None,
    active_admin_count: int = 2,
    delete_succeeds: bool = True,
) -> tuple[
    UserAdministrationService,
    SimpleNamespace,
    SimpleNamespace,
    AsyncMock,
    Mock,
]:
    commit = AsyncMock()
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=commit, rollback=AsyncMock()),
    )
    service = UserAdministrationService(
        session,
        Settings(app_env="test"),
        clock=lambda: now,
    )
    authentication = SimpleNamespace(
        acquire_admin_lifecycle_lock=AsyncMock(),
        lock_sessions_for_user=AsyncMock(return_value=latest_session_activity),
        lock_one_time_tokens_for_user=AsyncMock(),
    )

    async def touch_activity(user: User, *, at: datetime) -> datetime:
        user.last_active_at = at
        return at

    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=target),
        touch_activity=AsyncMock(side_effect=touch_activity),
        active_admin_count=AsyncMock(return_value=active_admin_count),
        delete_if_unreferenced=AsyncMock(return_value=delete_succeeds),
    )
    audit_add = Mock()
    service._auth = cast(AuthenticationService, authentication)
    service._users = cast(UserRepository, users)
    service._audit = cast(AuditRepository, SimpleNamespace(add=audit_add))
    return service, authentication, users, commit, audit_add


@pytest.mark.asyncio
async def test_current_admin_cannot_delete_self() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        role="admin",
        last_active_at=now - timedelta(days=11),
    )
    service, authentication, users, commit, audit_add = build_delete_service(
        now=now,
        target=target,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="不得删除当前账号",
            audit=audit_context(target),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "STATE_CONFLICT"
    assert caught.value.message == "不能删除当前登录的管理员账号。"
    authentication.acquire_admin_lifecycle_lock.assert_awaited_once()
    authentication.lock_sessions_for_user.assert_not_awaited()
    users.delete_if_unreferenced.assert_not_awaited()
    commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    assert denial.result == "denied"
    assert denial.change_summary["blocked"] == "current_actor"


@pytest.mark.asyncio
async def test_exactly_ten_days_inactive_account_cannot_be_deleted() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        last_active_at=now - timedelta(days=10),
    )
    service, _, users, commit, audit_add = build_delete_service(
        now=now,
        target=target,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="边界保护测试",
            audit=audit_context(make_active_admin()),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "STATE_CONFLICT"
    assert caught.value.message == "只能删除严格超过 10 天未进入系统的激活账号。"
    users.delete_if_unreferenced.assert_not_awaited()
    commit.assert_awaited_once()
    assert audit_add.call_args.args[0].change_summary["blocked"] == "not_inactive"


@pytest.mark.asyncio
async def test_recent_locked_session_prevents_stale_account_deletion() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        last_active_at=now - timedelta(days=20),
    )
    recent_session = now - timedelta(days=1)
    service, authentication, users, commit, audit_add = build_delete_service(
        now=now,
        target=target,
        latest_session_activity=recent_session,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="会话竞态保护测试",
            audit=audit_context(make_active_admin()),
        )

    assert caught.value.code == "STATE_CONFLICT"
    authentication.lock_sessions_for_user.assert_awaited_once_with(target.id)
    users.touch_activity.assert_awaited_once_with(target, at=recent_session)
    users.delete_if_unreferenced.assert_not_awaited()
    commit.assert_awaited_once()
    assert audit_add.call_args.args[0].change_summary["blocked"] == "not_inactive"


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_permanently_deleted() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        role="admin",
        last_active_at=now - timedelta(days=11),
    )
    service, _, users, commit, audit_add = build_delete_service(
        now=now,
        target=target,
        active_admin_count=1,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="最后管理员保护测试",
            audit=audit_context(make_active_admin()),
        )

    assert caught.value.code == "STATE_CONFLICT"
    assert caught.value.message == "不能删除系统中最后一个激活管理员。"
    users.active_admin_count.assert_awaited_once()
    users.delete_if_unreferenced.assert_not_awaited()
    commit.assert_awaited_once()
    assert audit_add.call_args.args[0].change_summary["blocked"] == "last_active_admin"


@pytest.mark.asyncio
async def test_retained_business_data_returns_stable_delete_error() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        last_active_at=now - timedelta(days=11),
    )
    service, _, users, commit, audit_add = build_delete_service(
        now=now,
        target=target,
        delete_succeeds=False,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="业务外键保护测试",
            audit=audit_context(make_active_admin()),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "USER_DELETE_BLOCKED"
    assert caught.value.message == "账号存在必须保留的业务记录，请改为禁用账号。"
    users.delete_if_unreferenced.assert_awaited_once_with(target)
    commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    assert denial.result == "denied"
    assert denial.change_summary["blocked"] == "retained_business_data"


@pytest.mark.asyncio
async def test_delete_user_locks_tokens_and_sessions_before_user_row() -> None:
    now = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    target = make_active_admin()
    target.email = "inactive@connect.hkust-gz.edu.cn"
    target.email_normalized = target.email
    target.student_number = "inactive-test"
    target.role = "student"
    target.created_at = now - timedelta(days=30)
    target.email_verified_at = now - timedelta(days=20)
    target.last_active_at = now - timedelta(days=11)

    commit = AsyncMock()
    session = cast(
        AsyncSession,
        SimpleNamespace(commit=commit, rollback=AsyncMock()),
    )
    service = UserAdministrationService(
        session,
        Settings(app_env="test"),
        clock=lambda: now,
    )
    lock_order: list[str] = []

    async def acquire_lifecycle_lock() -> None:
        lock_order.append("advisory")

    async def lock_sessions(_user_id: Any) -> None:
        lock_order.append("sessions")

    async def lock_tokens(_user_id: Any) -> None:
        lock_order.append("one_time_tokens")

    async def get_user(_user_id: Any, *, for_update: bool = False) -> User:
        lock_order.append("user_for_update" if for_update else "user_read")
        return target

    async def delete_user(_user: User) -> bool:
        lock_order.append("delete")
        return True

    service._auth = cast(
        AuthenticationService,
        SimpleNamespace(
            acquire_admin_lifecycle_lock=acquire_lifecycle_lock,
            lock_sessions_for_user=lock_sessions,
            lock_one_time_tokens_for_user=lock_tokens,
        ),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(
            get_by_id=get_user,
            delete_if_unreferenced=delete_user,
        ),
    )
    audit_add = Mock()
    service._audit = cast(AuditRepository, SimpleNamespace(add=audit_add))

    await service.delete_user(
        target.id,
        reason="清理长期未进入账号",
        audit=audit_context(make_active_admin()),
    )

    assert lock_order == [
        "advisory",
        "user_read",
        "one_time_tokens",
        "sessions",
        "user_for_update",
        "delete",
    ]
    commit.assert_awaited_once()
    assert audit_add.call_args.args[0].action == "user.delete"


class _DatabaseError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class _FailingNestedTransaction:
    def __init__(self, error: IntegrityError) -> None:
        self._error = error

    async def __aenter__(self) -> None:
        raise self._error

    async def __aexit__(self, *args: Any) -> None:
        return None


def repository_raising(error: IntegrityError) -> UserRepository:
    session = cast(
        AsyncSession,
        SimpleNamespace(
            begin_nested=Mock(return_value=_FailingNestedTransaction(error)),
        ),
    )
    return UserRepository(session)


@pytest.mark.asyncio
async def test_delete_if_unreferenced_maps_foreign_key_violation_to_false() -> None:
    error = IntegrityError("DELETE FROM users", {}, _DatabaseError("23503"))
    repository = repository_raising(error)

    assert await repository.delete_if_unreferenced(make_active_admin()) is False


@pytest.mark.asyncio
async def test_delete_if_unreferenced_reraises_other_integrity_errors() -> None:
    error = IntegrityError("DELETE FROM users", {}, _DatabaseError("40001"))
    repository = repository_raising(error)

    with pytest.raises(IntegrityError) as caught:
        await repository.delete_if_unreferenced(make_active_admin())

    assert caught.value is error
