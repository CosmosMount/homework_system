from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import DependencyUnavailableError
from app.health.domain import WorkerHeartbeatSnapshot
from app.health.service import HealthService


class FakeRepository:
    def __init__(self, heartbeat: WorkerHeartbeatSnapshot | None) -> None:
        self.heartbeat = heartbeat

    async def check_database(self) -> None:
        return None

    async def get_worker_heartbeat(self, worker_name: str) -> WorkerHeartbeatSnapshot | None:
        assert worker_name == "primary"
        return self.heartbeat


class UnreachableRepository(FakeRepository):
    async def check_database(self) -> None:
        raise OSError("database host is unreachable")

    async def get_worker_heartbeat(self, worker_name: str) -> WorkerHeartbeatSnapshot | None:
        raise OSError("database host is unreachable")


@pytest.mark.asyncio
async def test_database_socket_failure_is_reported_as_unavailable() -> None:
    service = HealthService(
        UnreachableRepository(None),
        worker_name="primary",
        worker_stale_after_seconds=300,
    )

    with pytest.raises(DependencyUnavailableError) as exc_info:
        await service.readiness()

    assert exc_info.value.details[0].field == "postgresql"
    assert exc_info.value.details[0].reason == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_worker_database_socket_failure_is_reported_as_unavailable() -> None:
    service = HealthService(
        UnreachableRepository(None),
        worker_name="primary",
        worker_stale_after_seconds=300,
    )

    with pytest.raises(DependencyUnavailableError) as exc_info:
        await service.worker_health()

    assert exc_info.value.details[0].field == "postgresql"
    assert exc_info.value.details[0].reason == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_recent_worker_heartbeat_is_healthy() -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    heartbeat = WorkerHeartbeatSnapshot(
        worker_name="primary",
        started_at=now - timedelta(hours=1),
        last_heartbeat_at=now - timedelta(seconds=10),
    )
    service = HealthService(
        FakeRepository(heartbeat),
        worker_name="primary",
        worker_stale_after_seconds=300,
        clock=lambda: now,
    )

    result = await service.worker_health()

    assert result.status == "healthy"
    assert result.age_seconds == 10


@pytest.mark.asyncio
async def test_stale_worker_heartbeat_is_unavailable() -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    heartbeat = WorkerHeartbeatSnapshot(
        worker_name="primary",
        started_at=now - timedelta(hours=1),
        last_heartbeat_at=now - timedelta(seconds=301),
    )
    service = HealthService(
        FakeRepository(heartbeat),
        worker_name="primary",
        worker_stale_after_seconds=300,
        clock=lambda: now,
    )

    with pytest.raises(DependencyUnavailableError) as exc_info:
        await service.worker_health()

    assert exc_info.value.details[0].reason == "STALE_HEARTBEAT"
