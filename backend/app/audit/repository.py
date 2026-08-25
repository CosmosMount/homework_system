from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: AuditLog) -> None:
        self._session.add(entry)

    async def list_entries(
        self,
        *,
        page: int,
        page_size: int,
        actor_user_id: UUID | None,
        action: str | None,
        target_type: str | None,
        target_id: UUID | None,
        request_id: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if actor_user_id is not None:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if action is not None:
            filters.append(AuditLog.action == action)
        if target_type is not None:
            filters.append(AuditLog.target_type == target_type)
        if target_id is not None:
            filters.append(AuditLog.target_id == target_id)
        if request_id is not None:
            filters.append(AuditLog.request_id == request_id)
        if created_from is not None:
            filters.append(AuditLog.created_at >= created_from)
        if created_to is not None:
            filters.append(AuditLog.created_at <= created_to)
        count: int | None = await self._session.scalar(
            select(func.count()).select_from(AuditLog).where(*filters)
        )
        entries = list(
            (
                await self._session.scalars(
                    select(AuditLog)
                    .where(*filters)
                    .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return entries, int(count or 0)
