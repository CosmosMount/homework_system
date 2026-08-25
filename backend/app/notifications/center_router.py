from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.announcements.schemas import (
    NotificationReadAllRequest,
    NotificationReadAllResponse,
    StudentNotificationPage,
    StudentNotificationResponse,
)
from app.auth.dependencies import (
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.notifications.center_service import NotificationCenterService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_center_service(
    session: SessionDependency,
) -> NotificationCenterService:
    return NotificationCenterService(session)


NotificationCenterServiceDependency = Annotated[
    NotificationCenterService,
    Depends(get_notification_center_service),
]


@router.get("", response_model=StudentNotificationPage)
async def list_notifications(
    service: NotificationCenterServiceDependency,
    context: AuthenticatedContextDependency,
    notification_status: Annotated[
        Literal["unread", "all"],
        Query(alias="status"),
    ] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> StudentNotificationPage:
    return await service.list(
        user_id=context.user.id,
        page=page,
        page_size=page_size,
        unread_only=notification_status == "unread",
    )


@router.post(
    "/{notification_id}/read",
    response_model=StudentNotificationResponse,
)
async def mark_notification_read(
    notification_id: UUID,
    service: NotificationCenterServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> StudentNotificationResponse:
    return await service.mark_read(notification_id, user_id=context.user.id)


@router.post("/read-all", response_model=NotificationReadAllResponse)
async def mark_all_notifications_read(
    payload: NotificationReadAllRequest,
    service: NotificationCenterServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> NotificationReadAllResponse:
    return await service.mark_all_read(
        user_id=context.user.id,
        before=payload.before,
        notification_type=payload.type,
    )
