from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.teams.models import Team, TeamMember
from app.teams.repository import TeamListRecord, TeamRepository
from app.teams.service import TeamAuditContext, TeamService


def make_context(*, role: str = "student") -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role=role),
            effective_role=role,
            is_admin=role == "admin",
            session=SimpleNamespace(student_view=False),
        ),
    )


def make_audit_context(*, role: str = "student") -> TeamAuditContext:
    return TeamAuditContext(
        actor=make_context(role=role),
        request_id="standalone-team-regression",
        ip_prefix="127.0.0.0/24",
    )


def make_team(
    name: str,
    *,
    captain_user_id: object | None = None,
    created_at: datetime | None = None,
) -> Team:
    now = created_at or datetime.now(UTC)
    captain_id = captain_user_id if captain_user_id is not None else uuid4()
    return Team(
        id=uuid4(),
        name=name,
        status="forming",
        captain_user_id=captain_id,
        invite_code_hash="a" * 64,
        invite_code_rotated_at=now,
        max_members=5,
        dissolved_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_service(now: datetime) -> tuple[TeamService, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    service = TeamService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    return service, session


def configure_invite_attempts(service: TeamService) -> None:
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            count_security_events=AsyncMock(return_value=0),
            add_security_event=Mock(),
        ),
    )


def test_team_models_have_no_competition_dependency_and_enforce_global_membership() -> None:
    assert "competition_id" not in Team.__table__.columns
    assert "competition_id" not in TeamMember.__table__.columns
    member_table = cast(Table, TeamMember.__table__)
    team_table = cast(Table, Team.__table__)
    current_user_index = next(
        index for index in member_table.indexes if index.name == "uq_team_members_current_user"
    )
    assert current_user_index.unique is True
    assert str(current_user_index.dialect_options["postgresql"]["where"])
    team_indexes = {index.name for index in team_table.indexes}
    assert "uq_teams_active_name" in team_indexes


@pytest.mark.asyncio
async def test_student_creates_team_without_competition_and_receives_invite_once() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    add_team = Mock()
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            add_team=add_team,
            add_member=add_member,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.create_team("  原子队  ", audit_context=audit_context)

    team = cast(Team, add_team.call_args.args[0])
    member = cast(TeamMember, add_member.call_args.args[0])
    assert team.name == "原子队"
    assert team.max_members == 5
    assert member.team_id == team.id
    assert member.user_id == audit_context.actor.user.id
    assert result.invite_code
    assert result.invite_code not in team.invite_code_hash
    assert "competition_id" not in result.model_dump()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_team_rejects_existing_global_membership() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    existing = make_team("已有队伍", captain_user_id=audit_context.actor.user.id)
    service, session = make_service(now)
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(team_for_user=AsyncMock(return_value=existing)),
    )

    with pytest.raises(ApplicationError) as captured:
        await service.create_team("另一支队伍", audit_context=audit_context)

    assert captured.value.code == "ALREADY_IN_TEAM"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_team_directory_exposes_summary_only() -> None:
    now = datetime.now(UTC)
    context = make_context()
    team = make_team("公开队名", created_at=now)
    service, _session = make_service(now)
    list_public_teams = AsyncMock(return_value=([TeamListRecord(team=team, member_count=2)], 1))
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            list_public_teams=list_public_teams,
            team_for_user=AsyncMock(return_value=None),
        ),
    )

    result = await service.public_teams(
        context=context,
        query="公开",
        page=1,
        page_size=20,
    )

    assert result.items[0].name == "公开队名"
    assert result.items[0].can_join is True
    assert "members" not in result.items[0].model_dump()
    assert "invite_code" not in result.items[0].model_dump()


@pytest.mark.asyncio
async def test_student_joins_team_without_registration_or_competition_window() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    team = make_team("第一队", created_at=now)
    service, session = make_service(now)
    configure_invite_attempts(service)
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            team_by_invite_hash=AsyncMock(return_value=team),
            member_count=AsyncMock(return_value=1),
            add_member=add_member,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.join_team("join-code", audit_context=audit_context)

    member = cast(TeamMember, add_member.call_args.args[0])
    assert result.id == team.id
    assert member.user_id == audit_context.actor.user.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_joins_smallest_available_team() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    larger = make_team("三人队", created_at=now - timedelta(minutes=2))
    smaller = make_team("一人队", created_at=now - timedelta(minutes=1))
    counts = {larger.id: 3, smaller.id: 1}
    service, session = make_service(now)
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[larger, smaller]),
            member_count=AsyncMock(side_effect=lambda team_id: counts[team_id]),
            add_member=add_member,
            add_team=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.auto_assign(audit_context=audit_context)

    assert result.assignment == "joined"
    assert result.id == smaller.id
    assert cast(TeamMember, add_member.call_args.args[0]).team_id == smaller.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_rolls_back_global_membership_conflict() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[]),
            add_member=Mock(),
            add_team=Mock(),
        ),
    )

    with pytest.raises(ApplicationError) as captured:
        await service.auto_assign(audit_context=audit_context)

    assert captured.value.code == "TEAM_MEMBERSHIP_CONFLICT"
    session.rollback.assert_awaited_once()
