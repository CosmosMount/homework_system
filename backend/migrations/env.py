from asyncio import run
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.announcements.models  # noqa: F401
import app.assignments.models  # noqa: F401
import app.competitions.models  # noqa: F401
import app.intentions.models  # noqa: F401
import app.submissions.models  # noqa: F401
from app.audit.models import AuditLog  # noqa: F401
from app.auth.models import AuthSecurityEvent, OneTimeToken, Session  # noqa: F401
from app.core.config import get_settings
from app.database.base import Base
from app.health.models import WorkerHeartbeat  # noqa: F401
from app.notifications.models import OutboxJob, StudentNotification  # noqa: F401
from app.uploads.models import StoredFile, UploadPart, UploadSession  # noqa: F401
from app.users.models import Cohort, Direction, User  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Any) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        pool_pre_ping=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run(run_migrations_online())
