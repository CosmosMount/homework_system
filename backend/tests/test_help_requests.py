from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.help_requests.models import HelpRequest
from app.help_requests.repository import AdminHelpRequestRecord, HelpRequestRepository
from app.help_requests.schemas import (
    HelpRequestCreateRequest,
    HelpRequestResolutionRequest,
)
from app.help_requests.service import HelpRequestAuditContext, HelpRequestService
from app.main import create_app
from app.notifications.models import StudentNotification
from app.notifications.repository import StudentNotificationRepository
from app.users.models import User


def make_context(
    role: str = "student",
    *,
    student_view: bool = False,
    user_id: UUID | None = None,
) -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=user_id or uuid4(), role=role),
            session=SimpleNamespace(student_view=student_view),
            effective_role="student" if student_view else role,
            is_admin=role == "admin" and not student_view,
        ),
    )


def make_audit_context(
    role: str = "student",
    *,
    student_view: bool = False,
    user_id: UUID | None = None,
) -> HelpRequestAuditContext:
    return HelpRequestAuditContext(
        actor=make_context(role, student_view=student_view, user_id=user_id),
        request_id="help-request-regression",
        ip_prefix="127.0.0.0/24",
    )


def make_request(
    now: datetime,
    *,
    request_type: str = "system_feedback",
    status: str = "open",
    revision: int = 1,
    created_by: UUID | None = None,
) -> HelpRequest:
    resolved = status == "resolved"
    return HelpRequest(
        id=uuid4(),
        request_type=request_type,
        status=status,
        title="移动端按钮无法使用",
        content_markdown="## 复现步骤",
        content_html="<h3>复现步骤</h3>",
        resolution_markdown="请刷新重试" if resolved else None,
        resolution_html="<p>请刷新重试</p>" if resolved else None,
        created_by=created_by or uuid4(),
        resolved_by=uuid4() if resolved else None,
        resolved_at=now if resolved else None,
        created_at=now,
        updated_at=now,
        revision=revision,
    )


def make_submitter(user_id: UUID) -> User:
    return cast(
        User,
        SimpleNamespace(
            id=user_id,
            full_name="测试学生",
            student_number="20260001",
            email="student@connect.hkust-gz.edu.cn",
        ),
    )


def make_service(now: datetime) -> tuple[HelpRequestService, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    service = HelpRequestService(cast(AsyncSession, session), clock=lambda: now)
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    service._notifications = cast(
        StudentNotificationRepository,
        SimpleNamespace(
            add_all=Mock(),
            unread_ids_for_target=AsyncMock(return_value=[]),
            unread_for_target=AsyncMock(return_value=[]),
        ),
    )
    return service, session


def test_help_request_schema_rejects_blank_unknown_and_invalid_revision() -> None:
    with pytest.raises(ValidationError):
        HelpRequestCreateRequest(
            request_type="system_feedback",
            title="   ",
            content_markdown="有内容",
        )
    with pytest.raises(ValidationError):
        HelpRequestCreateRequest(
            request_type="other",
            title="标题",
            content_markdown="有内容",
        )
    with pytest.raises(ValidationError):
        HelpRequestResolutionRequest(resolution_markdown="   ", revision=1)
    with pytest.raises(ValidationError):
        HelpRequestResolutionRequest(resolution_markdown="已处理", revision=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("request_type", ["system_feedback", "question"])
async def test_student_creates_private_sanitized_help_request(request_type: str) -> None:
    now = datetime.now(UTC)
    service, session = make_service(now)
    add_request = Mock()
    service._repo = cast(HelpRequestRepository, SimpleNamespace(add=add_request))
    audit_add = cast(Mock, service._audit.add)
    payload = HelpRequestCreateRequest(
        request_type=request_type,
        title="  移动端按钮无法使用  ",
        content_markdown="## 复现\n<script>alert(1)</script> [危险](javascript:alert(1))",
    )

    result = await service.create(payload, audit_context=make_audit_context())

    created = cast(HelpRequest, add_request.call_args.args[0])
    audit = cast(AuditLog, audit_add.call_args.args[0])
    assert result.request_type == request_type
    assert result.status == "open"
    assert created.title == "移动端按钮无法使用"
    assert "<script" not in created.content_html.lower()
    assert 'href="javascript:' not in created.content_html.lower()
    assert "content" not in audit.change_summary
    assert "title" not in audit.change_summary
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_list_and_detail_are_bound_to_current_user() -> None:
    now = datetime.now(UTC)
    student_id = uuid4()
    request = make_request(now, created_by=student_id)
    service, _session = make_service(now)
    list_student = AsyncMock(return_value=([request], 1))
    get_student = AsyncMock(side_effect=[request, None])
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(list_student=list_student, get_student=get_student),
    )
    context = make_context(user_id=student_id)

    page = await service.list_student(
        context=context,
        request_type="system_feedback",
        status="open",
        page=1,
        page_size=20,
    )
    detail = await service.student_detail(request.id, context=context)

    assert page.total == 1
    assert detail.id == request.id
    assert detail.notification_ids == []
    list_student.assert_awaited_once_with(
        user_id=student_id,
        request_type="system_feedback",
        status="open",
        page=1,
        page_size=20,
    )
    get_student.assert_awaited_with(request.id, student_id)
    cast(AsyncMock, service._notifications.unread_ids_for_target).assert_awaited_once_with(
        user_id=student_id,
        target_type="help_request",
        target_id=request.id,
    )

    with pytest.raises(ApplicationError) as hidden:
        await service.student_detail(uuid4(), context=context)
    assert hidden.value.status_code == 404
    assert hidden.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_plain_admin_is_blocked_from_student_path_but_student_view_is_allowed() -> None:
    now = datetime.now(UTC)
    service, session = make_service(now)
    add_request = Mock()
    service._repo = cast(HelpRequestRepository, SimpleNamespace(add=add_request))
    payload = HelpRequestCreateRequest(
        request_type="question",
        title="培训问题",
        content_markdown="如何选择方向？",
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.create(payload, audit_context=make_audit_context("admin"))
    assert blocked.value.status_code == 403
    session.commit.assert_not_awaited()

    admin_id = uuid4()
    result = await service.create(
        payload,
        audit_context=make_audit_context(
            "admin",
            student_view=True,
            user_id=admin_id,
        ),
    )
    created = cast(HelpRequest, add_request.call_args.args[0])
    assert result.request_type == "question"
    assert created.created_by == admin_id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_list_returns_identity_and_normalizes_query() -> None:
    now = datetime.now(UTC)
    request = make_request(now)
    record = AdminHelpRequestRecord(
        request=request,
        submitter=make_submitter(request.created_by),
    )
    service, _session = make_service(now)
    list_admin = AsyncMock(return_value=([record], 1))
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(list_admin=list_admin),
    )

    result = await service.list_admin(
        context=make_context("admin"),
        request_type=None,
        status="open",
        query="  移动端  ",
        page=1,
        page_size=20,
    )

    assert result.items[0].created_by.student_number == "20260001"
    list_admin.assert_awaited_once_with(
        request_type=None,
        status="open",
        query="移动端",
        page=1,
        page_size=20,
    )

    with pytest.raises(ApplicationError) as student_blocked:
        await service.list_admin(
            context=make_context(),
            request_type=None,
            status=None,
            query=None,
            page=1,
            page_size=20,
        )
    assert student_blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_resolution_updates_revision_and_adds_redacted_audit_notification() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    request = make_request(now)
    submitter = make_submitter(request.created_by)
    service, session = make_service(now)
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            get_submitter=AsyncMock(return_value=submitter),
        ),
    )
    audit_add = cast(Mock, service._audit.add)
    notification_add = cast(Mock, service._notifications.add_all)
    resolution = "## 处理结果\n已修复，请刷新后重试。"

    result = await service.resolve(
        request.id,
        HelpRequestResolutionRequest(
            resolution_markdown=resolution,
            revision=1,
        ),
        audit_context=make_audit_context("admin", user_id=admin_id),
    )

    audit = cast(AuditLog, audit_add.call_args.args[0])
    notification = cast(
        StudentNotification,
        notification_add.call_args.args[0][0],
    )
    assert result.status == "resolved"
    assert result.revision == 2
    assert request.resolved_by == admin_id
    assert request.resolution_html is not None
    assert "<h3" in request.resolution_html
    assert audit.action == "help_request.resolved"
    assert resolution not in str(audit.change_summary)
    assert notification.user_id == request.created_by
    assert notification.event_key == f"help_request_resolved:{request.id}:2"
    assert notification.target_url == f"/help/{request.id}"
    assert resolution not in notification.title
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_can_revise_resolution_with_current_revision() -> None:
    now = datetime.now(UTC)
    request = make_request(now, status="resolved", revision=2)
    service, _session = make_service(now)
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            get_submitter=AsyncMock(return_value=make_submitter(request.created_by)),
        ),
    )
    audit_add = cast(Mock, service._audit.add)

    result = await service.resolve(
        request.id,
        HelpRequestResolutionRequest(
            resolution_markdown="修订后的答复",
            revision=2,
        ),
        audit_context=make_audit_context("admin"),
    )

    audit = cast(AuditLog, audit_add.call_args.args[0])
    assert result.revision == 3
    assert result.resolution_markdown == "修订后的答复"
    assert audit.action == "help_request.resolution_revised"


@pytest.mark.asyncio
async def test_stale_resolution_revision_rolls_back_without_audit_or_notification() -> None:
    now = datetime.now(UTC)
    request = make_request(now, revision=2)
    service, session = make_service(now)
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            get_submitter=AsyncMock(return_value=make_submitter(request.created_by)),
        ),
    )
    audit_add = cast(Mock, service._audit.add)
    notification_add = cast(Mock, service._notifications.add_all)

    with pytest.raises(ApplicationError) as conflict:
        await service.resolve(
            request.id,
            HelpRequestResolutionRequest(
                resolution_markdown="过期答复",
                revision=1,
            ),
            audit_context=make_audit_context("admin"),
        )

    assert conflict.value.status_code == 409
    assert conflict.value.code == "REVISION_CONFLICT"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    audit_add.assert_not_called()
    notification_add.assert_not_called()


@pytest.mark.asyncio
async def test_resolution_notification_failure_rolls_back_atomic_transaction() -> None:
    now = datetime.now(UTC)
    request = make_request(now)
    service, session = make_service(now)
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            get_submitter=AsyncMock(return_value=make_submitter(request.created_by)),
        ),
    )
    notification_add = cast(Mock, service._notifications.add_all)
    notification_add.side_effect = RuntimeError("notification persistence failed")

    with pytest.raises(RuntimeError):
        await service.resolve(
            request.id,
            HelpRequestResolutionRequest(
                resolution_markdown="处理结果",
                revision=1,
            ),
            audit_context=make_audit_context("admin"),
        )

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


class CapturingPublicSession:
    def __init__(self, request: HelpRequest) -> None:
        self.request = request
        self.statements: list[str] = []

    @staticmethod
    def _render(statement: Select[tuple[object]]) -> str:
        return str(statement.compile(compile_kwargs={"literal_binds": True}))

    async def scalar(self, statement: Select[tuple[object]]) -> object:
        sql = self._render(statement)
        self.statements.append(sql)
        return 1 if "count(*)" in sql else self.request

    async def scalars(
        self,
        statement: Select[tuple[object]],
    ) -> SimpleNamespace:
        self.statements.append(self._render(statement))
        return SimpleNamespace(all=lambda: [self.request])


@pytest.mark.asyncio
async def test_public_repository_query_is_resolved_question_only_without_user_join() -> None:
    now = datetime.now(UTC)
    request = make_request(now, request_type="question", status="resolved")
    session = CapturingPublicSession(request)
    repository = HelpRequestRepository(cast(AsyncSession, session))

    requests, total = await repository.list_public(page=1, page_size=20)
    detail = await repository.get_public(request.id)

    assert requests == [request]
    assert total == 1
    assert detail is request
    assert len(session.statements) == 3
    for sql in session.statements:
        assert "users" not in sql
        assert "help_requests.request_type = 'question'" in sql
        assert "help_requests.status = 'resolved'" in sql


@pytest.mark.asyncio
async def test_public_service_allows_valid_roles_and_never_returns_identity_fields() -> None:
    now = datetime.now(UTC)
    request = make_request(now, request_type="question", status="resolved")
    service, _session = make_service(now)
    list_public = AsyncMock(return_value=([request], 1))
    get_public = AsyncMock(side_effect=[request, None, None])
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            list_public=list_public,
            get_public=get_public,
        ),
    )

    student_page = await service.list_public(
        context=make_context("student"),
        page=1,
        page_size=20,
    )
    admin_page = await service.list_public(
        context=make_context("admin"),
        page=1,
        page_size=20,
    )
    detail = await service.public_detail(
        request.id,
        context=make_context("student"),
    )

    assert student_page.items[0].id == request.id
    assert admin_page.items[0].id == request.id
    assert detail.resolution_html == request.resolution_html
    assert {
        "created_by",
        "resolved_by",
        "notification_ids",
        "content_markdown",
        "resolution_markdown",
    }.isdisjoint(detail.model_dump())
    assert list_public.await_count == 2

    with pytest.raises(ApplicationError) as open_or_missing:
        await service.public_detail(uuid4(), context=make_context("student"))
    assert open_or_missing.value.status_code == 404

    with pytest.raises(ApplicationError) as feedback_or_missing:
        await service.public_detail(uuid4(), context=make_context("admin"))
    assert feedback_or_missing.value.status_code == 404


@pytest.mark.asyncio
async def test_public_help_request_endpoints_require_authentication() -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    paths = [
        "/api/v1/help-requests/public",
        f"/api/v1/help-requests/public/{uuid4()}",
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        responses = [await client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [401, 401]
    assert {response.json()["error"]["code"] for response in responses} == {
        "AUTHENTICATION_REQUIRED"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_type", "status"),
    [("system_feedback", "open"), ("question", "resolved")],
)
async def test_admin_physically_deletes_help_request_with_redacted_audit(
    request_type: str,
    status: str,
) -> None:
    now = datetime.now(UTC)
    request = make_request(now, request_type=request_type, status=status)
    notification = cast(StudentNotification, SimpleNamespace(read_at=None))
    service, session = make_service(now)
    delete_request = AsyncMock()
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            delete=delete_request,
        ),
    )
    unread_for_target = AsyncMock(return_value=[notification])
    service._notifications = cast(
        StudentNotificationRepository,
        SimpleNamespace(
            add_all=Mock(),
            unread_ids_for_target=AsyncMock(return_value=[]),
            unread_for_target=unread_for_target,
        ),
    )
    audit_add = cast(Mock, service._audit.add)

    await service.remove(
        request.id,
        audit_context=make_audit_context("admin"),
    )

    audit = cast(AuditLog, audit_add.call_args.args[0])
    assert notification.read_at == now
    assert audit.action == "help_request.deleted"
    assert audit.change_summary == {
        "request_type": request_type,
        "status": status,
        "revision": request.revision,
        "deletion_mode": "physical",
    }
    assert {"title", "content", "resolution", "created_by"}.isdisjoint(audit.change_summary)
    unread_for_target.assert_awaited_once_with(
        target_type="help_request",
        target_id=request.id,
        for_update=True,
    )
    delete_request.assert_awaited_once_with(request)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_help_request_delete_requires_real_admin_and_missing_is_404() -> None:
    now = datetime.now(UTC)
    service, session = make_service(now)
    get_by_id = AsyncMock(return_value=None)
    delete_request = AsyncMock()
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(get_by_id=get_by_id, delete=delete_request),
    )

    for audit_context in (
        make_audit_context("student"),
        make_audit_context("admin", student_view=True),
    ):
        with pytest.raises(ApplicationError) as forbidden:
            await service.remove(uuid4(), audit_context=audit_context)
        assert forbidden.value.status_code == 403

    missing_id = uuid4()
    with pytest.raises(ApplicationError) as missing:
        await service.remove(
            missing_id,
            audit_context=make_audit_context("admin"),
        )
    assert missing.value.status_code == 404
    assert missing.value.code == "RESOURCE_NOT_FOUND"
    get_by_id.assert_awaited_once_with(missing_id, for_update=True)
    delete_request.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_help_request_delete_failure_rolls_back_transaction() -> None:
    now = datetime.now(UTC)
    request = make_request(now, request_type="question", status="resolved")
    notification = cast(StudentNotification, SimpleNamespace(read_at=None))
    service, session = make_service(now)
    service._repo = cast(
        HelpRequestRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=request),
            delete=AsyncMock(side_effect=RuntimeError("delete failed")),
        ),
    )
    service._notifications = cast(
        StudentNotificationRepository,
        SimpleNamespace(
            add_all=Mock(),
            unread_ids_for_target=AsyncMock(return_value=[]),
            unread_for_target=AsyncMock(return_value=[notification]),
        ),
    )

    with pytest.raises(RuntimeError, match="delete failed"):
        await service.remove(
            request.id,
            audit_context=make_audit_context("admin"),
        )

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_help_request_delete_endpoint_requires_authentication() -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.delete(
            f"/api/v1/admin/help-requests/{uuid4()}",
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
