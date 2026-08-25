from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.schemas import (
    NotificationReadAllResponse,
    StudentNotificationPage,
    StudentNotificationResponse,
)
from app.core.errors import ApplicationError
from app.notifications.models import StudentNotification
from app.notifications.repository import StudentNotificationRepository


class NotificationCenterService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._notifications = StudentNotificationRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _response(notification: StudentNotification) -> StudentNotificationResponse:
        return StudentNotificationResponse(
            id=notification.id,
            type=notification.notification_type,
            title=notification.title,
            target_url=notification.target_url,
            created_at=notification.created_at,
            read_at=notification.read_at,
        )

    async def list(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        unread_only: bool,
    ) -> StudentNotificationPage:
        items, total = await self._notifications.list_for_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
            unread_only=unread_only,
        )
        return StudentNotificationPage(
            items=[self._response(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def mark_read(
        self,
        notification_id: UUID,
        *,
        user_id: UUID,
    ) -> StudentNotificationResponse:
        notification = await self._notifications.get_for_user(
            notification_id,
            user_id,
            for_update=True,
        )
        if notification is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=404,
                code="RESOURCE_NOT_FOUND",
                message="站内通知不存在。",
            )
        if notification.read_at is None:
            notification.read_at = self._clock()
            await self._session.commit()
        else:
            await self._session.rollback()
        return self._response(notification)

    async def mark_all_read(
        self,
        *,
        user_id: UUID,
        before: datetime,
        notification_type: str | None,
    ) -> NotificationReadAllResponse:
        if before.tzinfo is None:
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="before 必须包含时区。",
            )
        notifications = await self._notifications.unread_before(
            user_id=user_id,
            before=before,
            notification_type=notification_type,
        )
        now = self._clock()
        for notification in notifications:
            notification.read_at = now
        await self._session.commit()
        return NotificationReadAllResponse(updated_count=len(notifications))
