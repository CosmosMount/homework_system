import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.users.models import User
from app.users.repository import (
    AccountErasurePreparation,
    AccountObjectCleanup,
    UserRepository,
)
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


@pytest.mark.parametrize(
    ("search", "expected_value"),
    [
        ("管理员", "admin"),
        ("学生", "student"),
        ("正常", "active"),
        ("待验证", "pending_email"),
        ("已禁用", "disabled"),
    ],
)
@pytest.mark.asyncio
async def test_repository_user_search_matches_localized_and_enum_role_status_labels(
    search: str,
    expected_value: str,
) -> None:
    scalar = AsyncMock(return_value=0)
    scalars = AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=[])))
    repository = UserRepository(cast(AsyncSession, SimpleNamespace(scalar=scalar, scalars=scalars)))

    await repository.list_users(
        page=1,
        page_size=20,
        status=None,
        role=None,
        cohort_id=None,
        direction_id=None,
        search=search,
        activity=None,
        inactive_before=None,
    )

    assert scalars.await_args is not None
    statement = scalars.await_args.args[0]
    parameter_values = statement.compile().params.values()
    assert any(
        value == expected_value or isinstance(value, (list, tuple)) and expected_value in value
        for value in parameter_values
    )

    await repository.list_users(
        page=1,
        page_size=20,
        status=None,
        role=None,
        cohort_id=None,
        direction_id=None,
        search=expected_value.upper(),
        activity=None,
        inactive_before=None,
    )

    assert scalars.await_args is not None
    english_statement = scalars.await_args.args[0]
    english_parameter_values = english_statement.compile().params.values()
    assert any(
        value == expected_value or isinstance(value, (list, tuple)) and expected_value in value
        for value in english_parameter_values
    )


@pytest.mark.asyncio
async def test_repository_user_search_treats_like_wildcards_as_text() -> None:
    scalars = AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=[])))
    scalar = AsyncMock(return_value=0)
    repository = UserRepository(
        cast(
            AsyncSession,
            SimpleNamespace(scalar=scalar, scalars=scalars),
        )
    )

    await repository.list_users(
        page=1,
        page_size=20,
        status=None,
        role=None,
        cohort_id=None,
        direction_id=None,
        search=r"account\%_",
        activity=None,
        inactive_before=None,
    )

    assert scalars.await_args is not None
    statement = scalars.await_args.args[0]
    assert r"%account\\\%\_%" in statement.compile().params.values()
    assert scalar.await_args is not None
    count_statement = scalar.await_args.args[0]
    compiled_statement = str(statement.compile())
    assert "ESCAPE" in compiled_statement
    assert "users.email_normalized" in compiled_statement
    assert "users.full_name" in compiled_statement
    assert "users.student_number" in compiled_statement
    assert count_statement.whereclause.compare(statement.whereclause)


def build_delete_service(
    *,
    now: datetime,
    target: User,
    actor: User | None = None,
    active_admin_count: int = 2,
    password_valid: bool = True,
    preparation: AccountErasurePreparation | None = None,
) -> tuple[
    UserAdministrationService,
    SimpleNamespace,
    SimpleNamespace,
    SimpleNamespace,
    Mock,
    Mock,
]:
    current_actor = actor or make_active_admin()
    commit = AsyncMock()
    rollback = AsyncMock()
    flush = AsyncMock()
    session_namespace = SimpleNamespace(commit=commit, rollback=rollback, flush=flush)
    session = cast(AsyncSession, session_namespace)
    service = UserAdministrationService(
        session,
        Settings(app_env="test"),
        clock=lambda: now,
    )
    authentication = SimpleNamespace(
        acquire_admin_lifecycle_lock=AsyncMock(),
        lock_sessions_for_user=AsyncMock(),
        lock_one_time_tokens_for_user=AsyncMock(),
        verify_current_password=Mock(return_value=password_valid),
    )

    async def get_user(user_id: Any, *, for_update: bool = False) -> User | None:
        del for_update
        if user_id == target.id:
            return target
        if user_id == current_actor.id:
            return current_actor
        return None

    resolved_preparation = preparation or AccountErasurePreparation(
        object_cleanups=(),
        deletion_counts={"submissions": 0, "personal_files": 0},
        teams_transferred=0,
        teams_dissolved=0,
        teams_invalidated=0,
    )
    users = SimpleNamespace(
        get_by_id=AsyncMock(side_effect=get_user),
        active_admin_count=AsyncMock(return_value=active_admin_count),
        prepare_account_erasure=AsyncMock(return_value=resolved_preparation),
        erase_account=AsyncMock(),
    )
    audit_add = Mock()
    outbox_add = Mock()
    service._auth = cast(AuthenticationService, authentication)
    service._users = cast(UserRepository, users)
    service._audit = cast(AuditRepository, SimpleNamespace(add=audit_add))
    service._outbox = cast(Any, SimpleNamespace(add=outbox_add))
    return service, authentication, users, session_namespace, audit_add, outbox_add


@pytest.mark.asyncio
async def test_current_admin_must_use_self_service_instead_of_admin_delete() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, role="admin", last_active_at=now)
    service, authentication, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=target,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="管理员本人申请删除",
            current_password="current-password",
            confirmation_email=target.email,
            backup_confirmed=True,
            audit=audit_context(target),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "STATE_CONFLICT"
    assert "个人资料页" in caught.value.message
    authentication.acquire_admin_lifecycle_lock.assert_awaited_once()
    authentication.lock_one_time_tokens_for_user.assert_awaited_once_with(target.id)
    authentication.lock_sessions_for_user.assert_awaited_once_with(target.id)
    authentication.verify_current_password.assert_not_called()
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    assert denial.result == "denied"
    assert denial.change_summary["blocked"] == "current_actor"


@pytest.mark.asyncio
async def test_admin_delete_rejects_wrong_current_password_without_logging_secrets() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    actor = make_active_admin()
    service, authentication, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
        password_valid=False,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="用户提出数据删除请求",
            current_password="never-log-this-password",
            confirmation_email=target.email,
            backup_confirmed=True,
            audit=audit_context(actor),
        )

    assert caught.value.status_code == 401
    assert caught.value.code == "INVALID_CREDENTIALS"
    authentication.verify_current_password.assert_called_once_with(
        actor,
        "never-log-this-password",
    )
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    serialized = json.dumps(denial.change_summary, ensure_ascii=False)
    assert denial.change_summary["blocked"] == "invalid_current_password"
    assert "never-log-this-password" not in serialized
    assert target.email not in serialized


@pytest.mark.asyncio
async def test_admin_delete_requires_target_email_and_backup_confirmation() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    actor = make_active_admin()
    service, _, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
    )

    with pytest.raises(ApplicationError) as email_error:
        await service.delete_user(
            target.id,
            reason="用户提出数据删除请求",
            current_password="current-password",
            confirmation_email="other@connect.hkust-gz.edu.cn",
            backup_confirmed=True,
            audit=audit_context(actor),
        )
    assert email_error.value.code == "VALIDATION_ERROR"
    assert email_error.value.details[0].field == "confirmation_email"
    assert audit_add.call_args.args[0].change_summary["blocked"] == ("confirmation_email_mismatch")

    service, _, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
    )
    with pytest.raises(ApplicationError) as backup_error:
        await service.delete_user(
            target.id,
            reason="用户提出数据删除请求",
            current_password="current-password",
            confirmation_email=target.email,
            backup_confirmed=False,
            audit=audit_context(actor),
        )
    assert backup_error.value.code == "VALIDATION_ERROR"
    assert backup_error.value.details[0].field == "backup_confirmed"
    assert audit_add.call_args.args[0].change_summary["blocked"] == "backup_not_confirmed"
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_permanently_deleted() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, role="admin", last_active_at=now)
    actor = make_active_admin()
    service, _, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
        active_admin_count=1,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="管理员离任账号清理",
            current_password="current-password",
            confirmation_email=target.email,
            backup_confirmed=True,
            audit=audit_context(actor),
        )

    assert caught.value.code == "STATE_CONFLICT"
    assert caught.value.message == "不能删除系统中最后一个激活管理员。"
    users.active_admin_count.assert_awaited_once()
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()
    assert audit_add.call_args.args[0].change_summary["blocked"] == "last_active_admin"


@pytest.mark.parametrize(
    ("status", "recent"),
    [
        ("active", True),
        ("pending_email", True),
        ("disabled", False),
    ],
)
@pytest.mark.asyncio
async def test_admin_can_delete_recent_pending_or_disabled_accounts(
    status: str,
    recent: bool,
) -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(
        now=now,
        status=status,
        last_active_at=now if recent else now - timedelta(days=60),
    )
    actor = make_active_admin()
    service, _, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
    )

    await service.delete_user(
        target.id,
        reason="用户提出数据删除请求",
        current_password="current-password",
        confirmation_email=f"  {target.email.upper()}  ",
        backup_confirmed=True,
        audit=audit_context(actor),
    )

    users.prepare_account_erasure.assert_awaited_once_with(target, now=now)
    users.erase_account.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    success = audit_add.call_args.args[0]
    assert success.result == "success"
    assert success.change_summary["previous_status"] == status
    assert "is_inactive" not in success.change_summary


@pytest.mark.asyncio
async def test_successful_admin_delete_enqueues_encrypted_object_cleanup_and_safe_audit() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    actor = make_active_admin()
    cleanup = AccountObjectCleanup(
        file_id=uuid4(),
        object_key="private/account-object-key",
        minio_upload_id="private-multipart-upload-id",
    )
    preparation = AccountErasurePreparation(
        object_cleanups=(cleanup,),
        deletion_counts={"submissions": 3, "personal_files": 1},
        teams_transferred=1,
        teams_dissolved=0,
        teams_invalidated=1,
    )
    service, _, users, session, audit_add, outbox_add = build_delete_service(
        now=now,
        target=target,
        actor=actor,
        preparation=preparation,
    )

    await service.delete_user(
        target.id,
        reason="用户提出数据删除请求",
        current_password="current-password",
        confirmation_email=target.email,
        backup_confirmed=True,
        audit=audit_context(actor),
    )

    job = outbox_add.call_args.args[0]
    assert job.job_type == "delete_account_object"
    assert job.payload == {"object_key": cleanup.object_key}
    assert cleanup.minio_upload_id not in (job.secret_payload_ciphertext or "")
    assert cast(Any, service)._outbox_cipher.decrypt(job.secret_payload_ciphertext) == {
        "minio_upload_id": cleanup.minio_upload_id
    }
    users.erase_account.assert_awaited_once_with(target, preparation)
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()

    success = audit_add.call_args.args[0]
    serialized = json.dumps(success.change_summary, ensure_ascii=False)
    assert success.change_summary["deletion_counts"]["submissions"] == 3
    assert success.change_summary["object_cleanup_count"] == 1
    assert success.change_summary["teams_transferred"] == 1
    assert cleanup.object_key not in serialized
    assert cleanup.minio_upload_id is not None
    assert cleanup.minio_upload_id not in serialized
    assert target.email not in serialized
    assert "current-password" not in serialized


@pytest.mark.asyncio
async def test_self_service_delete_uses_same_erasure_pipeline() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    service, authentication, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=target,
    )

    await service.delete_own_account(
        current_password="current-password",
        confirmation_email=target.email,
        audit=audit_context(target),
    )

    authentication.verify_current_password.assert_called_once_with(
        target,
        "current-password",
    )
    users.prepare_account_erasure.assert_awaited_once_with(target, now=now)
    users.erase_account.assert_awaited_once()
    session.commit.assert_awaited_once()
    success = audit_add.call_args.args[0]
    assert success.action == "user.self_delete"
    assert success.change_summary["mode"] == "self_service"
    assert success.change_summary["reason"] == "self_service_account_deletion"


@pytest.mark.asyncio
async def test_self_service_still_protects_last_active_admin() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, role="admin", last_active_at=now)
    service, _, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=target,
        active_admin_count=1,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_own_account(
            current_password="current-password",
            confirmation_email=target.email,
            audit=audit_context(target),
        )

    assert caught.value.code == "STATE_CONFLICT"
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    assert denial.action == "user.self_delete"
    assert denial.change_summary["blocked"] == "last_active_admin"


@pytest.mark.asyncio
async def test_delete_locks_tokens_and_sessions_before_target_user_row() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    actor = make_active_admin()
    service, authentication, users, _, _, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
    )
    lock_order: list[str] = []

    async def acquire_lifecycle_lock() -> None:
        lock_order.append("advisory")

    async def lock_tokens(_user_id: Any) -> None:
        lock_order.append("one_time_tokens")

    async def lock_sessions(_user_id: Any) -> None:
        lock_order.append("sessions")

    async def get_user(user_id: Any, *, for_update: bool = False) -> User:
        assert for_update is True
        lock_order.append("target_user" if user_id == target.id else "actor_user")
        return target if user_id == target.id else actor

    async def prepare(user: User, *, now: datetime) -> AccountErasurePreparation:
        del user, now
        lock_order.append("prepare")
        return AccountErasurePreparation(
            object_cleanups=(),
            deletion_counts={},
            teams_transferred=0,
            teams_dissolved=0,
            teams_invalidated=0,
        )

    async def erase(
        user: User,
        preparation: AccountErasurePreparation,
    ) -> None:
        del user, preparation
        lock_order.append("erase")

    authentication.acquire_admin_lifecycle_lock = acquire_lifecycle_lock
    authentication.lock_one_time_tokens_for_user = lock_tokens
    authentication.lock_sessions_for_user = lock_sessions
    authentication.verify_current_password = Mock(return_value=True)
    users.get_by_id = get_user
    users.prepare_account_erasure = prepare
    users.erase_account = erase

    await service.delete_user(
        target.id,
        reason="用户提出数据删除请求",
        current_password="current-password",
        confirmation_email=target.email,
        backup_confirmed=True,
        audit=audit_context(actor),
    )

    assert lock_order == [
        "advisory",
        "one_time_tokens",
        "sessions",
        "target_user",
        "actor_user",
        "prepare",
        "erase",
    ]


@pytest.mark.asyncio
async def test_admin_delete_rejects_reason_that_is_only_whitespace() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    actor = make_active_admin()
    service, authentication, users, session, audit_add, _ = build_delete_service(
        now=now,
        target=target,
        actor=actor,
    )

    with pytest.raises(ApplicationError) as caught:
        await service.delete_user(
            target.id,
            reason="   ",
            current_password="current-password",
            confirmation_email=target.email,
            backup_confirmed=True,
            audit=audit_context(actor),
        )

    assert caught.value.status_code == 400
    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.details[0].field == "reason"
    authentication.verify_current_password.assert_not_called()
    users.prepare_account_erasure.assert_not_awaited()
    session.commit.assert_awaited_once()
    denial = audit_add.call_args.args[0]
    assert denial.change_summary == {
        "mode": "admin",
        "reason": "",
        "blocked": "invalid_reason",
    }


@pytest.mark.asyncio
async def test_repository_erasure_enables_transaction_scoped_version_guard() -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    target = make_account(now=now, last_active_at=now)
    session_namespace = SimpleNamespace(
        execute=AsyncMock(),
        delete=AsyncMock(),
        flush=AsyncMock(),
    )
    repository = UserRepository(cast(AsyncSession, session_namespace))
    preparation = AccountErasurePreparation(
        object_cleanups=(),
        deletion_counts={},
        teams_transferred=0,
        teams_dissolved=0,
        teams_invalidated=0,
    )

    await repository.erase_account(target, preparation)

    statement = session_namespace.execute.await_args.args[0]
    assert str(statement) == "SET LOCAL pnx.account_erasure = 'on'"
