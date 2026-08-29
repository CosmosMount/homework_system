from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.help_requests.schemas import (
    AdminHelpRequestDetail,
    AdminHelpRequestPage,
    HelpRequestCreateRequest,
    HelpRequestDetail,
    HelpRequestPage,
    HelpRequestResolutionRequest,
    HelpRequestStatus,
    HelpRequestType,
    PublicHelpRequestDetail,
)
from app.help_requests.service import (
    HelpRequestAuditContext,
    HelpRequestService,
)

router = APIRouter(tags=["help-requests"])


def get_help_request_service(session: SessionDependency) -> HelpRequestService:
    return HelpRequestService(session)


HelpRequestServiceDependency = Annotated[
    HelpRequestService,
    Depends(get_help_request_service),
]


def _audit_context(
    request: Request, context: AuthenticatedContextDependency
) -> HelpRequestAuditContext:
    return HelpRequestAuditContext(
        actor=context,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/help-requests", response_model=HelpRequestPage)
async def list_help_requests(
    service: HelpRequestServiceDependency,
    context: AuthenticatedContextDependency,
    request_type: Annotated[HelpRequestType | None, Query(alias="type")] = None,
    request_status: Annotated[HelpRequestStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HelpRequestPage:
    return await service.list_student(
        context=context,
        request_type=request_type,
        status=request_status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/help-requests",
    response_model=HelpRequestDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_help_request(
    payload: HelpRequestCreateRequest,
    request: Request,
    service: HelpRequestServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> HelpRequestDetail:
    return await service.create(
        payload,
        audit_context=_audit_context(request, context),
    )


@router.get("/help-requests/public", response_model=HelpRequestPage)
async def list_public_help_requests(
    service: HelpRequestServiceDependency,
    context: AuthenticatedContextDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HelpRequestPage:
    return await service.list_public(
        context=context,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/help-requests/public/{request_id}",
    response_model=PublicHelpRequestDetail,
)
async def get_public_help_request(
    request_id: UUID,
    service: HelpRequestServiceDependency,
    context: AuthenticatedContextDependency,
) -> PublicHelpRequestDetail:
    return await service.public_detail(request_id, context=context)


@router.get("/help-requests/{request_id}", response_model=HelpRequestDetail)
async def get_help_request(
    request_id: UUID,
    service: HelpRequestServiceDependency,
    context: AuthenticatedContextDependency,
) -> HelpRequestDetail:
    return await service.student_detail(request_id, context=context)


@router.get("/admin/help-requests", response_model=AdminHelpRequestPage)
async def list_admin_help_requests(
    service: HelpRequestServiceDependency,
    context: AdminContextDependency,
    request_type: Annotated[HelpRequestType | None, Query(alias="type")] = None,
    request_status: Annotated[HelpRequestStatus | None, Query(alias="status")] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminHelpRequestPage:
    return await service.list_admin(
        context=context,
        request_type=request_type,
        status=request_status,
        query=query,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/admin/help-requests/{request_id}",
    response_model=AdminHelpRequestDetail,
)
async def get_admin_help_request(
    request_id: UUID,
    service: HelpRequestServiceDependency,
    context: AdminContextDependency,
) -> AdminHelpRequestDetail:
    return await service.admin_detail(request_id, context=context)


@router.put(
    "/admin/help-requests/{request_id}/resolution",
    response_model=AdminHelpRequestDetail,
)
async def resolve_admin_help_request(
    request_id: UUID,
    payload: HelpRequestResolutionRequest,
    request: Request,
    service: HelpRequestServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AdminHelpRequestDetail:
    return await service.resolve(
        request_id,
        payload,
        audit_context=_audit_context(request, context),
    )
