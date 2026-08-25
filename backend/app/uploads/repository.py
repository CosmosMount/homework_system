from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import AnnouncementFile
from app.submissions.models import VersionFile
from app.uploads.models import StoredFile, UploadPart, UploadSession


class UploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_file(self, stored_file: StoredFile) -> None:
        self._session.add(stored_file)

    def add_session(self, upload_session: UploadSession) -> None:
        self._session.add(upload_session)

    async def get_file(
        self,
        file_id: UUID,
        *,
        for_update: bool = False,
    ) -> StoredFile | None:
        statement = select(StoredFile).where(StoredFile.id == file_id)
        if for_update:
            statement = statement.with_for_update()
        result: StoredFile | None = await self._session.scalar(statement)
        return result

    async def get_files(
        self,
        file_ids: Sequence[UUID],
        *,
        for_update: bool = False,
    ) -> list[StoredFile]:
        if not file_ids:
            return []
        statement = select(StoredFile).where(StoredFile.id.in_(file_ids))
        if for_update:
            statement = statement.with_for_update()
        return list((await self._session.scalars(statement)).all())

    async def files_for_reconciliation(self) -> list[StoredFile]:
        return list(
            (await self._session.scalars(select(StoredFile).order_by(StoredFile.object_key))).all()
        )

    async def get_session(
        self,
        upload_id: UUID,
        *,
        user_id: UUID | None = None,
        for_update: bool = False,
    ) -> UploadSession | None:
        statement = select(UploadSession).where(UploadSession.id == upload_id)
        if user_id is not None:
            statement = statement.where(UploadSession.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result: UploadSession | None = await self._session.scalar(statement)
        return result

    async def get_session_by_file(self, file_id: UUID) -> UploadSession | None:
        result: UploadSession | None = await self._session.scalar(
            select(UploadSession).where(UploadSession.file_id == file_id)
        )
        return result

    async def bound_announcement_id(self, file_id: UUID) -> UUID | None:
        result: UUID | None = await self._session.scalar(
            select(AnnouncementFile.announcement_id).where(AnnouncementFile.file_id == file_id)
        )
        return result

    async def bound_version_id(self, file_id: UUID) -> UUID | None:
        result: UUID | None = await self._session.scalar(
            select(VersionFile.version_id).where(VersionFile.file_id == file_id)
        )
        return result

    async def get_by_idempotency(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> UploadSession | None:
        result: UploadSession | None = await self._session.scalar(
            select(UploadSession).where(
                UploadSession.user_id == user_id,
                UploadSession.idempotency_key == idempotency_key,
            )
        )
        return result

    async def parts(self, upload_id: UUID) -> list[UploadPart]:
        return list(
            (
                await self._session.scalars(
                    select(UploadPart)
                    .where(UploadPart.upload_session_id == upload_id)
                    .order_by(UploadPart.part_number)
                )
            ).all()
        )

    async def replace_parts(
        self,
        upload_id: UUID,
        parts: Sequence[UploadPart],
    ) -> None:
        await self._session.execute(
            delete(UploadPart).where(UploadPart.upload_session_id == upload_id)
        )
        self._session.add_all(list(parts))

    async def file_is_bound(self, file_id: UUID) -> bool:
        return (
            await self.bound_announcement_id(file_id) is not None
            or await self.bound_version_id(file_id) is not None
        )

    async def orphaned_available_files(
        self,
        *,
        created_before: datetime,
        limit: int,
    ) -> list[StoredFile]:
        bound_announcement = exists().where(AnnouncementFile.file_id == StoredFile.id)
        bound_version = exists().where(VersionFile.file_id == StoredFile.id)
        return list(
            (
                await self._session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.status == "available",
                        StoredFile.available_at <= created_before,
                        ~bound_announcement,
                        ~bound_version,
                    )
                    .order_by(StoredFile.available_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def terminal_files_for_cleanup(
        self,
        *,
        limit: int,
    ) -> list[StoredFile]:
        return list(
            (
                await self._session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.status.in_(("rejected", "aborted", "expired")),
                        StoredFile.deleted_at.is_(None),
                    )
                    .order_by(StoredFile.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def stale_sessions(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[UploadSession]:
        return list(
            (
                await self._session.scalars(
                    select(UploadSession)
                    .where(
                        UploadSession.status.in_(("initialized", "uploading")),
                        UploadSession.expires_at <= now,
                    )
                    .order_by(UploadSession.expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
