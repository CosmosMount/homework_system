from datetime import UTC, datetime, timedelta

import pytest

from app.operations.domain import DatabaseOperationsMetrics
from app.operations.service import OperationsSnapshotService


class FakeOperationsRepository:
    def __init__(self, metrics: DatabaseOperationsMetrics) -> None:
        self.metrics = metrics
        self.now: datetime | None = None
        self.orphan_cleanup_before: datetime | None = None

    async def read_metrics(
        self,
        *,
        now: datetime,
        orphan_cleanup_before: datetime,
    ) -> DatabaseOperationsMetrics:
        self.now = now
        self.orphan_cleanup_before = orphan_cleanup_before
        return self.metrics


@pytest.mark.asyncio
async def test_operations_snapshot_only_returns_safe_counts_and_ages() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    repository = FakeOperationsRepository(
        DatabaseOperationsMetrics(
            outbox_counts={
                "pending": 2,
                "retry": 3,
                "processing": 1,
                "dead": 4,
            },
            oldest_active_outbox_at=now - timedelta(seconds=75.25),
            upload_file_counts={"rejected": 5, "aborted": 6, "expired": 7},
            stale_upload_sessions=8,
            orphaned_available_files=9,
            cleanup_due_available_files=10,
        )
    )
    service = OperationsSnapshotService(
        repository,
        orphan_cleanup_delay_seconds=86400,
        clock=lambda: now,
    )

    snapshot = await service.snapshot()

    assert snapshot == {
        "status": "ok",
        "generated_at": "2026-08-25T08:00:00+00:00",
        "outbox": {
            "pending": 2,
            "retry": 3,
            "processing": 1,
            "active_total": 6,
            "oldest_active_age_seconds": 75.25,
            "dead": 4,
        },
        "uploads": {
            "rejected": 5,
            "aborted": 6,
            "expired": 7,
            "stale_sessions": 8,
            "orphaned_available": 9,
            "cleanup_due_available": 10,
        },
    }
    assert repository.now == now
    assert repository.orphan_cleanup_before == now - timedelta(days=1)


@pytest.mark.asyncio
async def test_operations_snapshot_has_null_oldest_age_when_queue_is_empty() -> None:
    now = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
    repository = FakeOperationsRepository(
        DatabaseOperationsMetrics(
            outbox_counts={},
            oldest_active_outbox_at=None,
            upload_file_counts={},
            stale_upload_sessions=0,
            orphaned_available_files=0,
            cleanup_due_available_files=0,
        )
    )

    snapshot = await OperationsSnapshotService(
        repository,
        orphan_cleanup_delay_seconds=86400,
        clock=lambda: now,
    ).snapshot()

    assert snapshot["outbox"] == {
        "pending": 0,
        "retry": 0,
        "processing": 0,
        "active_total": 0,
        "oldest_active_age_seconds": None,
        "dead": 0,
    }
