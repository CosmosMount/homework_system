"""Run only against a disposable PostgreSQL database, never the deployed database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.users.models import User
from app.users.repository import UserRepository


@pytest.mark.asyncio
async def test_erasure_releases_email_and_preserves_shared_immutable_version() -> None:
    url = os.environ.get("ACCOUNT_ERASURE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires a disposable PostgreSQL database at migration head")
    assert "pnx_erasure_test" in url, "refusing to use a non-isolated database"
    engine = create_async_engine(url)
    target_id, survivor_id, assignment_id = uuid4(), uuid4(), uuid4()
    own_submission_id, shared_submission_id = uuid4(), uuid4()
    own_version_id, shared_version_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection) as session:
                    for user_id, local_part in (
                        (target_id, "erased-regression"),
                        (survivor_id, "survivor-regression"),
                    ):
                        await session.execute(
                            text("""
                                INSERT INTO users
                                (id, email, email_normalized, student_number, full_name,
                                 password_hash, role, status, email_verified_at,
                                 password_changed_at, created_at, updated_at, revision)
                                VALUES (:id, :email, :email, :student_number, 'Test User',
                                        'test-hash', 'student', 'active', :now, :now, :now, :now, 1)
                            """),
                            {
                                "id": user_id,
                                "email": f"{local_part}@connect.hkust-gz.edu.cn",
                                "student_number": local_part,
                                "now": now,
                            },
                        )
                    await session.execute(
                        text("""
                            INSERT INTO assignments
                            (id, title, description_markdown, description_html,
                             submission_instructions, allowed_extensions, max_total_bytes,
                             publish_at, deadline, review_deadline,
                             created_at, updated_at, revision)
                            VALUES (:id, 'Test', 'Test', 'Test', 'Test', ARRAY['pdf'],
                                    100, :now, :deadline, :deadline, :now, :now, 1)
                        """),
                        {"id": assignment_id, "now": now, "deadline": now + timedelta(days=1)},
                    )
                    for submission_id, owner_id, version_id in (
                        (own_submission_id, target_id, own_version_id),
                        (shared_submission_id, survivor_id, shared_version_id),
                    ):
                        await session.execute(
                            text("""
                                INSERT INTO submissions
                                (id, assignment_id, owner_user_id, created_at, updated_at)
                                VALUES (:id, :assignment_id, :owner_id, :now, :now)
                            """),
                            {
                                "id": submission_id,
                                "assignment_id": assignment_id,
                                "owner_id": owner_id,
                                "now": now,
                            },
                        )
                        await session.execute(
                            text("""
                                INSERT INTO submission_versions
                                (id, submission_id, version_number, submitted_by,
                                 text_markdown, total_file_bytes, idempotency_key, submitted_at)
                                VALUES (:id, :submission_id, 1, :submitted_by,
                                        'Test', 0, :idempotency_key, :now)
                            """),
                            {
                                "id": version_id,
                                "submission_id": submission_id,
                                "submitted_by": target_id,
                                "idempotency_key": str(version_id),
                                "now": now,
                            },
                        )

                    # Ordinary mutations still fail, including FK-shaped updates
                    # attempted without an erasure context.
                    with pytest.raises(DBAPIError):
                        async with session.begin_nested():
                            await session.execute(
                                text(
                                    "UPDATE submission_versions "
                                    "SET submitted_by = NULL WHERE id = :id"
                                ),
                                {"id": shared_version_id},
                            )

                    user = await session.scalar(select(User).where(User.id == target_id))
                    assert user is not None
                    repository = UserRepository(session)
                    preparation = await repository.prepare_account_erasure(user, now=now)
                    await session.execute(text("SET LOCAL pnx.account_erasure = 'on'"))
                    await session.execute(
                        text("SELECT set_config('pnx.account_erasure_user_id', :id, true)"),
                        {"id": str(target_id)},
                    )
                    with pytest.raises(DBAPIError):
                        async with session.begin_nested():
                            await session.execute(
                                text(
                                    "UPDATE submission_versions SET text_markdown = 'changed' "
                                    "WHERE id = :id"
                                ),
                                {"id": shared_version_id},
                            )
                    await repository.erase_account(user, preparation)
                    assert (
                        await session.scalar(
                            text("SELECT count(*) FROM users WHERE id = :id"), {"id": target_id}
                        )
                        == 0
                    )
                    assert (
                        await session.scalar(
                            text("SELECT count(*) FROM submission_versions WHERE id = :id"),
                            {"id": own_version_id},
                        )
                        == 0
                    )
                    assert (
                        await session.scalar(
                            text("SELECT submitted_by FROM submission_versions WHERE id = :id"),
                            {"id": shared_version_id},
                        )
                        is None
                    )
                    await session.execute(
                        text("""
                            INSERT INTO users
                            (id, email, email_normalized, student_number, full_name,
                             password_hash, role, status, password_changed_at,
                             created_at, updated_at, revision)
                            VALUES (:id, :email, :email, :student_number, 'New User',
                                    'test-hash', 'student', 'pending_email', :now, :now, :now, 1)
                        """),
                        {
                            "id": uuid4(),
                            "email": "erased-regression@connect.hkust-gz.edu.cn",
                            "student_number": "erased-regression",
                            "now": now,
                        },
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
