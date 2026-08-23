from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import DependencyUnavailableError
from app.health.domain import WorkerHeartbeatSnapshot
from app.health.schemas import ReadyHealthResponse, WorkerHealthResponse


class HealthRepositoryProtocol(Protocol):
    async def check_database(self) -> None: ...

    async def get_worker_heartbeat(self, worker_name: str) -> WorkerHeartbeatSnapshot | None: ...


class HealthService:
    def __init__(
        self,
        repository: HealthRepositoryProtocol,
        *,
        worker_name: str,
        worker_stale_after_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._worker_name = worker_name
        self._worker_stale_after_seconds = worker_stale_after_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    async def readiness(self) -> ReadyHealthResponse:
        try:
            await self._repository.check_database()
        except (OSError, SQLAlchemyError) as exc:
            raise DependencyUnavailableError(field="postgresql", reason="UNAVAILABLE") from exc
        return ReadyHealthResponse()

    async def worker_health(self) -> WorkerHealthResponse:
        try:
            heartbeat = await self._repository.get_worker_heartbeat(self._worker_name)
        except (OSError, SQLAlchemyError) as exc:
            raise DependencyUnavailableError(field="postgresql", reason="UNAVAILABLE") from exc
        if heartbeat is None:
            raise DependencyUnavailableError(field="worker", reason="NO_HEARTBEAT")

        age_seconds = max(
            0.0,
            (self._clock() - heartbeat.last_heartbeat_at).total_seconds(),
        )
        if age_seconds > self._worker_stale_after_seconds:
            raise DependencyUnavailableError(field="worker", reason="STALE_HEARTBEAT")

        return WorkerHealthResponse(
            worker_name=heartbeat.worker_name,
            started_at=heartbeat.started_at,
            last_heartbeat_at=heartbeat.last_heartbeat_at,
            age_seconds=round(age_seconds, 3),
        )
