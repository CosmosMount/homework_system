import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from test_user_administration import build_delete_service, make_account

from app.core.config import Settings
from app.users.cleanup import InactiveAccountCleanupProcessor
from app.users.repository import AccountErasurePreparation, AccountObjectCleanup, UserRepository

NOW = datetime(2026, 9, 10, 8, tzinfo=UTC)


@pytest.mark.parametrize("status", ["active", "pending_email", "disabled"])
@pytest.mark.parametrize("role", ["student", "admin"])
@pytest.mark.parametrize("age,deleted", [(14, False), (15, False), (16, True)])
async def test_auto_deletion_boundary_and_account_states(status, role, age, deleted):
    target = make_account(
        now=NOW, status=status, role=role, last_active_at=NOW - timedelta(days=age)
    )
    service, auth, users, session, audit, _ = build_delete_service(now=NOW, target=target)
    auth.lock_sessions_for_user.return_value = None
    assert await service.delete_inactive_account(target.id) is deleted
    auth.acquire_admin_lifecycle_lock.assert_awaited_once()
    auth.lock_one_time_tokens_for_user.assert_awaited_once_with(target.id)
    auth.lock_sessions_for_user.assert_awaited_once_with(target.id)
    users.get_by_id.assert_awaited_once_with(target.id, for_update=True)
    auth.verify_current_password.assert_not_called()
    assert session.commit.await_count == int(deleted)
    assert users.erase_account.await_count == int(deleted)
    assert audit.call_count == int(deleted)
    assert session.rollback.await_count == int(not deleted)


@pytest.mark.parametrize("reference", ["last_active_at", "email_verified_at", "created_at"])
@pytest.mark.parametrize("over_boundary", [False, True])
async def test_never_logged_in_fallback_and_strict_microsecond_boundary(reference, over_boundary):
    target = make_account(now=NOW)
    target.last_active_at = None
    target.email_verified_at = None
    target.created_at = NOW - timedelta(days=30)
    setattr(target, reference, NOW - timedelta(days=15, microseconds=int(over_boundary)))
    service, auth, _, _, _, _ = build_delete_service(now=NOW, target=target)
    auth.lock_sessions_for_user.return_value = None
    assert await service.delete_inactive_account(target.id) is over_boundary


async def test_last_active_admin_is_preserved():
    target = make_account(now=NOW, role="admin")
    service, auth, users, session, _, _ = build_delete_service(
        now=NOW, target=target, active_admin_count=1
    )
    auth.lock_sessions_for_user.return_value = None
    assert await service.delete_inactive_account(target.id) is False
    users.erase_account.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.parametrize("changed", ["user", "session", "deleted"])
async def test_locked_state_rechecked_after_candidate_selection(changed):
    target = make_account(now=NOW)
    service, auth, users, _, _, _ = build_delete_service(now=NOW, target=target)
    auth.lock_sessions_for_user.return_value = NOW if changed == "session" else None
    if changed == "user":
        target.last_active_at = NOW
    if changed == "deleted":
        users.get_by_id.side_effect = None
        users.get_by_id.return_value = None
    assert await service.delete_inactive_account(target.id) is False
    users.erase_account.assert_not_awaited()


async def test_automatic_erasure_reuses_object_cleanup_and_anonymous_audit():
    target = make_account(now=NOW)
    cleanup = AccountObjectCleanup(uuid4(), "private-object", "private-upload")
    preparation = AccountErasurePreparation(
        object_cleanups=(cleanup,),
        deletion_counts={"submissions": 2},
        teams_transferred=1,
        teams_dissolved=0,
        teams_invalidated=0,
    )
    service, auth, users, session, audit, outbox = build_delete_service(
        now=NOW, target=target, preparation=preparation
    )
    auth.lock_sessions_for_user.return_value = None
    assert await service.delete_inactive_account(target.id) is True
    users.erase_account.assert_awaited_once_with(target, preparation)
    session.commit.assert_awaited_once()
    event = audit.call_args.args[0]
    assert event.actor_user_id is None
    assert event.action == "user.auto_delete"
    assert event.change_summary["mode"] == "automatic"
    assert event.change_summary["deletion_counts"] == {"submissions": 2}
    assert event.change_summary["teams_transferred"] == 1
    for secret in (target.email, "private-object", "private-upload"):
        assert secret not in json.dumps(event.change_summary)
    job = outbox.call_args.args[0]
    assert job.job_type == "delete_account_object"
    assert service._outbox_cipher.decrypt(job.secret_payload_ciphertext) == {
        "minio_upload_id": "private-upload"
    }


async def test_candidate_query_uses_strict_cutoff_and_keyset_without_status_exclusion():
    session = SimpleNamespace(scalars=AsyncMock(return_value=Mock(all=Mock(return_value=[]))))
    after_id = uuid4()
    await UserRepository(session).list_inactive_account_ids(
        before=NOW, after_id=after_id, limit=100
    )
    statement = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "coalesce(users.last_active_at, users.email_verified_at, users.created_at) <" in sql
    assert "users.id >" in sql
    assert "ORDER BY users.id" in sql
    assert "LIMIT" in sql
    assert "status" not in sql
    assert after_id in statement.params.values()


async def test_processor_batches_skips_failures_and_retries_next_hour(caplog):
    current = NOW
    factory = Mock(return_value=AsyncMock())
    processor = InactiveAccountCleanupProcessor(
        factory, Settings(app_env="test"), clock=lambda: current
    )
    candidate_ids = [UUID(int=index + 1) for index in range(100)]
    select_ids = AsyncMock(side_effect=[candidate_ids, [], [candidate_ids[0]]])
    erase = AsyncMock(side_effect=[SQLAlchemyError("private SQL"), *([True] * 99), True])
    with (
        patch.object(UserRepository, "list_inactive_account_ids", select_ids),
        patch("app.users.cleanup.UserAdministrationService") as service,
    ):
        service.return_value.delete_inactive_account = erase
        assert await processor.run_once() == 99
        assert await processor.run_once() == 0
        assert select_ids.call_args.kwargs["after_id"] == candidate_ids[-1]
        assert await processor.run_once() == 0
        assert select_ids.await_count == 2
        current += timedelta(hours=1)
        assert await processor.run_once() == 1
        assert select_ids.call_args.kwargs["after_id"] is None
    assert "inactive_account_cleanup_failed" in caplog.text
    assert "private SQL" not in caplog.text


async def test_failed_erasure_never_commits_or_calls_object_store():
    target = make_account(now=NOW)
    service, auth, users, session, _, _ = build_delete_service(now=NOW, target=target)
    auth.lock_sessions_for_user.return_value = None
    users.erase_account.side_effect = SQLAlchemyError("failed")
    with pytest.raises(SQLAlchemyError):
        await service.delete_inactive_account(target.id)
    session.commit.assert_not_awaited()


async def test_worker_invokes_account_cleanup_without_manual_trigger():
    from app import worker

    with (
        patch.object(worker, "configure_logging"),
        patch.object(worker, "record_heartbeat", new_callable=AsyncMock),
        patch.object(worker, "OutboxProcessor") as outbox,
        patch.object(worker, "UploadCleanupProcessor") as uploads,
        patch.object(worker, "InactiveAccountCleanupProcessor") as accounts,
        patch.object(worker, "engine", SimpleNamespace(dispose=AsyncMock())),
        patch.object(worker.asyncio, "sleep", side_effect=asyncio.CancelledError),
    ):
        outbox.return_value.run_once = AsyncMock()
        uploads.return_value.run_once = AsyncMock()
        accounts.return_value.run_once = AsyncMock()
        with pytest.raises(asyncio.CancelledError):
            await worker.run_worker(Settings(app_env="test"))
        accounts.return_value.run_once.assert_awaited_once()
