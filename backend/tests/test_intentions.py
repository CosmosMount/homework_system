from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

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
    FirstChoiceDirectionRecord,
    IntentionRepository,
    SurveyListRecord,
    SurveyOptionCount,
    SurveyRosterRecord,
)
from app.intentions.schemas import (
    IntentionAnswerRequest,
    IntentionAudienceInput,
    IntentionDirectionAssignmentRequest,
    IntentionDirectionMapping,
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


def make_context(
    role: str = "student",
    *,
    student_view: bool = False,
    direction_id: UUID | None = None,
) -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role=role, direction_id=direction_id),
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
    title: str = "培训方向问卷",
    all_students: bool = True,
) -> IntentionSurvey:
    actor_id = uuid4()
    return IntentionSurvey(
        id=uuid4(),
        title=title,
        description_markdown="## 请选择",
        description_html="<h2>请选择</h2>",
        status=status,
        all_students=all_students,
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

    direction_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionAudienceInput(all_students=True, direction_ids=[direction_id])
    with pytest.raises(ValidationError):
        IntentionAudienceInput(all_students=False, direction_ids=[])
    with pytest.raises(ValidationError):
        IntentionAudienceInput(
            all_students=False,
            direction_ids=[direction_id, direction_id],
        )


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
            replace_audience=AsyncMock(),
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
async def test_admin_creates_questionnaire_for_selected_active_directions() -> None:
    now = datetime.now(UTC)
    direction_ids = [uuid4(), uuid4()]
    directions = [
        cast(Direction, SimpleNamespace(id=direction_id)) for direction_id in direction_ids
    ]
    service, session = make_service(now)
    active_directions = AsyncMock(return_value=directions)
    replace_audience = AsyncMock()
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            add_survey=Mock(),
            add_question=Mock(),
            add_option=Mock(),
            active_directions_by_ids=active_directions,
            replace_audience=replace_audience,
        ),
    )
    payload = IntentionSurveyCreateRequest(
        title="分组问卷",
        questions=[question_payload("第一志愿", "机器人")],
        audience=IntentionAudienceInput(
            all_students=False,
            direction_ids=direction_ids,
        ),
    )

    result = await service.create(payload, audit_context=make_audit_context("admin"))

    assert result.audience.all_students is False
    assert set(result.audience.direction_ids) == set(direction_ids)
    active_directions.assert_awaited_once_with(direction_ids)
    replace_audience.assert_awaited_once_with(result.id, direction_ids)
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.change_summary == {"all_students": False, "direction_count": 2}


@pytest.mark.asyncio
async def test_admin_rejects_inactive_questionnaire_audience_and_rolls_back() -> None:
    now = datetime.now(UTC)
    direction_ids = [uuid4(), uuid4()]
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            active_directions_by_ids=AsyncMock(
                return_value=[cast(Direction, SimpleNamespace(id=direction_ids[0]))]
            )
        ),
    )
    payload = IntentionSurveyCreateRequest(
        title="分组问卷",
        questions=[question_payload("第一志愿", "机器人")],
        audience=IntentionAudienceInput(
            all_students=False,
            direction_ids=direction_ids,
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.create(payload, audit_context=make_audit_context("admin"))

    assert blocked.value.code == "INVALID_INTENTION_AUDIENCE"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


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
            audience_direction_ids=AsyncMock(return_value=[]),
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
    direction_ids = [uuid4(), uuid4()]
    replace_audience = AsyncMock()
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
            active_directions_by_ids=AsyncMock(
                return_value=[
                    cast(Direction, SimpleNamespace(id=direction_id))
                    for direction_id in direction_ids
                ]
            ),
            replace_audience=replace_audience,
            audience_direction_ids=AsyncMock(return_value=direction_ids),
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
        audience=IntentionAudienceInput(
            all_students=False,
            direction_ids=direction_ids,
        ),
    )

    result = await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert result.title == "更新后的问卷"
    assert result.revision == 2
    assert result.max_submissions == 4
    assert result.audience.all_students is False
    assert set(result.audience.direction_ids) == set(direction_ids)
    assert [question.prompt for question in result.questions] == ["第一志愿", "第二志愿"]
    assert result.questions[1].allow_multiple is True
    assert "<script" not in survey.description_html.lower()
    session.delete.assert_awaited_once_with(old_question)
    replace_audience.assert_awaited_once_with(survey.id, direction_ids)
    assert session.flush.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["open", "closed"])
async def test_admin_updates_opened_questionnaire_without_replacing_answer_structure(
    status: str,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status=status, max_submissions=1, all_students=False)
    first = make_question(survey.id, "第一志愿", 0)
    second = make_question(survey.id, "第二志愿", 1, allow_multiple=True)
    options = [
        make_option(first.id, "机器人", 0),
        make_option(first.id, "视觉", 1),
        make_option(second.id, "电控", 0),
        make_option(second.id, "嵌入式", 1),
    ]
    question_ids = [question.id for question in [first, second]]
    option_ids = [option.id for option in options]
    old_direction_id = uuid4()
    new_direction_id = uuid4()
    replace_audience = AsyncMock()
    add_question = Mock()
    add_option = Mock()
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(side_effect=[[first, second], [first, second]]),
            options=AsyncMock(return_value=options),
            responded_count=AsyncMock(return_value=3),
            active_directions_by_ids=AsyncMock(
                return_value=[cast(Direction, SimpleNamespace(id=new_direction_id))]
            ),
            audience_direction_ids=AsyncMock(side_effect=[[old_direction_id], [new_direction_id]]),
            replace_audience=replace_audience,
            add_question=add_question,
            add_option=add_option,
        ),
    )
    payload = IntentionSurveyPatchRequest(
        revision=1,
        title="开放后的新标题",
        description_markdown="## 更新后的说明",
        questions=[
            question_payload("首选技术组", "机器人", "视觉"),
            question_payload("可调剂技术组", "电控", "嵌入式", allow_multiple=True),
        ],
        max_submissions=5,
        audience=IntentionAudienceInput(
            all_students=False,
            direction_ids=[new_direction_id],
        ),
    )

    result = await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert result.status == status
    assert result.title == "开放后的新标题"
    assert result.revision == 2
    assert [question.id for question in result.questions] == question_ids
    assert [option.id for question in result.questions for option in question.options] == option_ids
    assert [question.prompt for question in result.questions] == [
        "首选技术组",
        "可调剂技术组",
    ]
    assert [option.label for option in result.questions[0].options] == ["机器人", "视觉"]
    session.delete.assert_not_awaited()
    add_question.assert_not_called()
    add_option.assert_not_called()
    replace_audience.assert_awaited_once_with(survey.id, [new_direction_id])
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.change_summary == {
        "status": status,
        "title_changed": True,
        "description_changed": True,
        "submission_limit_changed": True,
        "schedule_changed": False,
        "audience_changed": True,
        "question_prompt_change_count": 2,
        "all_students": False,
        "direction_count": 1,
    }
    assert "开放后的新标题" not in repr(audit.change_summary)
    assert "首选技术组" not in repr(audit.change_summary)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "revision", "expected_code"),
    [
        ("archived", 1, "INTENTION_ARCHIVED"),
        ("draft", 2, "REVISION_CONFLICT"),
        ("open", 2, "REVISION_CONFLICT"),
    ],
)
async def test_admin_update_rejects_archived_and_stale_revisions(
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
@pytest.mark.parametrize(
    "change",
    ["question_count", "question_type", "option_label", "option_count", "option_order"],
)
async def test_opened_questionnaire_rejects_answer_structure_changes(change: str) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="open")
    question = make_question(survey.id, "第一志愿", 0)
    options = [
        make_option(question.id, "机器人", 0),
        make_option(question.id, "视觉", 1),
    ]
    submitted_questions = [question_payload("可修改的题目", "机器人", "视觉")]
    if change == "question_count":
        submitted_questions.append(question_payload("新增题目", "电控"))
    elif change == "question_type":
        submitted_questions[0] = question_payload(
            "可修改的题目",
            "机器人",
            "视觉",
            allow_multiple=True,
        )
    elif change == "option_label":
        submitted_questions[0] = question_payload("可修改的题目", "机器人", "机械")
    elif change == "option_count":
        submitted_questions[0] = question_payload("可修改的题目", "机器人")
    elif change == "option_order":
        submitted_questions[0] = question_payload("可修改的题目", "视觉", "机器人")
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=[]),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=options),
        ),
    )
    payload = IntentionSurveyPatchRequest(
        revision=1,
        title="更新后的问卷",
        questions=submitted_questions,
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert blocked.value.code == "INTENTION_ANSWER_STRUCTURE_IMMUTABLE"
    assert question.prompt == "第一志愿"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    cast(Mock, service._audit.add).assert_not_called()


@pytest.mark.asyncio
async def test_opened_questionnaire_rejects_inactive_new_audience_before_mutation() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="open")
    direction_id = uuid4()
    questions = AsyncMock()
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_directions_by_ids=AsyncMock(return_value=[]),
            questions=questions,
        ),
    )
    payload = IntentionSurveyPatchRequest(
        revision=1,
        title="更新后的问卷",
        questions=[question_payload("第一志愿", "视觉")],
        audience=IntentionAudienceInput(
            all_students=False,
            direction_ids=[direction_id],
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    assert blocked.value.code == "INVALID_INTENTION_AUDIENCE"
    assert survey.title == "培训方向问卷"
    questions.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_opened_questionnaire_update_rolls_back_when_commit_fails() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="closed")
    question = make_question(survey.id, "第一志愿", 0)
    options = [make_option(question.id, "视觉", 0)]
    service, session = make_service(now)
    session.commit.side_effect = RuntimeError("database unavailable")
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=[]),
            questions=AsyncMock(return_value=[question]),
            options=AsyncMock(return_value=options),
            replace_audience=AsyncMock(),
        ),
    )
    payload = IntentionSurveyPatchRequest(
        revision=1,
        title="更新后的问卷",
        questions=[question_payload("首选方向", "视觉")],
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.patch(survey.id, payload, audit_context=make_audit_context("admin"))

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_closed_questionnaire_can_reopen_while_archived_remains_terminal() -> None:
    now = datetime.now(UTC)
    direction_id = uuid4()
    survey = make_survey(now, status="draft", all_students=False)
    service, session = make_service(now)
    audience_direction_ids = AsyncMock(return_value=[direction_id])
    active_directions = AsyncMock(return_value=[cast(Direction, SimpleNamespace(id=direction_id))])
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=audience_direction_ids,
            active_directions_by_ids=active_directions,
            list_surveys=AsyncMock(
                return_value=[
                    SurveyListRecord(
                        survey,
                        2,
                        0,
                        False,
                        direction_ids=(direction_id,),
                    )
                ]
            ),
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
    audience_direction_ids.assert_awaited_once_with(survey.id)
    active_directions.assert_awaited_once_with([direction_id])


@pytest.mark.asyncio
async def test_first_open_rejects_a_deactivated_audience_direction() -> None:
    now = datetime.now(UTC)
    direction_id = uuid4()
    survey = make_survey(now, status="draft", all_students=False)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=[direction_id]),
            active_directions_by_ids=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.transition(
            survey.id,
            "open",
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INVALID_INTENTION_AUDIENCE"
    assert survey.status == "draft"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_list_passes_current_direction_to_audience_filter() -> None:
    now = datetime.now(UTC)
    direction_id = uuid4()
    context = make_context(direction_id=direction_id)
    service, _session = make_service(now)
    list_surveys = AsyncMock(return_value=[])
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(list_surveys=list_surveys),
    )

    result = await service.list_student(context=context)

    assert result.total == 0
    list_surveys.assert_awaited_once_with(
        student_user_id=context.user.id,
        student_direction_id=direction_id,
        open_only=True,
    )


@pytest.mark.asyncio
async def test_qr_link_does_not_bypass_questionnaire_audience() -> None:
    now = datetime.now(UTC)
    direction_id = uuid4()
    survey = make_survey(now, all_students=False)
    targeted = AsyncMock(return_value=False)
    service, _session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            student_direction_is_targeted=targeted,
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.student_detail(
            survey.id,
            context=make_context(direction_id=direction_id),
            token="initial-token",
        )

    assert blocked.value.status_code == 404
    targeted.assert_awaited_once_with(survey.id, direction_id)


@pytest.mark.asyncio
async def test_non_target_student_cannot_submit_questionnaire() -> None:
    now = datetime.now(UTC)
    direction_id = uuid4()
    survey = make_survey(now, all_students=False)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            student_direction_is_targeted=AsyncMock(return_value=False),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(
                answers=[
                    IntentionAnswerRequest(
                        question_id=uuid4(),
                        selected_option_ids=[uuid4()],
                    )
                ]
            ),
            audit_context=IntentionAuditContext(
                actor=make_context(direction_id=direction_id),
                request_id="intention-regression",
                ip_prefix="127.0.0.0/24",
            ),
        )

    assert blocked.value.status_code == 404
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_first_choice_direction_assignment_schema_requires_confirmation_and_unique_options() -> (
    None
):
    option_id = uuid4()
    direction_id = uuid4()

    with pytest.raises(ValidationError):
        IntentionDirectionAssignmentRequest.model_validate(
            {
                "question_id": uuid4(),
                "option_mappings": [
                    {"option_id": option_id, "direction_id": direction_id},
                    {"option_id": option_id, "direction_id": uuid4()},
                ],
                "confirm_overwrite": True,
            }
        )
    with pytest.raises(ValidationError):
        IntentionDirectionAssignmentRequest.model_validate(
            {
                "question_id": uuid4(),
                "option_mappings": [
                    {"option_id": option_id, "direction_id": direction_id},
                ],
                "confirm_overwrite": False,
            }
        )


@pytest.mark.parametrize(
    "title",
    ["培训方向问卷", "意向选择问卷", "问卷意向选择"],
)
@pytest.mark.asyncio
async def test_first_choice_direction_assignment_rejects_other_survey_titles(
    title: str,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, title=title)
    questions = AsyncMock()
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=questions,
        ),
    )
    payload = IntentionDirectionAssignmentRequest(
        question_id=uuid4(),
        option_mappings=[
            IntentionDirectionMapping(
                option_id=uuid4(),
                direction_id=uuid4(),
            )
        ],
        confirm_overwrite=True,
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.apply_first_choice_directions(
            survey.id,
            payload,
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.status_code == 422
    assert blocked.value.code == "INVALID_INTENTION_DIRECTION_SURVEY"
    questions.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    cast(Mock, service._audit.add).assert_not_called()


@pytest.mark.asyncio
async def test_admin_applies_latest_first_choices_to_active_student_directions() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, title="意向选择")
    first = make_question(survey.id, "第一志愿", 0)
    second = make_question(survey.id, "第二志愿", 1)
    robot_option = make_option(first.id, "机器人", 0)
    vision_option = make_option(first.id, "视觉", 1)
    second_option = make_option(second.id, "电控", 0)
    robot_direction_id = uuid4()
    vision_direction_id = uuid4()
    robot_direction = cast(Direction, SimpleNamespace(id=robot_direction_id))
    vision_direction = cast(Direction, SimpleNamespace(id=vision_direction_id))
    first_user = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            direction_id=vision_direction_id,
            revision=3,
        ),
    )
    second_user = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            direction_id=vision_direction_id,
            revision=5,
        ),
    )
    records = [
        FirstChoiceDirectionRecord(user=first_user, option_id=robot_option.id),
        FirstChoiceDirectionRecord(user=second_user, option_id=vision_option.id),
    ]
    service, session = make_service(now)
    active_directions = AsyncMock(return_value=[robot_direction, vision_direction])
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first, second]),
            options=AsyncMock(return_value=[robot_option, vision_option, second_option]),
            active_directions_by_ids=active_directions,
            responded_count=AsyncMock(return_value=3),
            active_student_first_choices=AsyncMock(return_value=records),
        ),
    )
    payload = IntentionDirectionAssignmentRequest(
        question_id=first.id,
        option_mappings=[
            IntentionDirectionMapping(
                option_id=robot_option.id,
                direction_id=robot_direction_id,
            ),
            IntentionDirectionMapping(
                option_id=vision_option.id,
                direction_id=vision_direction_id,
            ),
        ],
        confirm_overwrite=True,
    )

    result = await service.apply_first_choice_directions(
        survey.id,
        payload,
        audit_context=make_audit_context("admin"),
    )

    assert result.eligible_response_count == 2
    assert result.updated_count == 1
    assert result.unchanged_count == 1
    assert result.skipped_response_count == 1
    assert first_user.direction_id == robot_direction_id
    assert first_user.revision == 4
    assert second_user.direction_id == vision_direction_id
    assert second_user.revision == 5
    direction_call = active_directions.await_args
    assert direction_call is not None
    assert set(direction_call.args[0]) == {
        robot_direction_id,
        vision_direction_id,
    }
    session.commit.assert_awaited_once()
    audit_items = [
        item.args[0] for item in cast(Mock, service._audit.add).call_args_list if item is not None
    ]
    assert [item.action for item in audit_items] == [
        "user.direction_assign_from_intention",
        "intention.first_choice_directions_apply",
    ]
    assert audit_items[0].target_type == "user"
    assert audit_items[0].target_id == first_user.id
    assert audit_items[0].change_summary["source_survey_id"] == str(survey.id)
    assert "option" not in repr([item.change_summary for item in audit_items])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("submitted_question", "allow_multiple", "expected_code"),
    [
        ("second", False, "INVALID_INTENTION_FIRST_CHOICE"),
        ("first", True, "INTENTION_FIRST_CHOICE_MUST_BE_SINGLE"),
    ],
)
async def test_first_choice_direction_assignment_rejects_wrong_or_multiple_question(
    submitted_question: str,
    allow_multiple: bool,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, title="意向选择")
    first = make_question(
        survey.id,
        "第一志愿",
        0,
        allow_multiple=allow_multiple,
    )
    second = make_question(survey.id, "第二志愿", 1)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first, second]),
        ),
    )
    question_id = first.id if submitted_question == "first" else second.id
    payload = IntentionDirectionAssignmentRequest(
        question_id=question_id,
        option_mappings=[IntentionDirectionMapping(option_id=uuid4(), direction_id=uuid4())],
        confirm_overwrite=True,
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.apply_first_choice_directions(
            survey.id,
            payload,
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == expected_code
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_choice_direction_assignment_requires_complete_active_mapping() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, title="意向选择")
    first = make_question(survey.id, "第一志愿", 0)
    robot_option = make_option(first.id, "机器人", 0)
    vision_option = make_option(first.id, "视觉", 1)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first]),
            options=AsyncMock(return_value=[robot_option, vision_option]),
        ),
    )
    payload = IntentionDirectionAssignmentRequest(
        question_id=first.id,
        option_mappings=[
            IntentionDirectionMapping(
                option_id=robot_option.id,
                direction_id=uuid4(),
            )
        ],
        confirm_overwrite=True,
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.apply_first_choice_directions(
            survey.id,
            payload,
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INVALID_INTENTION_DIRECTION_MAPPING"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_choice_direction_assignment_rejects_inactive_direction_or_no_students() -> (
    None
):
    now = datetime.now(UTC)
    survey = make_survey(now, title="意向选择")
    first = make_question(survey.id, "第一志愿", 0)
    option = make_option(first.id, "机器人", 0)
    direction_id = uuid4()
    payload = IntentionDirectionAssignmentRequest(
        question_id=first.id,
        option_mappings=[
            IntentionDirectionMapping(
                option_id=option.id,
                direction_id=direction_id,
            )
        ],
        confirm_overwrite=True,
    )

    for directions, expected_code in [
        ([], "INVALID_INTENTION_DIRECTION_MAPPING"),
        ([cast(Direction, SimpleNamespace(id=direction_id))], "NO_INTENTION_DIRECTION_RESPONSES"),
    ]:
        service, session = make_service(now)
        service._repo = cast(
            IntentionRepository,
            SimpleNamespace(
                get_survey=AsyncMock(return_value=survey),
                questions=AsyncMock(return_value=[first]),
                options=AsyncMock(return_value=[option]),
                active_directions_by_ids=AsyncMock(return_value=directions),
                responded_count=AsyncMock(return_value=1),
                active_student_first_choices=AsyncMock(return_value=[]),
            ),
        )

        with pytest.raises(ApplicationError) as blocked:
            await service.apply_first_choice_directions(
                survey.id,
                payload,
                audit_context=make_audit_context("admin"),
            )

        assert blocked.value.code == expected_code
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_first_choice_repository_locks_only_active_students_in_stable_order() -> None:
    session = AsyncMock(spec=AsyncSession)
    rows = Mock()
    rows.all.return_value = []
    session.execute.return_value = rows
    repository = IntentionRepository(cast(AsyncSession, session))

    records = await repository.active_student_first_choices(uuid4(), uuid4())

    assert records == []
    execute_call = session.execute.await_args
    assert execute_call is not None
    sql = str(execute_call.args[0])
    assert "users.role =" in sql
    assert "users.status =" in sql
    assert "ORDER BY users.id" in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_first_choice_direction_assignment_rolls_back_when_commit_fails() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, title="意向选择")
    first = make_question(survey.id, "第一志愿", 0)
    option = make_option(first.id, "机器人", 0)
    direction_id = uuid4()
    direction = cast(Direction, SimpleNamespace(id=direction_id))
    user = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            direction_id=None,
            revision=1,
        ),
    )
    service, session = make_service(now)
    session.commit.side_effect = RuntimeError("commit failed")
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            questions=AsyncMock(return_value=[first]),
            options=AsyncMock(return_value=[option]),
            active_directions_by_ids=AsyncMock(return_value=[direction]),
            responded_count=AsyncMock(return_value=1),
            active_student_first_choices=AsyncMock(
                return_value=[
                    FirstChoiceDirectionRecord(
                        user=user,
                        option_id=option.id,
                    )
                ]
            ),
        ),
    )
    payload = IntentionDirectionAssignmentRequest(
        question_id=first.id,
        option_mappings=[
            IntentionDirectionMapping(
                option_id=option.id,
                direction_id=direction_id,
            )
        ],
        confirm_overwrite=True,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.apply_first_choice_directions(
            survey.id,
            payload,
            audit_context=make_audit_context("admin"),
        )

    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()


async def test_first_choice_direction_assignment_rejects_student_views() -> None:
    service, _session = make_service(datetime.now(UTC))
    payload = IntentionDirectionAssignmentRequest(
        question_id=uuid4(),
        option_mappings=[IntentionDirectionMapping(option_id=uuid4(), direction_id=uuid4())],
        confirm_overwrite=True,
    )

    for context in [
        make_audit_context(),
        IntentionAuditContext(
            actor=make_context("admin", student_view=True),
            request_id="intention-regression",
            ip_prefix="127.0.0.0/24",
        ),
    ]:
        with pytest.raises(ApplicationError) as blocked:
            await service.apply_first_choice_directions(
                uuid4(),
                payload,
                audit_context=context,
            )
        assert blocked.value.status_code == 403


def test_email_notification_request_rejects_duplicate_members() -> None:
    member_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionEmailNotificationRequest(recipient_user_ids=[member_id, member_id])


def test_email_notification_request_rejects_duplicate_directions() -> None:
    direction_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionEmailNotificationRequest(
            recipient_scope="direction",
            direction_ids=[direction_id, direction_id],
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"direction_id": uuid4()},
        {"direction_ids": [uuid4()]},
        {"recipient_scope": "direction"},
        {
            "recipient_scope": "direction",
            "direction_ids": [uuid4()],
            "recipient_user_ids": [uuid4()],
        },
        {"recipient_scope": "direction", "direction_id": uuid4(), "direction_ids": [uuid4()]},
        {"recipient_scope": "all", "recipient_user_ids": [uuid4()]},
        {"recipient_scope": "all", "direction_id": uuid4()},
        {"recipient_scope": "all", "direction_ids": [uuid4()]},
    ],
)
def test_email_notification_request_rejects_incompatible_scope(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IntentionEmailNotificationRequest.model_validate(payload)


def test_email_notification_request_accepts_manual_directions_legacy_and_all() -> None:
    assert (
        IntentionEmailNotificationRequest(recipient_user_ids=[uuid4()]).recipient_scope == "manual"
    )
    assert (
        IntentionEmailNotificationRequest(
            recipient_scope="direction",
            direction_ids=[uuid4(), uuid4()],
        ).recipient_scope
        == "direction"
    )
    assert (
        IntentionEmailNotificationRequest(
            recipient_scope="direction",
            direction_id=uuid4(),
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
async def test_admin_queues_active_students_in_selected_directions() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    direction_ids = [uuid4(), uuid4()]
    directions = [
        cast(Direction, SimpleNamespace(id=direction_id, is_active=True))
        for direction_id in direction_ids
    ]
    members = [
        cast(
            User,
            SimpleNamespace(
                id=uuid4(),
                email=f"direction-{index}@connect.hkust-gz.edu.cn",
                full_name=f"技术组学生 {index}",
            ),
        )
        for index in range(2)
    ]
    service, session = make_service(now)
    active_directions = AsyncMock(return_value=directions)
    active_scope = AsyncMock(return_value=members)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_directions_by_ids=active_directions,
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
            direction_ids=direction_ids,
        ),
        audit_context=make_audit_context("admin"),
    )

    assert result.requested_count == 2
    assert result.queued_count == 2
    active_directions.assert_awaited_once_with(direction_ids)
    active_scope.assert_awaited_once_with(direction_ids=direction_ids)
    assert outbox_add.call_count == 2
    session.commit.assert_awaited_once()
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.change_summary == {
        "recipient_scope": "direction",
        "direction_ids": sorted(str(direction_id) for direction_id in direction_ids),
        "requested_count": 2,
        "queued_count": 2,
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
    active_scope.assert_awaited_once_with(direction_ids=None)
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
    direction_ids = [uuid4(), uuid4()]
    service, session = make_service(now)
    active_scope = AsyncMock()
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            active_directions_by_ids=AsyncMock(
                return_value=[cast(Direction, SimpleNamespace(id=direction_ids[0]))]
            ),
            active_students_for_email_scope=active_scope,
        ),
    )

    with pytest.raises(ApplicationError) as invalid_direction:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(
                recipient_scope="direction",
                direction_ids=direction_ids,
            ),
            audit_context=make_audit_context("admin"),
        )
    assert invalid_direction.value.code == "INVALID_INTENTION_EMAIL_DIRECTION"
    active_scope.assert_not_awaited()

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
async def test_questionnaire_email_rejects_members_outside_its_audience() -> None:
    now = datetime.now(UTC)
    target_direction_id = uuid4()
    member = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            email="outside@connect.hkust-gz.edu.cn",
            full_name="非目标学生",
            direction_id=uuid4(),
        ),
    )
    survey = make_survey(now, all_students=False)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=[target_direction_id]),
            active_students_by_ids=AsyncMock(return_value=[member]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(recipient_user_ids=[member.id]),
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INVALID_INTENTION_EMAIL_RECIPIENTS"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_questionnaire_email_rejects_directions_outside_its_audience() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, all_students=False)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=[uuid4()]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.send_email_notifications(
            survey.id,
            IntentionEmailNotificationRequest(
                recipient_scope="direction",
                direction_ids=[uuid4()],
            ),
            audit_context=make_audit_context("admin"),
        )

    assert blocked.value.code == "INVALID_INTENTION_EMAIL_DIRECTION"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_email_scope_uses_only_questionnaire_target_directions() -> None:
    now = datetime.now(UTC)
    target_direction_ids = [uuid4(), uuid4()]
    survey = make_survey(now, all_students=False)
    service, session = make_service(now)
    active_scope = AsyncMock(
        return_value=[
            cast(
                User,
                SimpleNamespace(
                    id=uuid4(),
                    email="target@connect.hkust-gz.edu.cn",
                    full_name="目标学生",
                    direction_id=target_direction_ids[0],
                ),
            )
        ]
    )
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            audience_direction_ids=AsyncMock(return_value=target_direction_ids),
            active_students_for_email_scope=active_scope,
        ),
    )
    service._outbox = cast(
        OutboxRepository,
        SimpleNamespace(
            existing_event_keys=AsyncMock(return_value=set()),
            add=Mock(),
        ),
    )

    result = await service.send_email_notifications(
        survey.id,
        IntentionEmailNotificationRequest(recipient_scope="all"),
        audit_context=make_audit_context("admin"),
    )

    assert result.requested_count == 1
    active_scope.assert_awaited_once_with(direction_ids=target_direction_ids)
    session.commit.assert_awaited_once()


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
    active_student_count = AsyncMock(return_value=total_students)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            responded_count=AsyncMock(return_value=responded),
            active_student_count=active_student_count,
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
    active_student_count.assert_awaited_once_with(direction_ids=None)


@pytest.mark.asyncio
async def test_admin_stats_count_only_current_target_students() -> None:
    now = datetime.now(UTC)
    direction_ids = [uuid4(), uuid4()]
    survey = make_survey(now, all_students=False)
    service, _session = make_service(now)
    active_student_count = AsyncMock(return_value=7)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            responded_count=AsyncMock(return_value=2),
            audience_direction_ids=AsyncMock(return_value=direction_ids),
            active_student_count=active_student_count,
            questions=AsyncMock(return_value=[]),
            option_counts=AsyncMock(return_value=[]),
        ),
    )

    result = await service.stats(survey.id, context=make_context("admin"))

    assert result.total_active_students == 7
    active_student_count.assert_awaited_once_with(direction_ids=direction_ids)


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
