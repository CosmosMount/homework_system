import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.competitions.service import CompetitionLifecycleProcessor
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.session import engine, session_factory
from app.health.repository import HealthRepository
from app.notifications.service import OutboxProcessor
from app.uploads.object_store import ObjectStoreError
from app.uploads.service import UploadCleanupProcessor

logger = logging.getLogger(__name__)


async def record_heartbeat(
    factory: async_sessionmaker[AsyncSession],
    *,
    worker_name: str,
    started_at: datetime,
    clock: Callable[[], datetime] | None = None,
) -> None:
    now = (clock or (lambda: datetime.now(UTC)))()
    async with factory() as session, session.begin():
        await HealthRepository(session).record_worker_heartbeat(
            worker_name=worker_name,
            started_at=started_at,
            heartbeat_at=now,
        )


async def run_worker(settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    started_at = datetime.now(UTC)
    next_heartbeat_at = started_at
    outbox = OutboxProcessor(session_factory, resolved_settings)
    upload_cleanup = UploadCleanupProcessor(session_factory, resolved_settings)
    competition_lifecycle = CompetitionLifecycleProcessor(session_factory, resolved_settings)
    logger.info(
        "worker_started",
        extra={
            "event": "worker_started",
            "service": "worker",
            "worker_name": resolved_settings.worker_name,
        },
    )
    try:
        while True:
            try:
                now = datetime.now(UTC)
                if now >= next_heartbeat_at:
                    await record_heartbeat(
                        session_factory,
                        worker_name=resolved_settings.worker_name,
                        started_at=started_at,
                    )
                    next_heartbeat_at = now + timedelta(
                        seconds=resolved_settings.worker_heartbeat_interval_seconds
                    )
                await outbox.run_once()
                await upload_cleanup.run_once()
                await competition_lifecycle.run_once()
            except (SQLAlchemyError, ObjectStoreError, OSError):
                logger.warning(
                    "worker_iteration_failed",
                    exc_info=True,
                    extra={
                        "event": "worker_iteration_failed",
                        "service": "worker",
                        "worker_name": resolved_settings.worker_name,
                    },
                )
            await asyncio.sleep(resolved_settings.worker_poll_interval_seconds)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_worker())
