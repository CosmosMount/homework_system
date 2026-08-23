import asyncio
import logging

from app.core.config import get_settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import configure_logging
from app.database.session import engine, session_factory
from app.health.repository import HealthRepository
from app.health.service import HealthService

logger = logging.getLogger(__name__)


async def worker_is_healthy() -> bool:
    settings = get_settings()
    try:
        async with session_factory() as session:
            service = HealthService(
                HealthRepository(session),
                worker_name=settings.worker_name,
                worker_stale_after_seconds=settings.worker_stale_after_seconds,
            )
            await service.worker_health()
    except (DependencyUnavailableError, OSError):
        return False
    finally:
        await engine.dispose()
    return True


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    healthy = asyncio.run(worker_is_healthy())
    if not healthy:
        logger.warning(
            "worker_healthcheck_failed",
            extra={"event": "worker_healthcheck_failed", "service": "worker"},
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
