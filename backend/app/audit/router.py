from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.audit.repository import AuditRepository
from app.audit.schemas import AuditLogPage, AuditLogResponse
from app.auth.dependencies import AdminContextDependency, SessionDependency

router = APIRouter(prefix="/admin/audit-logs", tags=["audit"])


def get_audit_repository(session: SessionDependency) -> AuditRepository:
    return AuditRepository(session)


AuditRepositoryDependency = Annotated[AuditRepository, Depends(get_audit_repository)]


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    repository: AuditRepositoryDependency,
    _admin: AdminContextDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    actor_user_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    target_type: Annotated[str | None, Query(max_length=100)] = None,
    target_id: UUID | None = None,
    request_id: Annotated[str | None, Query(max_length=64)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AuditLogPage:
    entries, total = await repository.list_entries(
        page=page,
        page_size=page_size,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        created_from=created_from,
        created_to=created_to,
    )
    return AuditLogPage(
        items=[
            AuditLogResponse(
                id=entry.id,
                actor_user_id=entry.actor_user_id,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                request_id=entry.request_id,
                ip_prefix=entry.ip_prefix,
                result=entry.result,
                change_summary=entry.change_summary,
                created_at=entry.created_at,
            )
            for entry in entries
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
