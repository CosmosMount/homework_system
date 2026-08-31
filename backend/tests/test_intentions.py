from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.security import sha256_hexdigest
from app.intentions.models import (
    IntentionOption,
    IntentionQuestion,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.intentions.repository import (
    IntentionRepository,
    SurveyListRecord,
    SurveyOptionCount,
    SurveyRosterRecord,
)
from app.intentions.schemas import (
    IntentionAnswerRequest,
    IntentionEmailNotificationRequest,
    IntentionOptionInput,
    IntentionQuestionInput,
    IntentionResponseRequest,
    IntentionSurveyCreateRequest,
    IntentionSurveyPatchRequest,
)
from app.intentions.service import IntentionAuditContext, IntentionService
from app.notifications.mailer import PermanentMailError, render_mail
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.users.models import Direction, User


def make_context(role: str = "student", *, student_view: bool = False) -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role=role),
            session=SimpleNamespace(student_view=student_view),
            effective_role="student" if student_view else role,
            is_admin=role == "admin" and not student_view,
        ),
    )


def make_audit_context(role: str = "student") -> IntentionAuditContext:
    return IntentionAuditContext(
        actor=make_context(role),
        request_id="intention-regression",
        ip_prefix="127.0.0.0/24",
    )


def make_survey(
    now: datetime,
    *,
    status: str = "open",
    max_submissions: int | None = None,
) -> IntentionSurvey:
    actor_id = uuid4()
    return IntentionSurvey(
        id=uuid4(),
        title="培训方向问卷",
        description_markdown="## 请选择",
        description_html="<h2>请选择</h2>",
        status=status,
        max_submissions=max_submissions,
        starts_at=None,
        ends_at=None,
        public_token_hash=sha256_hexdigest("initial-token"),
        created_by=actor_id,
        updated_by=actor_id,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_question(
    survey_id: object, prompt: str, order: int, *, allow_multiple: bool = False
) -> IntentionQuestion:
    return IntentionQuestion(
        id=uuid4(),
        survey_id=survey_id,
        prompt=prompt,
        allow_multiple=allow_multiple,
        display_order=order,
    )


def make_option(question_id: object, label: str, order: int) -> IntentionOption:
    return IntentionOption(
        id=uuid4(),
        question_id=question_id,
        label=label,
        display_order=order,
    )


def make_service(now: datetime) -> tuple[IntentionService, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    service = IntentionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    return service, session


def question_payload(
    prompt: str, *labels: str, allow_multiple: bool = False
) -> IntentionQuestionInput:
    return IntentionQuestionInput(
        prompt=prompt,
        options=[IntentionOptionInput(label=label) for label in labels],
        allow_multiple=allow_multiple,
    )


def answer(question: IntentionQuestion, *options: IntentionOption) -> IntentionAnswerRequest:
    return IntentionAnswerRequest(
        question_id=question.id,
        selected_option_ids=[option.id for option in options],
    )


def test_questionnaire_schema_rejects_blank_duplicate_and_invalid_limits() -> None:
    valid_question = question_payload("第一志愿", "视觉")

    with pytest.raises(ValidationError):
        IntentionSurveyCreateRequest(title="   ", questions=[valid_question])
    with pytest.raises(ValidationError):
        question_payload("第一志愿", "视觉", " 视觉 ")
    with pytest.raises(ValidationError):
        IntentionQuestionInput(prompt="  ", options=[IntentionOptionInput(label="视觉")])
    with pytest.raises(ValidationError):
        IntentionSurveyCreateRequest(
            title="培训方向", questions=[valid_question], max_submissions=0
        )

    option_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionAnswerRequest(question_id=uuid4(), selected_option_ids=[option_id, option_id])


@pytest.mark.asyncio
async def test_admin_creates_sanitized_multi_question_questionnaire() -> None:
    now = datetime.now(UTC)
    service, session = make_service(now)
    persistence_order: list[str] = []
    add_survey = Mock(side_effect=lambda _survey: persistence_order.append("survey"))
    add_question = Mock(side_effect=lambda _question: persistence_order.append("question"))
    add_option = Mock(side_effect=lambda _option: persistence_order.append("option"))
    session.flush.side_effect = lambda: persistence_order.append("flush")
    session.commit.side_effect = lambda: persistence_order.append("commit")
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            add_survey=add_survey,
            add_question=add_question,
            add_option=add_option,
        ),
    )
    payload = IntentionSurveyCreateRequest(
        title="  培训方向问卷  ",
        description_markdown="## 说明\n<script>alert(1)</script>",
        questions=[
            question_payload("第一志愿", "机器人", "视觉"),
            question_payload("第二志愿", "机器人", "视觉", allow_multiple=True),
        ],
        max_submissions=2,
    )

    result = await service.create(payload, audit_context=make_audit_context("admin"))

    survey = cast(IntentionSurvey, add_survey.call_args.args[0])
    assert result.title == "培训方向问卷"
    assert result.question_count == 2
    assert result.max_submissions == 2
    assert "<h3" in survey.description_html
    assert "<script" not in survey.description_html.lower()
    assert len(survey.public_token_hash) == 64
    assert [call.args[0].prompt for call in add_question.call_args_list] == [
        "第一志愿",
        "第二志愿",
    ]
    assert persistence_order == [
        "survey",
        "flush",
        "question",
        "question",
        "flush",
        "option",
        "option",
        "option",
        "option",
        "commit",
    ]
    assert session.flush.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "open", "closed", "archived"])
async def test_admin_can_read_complete_questionnaire_in_every_status(status: str) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status=status, max_submissions=3)
    first = make_question(survey.id, "第一志愿", 0)
    second = make_question(survey.id, "第二志愿", 1, allow_multiple=True)
    options = [
        make_option(first.id, "机器人", 0),
        make_option(first.id, "视觉", 1),
        make_option(second.id, "电控", 0),
    ]
    service, _session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first, second]),
            options=AsyncMock(return_value=options),
            responded_count=AsyncMock(return_value=2),
        ),
    )

    result = await service.admin_detail(survey.id, context=make_context("admin"))

    assert result.status == status
    assert result.question_count == 2
    assert result.responded_count == 2
    assert [question.prompt for question in result.questions] == ["第一志愿", "第二志愿"]
    assert [option.label for option in result.questions[0].options] == ["机器人", "视觉"]


@pytest.mark.asyncio
async def test_admin_detail_rejects_students_and_admin_student_view() -> None:
    now = datetime.now(UTC)
    service, _session = make_service(now)

    with pytest.raises(ApplicationError) as student_blocked:
        await service.admin_detail(uuid4(), context=make_context())
    assert student_blocked.value.status_code == 403

    with pytest.raises(ApplicationError) as view_blocked:
        await service.admin_detail(uuid4(), context=make_context("admin", student_view=True))
    assert view_blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_updates_draft_structure_and_returns_fresh_detail() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="draft", max_submissions=1)
    old_question = make_question(survey.id, "旧问题", 0)
    new_questions: list[IntentionQuestion] = []
    new_options: list[IntentionOption] = []
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(side_effect=[[old_question], new_questions]),
            options=AsyncMock(side_effect=lambda _survey_id: new_options),
            responded_count=AsyncMock(return_value=0),
            add_question=Mock(side_effect=new_questions.append),
            add_option=Mock(side_effect=new_options.append),
        ),
    )
    payload = IntentionSurveyPatchRequest(
        revision=1,
        title="更新后的问卷",
        description_markdown="## 新说明\n<script>alert(1)</script>",
        questions=[
            question_payload("第一志愿", "机械", "视觉"),
            question_payload("第二志愿", "电控", "嵌入式", allow_multiple=True),
        ],
        max_submissions=4,
    )

    result = await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert result.title == "更新后的问卷"
    assert result.revision == 2
    assert result.max_submissions == 4
    assert [question.prompt for question in result.questions] == ["第一志愿", "第二志愿"]
    assert result.questions[1].allow_multiple is True
    assert "<script" not in survey.description_html.lower()
    session.delete.assert_awaited_once_with(old_question)
    assert session.flush.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "revision", "expected_code"),
    [
        ("open", 1, "INTENTION_ALREADY_OPEN"),
        ("closed", 1, "INTENTION_ALREADY_OPEN"),
        ("archived", 1, "INTENTION_ALREADY_OPEN"),
        ("draft", 2, "REVISION_CONFLICT"),
    ],
)
async def test_admin_update_rejects_non_drafts_and_stale_revisions(
    status: str, revision: int, expected_code: str
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status=status)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(get_survey=AsyncMock(return_value=survey)),
    )
    payload = IntentionSurveyPatchRequest(
        revision=revision,
        title="更新后的问卷",
        questions=[question_payload("第一志愿", "视觉")],
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert blocked.value.code == expected_code
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_closed_questionnaire_can_reopen_while_archived_remains_terminal() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="draft")
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            list_surveys=AsyncMock(return_value=[SurveyListRecord(survey, 2, 0, False)]),
        ),
    )
    audit_context = make_audit_context("admin")

    assert (
        await service.transition(survey.id, "open", audit_context=audit_context)
    ).status == "open"
    assert (
        await service.transition(survey.id, "closed", audit_context=audit_context)
    ).status == "closed"
    assert (
        await service.transition(survey.id, "open", audit_context=audit_context)
    ).status == "open"
    assert survey.public_token_hash == sha256_hexdigest("initial-token")
    assert (
        await service.transition(survey.id, "closed", audit_context=audit_context)
    ).status == "closed"
    assert (
        await service.transition(survey.id, "archived", audit_context=audit_context)
    ).status == "archived"

    with pytest.raises(ApplicationError) as blocked:
        await service.transition(survey.id, "open", audit_context=audit_context)
    assert blocked.value.code == "STATE_CONFLICT"
    assert session.commit.await_count == 5
    session.rollback.assert_awaited_once()
    audit_add = cast(Mock, service._audit.add)
    assert [item.args[0].action for item in audit_add.call_args_list] == [
        "intention.open",
        "intention.closed",
        "intention.reopen",
        "intention.closed",
        "intention.archived",
    ]
    assert audit_add.call_args_list[2].args[0].change_summary == {
        "from_status": "closed",
        "to_status": "open",
    }


def test_email_notification_request_rejects_duplicate_members() -> None:
    member_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionEmailNotificationRequest(recipient_user_ids=[member_id, member_id])


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"direction_id": uuid4()},
        {"recipient_scope": "direction"},
        {"recipient_scope": "direction", "direction_id": uuid4(), "recipient_user_ids": [uuid4()]},
        {"recipient_scope": "all", "recipient_user_ids": [uuid4()]},
        {"recipient_scope": "all", "direction_id": uuid4()},
    ],
)
def test_email_notification_request_rejects_incompatible_scope(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IntentionEmailNotificationRequest.model_validate(payload)


def test_email_notification_request_accepts_manual_direction_and_all() -> None:
    assert (
        IntentionEmailNotificationRequest(recipient_user_ids=[uuid4()]).recipient_scope == "manual"
    )
    assert (
        IntentionEmailNotificationRequest(
            recipient_scope="direction", direction_id=uuid4()
        ).recipient_scope
        == "direction"
    )
    assert IntentionEmailNotificationRequest(recipient_scope="all").recipient_scope == "all"


@pytest.mark.asyncio
async def test_admin_queues_selected_members_once_per_open_revision() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    first = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            email="first@connect.hkust-gz.edu.cn",
            full_name="第一位学生",
        ),
    )
    second = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            email="second@connect.hkust-gz.edu.cn",
            full_name="第二位学生",
        ),
    )
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_students_by_ids=AsyncMock(return_value=[first, second]),
        ),
    )
    first_key = service._mail_event_key(survey, first.id)
    second_key = service._mail_event_key(survey, second.id)
    outbox_add = Mock()
    service._outbox = cast(
        OutboxRepository,
        SimpleNamespace(
            existing_event_keys=AsyncMock(return_value={second_key}),
            add=outbox_add,
        ),
    )

    result = await service.send_email_notifications(
        survey.id,
        IntentionEmailNotificationRequest(recipient_user_ids=[first.id, second.id]),
        audit_context=make_audit_context("admin"),
    )

    assert result.requested_count == 2
    assert result.queued_count == 1
    assert result.already_queued_count == 1
    queued_job = cast(OutboxJob, outbox_add.call_args.args[0])
    assert queued_job.event_key == first_key
    assert queued_job.job_type == "intention_open_email"
    assert queued_job.payload == {
        "recipient": first.email,
        "full_name": first.full_name,
        "survey_id": str(survey.id),
        "title": survey.title,
        "target_url": f"/intentions/{survey.id}",
    }
    previous_key = service._mail_event_key(survey, first.id)
    survey.revision += 1
    assert service._mail_event_key(survey, first.id) != previous_key
    assert second_key != queued_job.event_key
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.action == "intention.email_notify"
    assert audit.change_summary == {
        "recipient_scope": "manual",
        "requested_count": 2,
        "queued_count": 1,
        "already_queued_count": 1,
    }


@pytest.mark.asyncio
async def test_admin_queues_active_students_in_selected_direction() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    direction_id = uuid4()
    direction = cast(
        Direction,
        SimpleNamespace(id=direction_id, is_active=True),
    )
    member = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            email="direction@connect.hkust-gz.edu.cn",
            full_name="技术组学生",
        ),
    )
    service, session = make_service(now)
    active_direction = AsyncMock(return_value=direction)
    active_scope = AsyncMock(return_value=[member])
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_direction=active_direction,
            active_students_for_email_scope=active_scope,
        ),
    )
    outbox_add = Mock()
    service._outbox = cast(
        OutboxRepository,
        SimpleNamespace(
            existing_event_keys=AsyncMock(return_value=set()),
            add=outbox_add,
        ),
    )

    result = await service.send_email_notifications(
        survey.id,
        IntentionEmailNotificationRequest(
            recipient_scope="direction",
            direction_id=direction_id,
        ),
        audit_context=make_audit_context("admin"),
    )

    assert result.requested_count == 1
    assert result.queued_count == 1
    active_direction.assert_awaited_once_with(direction_id)
    active_scope.assert_awaited_once_with(direction_id=direction_id)
    assert outbox_add.call_count == 1
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.change_summary == {
        "recipient_scope": "direction",
        "direction_id": str(direction_id),
        "requested_count": 1,
        "queued_count": 1,
        "already_queued_count": 0,
    }


@pytest.mark.asyncio
async def test_admin_queues_all_active_students_from_authoritative_scope() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    members = [
        cast(
            User,
            SimpleNamespace(
                id=uuid4(),
                email=f"all-{index}@connect.hkust-gz.edu.cn",
                full_name=f"全部学生 {index}",
            ),
        )
        for index in range(2)
    ]
    service, session = make_service(now)
    active_scope = AsyncMock(return_value=members)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_students_for_email_scope=active_scope,
        ),
    )
    outbox_add = Mock()
    service._outbox = cast(
        OutboxRepository,
        SimpleNamespace(
            existing_event_keys=AsyncMock(return_value=set()),
            add=outbox_add,
        ),
    )

    result = await service.send_email_notifications(
        survey.id,
        IntentionEmailNotificationRequest(recipient_scope="all"),
        audit_context=make_audit_context("admin"),
    )

    assert result.requested_count == 2
    assert result.queued_count == 2
    active_scope.assert_awaited_once_with(direction_id=None)
    assert outbox_add.call_count == 2
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.change_summary == {
        "recipient_scope": "all",
        "requested_count": 2,
        "queued_count": 2,
        "already_queued_count": 0,
    }


@pytest.mark.asyncio
async def test_questionnaire_email_rejects_inactive_direction_or_empty_scope() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    direction_id = uuid4()
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_direction=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(ApplicationError) as invalid_direction:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(
                recipient_scope="direction",
                direction_id=direction_id,
            ),
            audit_context=make_audit_context("admin"),
        )
    assert invalid_direction.value.code == "INVALID_INTENTION_EMAIL_DIRECTION"

    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_students_for_email_scope=AsyncMock(return_value=[]),
        ),
    )
    with pytest.raises(ApplicationError) as empty_scope:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(recipient_scope="all"),
            audit_context=make_audit_context("admin"),
        )
    assert empty_scope.value.code == "NO_INTENTION_EMAIL_RECIPIENTS"
    assert session.rollback.await_count == 2
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_questionnaire_email_rejects_non_active_selected_member() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_students_by_ids=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(recipient_user_ids=[uuid4()]),
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INVALID_INTENTION_EMAIL_RECIPIENTS"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_questionnaire_email_rejects_closed_or_outside_window() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="closed")
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(get_survey=AsyncMock(return_value=survey)),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(recipient_user_ids=[uuid4()]),
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INTENTION_CLOSED"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_questionnaire_email_template_contains_only_safe_fill_link() -> None:
    now = datetime.now(UTC)
    survey_id = uuid4()
    job = OutboxJob(
        id=uuid4(),
        job_type="intention_open_email",
        event_key=f"intention:{survey_id}:open:3:email:{uuid4()}",
        payload={
            "recipient": "student@connect.hkust-gz.edu.cn",
            "full_name": "测试同学",
            "survey_id": str(survey_id),
            "title": "方向 <script>问卷",
            "target_url": f"/intentions/{survey_id}",
        },
        secret_payload_ciphertext=None,
        status="pending",
        available_at=now,
        attempt_count=0,
        max_attempts=8,
        locked_by=None,
        locked_at=None,
        last_error_code=None,
        last_error_summary=None,
        created_at=now,
        sent_at=None,
    )

    rendered = render_mail(job, {}, app_base_url="https://training.example.edu/")

    assert rendered.recipient == "student@connect.hkust-gz.edu.cn"
    assert f"https://training.example.edu/intentions/{survey_id}" in rendered.text
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html
    assert "token=" not in rendered.text


def test_questionnaire_email_template_rejects_external_target_url() -> None:
    now = datetime.now(UTC)
    job = OutboxJob(
        id=uuid4(),
        job_type="intention_open_email",
        event_key=f"intention:{uuid4()}:open:1:email:{uuid4()}",
        payload={
            "recipient": "student@connect.hkust-gz.edu.cn",
            "full_name": "测试同学",
            "title": "方向问卷",
            "target_url": "https://evil.invalid/intentions/fake",
        },
        secret_payload_ciphertext=None,
        status="pending",
        available_at=now,
        attempt_count=0,
        max_attempts=8,
        locked_by=None,
        locked_at=None,
        last_error_code=None,
        last_error_summary=None,
        created_at=now,
        sent_at=None,
    )

    with pytest.raises(PermanentMailError):
        render_mail(job, {}, app_base_url="https://training.example.edu")


@pytest.mark.asyncio
async def test_student_submits_all_single_and_multiple_choice_questions() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, max_submissions=2)
    first_question = make_question(survey.id, "第一志愿", 0)
    second_question = make_question(survey.id, "第二志愿", 1, allow_multiple=True)
    robot_first = make_option(first_question.id, "机器人", 0)
    vision_first = make_option(first_question.id, "视觉", 1)
    robot_second = make_option(second_question.id, "机器人", 0)
    vision_second = make_option(second_question.id, "视觉", 1)
    questions = [first_question, second_question]
    options = [robot_first, vision_first, robot_second, vision_second]
    service, session = make_service(now)
    add_response = Mock()
    add_response_option = Mock()
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=questions),
            options=AsyncMock(return_value=options),
            get_response=AsyncMock(return_value=None),
            add_response=add_response,
            add_response_option=add_response_option,
        ),
    )

    created = await service.submit_response(
        survey.id,
        IntentionResponseRequest(
            answers=[
                answer(first_question, vision_first),
                answer(second_question, robot_second, vision_second),
            ],
            free_text="  愿意担任队长  ",
        ),
        audit_context=make_audit_context(),
    )

    response = cast(IntentionResponse, add_response.call_args.args[0])
    assert created.submission_count == 1
    assert created.free_text == "愿意担任队长"
    assert created.answers[0].selected_option_ids == [vision_first.id]
    assert created.answers[1].selected_option_ids == [robot_second.id, vision_second.id]
    assert response.submission_count == 1
    assert add_response_option.call_count == 3
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_submission_limit_allows_update_then_rejects_next_attempt() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, max_submissions=2)
    question = make_question(survey.id, "第一志愿", 0)
    robot = make_option(question.id, "机器人", 0)
    vision = make_option(question.id, "视觉", 1)
    response = IntentionResponse(
        id=uuid4(),
        survey_id=survey.id,
        user_id=uuid4(),
        free_text=None,
        submission_count=1,
        submitted_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )
    old_link = IntentionResponseOption(response_id=response.id, option_id=robot.id)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=[robot, vision]),
            get_response=AsyncMock(return_value=response),
            response_options=AsyncMock(return_value=[old_link]),
            add_response_option=Mock(),
        ),
    )
    payload = IntentionResponseRequest(answers=[answer(question, vision)])

    updated = await service.submit_response(survey.id, payload, audit_context=make_audit_context())
    assert updated.submission_count == 2
    assert response.submission_count == 2
    session.delete.assert_awaited_once_with(old_link)

    with pytest.raises(ApplicationError) as blocked:
        await service.submit_response(survey.id, payload, audit_context=make_audit_context())
    assert blocked.value.code == "INTENTION_SUBMISSION_LIMIT_REACHED"
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_missing_question_cross_question_option_and_single_multiple_are_rejected() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    first_question = make_question(survey.id, "第一志愿", 0)
    second_question = make_question(survey.id, "第二志愿", 1)
    first = make_option(first_question.id, "机器人", 0)
    second = make_option(first_question.id, "视觉", 1)
    other = make_option(second_question.id, "嵌入式", 0)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first_question, second_question]),
            options=AsyncMock(return_value=[first, second, other]),
            get_response=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(ApplicationError) as missing:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(answers=[answer(first_question, first)]),
            audit_context=make_audit_context(),
        )
    assert missing.value.status_code == 422

    with pytest.raises(ApplicationError) as crossed:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(
                answers=[answer(first_question, other), answer(second_question, other)]
            ),
            audit_context=make_audit_context(),
        )
    assert crossed.value.status_code == 400

    with pytest.raises(ApplicationError) as multiple:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(
                answers=[answer(first_question, first, second), answer(second_question, other)]
            ),
            audit_context=make_audit_context(),
        )
    assert multiple.value.status_code == 422
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_questionnaire_response_integrity_conflict_is_recoverable() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    question = make_question(survey.id, "第一志愿", 0)
    option = make_option(question.id, "机器人", 0)
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=[option]),
            get_response=AsyncMock(return_value=None),
            add_response=Mock(),
            add_response_option=Mock(),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(answers=[answer(question, option)]),
            audit_context=make_audit_context(),
        )

    assert blocked.value.code == "INTENTION_RESPONSE_CONFLICT"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("total_students", "responded", "response_count", "expected_rate", "expected_option"),
    [(0, 0, 0, 0.0, 0.0), (8, 2, 1, 25.0, 50.0)],
)
async def test_admin_stats_are_grouped_by_question(
    total_students: int,
    responded: int,
    response_count: int,
    expected_rate: float,
    expected_option: float,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    question = make_question(survey.id, "第一志愿", 0)
    option = make_option(question.id, "机器人", 0)
    service, _session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            responded_count=AsyncMock(return_value=responded),
            active_student_count=AsyncMock(return_value=total_students),
            questions=AsyncMock(return_value=[question]),
            option_counts=AsyncMock(
                return_value=[
                    SurveyOptionCount(
                        question=question,
                        option=option,
                        response_count=response_count,
                    )
                ]
            ),
        ),
    )

    result = await service.stats(survey.id, context=make_context("admin"))

    assert result.response_rate == expected_rate
    assert result.questions[0].prompt == "第一志愿"
    assert result.questions[0].options[0].percentage == expected_option


@pytest.mark.asyncio
async def test_admin_roster_returns_identity_latest_answers_and_submission_count() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    question = make_question(survey.id, "第一志愿", 0)
    option = make_option(question.id, "视觉", 0)
    response = IntentionResponse(
        id=uuid4(),
        survey_id=survey.id,
        user_id=uuid4(),
        free_text="愿意调剂",
        submission_count=2,
        submitted_at=now,
        created_at=now,
        updated_at=now,
        revision=2,
    )
    user = SimpleNamespace(
        id=response.user_id,
        full_name="测试学生",
        student_number="20260001",
        email="student@connect.hkust-gz.edu.cn",
    )
    link = IntentionResponseOption(response_id=response.id, option_id=option.id)
    service, _session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=[option]),
            roster=AsyncMock(
                return_value=[SurveyRosterRecord(response=response, user=cast(User, user))]
            ),
            response_options_for_responses=AsyncMock(return_value={response.id: [link]}),
        ),
    )

    result = await service.roster(survey.id, context=make_context("admin"))

    assert result.total == 1
    assert result.items[0].full_name == "测试学生"
    assert result.items[0].answers[0].selected_options == ["视觉"]
    assert result.items[0].submission_count == 2


@pytest.mark.asyncio
async def test_roster_rejects_students_and_admin_student_view() -> None:
    now = datetime.now(UTC)
    service, _session = make_service(now)

    with pytest.raises(ApplicationError) as student_blocked:
        await service.roster(uuid4(), context=make_context())
    assert student_blocked.value.status_code == 403

    admin_student_view = make_context("admin", student_view=True)
    with pytest.raises(ApplicationError) as view_blocked:
        await service.roster(uuid4(), context=admin_student_view)
    assert view_blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_qr_token_rotation_hashes_secret_and_invalidates_old_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    question = make_question(survey.id, "第一志愿", 0)
    option = make_option(question.id, "机器人", 0)
    service, session = make_service(now)
    tokens = iter(["first-qr-token", "second-qr-token"])
    monkeypatch.setattr("app.intentions.service.random_urlsafe_token", lambda _size: next(tokens))
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=[option]),
            get_response=AsyncMock(return_value=None),
        ),
    )
    audit_context = make_audit_context("admin")

    first = await service.qr_token(survey.id, audit_context=audit_context)
    second = await service.qr_token(survey.id, audit_context=audit_context)

    assert first.token == "first-qr-token"
    assert second.token == "second-qr-token"
    assert survey.public_token_hash == sha256_hexdigest(second.token)
    assert second.token not in survey.public_token_hash
    assert "token=second-qr-token" in second.fill_url

    with pytest.raises(ApplicationError) as old_token:
        await service.student_detail(survey.id, context=make_context(), token=first.token)
    assert old_token.value.status_code == 404
    detail = await service.student_detail(survey.id, context=make_context(), token=second.token)
    assert detail.id == survey.id
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_closed_questionnaire_cannot_generate_another_qr_token() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="closed")
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(get_survey=AsyncMock(return_value=survey)),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.qr_token(
            survey.id,
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INTENTION_CLOSED"
    session.rollback.assert_awaited_once()
