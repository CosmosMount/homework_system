from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.domain import WorkerHeartbeatSnapshot
from app.health.models import WorkerHeartbeat


class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_database(self) -> None:
        await self._session.execute(text("SELECT 1"))

    async def get_worker_heartbeat(self, worker_name: str) -> WorkerHeartbeatSnapshot | None:
        row = await self._session.scalar(
            select(WorkerHeartbeat).where(WorkerHeartbeat.worker_name == worker_name)
        )
        if row is None:
            return None
        return WorkerHeartbeatSnapshot(
            worker_name=row.worker_name,
            started_at=row.started_at,
            last_heartbeat_at=row.last_heartbeat_at,
        )

    async def record_worker_heartbeat(
        self,
        *,
        worker_name: str,
        started_at: datetime,
        heartbeat_at: datetime,
    ) -> None:
        statement = insert(WorkerHeartbeat).values(
            worker_name=worker_name,
            started_at=started_at,
            last_heartbeat_at=heartbeat_at,
            updated_at=heartbeat_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_name],
            set_={
                "last_heartbeat_at": heartbeat_at,
                "updated_at": heartbeat_at,
            },
        )
        await self._session.execute(statement)
