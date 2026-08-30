from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.announcements.schemas import (
    AnnouncementAdminPage,
    AnnouncementAdminResponse,
    AnnouncementCreateRequest,
    AnnouncementDetailResponse,
    AnnouncementPage,
    AnnouncementPatchRequest,
    DashboardResponse,
)
from app.announcements.service import (
    AnnouncementAuditContext,
    AnnouncementService,
)
from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id

router = APIRouter(tags=["announcements"])


def get_announcement_service(session: SessionDependency) -> AnnouncementService:
    return AnnouncementService(session)


AnnouncementServiceDependency = Annotated[
    AnnouncementService,
    Depends(get_announcement_service),
]


def _audit_context(
    request: Request,
    admin: AdminContextDependency,
) -> AnnouncementAuditContext:
    return AnnouncementAuditContext(
        actor=admin,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    service: AnnouncementServiceDependency,
    context: AuthenticatedContextDependency,
) -> DashboardResponse:
    return await service.dashboard(context=context)


@router.get("/announcements", response_model=AnnouncementPage)
async def list_announcements(
    service: AnnouncementServiceDependency,
    context: AuthenticatedContextDependency,
    query: Annotated[str | None, Query(max_length=200)] = None,
    unread: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AnnouncementPage:
    return await service.list_student(
        context=context,
        page=page,
        page_size=page_size,
        query=query,
        unread=unread,
    )


@router.get(
    "/announcements/{announcement_id}",
    response_model=AnnouncementDetailResponse,
)
async def get_announcement(
    announcement_id: UUID,
    service: AnnouncementServiceDependency,
    context: AuthenticatedContextDependency,
) -> AnnouncementDetailResponse:
    return await service.get_student(announcement_id, context=context)


@router.get("/admin/announcements", response_model=AnnouncementAdminPage)
async def list_admin_announcements(
    service: AnnouncementServiceDependency,
    _admin: AdminContextDependency,
    announcement_status: Annotated[
        Literal["draft", "scheduled", "published", "archived"] | None,
        Query(alias="status"),
    ] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AnnouncementAdminPage:
    return await service.list_admin(
        page=page,
        page_size=page_size,
        status=announcement_status,
        query=query,
    )


@router.post(
    "/admin/announcements",
    response_model=AnnouncementAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_announcement(
    payload: AnnouncementCreateRequest,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AnnouncementAdminResponse:
    return await service.create_draft(
        payload,
        audit=_audit_context(request, admin),
    )


@router.get(
    "/admin/announcements/{announcement_id}",
    response_model=AnnouncementAdminResponse,
)
async def get_admin_announcement(
    announcement_id: UUID,
    service: AnnouncementServiceDependency,
    _admin: AdminContextDependency,
) -> AnnouncementAdminResponse:
    return await service.get_admin(announcement_id)


@router.patch(
    "/admin/announcements/{announcement_id}",
    response_model=AnnouncementAdminResponse,
)
async def patch_announcement(
    announcement_id: UUID,
    payload: AnnouncementPatchRequest,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AnnouncementAdminResponse:
    return await service.patch(
        announcement_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.delete(
    "/admin/announcements/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_announcement(
    announcement_id: UUID,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.remove(
        announcement_id,
        audit=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/announcements/{announcement_id}/publish",
    response_model=AnnouncementAdminResponse,
)
async def publish_announcement(
    announcement_id: UUID,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
    _idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> AnnouncementAdminResponse:
    return await service.publish(
        announcement_id,
        audit=_audit_context(request, admin),
    )


@router.post(
    "/admin/announcements/{announcement_id}/archive",
    response_model=AnnouncementAdminResponse,
)
async def archive_announcement(
    announcement_id: UUID,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AnnouncementAdminResponse:
    return await service.archive(
        announcement_id,
        audit=_audit_context(request, admin),
    )


@router.post(
    "/admin/announcements/{announcement_id}/send-update",
    response_model=AnnouncementAdminResponse,
)
async def send_announcement_update(
    announcement_id: UUID,
    request: Request,
    service: AnnouncementServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
    _idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> AnnouncementAdminResponse:
    return await service.send_update(
        announcement_id,
        audit=_audit_context(request, admin),
    )
