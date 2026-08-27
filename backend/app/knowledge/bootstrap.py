import argparse
import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.session import engine, session_factory
from app.knowledge.feishu_client import KnowledgeSyncError
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeSynchronizer

logger = logging.getLogger(__name__)


class _Synchronizer(Protocol):
    async def synchronize(self, run_id: UUID) -> None: ...


async def bootstrap_active_run(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    synchronizer: _Synchronizer | None = None,
) -> int:
    async with factory() as session:
        run = await KnowledgeRepository(session).active_run()
    if run is None:
        logger.error(
            "knowledge_bootstrap_no_active_run",
            extra={"event": "knowledge_bootstrap_no_active_run"},
        )
        return 2

    resolved_synchronizer = synchronizer or KnowledgeSynchronizer(factory, settings)
    logger.info(
        "knowledge_bootstrap_started",
        extra={"event": "knowledge_bootstrap_started", "stage": "initializing"},
    )
    try:
        await resolved_synchronizer.synchronize(run.id)
    except KnowledgeSyncError as exc:
        logger.error(
            "knowledge_bootstrap_failed",
            extra={
                "event": "knowledge_bootstrap_failed",
                "error_code": exc.code,
            },
        )
        return 1
    logger.info(
        "knowledge_bootstrap_succeeded",
        extra={"event": "knowledge_bootstrap_succeeded", "stage": "completed"},
    )
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="以前台方式接管唯一进行中的飞书知识库同步。")
    return parser.parse_args(argv)


async def _run_cli() -> int:
    try:
        return await bootstrap_active_run(
            session_factory,
            get_settings(),
        )
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    _parse_args(argv)
    configure_logging(get_settings().log_level)
    return asyncio.run(_run_cli())


if __name__ == "__main__":
    raise SystemExit(main())
