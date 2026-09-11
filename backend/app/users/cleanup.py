import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.users.repository import UserRepository
from app.users.service import ACCOUNT_AUTO_DELETION_THRESHOLD, UserAdministrationService

logger = logging.getLogger(__name__)
ACCOUNT_CLEANUP_BATCH_SIZE = 100
ACCOUNT_CLEANUP_INTERVAL = timedelta(hours=1)


class InactiveAccountCleanupProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._next_run_at: datetime | None = None
        self._after_id: UUID | None = None

    async def run_once(self) -> int:
        now = self._clock()
        if self._next_run_at is not None and now < self._next_run_at:
            return 0
        async with self._factory() as session:
            user_ids = await UserRepository(session).list_inactive_account_ids(
                before=now - ACCOUNT_AUTO_DELETION_THRESHOLD,
                after_id=self._after_id,
                limit=ACCOUNT_CLEANUP_BATCH_SIZE,
            )
        deleted = 0
        for user_id in user_ids:
            try:
                async with self._factory() as session:
                    service = UserAdministrationService(session, self._settings, clock=self._clock)
                    deleted += int(await service.delete_inactive_account(user_id))
            except SQLAlchemyError:
                logger.warning(
                    "inactive_account_cleanup_failed",
                    extra={"event": "inactive_account_cleanup_failed", "service": "worker"},
                )
            self._after_id = user_id
        if len(user_ids) < ACCOUNT_CLEANUP_BATCH_SIZE:
            self._after_id = None
            self._next_run_at = self._clock() + ACCOUNT_CLEANUP_INTERVAL
        return deleted
