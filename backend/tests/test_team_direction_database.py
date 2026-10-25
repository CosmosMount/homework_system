import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.models import Session
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.teams.models import TeamSettings
from app.teams.schemas import TeamSettingsUpdateRequest
from app.teams.service import TeamAuditContext, TeamService
from app.users.direction_service import UserDirectionService
from app.users.models import Direction, User
from app.users.schemas import SelfDirectionRequest
from app.users.service import AuditContext

DATABASE_URL = os.environ.get("TEAM_DIRECTION_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="需要显式指定隔离队伍测试数据库")


def actor_context(user: User) -> AuthenticatedContext:
    return AuthenticatedContext(
        user=user, session=cast(Session, SimpleNamespace(student_view=False))
    )


def team_audit(user: User) -> TeamAuditContext:
    return TeamAuditContext(
        actor=actor_context(user), request_id="isolated-team-test", ip_prefix="127.0.0.0/24"
    )


@pytest.mark.asyncio
async def test_real_database_serializes_join_direction_change_and_permission_switch() -> None:
    assert DATABASE_URL is not None
    url = make_url(DATABASE_URL)
    assert url.host in {"127.0.0.1", "localhost"}
    assert url.database == "pnx_test_team_direction"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(app_env="test")
    now = datetime.now(UTC)
    suffix = uuid4().hex
    try:
        async with factory() as session:
            directions = [
                Direction(id=uuid4(), code=f"{name}-{suffix}", name=label, is_active=True)
                for name, label in (
                    ("mechanical", "机械"),
                    ("algorithm", "算法"),
                    ("control", "嵌入式-控制"),
                    ("hardware", "嵌入式-硬件"),
                )
            ]
            session.add_all(directions)
            await session.flush()
            users = []
            for index, direction in enumerate(
                [directions[0]] * 3 + [directions[1], directions[2], directions[0], directions[3]]
            ):
                email = f"team-{suffix}-{index}@connect.hkust-gz.edu.cn"
                users.append(
                    User(
                        id=uuid4(),
                        email=email,
                        email_normalized=email,
                        student_number=f"{suffix}-{index}",
                        full_name=f"隔离测试{index}",
                        password_hash="unused-isolated-test-password-hash",
                        role="admin" if index == 5 else "student",
                        status="active",
                        direction_id=direction.id,
                        email_verified_at=now,
                        password_changed_at=now,
                    )
                )
            session.add_all(users)
            await session.execute(
                update(TeamSettings).values(is_team_open=True, is_direction_change_open=True)
            )
            await session.commit()
            user_ids = [user.id for user in users]
            algorithm_direction = directions[1].id

        async def load_user(session: AsyncSession, user_id: UUID) -> User:
            user = await session.get(User, user_id)
            assert user is not None
            return user

        async with factory() as session:
            captain = await load_user(session, user_ids[0])
            created = await TeamService(session, settings).create_team(
                f"隔离人数规则测试-{suffix}", audit_context=team_audit(captain)
            )
            assert created.composition.mechanical == 1
            assert created.composition.is_complete is False
            assert created.max_members == 5
            invite_code, team_id = created.invite_code, created.id

        async def join(user_id: UUID) -> str:
            async with factory() as session:
                user = await load_user(session, user_id)
                try:
                    await TeamService(session, settings).join_team(
                        invite_code, audit_context=team_audit(user)
                    )
                    return "joined"
                except ApplicationError as error:
                    return error.code

        results = await asyncio.wait_for(
            asyncio.gather(join(user_ids[1]), join(user_ids[2])), timeout=10
        )
        assert sorted(results) == ["TEAM_COMPOSITION_CONFLICT", "joined"]
        assert await join(user_ids[4]) == "joined"
        assert await join(user_ids[6]) == "joined"

        async def change_captain_direction() -> str:
            async with factory() as session:
                captain = await load_user(session, user_ids[0])
                try:
                    await UserDirectionService(session, settings).change(
                        SelfDirectionRequest(
                            direction_id=algorithm_direction, revision=captain.revision
                        ),
                        audit=AuditContext(
                            actor=actor_context(captain),
                            request_id="isolated-change",
                            ip_prefix="127.0.0.0/24",
                        ),
                    )
                    return "changed"
                except ApplicationError as error:
                    return error.code

        results = await asyncio.wait_for(
            asyncio.gather(change_captain_direction(), join(user_ids[3])), timeout=10
        )
        assert results.count("TEAM_COMPOSITION_CONFLICT") == 1
        async with factory() as session:
            captain = await load_user(session, user_ids[0])
            team = await TeamService(session, settings).my_team(context=actor_context(captain))
            assert team is not None and team.id == team_id
            assert team.composition.algorithm == 1
            assert team.composition.mechanical <= 2
            assert team.composition.embedded_control == 1
            assert team.composition.embedded_hardware == 1
            assert team.composition.is_complete is True

        async with factory() as session:
            admin = await load_user(session, user_ids[5])
            config = await session.scalar(select(TeamSettings))
            assert config is not None
            response = await TeamService(session, settings).update_admin_team_settings(
                TeamSettingsUpdateRequest(is_direction_change_open=False, revision=config.revision),
                audit_context=team_audit(admin),
            )
            assert response.is_team_open is True
            assert response.is_direction_change_open is False
            unchanged = await TeamService(session, settings).update_admin_team_settings(
                TeamSettingsUpdateRequest(
                    is_direction_change_open=False, revision=response.revision
                ),
                audit_context=team_audit(admin),
            )
            assert unchanged.revision == response.revision
        assert await change_captain_direction() == "DIRECTION_CHANGE_CLOSED"
    finally:
        await engine.dispose()
