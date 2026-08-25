from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.auth.dependencies import AdminContextDependency, CsrfDependency, SessionDependency
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.notifications.admin_service import OutboxAdministrationService
from app.notifications.schemas import OutboxJobPage, OutboxJobResponse

router = APIRouter(prefix="/admin/mail-outbox", tags=["mail-administration"])


def get_outbox_administration_service(
    session: SessionDependency,
) -> OutboxAdministrationService:
    return OutboxAdministrationService(session)


OutboxAdministrationServiceDependency = Annotated[
    OutboxAdministrationService,
    Depends(get_outbox_administration_service),
]


@router.get("", response_model=OutboxJobPage)
async def list_outbox_jobs(
    service: OutboxAdministrationServiceDependency,
    _admin: AdminContextDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query(max_length=16)] = None,
    job_type: Annotated[str | None, Query(max_length=64)] = None,
) -> OutboxJobPage:
    return await service.list_jobs(
        page=page,
        page_size=page_size,
        status=status,
        job_type=job_type,
    )


@router.post("/{job_id}/retry", response_model=OutboxJobResponse)
async def retry_outbox_job(
    job_id: UUID,
    request: Request,
    service: OutboxAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> OutboxJobResponse:
    return await service.retry(
        job_id,
        admin=admin,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )
