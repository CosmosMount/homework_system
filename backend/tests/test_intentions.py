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
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.intentions.repository import (
    IntentionRepository,
    SurveyListRecord,
    SurveyOptionCount,
)
from app.intentions.schemas import (
    IntentionOptionInput,
    IntentionResponseRequest,
    IntentionSurveyCreateRequest,
)
from app.intentions.service import IntentionAuditContext, IntentionService


def make_context(role: str = "student") -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role=role),
            session=SimpleNamespace(student_view=False),
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
    allow_multiple: bool = False,
) -> IntentionSurvey:
    actor_id = uuid4()
    return IntentionSurvey(
        id=uuid4(),
        title="培训方向意向",
        description_markdown="## 请选择",
        description_html="<h2>请选择</h2>",
        status=status,
        allow_multiple=allow_multiple,
        starts_at=None,
        ends_at=None,
        public_token_hash=sha256_hexdigest("initial-token"),
        created_by=actor_id,
        updated_by=actor_id,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_option(survey_id: object, label: str, order: int) -> IntentionOption:
    return IntentionOption(
        id=uuid4(),
        survey_id=survey_id,
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


def test_intention_schema_rejects_blank_duplicate_and_invalid_selection_payloads() -> None:
    valid_option = [IntentionOptionInput(label="视觉")]

    with pytest.raises(ValidationError):
        IntentionSurveyCreateRequest(title="   ", options=valid_option)
    with pytest.raises(ValidationError):
        IntentionSurveyCreateRequest(
            title="培训方向",
            options=[IntentionOptionInput(label="视觉"), IntentionOptionInput(label=" 视觉 ")],
        )
    with pytest.raises(ValidationError):
        IntentionOptionInput(label="  ")

    option_id = uuid4()
    with pytest.raises(ValidationError):
        IntentionResponseRequest(selected_option_ids=[option_id, option_id])


@pytest.mark.asyncio
async def test_admin_creates_sanitized_intention_survey_and_options() -> None:
    now = datetime.now(UTC)
    service, session = make_service(now)
    persistence_order: list[str] = []
    add_survey = Mock(side_effect=lambda _survey: persistence_order.append("survey"))
    add_option = Mock(side_effect=lambda _option: persistence_order.append("option"))
    session.flush.side_effect = lambda: persistence_order.append("flush")
    session.commit.side_effect = lambda: persistence_order.append("commit")
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(add_survey=add_survey, add_option=add_option),
    )
    payload = IntentionSurveyCreateRequest(
        title="  培训方向意向  ",
        description_markdown="## 说明\n<script>alert(1)</script>",
        options=[IntentionOptionInput(label="机器人"), IntentionOptionInput(label="视觉")],
        allow_multiple=True,
    )

    result = await service.create(payload, audit_context=make_audit_context("admin"))

    survey = cast(IntentionSurvey, add_survey.call_args.args[0])
    assert result.title == "培训方向意向"
    assert result.option_count == 2
    assert "<h3" in survey.description_html
    assert "<script" not in survey.description_html.lower()
    assert survey.public_token_hash != "initial-token"
    assert len(survey.public_token_hash) == 64
    assert [call.args[0].label for call in add_option.call_args_list] == ["机器人", "视觉"]
    assert persistence_order == ["survey", "flush", "option", "option", "commit"]
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_intention_status_moves_forward_only() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, status="draft")
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            list_surveys=AsyncMock(
                return_value=[
                    SurveyListRecord(survey, option_count=2, responded_count=0, has_response=False)
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
        await service.transition(survey.id, "archived", audit_context=audit_context)
    ).status == "archived"

    with pytest.raises(ApplicationError) as blocked:
        await service.transition(survey.id, "open", audit_context=audit_context)
    assert blocked.value.code == "STATE_CONFLICT"
    assert session.commit.await_count == 3
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_can_submit_and_modify_an_open_intention() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now, allow_multiple=True)
    first = make_option(survey.id, "机器人", 0)
    second = make_option(survey.id, "视觉", 1)
    service, session = make_service(now)
    add_response = Mock()
    add_response_option = Mock()
    get_response = AsyncMock(return_value=None)
    response_options = AsyncMock(return_value=[])
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            options=AsyncMock(return_value=[first, second]),
            get_response=get_response,
            response_options=response_options,
            add_response=add_response,
            add_response_option=add_response_option,
        ),
    )
    audit_context = make_audit_context()

    created = await service.submit_response(
        survey.id,
        IntentionResponseRequest(
            selected_option_ids=[first.id, second.id], free_text="  愿意担任队长  "
        ),
        audit_context=audit_context,
    )
    response = cast(IntentionResponse, add_response.call_args.args[0])
    assert created.selected_option_ids == [first.id, second.id]
    assert created.free_text == "愿意担任队长"
    assert response.revision == 1

    existing_link = IntentionResponseOption(response_id=response.id, option_id=first.id)
    get_response.return_value = response
    response_options.return_value = [existing_link]
    updated = await service.submit_response(
        survey.id,
        IntentionResponseRequest(selected_option_ids=[second.id], free_text="  "),
        audit_context=audit_context,
    )

    assert updated.selected_option_ids == [second.id]
    assert updated.free_text is None
    assert response.revision == 2
    session.delete.assert_awaited_once_with(existing_link)
    session.flush.assert_awaited_once()
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_single_choice_and_closed_survey_reject_invalid_answers() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    first = make_option(survey.id, "机器人", 0)
    second = make_option(survey.id, "视觉", 1)
    service, session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            options=AsyncMock(return_value=[first, second]),
            get_response=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(ApplicationError) as multiple:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(selected_option_ids=[first.id, second.id]),
            audit_context=make_audit_context(),
        )
    assert multiple.value.status_code == 422

    survey.status = "closed"
    with pytest.raises(ApplicationError) as closed:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(selected_option_ids=[first.id]),
            audit_context=make_audit_context(),
        )
    assert closed.value.code == "INTENTION_CLOSED"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_intention_response_integrity_conflict_is_recoverable() -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    option = make_option(survey.id, "机器人", 0)
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            options=AsyncMock(return_value=[option]),
            get_response=AsyncMock(return_value=None),
            add_response=Mock(),
            add_response_option=Mock(),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.submit_response(
            survey.id,
            IntentionResponseRequest(selected_option_ids=[option.id]),
            audit_context=make_audit_context(),
        )

    assert blocked.value.code == "INTENTION_RESPONSE_CONFLICT"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("total_students", "responded", "response_count", "expected_rate", "expected_option"),
    [(0, 0, 0, 0.0, 0.0), (8, 2, 1, 25.0, 50.0)],
)
async def test_admin_stats_handle_zero_and_nonzero_denominators(
    total_students: int,
    responded: int,
    response_count: int,
    expected_rate: float,
    expected_option: float,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    option = make_option(survey.id, "机器人", 0)
    service, _session = make_service(now)
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
            responded_count=AsyncMock(return_value=responded),
            active_student_count=AsyncMock(return_value=total_students),
            option_counts=AsyncMock(
                return_value=[SurveyOptionCount(option=option, response_count=response_count)]
            ),
        ),
    )

    result = await service.stats(survey.id, context=make_context("admin"))

    assert result.response_rate == expected_rate
    assert result.options[0].percentage == expected_option


@pytest.mark.asyncio
async def test_qr_token_rotation_hashes_secret_and_invalidates_old_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    survey = make_survey(now)
    option = make_option(survey.id, "机器人", 0)
    service, session = make_service(now)
    tokens = iter(["first-qr-token", "second-qr-token"])
    monkeypatch.setattr("app.intentions.service.random_urlsafe_token", lambda _size: next(tokens))
    service._repo = cast(
        IntentionRepository,
        SimpleNamespace(
            get_survey=AsyncMock(return_value=survey),
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
async def test_closed_intention_cannot_generate_another_qr_token() -> None:
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
