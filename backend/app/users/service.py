from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError, ErrorDetail
from app.core.identifiers import uuid7
from app.core.security import is_campus_email, normalize_email
from app.users.models import Cohort, Direction, User
from app.users.repository import UserRepository
from app.users.schemas import (
    CohortCreateRequest,
    CohortPatchRequest,
    CohortResponse,
    DirectionCreateRequest,
    DirectionPatchRequest,
    DirectionResponse,
    UserPage,
    UserPatchRequest,
    UserResponse,
    UserRoleRequest,
)


@dataclass(frozen=True, slots=True)
class AuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class UserAdministrationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        clock: Any | None = None,
    ) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)
        self._auth = AuthenticationService(session, settings, clock=clock)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._settings = settings

    def _add_audit(
        self,
        audit: AuditContext,
        *,
        action: str,
        target_type: str,
        target_id: UUID,
        change_summary: dict[str, Any],
        result: str = "success",
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=audit.actor.user.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                result=result,
                change_summary=change_summary,
                created_at=self._clock(),
            )
        )

    @staticmethod
    def _not_found(resource: str) -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource}不存在。",
        )

    @staticmethod
    def _revision_conflict() -> ApplicationError:
        return ApplicationError(
            status_code=409,
            code="REVISION_CONFLICT",
            message="资源已被其他操作更新，请刷新后重试。",
        )

    async def _response(self, user: User) -> UserResponse:
        return await self._auth.user_response(user)

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        role: str | None,
        cohort_id: UUID | None,
        direction_id: UUID | None,
        search: str | None,
    ) -> UserPage:
        users, total = await self._users.list_users(
            page=page,
            page_size=page_size,
            status=status,
            role=role,
            cohort_id=cohort_id,
            direction_id=direction_id,
            search=search,
        )
        return UserPage(
            items=[await self._response(user) for user in users],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def disable_user(
        self,
        user_id: UUID,
        *,
        reason: str,
        audit: AuditContext,
    ) -> UserResponse:
        user = await self._users.get_by_id(user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise self._not_found("用户")
        if (
            user.role == "admin"
            and user.status == "active"
            and await self._users.active_admin_count() <= 1
        ):
            self._add_audit(
                audit,
                action="user.disable",
                target_type="user",
                target_id=user.id,
                change_summary={"reason": reason, "blocked": "last_active_admin"},
                result="denied",
            )
            await self._session.commit()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="不能禁用系统中最后一个激活管理员。",
            )
        now = self._clock()
        user.status = "disabled"
        user.disabled_at = now
        user.disabled_by = audit.actor.user.id
        user.disabled_reason = reason.strip()
        user.revision += 1
        await self._auth.revoke_all_sessions_for_user(user.id)
        self._add_audit(
            audit,
            action="user.disable",
            target_type="user",
            target_id=user.id,
            change_summary={"reason": reason.strip()},
        )
        await self._session.commit()
        return await self._response(user)

    async def restore_user(
        self,
        user_id: UUID,
        *,
        reason: str,
        audit: AuditContext,
    ) -> UserResponse:
        user = await self._users.get_by_id(user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise self._not_found("用户")
        if user.status != "disabled":
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="账号当前不处于禁用状态。",
            )
        user.status = "active" if user.email_verified_at is not None else "pending_email"
        user.disabled_at = None
        user.disabled_by = None
        user.disabled_reason = None
        user.revision += 1
        self._add_audit(
            audit,
            action="user.restore",
            target_type="user",
            target_id=user.id,
            change_summary={"reason": reason.strip(), "status": user.status},
        )
        await self._session.commit()
        return await self._response(user)

    async def patch_user(
        self,
        user_id: UUID,
        payload: UserPatchRequest,
        *,
        audit: AuditContext,
    ) -> UserResponse:
        user = await self._users.get_by_id(user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise self._not_found("用户")
        if user.revision != payload.revision:
            await self._session.rollback()
            raise self._revision_conflict()

        changes: dict[str, Any] = {}
        fields = payload.model_fields_set
        if "full_name" in fields and payload.full_name is not None:
            next_name = payload.full_name.strip()
            if not next_name:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="VALIDATION_ERROR",
                    message="请求参数不符合要求。",
                    details=[ErrorDetail(field="full_name", reason="EMPTY_VALUE")],
                )
            changes["full_name"] = {"from": user.full_name, "to": next_name}
            user.full_name = next_name
        if "student_number" in fields and payload.student_number is not None:
            next_number = payload.student_number.strip()
            changes["student_number"] = {"from": user.student_number, "to": next_number}
            user.student_number = next_number
        email_changed = False
        if "email" in fields and payload.email is not None:
            next_email = normalize_email(payload.email)
            if not is_campus_email(next_email, domain=self._settings.campus_email_domain):
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="VALIDATION_ERROR",
                    message="请求参数不符合要求。",
                    details=[ErrorDetail(field="email", reason="INVALID_CAMPUS_EMAIL")],
                )
            if next_email != user.email_normalized:
                changes["email"] = {"changed": True}
                user.email = next_email
                user.email_normalized = next_email
                user.email_verified_at = None
                user.status = "pending_email"
                user.disabled_at = None
                user.disabled_by = None
                user.disabled_reason = None
                email_changed = True

        if "cohort_id" in fields:
            if payload.cohort_id is not None:
                cohort = await self._users.get_cohort(payload.cohort_id)
                if cohort is None:
                    await self._session.rollback()
                    raise self._not_found("届次")
            changes["cohort_id"] = {
                "from": str(user.cohort_id) if user.cohort_id is not None else None,
                "to": str(payload.cohort_id) if payload.cohort_id is not None else None,
            }
            user.cohort_id = payload.cohort_id
        if "direction_id" in fields:
            if payload.direction_id is not None:
                direction = await self._users.get_direction(payload.direction_id)
                if direction is None:
                    await self._session.rollback()
                    raise self._not_found("方向")
            changes["direction_id"] = {
                "from": str(user.direction_id) if user.direction_id is not None else None,
                "to": str(payload.direction_id) if payload.direction_id is not None else None,
            }
            user.direction_id = payload.direction_id

        if not changes:
            await self._session.commit()
            return await self._response(user)

        user.revision += 1
        if email_changed:
            await self._auth.revoke_all_sessions_for_user(user.id)
            await self._auth.issue_email_verification_for_user(user)
            self._auth.enqueue_security_alert(user=user, event="email_changed")
        self._add_audit(
            audit,
            action="user.update",
            target_type="user",
            target_id=user.id,
            change_summary=changes,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            constraint_name = getattr(getattr(exc, "orig", None), "constraint_name", "")
            if constraint_name == "uq_users_email_normalized":
                field, reason = "email", "EMAIL_ALREADY_REGISTERED"
            elif constraint_name == "uq_users_student_number":
                field, reason = "student_number", "STUDENT_NUMBER_ALREADY_REGISTERED"
            else:
                raise
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="请求参数不符合要求。",
                details=[ErrorDetail(field=field, reason=reason)],
            ) from exc
        return await self._response(user)

    async def change_role(
        self,
        user_id: UUID,
        payload: UserRoleRequest,
        *,
        audit: AuditContext,
    ) -> UserResponse:
        user = await self._users.get_by_id(user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise self._not_found("用户")
        if (
            user.role == "admin"
            and payload.role != "admin"
            and user.status == "active"
            and await self._users.active_admin_count() <= 1
        ):
            self._add_audit(
                audit,
                action="user.role_change",
                target_type="user",
                target_id=user.id,
                change_summary={
                    "reason": payload.reason,
                    "blocked": "last_active_admin",
                },
                result="denied",
            )
            await self._session.commit()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="不能撤销系统中最后一个激活管理员的角色。",
            )
        previous_role = user.role
        user.role = payload.role
        user.revision += 1
        if previous_role != payload.role:
            await self._auth.revoke_all_sessions_for_user(user.id)
        self._add_audit(
            audit,
            action="user.role_change",
            target_type="user",
            target_id=user.id,
            change_summary={
                "from": previous_role,
                "to": payload.role,
                "reason": payload.reason.strip(),
            },
        )
        await self._session.commit()
        return await self._response(user)

    @staticmethod
    def _cohort_response(cohort: Cohort) -> CohortResponse:
        return CohortResponse(
            id=cohort.id,
            code=cohort.code,
            name=cohort.name,
            start_year=cohort.start_year,
            is_active=cohort.is_active,
            revision=cohort.revision,
        )

    async def list_cohorts(self) -> list[CohortResponse]:
        return [self._cohort_response(item) for item in await self._users.list_cohorts()]

    async def create_cohort(
        self, payload: CohortCreateRequest, *, audit: AuditContext
    ) -> CohortResponse:
        cohort = Cohort(
            id=uuid7(),
            code=payload.code.strip().lower(),
            name=payload.name.strip(),
            start_year=payload.start_year,
            is_active=True,
        )
        self._users.add_cohort(cohort)
        self._add_audit(
            audit,
            action="cohort.create",
            target_type="cohort",
            target_id=cohort.id,
            change_summary={"code": cohort.code, "name": cohort.name},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="届次编码已存在。",
            ) from exc
        return self._cohort_response(cohort)

    async def patch_cohort(
        self,
        cohort_id: UUID,
        payload: CohortPatchRequest,
        *,
        audit: AuditContext,
    ) -> CohortResponse:
        cohort = await self._users.get_cohort(cohort_id, for_update=True)
        if cohort is None:
            await self._session.rollback()
            raise self._not_found("届次")
        if cohort.revision != payload.revision:
            await self._session.rollback()
            raise self._revision_conflict()
        changes: dict[str, Any] = {}
        for field in ("name", "start_year", "is_active"):
            value = getattr(payload, field)
            if field in payload.model_fields_set and value is not None:
                changes[field] = {"from": getattr(cohort, field), "to": value}
                setattr(cohort, field, value.strip() if isinstance(value, str) else value)
        if changes:
            cohort.revision += 1
            self._add_audit(
                audit,
                action="cohort.update",
                target_type="cohort",
                target_id=cohort.id,
                change_summary=changes,
            )
            await self._session.commit()
        else:
            await self._session.commit()
        return self._cohort_response(cohort)

    @staticmethod
    def _direction_response(direction: Direction) -> DirectionResponse:
        return DirectionResponse(
            id=direction.id,
            code=direction.code,
            name=direction.name,
            description=direction.description,
            is_active=direction.is_active,
            revision=direction.revision,
        )

    async def list_directions(self) -> list[DirectionResponse]:
        return [self._direction_response(item) for item in await self._users.list_directions()]

    async def create_direction(
        self, payload: DirectionCreateRequest, *, audit: AuditContext
    ) -> DirectionResponse:
        direction = Direction(
            id=uuid7(),
            code=payload.code.strip().lower(),
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            is_active=True,
        )
        self._users.add_direction(direction)
        self._add_audit(
            audit,
            action="direction.create",
            target_type="direction",
            target_id=direction.id,
            change_summary={"code": direction.code, "name": direction.name},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="方向编码已存在。",
            ) from exc
        return self._direction_response(direction)

    async def patch_direction(
        self,
        direction_id: UUID,
        payload: DirectionPatchRequest,
        *,
        audit: AuditContext,
    ) -> DirectionResponse:
        direction = await self._users.get_direction(direction_id, for_update=True)
        if direction is None:
            await self._session.rollback()
            raise self._not_found("方向")
        if direction.revision != payload.revision:
            await self._session.rollback()
            raise self._revision_conflict()
        changes: dict[str, Any] = {}
        for field in ("name", "description", "is_active"):
            if field not in payload.model_fields_set:
                continue
            value = getattr(payload, field)
            if field == "name" and value is None:
                continue
            next_value = value.strip() if isinstance(value, str) else value
            changes[field] = {"from": getattr(direction, field), "to": next_value}
            setattr(direction, field, next_value)
        if changes:
            direction.revision += 1
            self._add_audit(
                audit,
                action="direction.update",
                target_type="direction",
                target_id=direction.id,
                change_summary=changes,
            )
            await self._session.commit()
        else:
            await self._session.commit()
        return self._direction_response(direction)
