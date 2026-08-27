from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticatedContext
from app.competitions.models import Competition, CompetitionRegistration, Team, TeamMember
from app.competitions.repository import (
    CompetitionRepository,
    TeamDirectoryRecord,
)
from app.competitions.service import CompetitionAuditContext, CompetitionService
from app.core.config import Settings
from app.core.errors import ApplicationError


def make_context() -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role="student"),
            session=SimpleNamespace(student_view=False),
        ),
    )


def make_audit_context() -> CompetitionAuditContext:
    return CompetitionAuditContext(
        actor=make_context(),
        request_id="team-matching-regression",
        ip_prefix="127.0.0.0/24",
    )


def make_competition(now: datetime) -> Competition:
    actor_id = uuid4()
    return Competition(
        id=uuid4(),
        name="新生校内赛",
        description_markdown="公告",
        description_html="<p>公告</p>",
        rules_url=None,
        status="registration_open",
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


def make_team(
    competition: Competition,
    name: str,
    *,
    created_at: datetime | None = None,
) -> Team:
    captain_id = uuid4()
    return Team(
        id=uuid4(),
        competition_id=competition.id,
        name=name,
        status="forming",
        captain_user_id=captain_id,
        invite_code_hash="a" * 64,
        invite_code_rotated_at=competition.created_at,
        min_size_waived_at=None,
        min_size_waived_by=None,
        waiver_reason=None,
        disqualified_at=None,
        disqualified_by=None,
        disqualification_reason=None,
        locked_at=None,
        dissolved_at=None,
        created_at=created_at or competition.created_at,
        updated_at=competition.created_at,
        revision=1,
    )


def make_registration(
    competition_id: UUID,
    user_id: UUID,
    now: datetime,
) -> CompetitionRegistration:
    return CompetitionRegistration(
        id=uuid4(),
        competition_id=competition_id,
        user_id=user_id,
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


def make_service(now: datetime) -> tuple[CompetitionService, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    service = CompetitionService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    return service, session


def configure_invite_attempts(service: CompetitionService) -> None:
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            count_security_events=AsyncMock(return_value=0),
            add_security_event=Mock(),
        ),
    )


@pytest.mark.asyncio
async def test_team_directory_forwards_search_and_pagination_without_private_fields() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    team = make_team(competition, "原子队")
    context = make_context()
    service, _session = make_service(now)
    list_public_teams = AsyncMock(
        return_value=([TeamDirectoryRecord(team=team, member_count=2)], 23)
    )
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            list_public_teams=list_public_teams,
        ),
    )

    result = await service.public_teams(
        competition.id,
        context=context,
        query=" 原子 ",
        page=2,
        page_size=10,
    )

    list_public_teams.assert_awaited_once_with(
        competition.id,
        query=" 原子 ",
        page=2,
        page_size=10,
        max_team_size=competition.max_team_size,
    )
    assert result.total == 23
    assert result.page == 2
    assert result.items[0].name == "原子队"
    assert result.items[0].can_join is True
    assert "invite_code" not in result.items[0].model_dump()
    assert "members" not in result.items[0].model_dump()


@pytest.mark.asyncio
async def test_registered_student_joins_team_with_valid_invite() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    team = make_team(competition, "第一队")
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    service, session = make_service(now)
    configure_invite_attempts(service)
    add_member = Mock()
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(return_value=registration),
            team_for_user=AsyncMock(return_value=None),
            team_by_invite_hash=AsyncMock(return_value=team),
            member_count=AsyncMock(return_value=1),
            add_member=add_member,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.join_team(
        competition.id,
        "join-code",
        audit_context=audit_context,
    )

    added = cast(TeamMember, add_member.call_args.args[0])
    assert result.id == team.id
    assert added.user_id == audit_context.actor.user.id
    assert added.team_id == team.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unregistered", "REGISTRATION_REQUIRED"),
        ("invalid_invite", "INVITE_CODE_INVALID"),
        ("full", "TEAM_FULL"),
    ],
)
async def test_invite_join_rejects_invalid_eligibility_and_capacity(
    case: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    team = make_team(competition, "第一队")
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    service, session = make_service(now)
    configure_invite_attempts(service)
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(
                return_value=None if case == "unregistered" else registration
            ),
            team_for_user=AsyncMock(return_value=None),
            team_by_invite_hash=AsyncMock(return_value=None if case == "invalid_invite" else team),
            member_count=AsyncMock(return_value=competition.max_team_size if case == "full" else 1),
            add_member=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.join_team(
            competition.id,
            "join-code",
            audit_context=audit_context,
        )

    assert blocked.value.code == expected_code
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_joins_the_smallest_forming_team() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    larger = make_team(competition, "三人队", created_at=now - timedelta(minutes=2))
    smaller = make_team(competition, "一人队", created_at=now - timedelta(minutes=1))
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    service, session = make_service(now)
    add_member = Mock()
    counts = {larger.id: 3, smaller.id: 1}
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(return_value=registration),
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[larger, smaller]),
            member_count=AsyncMock(side_effect=lambda team_id: counts[team_id]),
            add_member=add_member,
            add_team=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.auto_assign(competition.id, audit_context=audit_context)

    added = cast(TeamMember, add_member.call_args.args[0])
    assert result.assignment == "joined"
    assert result.id == smaller.id
    assert result.invite_code is None
    assert added.team_id == smaller.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_creates_team_and_returns_invite_only_once() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    service, _session = make_service(now)
    add_team = Mock()
    team_for_user = AsyncMock(return_value=None)
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(return_value=registration),
            team_for_user=team_for_user,
            forming_teams_for_update=AsyncMock(return_value=[]),
            add_member=Mock(),
            add_team=add_team,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    created = await service.auto_assign(competition.id, audit_context=audit_context)
    team = cast(Team, add_team.call_args.args[0])

    assert created.assignment == "created"
    assert created.invite_code is not None
    assert created.invite_code not in team.invite_code_hash
    assert team.captain_user_id == audit_context.actor.user.id

    team_for_user.return_value = team
    later = await service.my_team(competition.id, context=audit_context.actor)
    assert "invite_code" not in later.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unregistered", "REGISTRATION_REQUIRED"),
        ("existing", "ALREADY_IN_TEAM"),
        ("closed", "COMPETITION_REGISTRATION_CLOSED"),
    ],
)
async def test_auto_assign_rejects_invalid_state(case: str, expected_code: str) -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    existing = make_team(competition, "已有队伍")
    if case == "closed":
        competition.status = "registration_closed"
        competition.registration_end = now - timedelta(minutes=1)
        competition.submission_start = now + timedelta(minutes=1)
    service, session = make_service(now)
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(
                return_value=None if case == "unregistered" else registration
            ),
            team_for_user=AsyncMock(return_value=existing if case == "existing" else None),
            forming_teams_for_update=AsyncMock(return_value=[]),
            add_member=Mock(),
            add_team=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.auto_assign(competition.id, audit_context=audit_context)

    assert blocked.value.code == expected_code
    if case == "unregistered":
        session.rollback.assert_not_awaited()
    else:
        session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_integrity_conflict_rolls_back() -> None:
    now = datetime.now(UTC)
    competition = make_competition(now)
    audit_context = make_audit_context()
    registration = make_registration(competition.id, audit_context.actor.user.id, now)
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    service._competitions = cast(
        CompetitionRepository,
        SimpleNamespace(
            get_competition=AsyncMock(return_value=competition),
            get_registration=AsyncMock(return_value=registration),
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[]),
            add_member=Mock(),
            add_team=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(ApplicationError) as blocked:
        await service.auto_assign(competition.id, audit_context=audit_context)

    assert blocked.value.code == "TEAM_MEMBERSHIP_CONFLICT"
    session.rollback.assert_awaited_once()
