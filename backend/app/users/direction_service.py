from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.teams.composition import TeamCompositionService
from app.teams.repository import TeamRepository
from app.users.repository import UserRepository
from app.users.schemas import (
    CategorySummary,
    SelfDirectionOptionsResponse,
    SelfDirectionRequest,
    UserResponse,
)
from app.users.service import AuditContext


class UserDirectionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._teams = TeamRepository(session)
        self._composition = TeamCompositionService(session)
        self._assignments = AssignmentRepository(session)
        self._audit = AuditRepository(session)
        self._auth = AuthenticationService(session, settings)

    @staticmethod
    def _require_student(context: AuthenticatedContext) -> None:
        if context.user.role != "student" or context.user.status != "active":
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅学生可修改本人方向。"
            )

    async def options(self, context: AuthenticatedContext) -> SelfDirectionOptionsResponse:
        self._require_student(context)
        settings = await self._teams.team_settings()
        if settings is None:
            raise RuntimeError("team_settings singleton is missing")
        return SelfDirectionOptionsResponse(
            is_direction_change_open=settings.is_direction_change_open,
            directions=[
                CategorySummary(id=direction.id, code=direction.code, name=direction.name)
                for direction in await self._users.list_directions()
                if direction.is_active
            ],
        )

    async def change(self, payload: SelfDirectionRequest, *, audit: AuditContext) -> UserResponse:
        self._require_student(audit.actor)
        settings = await self._teams.team_settings(for_update=True)
        if settings is None:
            raise RuntimeError("team_settings singleton is missing")
        if not settings.is_direction_change_open:
            await self._session.rollback()
            raise ApplicationError(
                status_code=403,
                code="DIRECTION_CHANGE_CLOSED",
                message="管理员暂未开放学生自助修改技术方向。",
            )
        user = await self._users.get_by_id(audit.actor.user.id, for_update=True)
        if user is None or user.role != "student" or user.status != "active":
            await self._session.rollback()
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅学生可修改本人方向。"
            )
        if user.revision != payload.revision:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409, code="REVISION_CONFLICT", message="个人资料已更新，请刷新后重试。"
            )
        direction = await self._users.get_direction(payload.direction_id, for_update=True)
        if direction is None or not direction.is_active:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400, code="INVALID_DIRECTION", message="请选择仍启用的技术方向。"
            )
        if user.direction_id != direction.id:
            await self._composition.validate_direction_changes({user.id: direction.id})
            previous = user.direction_id
            user.direction_id = direction.id
            user.revision += 1
            now = datetime.now(UTC)
            added_count = await self._assignments.add_historical_assignment_audiences_for_student(
                user=user, created_at=now
            )
            self._audit.add(
                AuditLog(
                    id=uuid7(),
                    actor_user_id=user.id,
                    action="user.self_direction_update",
                    target_type="user",
                    target_id=user.id,
                    request_id=audit.request_id,
                    ip_prefix=audit.ip_prefix,
                    result="success",
                    created_at=now,
                    change_summary={
                        "direction_id": {
                            "from": str(previous) if previous else None,
                            "to": str(direction.id),
                        },
                        "historical_assignment_audience_added_count": added_count,
                    },
                )
            )
        response = await self._auth.user_response(user)
        await self._session.commit()
        return response
