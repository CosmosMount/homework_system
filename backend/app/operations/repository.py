from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.announcements.models import AnnouncementFile
from app.notifications.models import OutboxJob
from app.operations.domain import DatabaseOperationsMetrics
from app.submissions.models import VersionFile
from app.uploads.models import StoredFile, UploadSession

_ACTIVE_OUTBOX_STATUSES = ("pending", "retry", "processing")
_OUTBOX_STATUSES = (*_ACTIVE_OUTBOX_STATUSES, "dead")
_FAILED_UPLOAD_STATUSES = ("rejected", "aborted", "expired")


class OperationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_metrics(
        self,
        *,
        now: datetime,
        orphan_cleanup_before: datetime,
    ) -> DatabaseOperationsMetrics:
        outbox_counts = {
            status: await self._count_outbox(OutboxJob.status == status)
            for status in _OUTBOX_STATUSES
        }
        upload_file_counts = {
            status: await self._count_stored_files(StoredFile.status == status)
            for status in _FAILED_UPLOAD_STATUSES
        }
        oldest_active_outbox_at = await self._session.scalar(
            select(func.min(OutboxJob.created_at)).where(
                OutboxJob.status.in_(_ACTIVE_OUTBOX_STATUSES)
            )
        )
        stale_upload_sessions = await self._count_upload_sessions(
            UploadSession.status.in_(("initialized", "uploading")),
            UploadSession.expires_at <= now,
        )
        bound_to_announcement = exists().where(AnnouncementFile.file_id == StoredFile.id)
        bound_to_version = exists().where(VersionFile.file_id == StoredFile.id)
        orphan_conditions = (
            StoredFile.status == "available",
            StoredFile.deleted_at.is_(None),
            ~bound_to_announcement,
            ~bound_to_version,
        )
        orphaned_available_files = await self._count_stored_files(*orphan_conditions)
        cleanup_due_available_files = await self._count_stored_files(
            *orphan_conditions,
            StoredFile.available_at <= orphan_cleanup_before,
        )
        return DatabaseOperationsMetrics(
            outbox_counts=outbox_counts,
            oldest_active_outbox_at=oldest_active_outbox_at,
            upload_file_counts=upload_file_counts,
            stale_upload_sessions=stale_upload_sessions,
            orphaned_available_files=orphaned_available_files,
            cleanup_due_available_files=cleanup_due_available_files,
        )

    async def _count_outbox(self, *conditions: ColumnElement[bool]) -> int:
        value = await self._session.scalar(
            select(func.count()).select_from(OutboxJob).where(*conditions)
        )
        return int(value or 0)

    async def _count_stored_files(self, *conditions: ColumnElement[bool]) -> int:
        value = await self._session.scalar(
            select(func.count()).select_from(StoredFile).where(*conditions)
        )
        return int(value or 0)

    async def _count_upload_sessions(self, *conditions: ColumnElement[bool]) -> int:
        value = await self._session.scalar(
            select(func.count()).select_from(UploadSession).where(*conditions)
        )
        return int(value or 0)
