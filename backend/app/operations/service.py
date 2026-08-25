from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.operations.domain import DatabaseOperationsMetrics


class OperationsRepositoryProtocol(Protocol):
    async def read_metrics(
        self,
        *,
        now: datetime,
        orphan_cleanup_before: datetime,
    ) -> DatabaseOperationsMetrics: ...


class OperationsSnapshotService:
    def __init__(
        self,
        repository: OperationsRepositoryProtocol,
        *,
        orphan_cleanup_delay_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._orphan_cleanup_delay_seconds = orphan_cleanup_delay_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    async def snapshot(self) -> dict[str, object]:
        now = self._clock()
        metrics = await self._repository.read_metrics(
            now=now,
            orphan_cleanup_before=now - timedelta(seconds=self._orphan_cleanup_delay_seconds),
        )
        oldest_age = None
        if metrics.oldest_active_outbox_at is not None:
            oldest_age = round(
                max(0.0, (now - metrics.oldest_active_outbox_at).total_seconds()),
                3,
            )
        active_total = sum(
            metrics.outbox_counts.get(status, 0) for status in ("pending", "retry", "processing")
        )
        return {
            "status": "ok",
            "generated_at": now.isoformat(),
            "outbox": {
                "pending": metrics.outbox_counts.get("pending", 0),
                "retry": metrics.outbox_counts.get("retry", 0),
                "processing": metrics.outbox_counts.get("processing", 0),
                "active_total": active_total,
                "oldest_active_age_seconds": oldest_age,
                "dead": metrics.outbox_counts.get("dead", 0),
            },
            "uploads": {
                "rejected": metrics.upload_file_counts.get("rejected", 0),
                "aborted": metrics.upload_file_counts.get("aborted", 0),
                "expired": metrics.upload_file_counts.get("expired", 0),
                "stale_sessions": metrics.stale_upload_sessions,
                "orphaned_available": metrics.orphaned_available_files,
                "cleanup_due_available": metrics.cleanup_due_available_files,
            },
        }
