from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext
from app.competitions.models import (
    Competition,
    CompetitionRegistration,
    CompetitionTask,
    Team,
    TeamMember,
)
from app.competitions.policy import (
    registration_is_open,
    task_submission_is_open,
    team_is_valid_for_lock,
    timed_competition_status,
)
from app.competitions.repository import CompetitionRepository, TeamListRecord
from app.competitions.schemas import AdminReasonRequest, CompetitionCreateRequest
from app.competitions.service import CompetitionAuditContext, CompetitionService
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.submissions.models import Submission
from app.users.repository import UserRepository


def make_competition(
    now: datetime,
    *,
    status: str = "registration_open",
) -> Competition:
    actor_id = uuid4()
    return Competition(
        id=uuid4(),
        name="新生校内赛",
        description_markdown="说明",
        description_html="<p>说明</p>",
        rules_url=None,
        status=status,
        registration_start=now - timedelta(hours=1),
        registration_end=now + timedelta(hours=1),
        submission_start=now + timedelta(hours=2),
        submission_end=now + timedelta(days=1),
        min_team_size=2,
        max_team_size=4,
        created_by=actor_id,
        updated_by=actor_id,
        published_at=now - timedelta(hours=2),
        archived_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_team(competition: Competition, *, status: str = "forming") -> Team:
    now = competition.created_at
    return Team(
        id=uuid4(),
        competition_id=competition.id,
        name="测试队",
        status=status,
        captain_user_id=uuid4(),
        invite_code_hash="a" * 64,
        invite_code_rotated_at=now,
        min_size_waived_at=None,
        min_size_waived_by=None,
        waiver_reason=None,
        disqualified_at=None,
        disqualified_by=None,
        disqualification_reason=None,
        locked_at=now if status == "locked" else None,
        dissolved_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_task(competition: Competition, now: datetime) -> CompetitionTask:
    return CompetitionTask(
        id=uuid4(),
        competition_id=competition.id,
        title="赛题",
        description_markdown="说明",
        description_html="<p>说明</p>",
        resource_url=None,
        allowed_extensions=["zip"],
        max_total_bytes=1024,
        deadline=now + timedelta(hours=2),
        display_order=0,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def test_competition_status_windows_and_team_lock_policy() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)

    assert registration_is_open(competition, now)
    assert timed_competition_status(competition, now) == "registration_open"

    competition.registration_end = now - timedelta(minutes=1)
    competition.submission_start = now + timedelta(minutes=1)
    assert timed_competition_status(competition, now) == "registration_closed"

    competition.submission_start = now - timedelta(minutes=1)
    competition.submission_end = now + timedelta(hours=1)
    assert timed_competition_status(competition, now) == "submission_open"

    team = make_team(competition)
    assert not team_is_valid_for_lock(competition, team, 1)
    team.min_size_waived_at = now
    assert team_is_valid_for_lock(competition, team, 1)


def test_team_submission_requires_locked_team_and_open_task_deadline() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now, status="submission_open")
    competition.submission_start = now - timedelta(minutes=1)
    task = make_task(competition, now)
    team = make_team(competition, status="locked")

    assert task_submission_is_open(competition, task, team, now)
    team.status = "invalid"
    assert not task_submission_is_open(competition, task, team, now)
    team.status = "locked"
    task.deadline = now
    assert not task_submission_is_open(competition, task, team, now)


def test_competition_schema_rejects_invalid_windows_and_team_sizes() -> None:
    now = datetime.now(UTC)
    valid = {
        "name": "赛事",
        "description_markdown": "说明",
        "registration_start": now,
        "registration_end": now + timedelta(hours=1),
        "submission_start": now + timedelta(hours=1),
        "submission_end": now + timedelta(hours=2),
        "min_team_size": 2,
        "max_team_size": 4,
    }
    CompetitionCreateRequest(**valid)

    with pytest.raises(ValidationError):
        CompetitionCreateRequest(
            **{
                **valid,
                "registration_end": now + timedelta(hours=3),
            }
        )
    with pytest.raises(ValidationError):
        CompetitionCreateRequest(
            **{
                **valid,
                "min_team_size": 5,
            }
        )


def test_invite_code_hash_uses_secret_pepper_and_never_contains_plaintext() -> None:
    first = CompetitionService(
        cast(AsyncSession, object()),
        Settings(
            app_env="test",
            team_invite_code_pepper="first-independent-pepper-at-least-32-bytes",
        ),
    )
    second = CompetitionService(
        cast(AsyncSession, object()),
        Settings(
            app_env="test",
            team_invite_code_pepper="second-independent-pepper-at-least-32-bytes",
        ),
    )
    code = "A1B2C3D4E5F6"

    first_hash = first._invite_hash(code)
    second_hash = second._invite_hash(code)

    assert len(first_hash) == 64
    assert code not in first_hash
    assert first_hash != second_hash
    assert first_hash == first._invite_hash(code.lower())


def test_stage_five_database_metadata_contains_hard_constraints() -> None:
    submission_table = cast(Table, Submission.__table__)
    submission_constraint_names = {constraint.name for constraint in submission_table.constraints}
    assert "ck_submissions_owner_target_pair" in submission_constraint_names

    membership_table = cast(Table, TeamMember.__table__)
    membership_index = next(
        index
        for index in membership_table.indexes
        if index.name == "uq_team_members_current_competition_user"
    )
    assert membership_index.unique
    assert membership_index.dialect_options["postgresql"]["where"] is not None


@pytest.mark.asyncio
async def test_archiving_preserves_ineligible_team_statuses() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    competition = make_competition(now, status="submission_closed")
    locked = make_team(competition, status="locked")
    invalid = make_team(competition, status="invalid")
    disqualified = make_team(competition, status="disqualified")
    records = [
        TeamListRecord(team=team, member_count=2, submission_count=0)
        for team in (locked, invalid, disqualified)
    ]
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            list_teams=AsyncMock(return_value=records),
            get_registration=AsyncMock(return_value=None),
            team_for_user=AsyncMock(return_value=None),
            tasks=AsyncMock(return_value=[]),
        ),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    actor = cast(
        AuthenticatedContext,
        SimpleNamespace(user=SimpleNamespace(id=admin_id, role="admin"), session=object()),
    )

    await service.archive_competition(
        competition.id,
        audit_context=CompetitionAuditContext(
            actor=actor,
            request_id="archive-regression",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert competition.status == "archived"
    assert locked.status == "archived"
    assert invalid.status == "invalid"
    assert disqualified.status == "disqualified"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_cannot_create_second_current_campus_competition() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    existing = make_competition(now, status="draft")
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            acquire_campus_competition_lock=AsyncMock(),
            current_competition=AsyncMock(return_value=existing),
        ),
    )
    admin = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=admin_id, role="admin"),
            session=object(),
        ),
    )
    payload = CompetitionCreateRequest(
        name="第二条赛事",
        description_markdown="说明",
        registration_start=now,
        registration_end=now + timedelta(hours=1),
        submission_start=now + timedelta(hours=1),
        submission_end=now + timedelta(hours=2),
        min_team_size=2,
        max_team_size=4,
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.create_competition(
            payload,
            audit_context=CompetitionAuditContext(
                actor=admin,
                request_id="duplicate-campus-competition",
                ip_prefix="127.0.0.0/24",
            ),
        )

    assert blocked.value.status_code == 409
    assert blocked.value.code == "CAMPUS_COMPETITION_EXISTS"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_can_publish_announcement_only_competition_without_tasks() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    competition = make_competition(now, status="draft")
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            tasks=AsyncMock(return_value=[]),
            get_registration=AsyncMock(return_value=None),
            team_for_user=AsyncMock(return_value=None),
        ),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    admin = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=admin_id, role="admin"),
            session=object(),
        ),
    )

    result = await service.publish_competition(
        competition.id,
        audit_context=CompetitionAuditContext(
            actor=admin,
            request_id="publish-announcement-only",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert result.id == competition.id
    assert competition.status == "registration_open"
    assert competition.published_at == now
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_registration_disqualification_blocks_reregistration_and_team() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    student_id = uuid4()
    competition = make_competition(now, status="registration_open")
    registration = CompetitionRegistration(
        id=uuid4(),
        competition_id=competition.id,
        user_id=student_id,
        status="registered",
        registered_at=now,
        withdrawn_at=None,
        disqualified_at=None,
        disqualified_by=None,
        disqualification_reason=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )
    team = make_team(competition, status="forming")
    team.captain_user_id = student_id
    student = SimpleNamespace(
        id=student_id,
        full_name="被取消资格学生",
        student_number="20260001",
    )
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(return_value=registration),
            team_for_user=AsyncMock(return_value=team),
        ),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(get_by_id=AsyncMock(return_value=student)),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    admin = cast(
        AuthenticatedContext,
        SimpleNamespace(user=SimpleNamespace(id=admin_id, role="admin"), session=object()),
    )
    student_context = cast(
        AuthenticatedContext,
        SimpleNamespace(user=SimpleNamespace(id=student_id, role="student"), session=object()),
    )

    response = await service.disqualify_registration(
        competition.id,
        student_id,
        AdminReasonRequest(reason="违反赛事资格要求"),
        audit_context=CompetitionAuditContext(
            actor=admin,
            request_id="disqualify-registration",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert response.status == "disqualified"
    assert response.disqualification_reason == "违反赛事资格要求"
    assert registration.status == "disqualified"
    assert team.status == "disqualified"
    assert team.disqualification_reason == "队内成员被取消个人参赛资格。"

    with pytest.raises(ApplicationError) as blocked:
        await service.register(
            competition.id,
            audit_context=CompetitionAuditContext(
                actor=student_context,
                request_id="blocked-reregister",
                ip_prefix="127.0.0.0/24",
            ),
        )
    assert blocked.value.status_code == 409
    assert blocked.value.code == "COMPETITION_DISQUALIFIED"


@pytest.mark.asyncio
async def test_admin_member_removal_invalidates_undersized_locked_team() -> None:
    now = datetime.now(UTC)
    admin_id = uuid4()
    removed_user_id = uuid4()
    competition = make_competition(now, status="submission_open")
    competition.submission_start = now - timedelta(minutes=1)
    team = make_team(competition, status="locked")
    member = TeamMember(
        id=uuid4(),
        team_id=team.id,
        competition_id=competition.id,
        user_id=removed_user_id,
        joined_at=now - timedelta(days=1),
        left_at=None,
        added_by_admin=False,
        admin_reason=None,
    )
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_team=AsyncMock(return_value=team),
            current_member=AsyncMock(return_value=member),
            get_competition=AsyncMock(return_value=competition),
            member_count=AsyncMock(return_value=2),
            current_members=AsyncMock(return_value=[]),
        ),
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    admin = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=admin_id, role="admin"),
            session=object(),
        ),
    )

    response = await service.admin_remove_member(
        team.id,
        removed_user_id,
        AdminReasonRequest(reason="纠正错误成员记录"),
        audit_context=CompetitionAuditContext(
            actor=admin,
            request_id="remove-member-regression",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert member.left_at == now
    assert team.status == "invalid"
    assert team.revision == 2
    assert response.status == "invalid"
    session.commit.assert_awaited_once()
