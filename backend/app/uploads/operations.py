import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.uploads.object_store import MinioObjectStore, ObjectInspection
from app.uploads.repository import UploadRepository


class StorageOperationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class StorageReconciliationReport:
    database_file_count: int
    available_file_count: int
    bucket_object_count: int
    missing_objects: list[dict[str, object]]
    size_mismatches: list[dict[str, object]]
    sha256_mismatches: list[dict[str, object]]
    untracked_objects: list[str]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_objects
            or self.size_mismatches
            or self.sha256_mismatches
            or self.untracked_objects
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "inconsistent",
            "database_file_count": self.database_file_count,
            "available_file_count": self.available_file_count,
            "bucket_object_count": self.bucket_object_count,
            "missing_objects": self.missing_objects,
            "size_mismatches": self.size_mismatches,
            "sha256_mismatches": self.sha256_mismatches,
            "untracked_objects": self.untracked_objects,
        }


class StorageReconciler:
    def __init__(
        self,
        repository: UploadRepository,
        object_store: MinioObjectStore,
    ) -> None:
        self._repository = repository
        self._object_store = object_store

    async def run(self) -> StorageReconciliationReport:
        records = await self._repository.files_for_reconciliation()
        bucket_keys = set(await self._object_store.list_object_keys())
        database_keys = {record.object_key for record in records}
        available_records = [
            record
            for record in records
            if record.status == "available" and record.deleted_at is None
        ]
        missing_objects: list[dict[str, object]] = []
        size_mismatches: list[dict[str, object]] = []
        sha256_mismatches: list[dict[str, object]] = []

        for record in available_records:
            identity: dict[str, object] = {
                "file_id": str(record.id),
                "object_key": record.object_key,
            }
            if record.object_key not in bucket_keys:
                missing_objects.append(identity)
                continue
            inspection = await self._object_store.inspect(record.object_key)
            if inspection.size_bytes != record.size_bytes:
                size_mismatches.append(
                    {
                        **identity,
                        "expected_size_bytes": record.size_bytes,
                        "actual_size_bytes": inspection.size_bytes,
                    }
                )
            if inspection.sha256 != record.sha256:
                sha256_mismatches.append(
                    {
                        **identity,
                        "expected_sha256": record.sha256,
                        "actual_sha256": inspection.sha256,
                    }
                )

        return StorageReconciliationReport(
            database_file_count=len(records),
            available_file_count=len(available_records),
            bucket_object_count=len(bucket_keys),
            missing_objects=missing_objects,
            size_mismatches=size_mismatches,
            sha256_mismatches=sha256_mismatches,
            untracked_objects=sorted(bucket_keys - database_keys),
        )


@dataclass(frozen=True, slots=True)
class ObjectManifestEntry:
    object_key: str
    size_bytes: int
    sha256: str
    content_type: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "object_key": self.object_key,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "content_type": self.content_type,
        }


@dataclass(frozen=True, slots=True)
class ObjectBackupManifest:
    version: int
    backup_id: str | None
    mode: str
    base_backup_id: str | None
    base_manifest_sha256: str | None
    inventory: list[ObjectManifestEntry]
    payload_entries: list[ObjectManifestEntry]
    deleted_object_keys: list[str]


_BACKUP_ID_PATTERN = re.compile(r"^pnx-backup-[0-9]{8}T[0-9]{6}Z-(?:daily|weekly)$")
_SAFE_OBJECT_KEY_PREFIXES = frozenset({"knowledge", "objects"})


def _payload_path(root: Path, object_key: str) -> Path:
    pure_path = PurePosixPath(object_key)
    if (
        pure_path.is_absolute()
        or len(pure_path.parts) < 2
        or pure_path.parts[0] not in _SAFE_OBJECT_KEY_PREFIXES
        or any(part in {"", ".", ".."} for part in pure_path.parts)
    ):
        raise StorageOperationError("UNSAFE_OBJECT_KEY")
    return root.joinpath("payload", *pure_path.parts)


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(8 * 1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            digest.update(chunk)
    return size_bytes, digest.hexdigest()


def _prepare_export_directory(output: Path) -> None:
    if output.exists() or not output.parent.is_dir():
        raise StorageOperationError("EXPORT_TARGET_MUST_NOT_EXIST")
    output.mkdir(mode=0o700)


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _is_directory(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_manifest(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_entries(raw_objects: object) -> list[ObjectManifestEntry]:
    if not isinstance(raw_objects, list):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")
    entries: list[ObjectManifestEntry] = []
    seen_keys: set[str] = set()
    for raw_entry in raw_objects:
        if not isinstance(raw_entry, dict):
            raise StorageOperationError("INVALID_OBJECT_MANIFEST")
        object_key = raw_entry.get("object_key")
        size_bytes = raw_entry.get("size_bytes")
        sha256 = raw_entry.get("sha256")
        content_type = raw_entry.get("content_type")
        if (
            not isinstance(object_key, str)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or (content_type is not None and not isinstance(content_type, str))
            or object_key in seen_keys
        ):
            raise StorageOperationError("INVALID_OBJECT_MANIFEST")
        _payload_path(Path("."), object_key)
        seen_keys.add(object_key)
        entries.append(
            ObjectManifestEntry(
                object_key=object_key,
                size_bytes=size_bytes,
                sha256=sha256,
                content_type=content_type,
            )
        )
    return entries


def _parse_manifest(raw_manifest: object) -> ObjectBackupManifest:
    if not isinstance(raw_manifest, dict):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")
    version = raw_manifest.get("version")
    if version == 1:
        entries = _manifest_entries(raw_manifest.get("objects"))
        return ObjectBackupManifest(
            version=1,
            backup_id=None,
            mode="full",
            base_backup_id=None,
            base_manifest_sha256=None,
            inventory=entries,
            payload_entries=entries,
            deleted_object_keys=[],
        )
    if version != 2:
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")

    backup_id = raw_manifest.get("backup_id")
    mode = raw_manifest.get("mode")
    base_backup_id = raw_manifest.get("base_backup_id")
    base_manifest_sha256 = raw_manifest.get("base_manifest_sha256")
    if (
        not isinstance(backup_id, str)
        or _BACKUP_ID_PATTERN.fullmatch(backup_id) is None
        or mode not in {"full", "incremental"}
        or (base_backup_id is not None and not isinstance(base_backup_id, str))
        or (base_manifest_sha256 is not None and not isinstance(base_manifest_sha256, str))
    ):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")

    inventory = _manifest_entries(raw_manifest.get("inventory"))
    payload_entries = _manifest_entries(raw_manifest.get("objects"))
    raw_deleted_keys = raw_manifest.get("deleted_object_keys")
    if not isinstance(raw_deleted_keys, list):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")
    deleted_object_keys: list[str] = []
    seen_deleted_keys: set[str] = set()
    for object_key in raw_deleted_keys:
        if not isinstance(object_key, str) or object_key in seen_deleted_keys:
            raise StorageOperationError("INVALID_OBJECT_MANIFEST")
        _payload_path(Path("."), object_key)
        seen_deleted_keys.add(object_key)
        deleted_object_keys.append(object_key)

    inventory_by_key = {entry.object_key: entry for entry in inventory}
    payload_by_key = {entry.object_key: entry for entry in payload_entries}
    if (
        any(
            inventory_by_key.get(object_key) != entry
            for object_key, entry in payload_by_key.items()
        )
        or set(inventory_by_key) & seen_deleted_keys
    ):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")

    if mode == "full":
        if (
            base_backup_id is not None
            or base_manifest_sha256 is not None
            or deleted_object_keys
            or payload_by_key != inventory_by_key
        ):
            raise StorageOperationError("INVALID_OBJECT_MANIFEST")
    elif (
        not isinstance(base_backup_id, str)
        or not base_backup_id.endswith("-weekly")
        or not isinstance(base_manifest_sha256, str)
        or len(base_manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in base_manifest_sha256)
        or not backup_id.endswith("-daily")
    ):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")

    return ObjectBackupManifest(
        version=2,
        backup_id=backup_id,
        mode=mode,
        base_backup_id=base_backup_id,
        base_manifest_sha256=base_manifest_sha256,
        inventory=inventory,
        payload_entries=payload_entries,
        deleted_object_keys=deleted_object_keys,
    )


def _load_manifest(path: Path) -> ObjectBackupManifest:
    if not _is_regular_file(path):
        raise StorageOperationError("INVALID_OBJECT_MANIFEST")
    try:
        return _parse_manifest(_read_manifest(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StorageOperationError("INVALID_OBJECT_MANIFEST") from exc


def _entry_from_inspection(
    object_key: str,
    inspection: ObjectInspection,
) -> ObjectManifestEntry:
    return ObjectManifestEntry(
        object_key=object_key,
        size_bytes=inspection.size_bytes,
        sha256=inspection.sha256,
        content_type=inspection.content_type,
    )


def _inspection_matches(
    inspection: ObjectInspection,
    entry: ObjectManifestEntry,
) -> bool:
    return (
        inspection.size_bytes == entry.size_bytes
        and inspection.sha256 == entry.sha256
        and inspection.content_type == entry.content_type
    )


class StorageTransfer:
    def __init__(self, object_store: MinioObjectStore) -> None:
        self._object_store = object_store

    async def export(
        self,
        output: Path,
        *,
        backup_id: str | None = None,
        base_manifest: Path | None = None,
    ) -> dict[str, object]:
        if backup_id is None and base_manifest is not None:
            raise StorageOperationError("BACKUP_ID_REQUIRED")
        if backup_id is not None and _BACKUP_ID_PATTERN.fullmatch(backup_id) is None:
            raise StorageOperationError("INVALID_BACKUP_ID")

        base: ObjectBackupManifest | None = None
        base_manifest_sha256: str | None = None
        if base_manifest is not None:
            base = await asyncio.to_thread(_load_manifest, base_manifest)
            if (
                base.version != 2
                or base.mode != "full"
                or base.backup_id is None
                or not base.backup_id.endswith("-weekly")
                or backup_id is None
                or not backup_id.endswith("-daily")
            ):
                raise StorageOperationError("INVALID_INCREMENTAL_BASE")
            _, base_manifest_sha256 = await asyncio.to_thread(
                _file_digest,
                base_manifest,
            )
        elif backup_id is not None and not backup_id.endswith("-weekly"):
            raise StorageOperationError("INCREMENTAL_BASE_REQUIRED")

        await asyncio.to_thread(_prepare_export_directory, output)
        inventory: list[ObjectManifestEntry] = []
        payload_entries: list[ObjectManifestEntry] = []
        total_bytes = 0
        payload_bytes = 0
        current_keys = await self._object_store.list_object_keys()
        base_by_key = (
            {entry.object_key: entry for entry in base.inventory} if base is not None else {}
        )
        for object_key in current_keys:
            base_entry = base_by_key.get(object_key)
            if base_entry is None:
                inspection = await self._object_store.export_to_path(
                    object_key,
                    _payload_path(output, object_key),
                )
                entry = _entry_from_inspection(object_key, inspection)
                payload_entries.append(entry)
                payload_bytes += entry.size_bytes
            else:
                inspection = await self._object_store.inspect(object_key)
                entry = _entry_from_inspection(object_key, inspection)
                if entry != base_entry:
                    inspection = await self._object_store.export_to_path(
                        object_key,
                        _payload_path(output, object_key),
                    )
                    entry = _entry_from_inspection(object_key, inspection)
                    payload_entries.append(entry)
                    payload_bytes += entry.size_bytes
            inventory.append(entry)
            total_bytes += entry.size_bytes

        deleted_object_keys = sorted(set(base_by_key) - set(current_keys))
        created_at = datetime.now(UTC).isoformat()
        if backup_id is None:
            manifest: dict[str, object] = {
                "version": 1,
                "created_at": created_at,
                "objects": [entry.to_dict() for entry in inventory],
            }
        else:
            manifest = {
                "version": 2,
                "backup_id": backup_id,
                "mode": "incremental" if base is not None else "full",
                "created_at": created_at,
                "base_backup_id": base.backup_id if base is not None else None,
                "base_manifest_sha256": base_manifest_sha256,
                "inventory": [entry.to_dict() for entry in inventory],
                "objects": [entry.to_dict() for entry in payload_entries],
                "deleted_object_keys": deleted_object_keys,
            }
        manifest_path = output / "manifest.json"
        await asyncio.to_thread(_write_manifest, manifest_path, manifest)
        return {
            "object_count": len(inventory),
            "total_bytes": total_bytes,
            "payload_object_count": len(payload_entries),
            "payload_bytes": payload_bytes,
            "deleted_object_count": len(deleted_object_keys),
            "manifest": "manifest.json",
        }

    async def import_into_empty_bucket(self, source: Path) -> dict[str, object]:
        if not await asyncio.to_thread(_is_directory, source):
            raise StorageOperationError("IMPORT_SOURCE_INVALID")
        if await self._object_store.list_object_keys():
            raise StorageOperationError("TARGET_BUCKET_NOT_EMPTY")
        manifest = await asyncio.to_thread(_load_manifest, source / "manifest.json")
        if manifest.mode != "full":
            raise StorageOperationError("FULL_OBJECT_BACKUP_REQUIRED")
        entries = manifest.inventory
        total_bytes = 0

        for entry in entries:
            payload = _payload_path(source, entry.object_key)
            if not await asyncio.to_thread(_is_regular_file, payload):
                raise StorageOperationError("OBJECT_PAYLOAD_MISSING")
            size_bytes, sha256 = await asyncio.to_thread(_file_digest, payload)
            if size_bytes != entry.size_bytes or sha256 != entry.sha256:
                raise StorageOperationError("OBJECT_PAYLOAD_MISMATCH")
            inspection = await self._object_store.import_from_path(
                entry.object_key,
                payload,
                content_type=entry.content_type,
            )
            if not _inspection_matches(inspection, entry):
                raise StorageOperationError("OBJECT_IMPORT_VERIFICATION_FAILED")
            total_bytes += entry.size_bytes

        restored_keys = set(await self._object_store.list_object_keys())
        expected_keys = {entry.object_key for entry in entries}
        if restored_keys != expected_keys:
            raise StorageOperationError("OBJECT_IMPORT_SET_MISMATCH")
        return {
            "object_count": len(entries),
            "total_bytes": total_bytes,
        }

    async def apply_incremental(
        self,
        source: Path,
        *,
        base_manifest: Path,
    ) -> dict[str, object]:
        if not await asyncio.to_thread(_is_directory, source):
            raise StorageOperationError("IMPORT_SOURCE_INVALID")
        incremental = await asyncio.to_thread(_load_manifest, source / "manifest.json")
        base = await asyncio.to_thread(_load_manifest, base_manifest)
        if (
            incremental.version != 2
            or incremental.mode != "incremental"
            or base.version != 2
            or base.mode != "full"
            or incremental.base_backup_id != base.backup_id
        ):
            raise StorageOperationError("INVALID_INCREMENTAL_CHAIN")
        _, actual_base_manifest_sha256 = await asyncio.to_thread(
            _file_digest,
            base_manifest,
        )
        if incremental.base_manifest_sha256 != actual_base_manifest_sha256:
            raise StorageOperationError("INCREMENTAL_BASE_CHECKSUM_MISMATCH")

        base_by_key = {entry.object_key: entry for entry in base.inventory}
        inventory_by_key = {entry.object_key: entry for entry in incremental.inventory}
        payload_by_key = {entry.object_key: entry for entry in incremental.payload_entries}
        expected_deleted_keys = set(base_by_key) - set(inventory_by_key)
        expected_payload_keys = {
            object_key
            for object_key, entry in inventory_by_key.items()
            if base_by_key.get(object_key) != entry
        }
        if (
            set(incremental.deleted_object_keys) != expected_deleted_keys
            or set(payload_by_key) != expected_payload_keys
        ):
            raise StorageOperationError("INVALID_INCREMENTAL_DELTA")

        bucket_keys = set(await self._object_store.list_object_keys())
        if bucket_keys != set(base_by_key):
            raise StorageOperationError("INCREMENTAL_BASE_BUCKET_MISMATCH")
        for entry in base.inventory:
            inspection = await self._object_store.inspect(entry.object_key)
            if not _inspection_matches(inspection, entry):
                raise StorageOperationError("INCREMENTAL_BASE_BUCKET_MISMATCH")

        for entry in incremental.payload_entries:
            payload = _payload_path(source, entry.object_key)
            if not await asyncio.to_thread(_is_regular_file, payload):
                raise StorageOperationError("OBJECT_PAYLOAD_MISSING")
            size_bytes, sha256 = await asyncio.to_thread(_file_digest, payload)
            if size_bytes != entry.size_bytes or sha256 != entry.sha256:
                raise StorageOperationError("OBJECT_PAYLOAD_MISMATCH")

        imported_bytes = 0
        for entry in incremental.payload_entries:
            inspection = await self._object_store.import_from_path(
                entry.object_key,
                _payload_path(source, entry.object_key),
                content_type=entry.content_type,
            )
            if not _inspection_matches(inspection, entry):
                raise StorageOperationError("OBJECT_IMPORT_VERIFICATION_FAILED")
            imported_bytes += entry.size_bytes
        for object_key in incremental.deleted_object_keys:
            await self._object_store.delete_object(object_key)

        restored_keys = set(await self._object_store.list_object_keys())
        if restored_keys != set(inventory_by_key):
            raise StorageOperationError("OBJECT_IMPORT_SET_MISMATCH")
        for entry in incremental.inventory:
            inspection = await self._object_store.inspect(entry.object_key)
            if not _inspection_matches(inspection, entry):
                raise StorageOperationError("OBJECT_IMPORT_VERIFICATION_FAILED")

        return {
            "object_count": len(incremental.inventory),
            "total_bytes": sum(entry.size_bytes for entry in incremental.inventory),
            "imported_object_count": len(incremental.payload_entries),
            "imported_bytes": imported_bytes,
            "deleted_object_count": len(incremental.deleted_object_keys),
        }
