"""Opt-in deadline-removal migration checks on a disposable PostgreSQL database."""

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ.get("ASSIGNMENT_DEADLINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="需要显式指定隔离作业迁移测试数据库")


def isolated_url() -> str:
    assert DATABASE_URL is not None
    url = make_url(DATABASE_URL)
    assert url.host == "127.0.0.1" and url.database == "pnx_test_assignment_deadline"
    return DATABASE_URL


def alembic(target: str, direction: str = "upgrade") -> None:
    url = make_url(isolated_url())
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_HOST": str(url.host),
        "DATABASE_PORT": str(url.port),
        "DATABASE_NAME": str(url.database),
        "DATABASE_USER": str(url.username),
        "DATABASE_PASSWORD": url.password or "unused",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", direction, *([] if direction == "check" else [target])],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_removal_reopens_only_automatic_closes_and_roundtrips() -> None:
    alembic("20260927_0028")
    now = datetime.now(UTC)
    old_deadline = now - timedelta(days=1)
    automatic, manual, overridden, archived = (uuid4() for _ in range(4))
    close_job, extension_job = uuid4(), uuid4()

    async def seed() -> None:
        engine = create_async_engine(isolated_url())
        try:
            async with engine.begin() as connection:
                for assignment_id, status in (
                    (automatic, "closed"),
                    (manual, "closed"),
                    (overridden, "closed"),
                    (archived, "archived"),
                ):
                    await connection.execute(
                        text("""
                        INSERT INTO assignments
                        (id, title, description_markdown, description_html,
                         submission_instructions, allowed_extensions, max_total_bytes,
                         publish_at, published_at, deadline, review_deadline,
                         status, closed_at, archived_at)
                        VALUES (:id, 'legacy', 'legacy', '<p>legacy</p>', 'submit',
                                ARRAY['pdf'], 1024, :publish_at, :publish_at,
                                :deadline, :deadline, :status, :deadline, :archived_at)
                    """),
                        {
                            "id": assignment_id,
                            "publish_at": now - timedelta(days=2),
                            "deadline": old_deadline,
                            "status": status,
                            "archived_at": now if status == "archived" else None,
                        },
                    )
                for assignment_id, action, at in (
                    (automatic, "assignment.close_automatic", now - timedelta(hours=2)),
                    (manual, "assignment.close", now - timedelta(hours=2)),
                    (overridden, "assignment.close_automatic", now - timedelta(hours=3)),
                    (overridden, "assignment.close", now - timedelta(hours=2)),
                    (archived, "assignment.close_automatic", now - timedelta(hours=2)),
                ):
                    await connection.execute(
                        text("""
                        INSERT INTO audit_logs
                        (id, action, target_type, target_id, request_id,
                         ip_prefix, result, change_summary, created_at)
                        VALUES (:id, :action, 'assignment', :target_id,
                                'seed', 'test', 'success', '{}'::jsonb, :created_at)
                    """),
                        {
                            "id": uuid4(),
                            "action": action,
                            "target_id": assignment_id,
                            "created_at": at,
                        },
                    )
                for job_id, job_type in (
                    (close_job, "close_assignment"),
                    (extension_job, "assignment_extension_email"),
                ):
                    await connection.execute(
                        text("""
                        INSERT INTO outbox_jobs
                        (id, job_type, event_key, payload, status, available_at, created_at)
                        VALUES (:id, :job_type, :event_key, '{}'::jsonb,
                                'pending', :now, :now)
                    """),
                        {"id": job_id, "job_type": job_type, "event_key": str(job_id), "now": now},
                    )
        finally:
            await engine.dispose()

    async def verify(upgraded: bool) -> None:
        engine = create_async_engine(isolated_url())
        try:
            async with engine.connect() as connection:
                for assignment_id, expected_status in (
                    (automatic, "published" if upgraded else "closed"),
                    (manual, "closed"),
                    (overridden, "closed"),
                    (archived, "archived"),
                ):
                    result = await connection.execute(
                        text("SELECT status, closed_at FROM assignments WHERE id=:id"),
                        {"id": assignment_id},
                    )
                    status, closed_at = result.one()
                    assert status == expected_status
                    assert (closed_at is None) == (upgraded and assignment_id == automatic)
                if upgraded:
                    for job_id in (close_job, extension_job):
                        status = await connection.scalar(
                            text("SELECT status FROM outbox_jobs WHERE id=:id"), {"id": job_id}
                        )
                        assert status == "dead"
        finally:
            await engine.dispose()

    asyncio.run(seed())
    alembic("20260927_0029")
    asyncio.run(verify(True))
    alembic("20260927_0028", "downgrade")
    asyncio.run(verify(False))
    alembic("20260927_0029")
    asyncio.run(verify(True))
    alembic("head", "check")
