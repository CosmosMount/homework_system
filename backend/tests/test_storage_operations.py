import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from app.uploads.models import StoredFile
from app.uploads.object_store import MinioObjectStore, ObjectInspection
from app.uploads.operations import (
    StorageOperationError,
    StorageReconciler,
    StorageTransfer,
)
from app.uploads.repository import UploadRepository


def _stored_file(
    *,
    object_key: str,
    payload: bytes,
    status: str = "available",
) -> StoredFile:
    now = datetime.now(UTC)
    return StoredFile(
        id=uuid4(),
        owner_user_id=uuid4(),
        purpose="assignment_submission",
        object_key=object_key,
        original_name="never-export-this-name.pdf",
        extension="pdf",
        declared_media_type="application/pdf",
        detected_media_type="application/pdf",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        status=status,
        created_at=now,
        available_at=now if status == "available" else None,
        deleted_at=None,
    )


class FakeRepository:
    def __init__(self, records: list[StoredFile]) -> None:
        self.records = records

    async def files_for_reconciliation(self) -> list[StoredFile]:
        return self.records


def _write_payload(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


class FakeObjectStore:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = dict(payloads)

    async def list_object_keys(self) -> list[str]:
        return sorted(self.payloads)

    async def inspect(self, object_key: str) -> ObjectInspection:
        payload = self.payloads[object_key]
        return ObjectInspection(
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            first_bytes=payload[:32],
            content_type="application/pdf",
        )

    async def export_to_path(
        self,
        object_key: str,
        destination: Path,
    ) -> ObjectInspection:
        payload = self.payloads[object_key]
        await asyncio.to_thread(_write_payload, destination, payload)
        return await self.inspect(object_key)

    async def import_from_path(
        self,
        object_key: str,
        source: Path,
        *,
        content_type: str | None,
    ) -> ObjectInspection:
        del content_type
        self.payloads[object_key] = await asyncio.to_thread(source.read_bytes)
        return await self.inspect(object_key)

    async def delete_object(self, object_key: str) -> None:
        self.payloads.pop(object_key, None)


@pytest.mark.asyncio
async def test_storage_reconciliation_reports_only_actionable_object_metadata() -> None:
    healthy = _stored_file(object_key="objects/2026/08/healthy", payload=b"healthy")
    missing = _stored_file(object_key="objects/2026/08/missing", payload=b"missing")
    wrong_size = _stored_file(object_key="objects/2026/08/size", payload=b"expected")
    wrong_size.sha256 = hashlib.sha256(b"x").hexdigest()
    wrong_hash = _stored_file(object_key="objects/2026/08/hash", payload=b"expected-hash")
    terminal = _stored_file(
        object_key="objects/2026/08/terminal",
        payload=b"terminal",
        status="expired",
    )
    store = FakeObjectStore(
        {
            healthy.object_key: b"healthy",
            wrong_size.object_key: b"x",
            wrong_hash.object_key: b"unexpected-md",
            "objects/2026/08/untracked": b"candidate",
        }
    )
    repository = FakeRepository([healthy, missing, wrong_size, wrong_hash, terminal])
    reconciler = StorageReconciler(
        cast(UploadRepository, repository),
        cast(MinioObjectStore, store),
    )

    report = await reconciler.run()
    serialized = json.dumps(report.to_dict(), sort_keys=True)

    assert report.ok is False
    assert [item["file_id"] for item in report.missing_objects] == [str(missing.id)]
    assert [item["file_id"] for item in report.size_mismatches] == [str(wrong_size.id)]
    assert [item["file_id"] for item in report.sha256_mismatches] == [str(wrong_hash.id)]
    assert report.untracked_objects == ["objects/2026/08/untracked"]
    assert "never-export-this-name" not in serialized


@pytest.mark.asyncio
async def test_storage_export_and_empty_bucket_import_round_trip(tmp_path: Path) -> None:
    source = FakeObjectStore(
        {
            "objects/2026/08/first": b"first-payload",
            "objects/2026/08/second": b"second-payload",
        }
    )
    bundle = tmp_path / "bundle"
    export_summary = await StorageTransfer(cast(MinioObjectStore, source)).export(bundle)

    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert export_summary["object_count"] == 2
    assert "original_name" not in json.dumps(manifest)
    assert {item["object_key"] for item in manifest["objects"]} == set(source.payloads)

    target = FakeObjectStore({})
    import_summary = await StorageTransfer(cast(MinioObjectStore, target)).import_into_empty_bucket(
        bundle
    )

    assert import_summary["object_count"] == export_summary["object_count"]
    assert import_summary["total_bytes"] == export_summary["total_bytes"]
    assert target.payloads == source.payloads


@pytest.mark.asyncio
async def test_storage_import_rejects_nonempty_bucket_and_unsafe_key(tmp_path: Path) -> None:
    source = FakeObjectStore({"objects/2026/08/file": b"payload"})
    bundle = tmp_path / "bundle"
    await StorageTransfer(cast(MinioObjectStore, source)).export(bundle)

    nonempty = FakeObjectStore({"objects/existing": b"existing"})
    with pytest.raises(StorageOperationError, match="TARGET_BUCKET_NOT_EMPTY"):
        await StorageTransfer(cast(MinioObjectStore, nonempty)).import_into_empty_bucket(bundle)

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["objects"][0]["object_key"] = "../escape"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StorageOperationError, match="UNSAFE_OBJECT_KEY"):
        await StorageTransfer(cast(MinioObjectStore, FakeObjectStore({}))).import_into_empty_bucket(
            bundle
        )


@pytest.mark.asyncio
async def test_weekly_full_and_daily_incremental_object_round_trip(tmp_path: Path) -> None:
    weekly_id = "pnx-backup-20260823T000000Z-weekly"
    daily_id = "pnx-backup-20260824T000000Z-daily"
    source = FakeObjectStore(
        {
            "objects/2026/08/unchanged": b"unchanged",
            "objects/2026/08/changed": b"before-change",
            "objects/2026/08/deleted": b"deleted-after-weekly",
        }
    )
    weekly_bundle = tmp_path / "weekly"
    weekly_summary = await StorageTransfer(cast(MinioObjectStore, source)).export(
        weekly_bundle,
        backup_id=weekly_id,
    )

    source.payloads["objects/2026/08/changed"] = b"after-change"
    source.payloads["objects/2026/08/created"] = b"created-after-weekly"
    del source.payloads["objects/2026/08/deleted"]
    daily_bundle = tmp_path / "daily"
    daily_summary = await StorageTransfer(cast(MinioObjectStore, source)).export(
        daily_bundle,
        backup_id=daily_id,
        base_manifest=weekly_bundle / "manifest.json",
    )

    daily_manifest = json.loads((daily_bundle / "manifest.json").read_text(encoding="utf-8"))
    assert weekly_summary["payload_object_count"] == 3
    assert daily_summary["object_count"] == 3
    assert daily_summary["payload_object_count"] == 2
    assert daily_summary["deleted_object_count"] == 1
    assert daily_manifest["mode"] == "incremental"
    assert daily_manifest["base_backup_id"] == weekly_id
    assert {entry["object_key"] for entry in daily_manifest["objects"]} == {
        "objects/2026/08/changed",
        "objects/2026/08/created",
    }
    assert daily_manifest["deleted_object_keys"] == ["objects/2026/08/deleted"]
    assert not (daily_bundle / "payload/objects/2026/08/unchanged").exists()

    target = FakeObjectStore({})
    target_transfer = StorageTransfer(cast(MinioObjectStore, target))
    await target_transfer.import_into_empty_bucket(weekly_bundle)
    import_summary = await target_transfer.apply_incremental(
        daily_bundle,
        base_manifest=weekly_bundle / "manifest.json",
    )

    assert import_summary["object_count"] == 3
    assert import_summary["imported_object_count"] == 2
    assert import_summary["deleted_object_count"] == 1
    assert target.payloads == source.payloads


@pytest.mark.asyncio
async def test_incremental_import_rejects_wrong_base_bucket(tmp_path: Path) -> None:
    weekly_id = "pnx-backup-20260823T000000Z-weekly"
    source = FakeObjectStore({"objects/2026/08/file": b"weekly"})
    weekly_bundle = tmp_path / "weekly"
    await StorageTransfer(cast(MinioObjectStore, source)).export(
        weekly_bundle,
        backup_id=weekly_id,
    )
    source.payloads["objects/2026/08/new"] = b"daily"
    daily_bundle = tmp_path / "daily"
    await StorageTransfer(cast(MinioObjectStore, source)).export(
        daily_bundle,
        backup_id="pnx-backup-20260824T000000Z-daily",
        base_manifest=weekly_bundle / "manifest.json",
    )

    wrong_target = FakeObjectStore({"objects/2026/08/file": b"tampered"})
    with pytest.raises(StorageOperationError, match="INCREMENTAL_BASE_BUCKET_MISMATCH"):
        await StorageTransfer(cast(MinioObjectStore, wrong_target)).apply_incremental(
            daily_bundle,
            base_manifest=weekly_bundle / "manifest.json",
        )
