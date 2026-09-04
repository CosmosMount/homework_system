import base64
import hashlib
from collections.abc import AsyncIterator
from typing import cast

import pytest

from app.core.config import Settings
from app.uploads.object_store import MinioObjectStore, ObjectStoreError, S3Client


class RecordingS3Client:
    def __init__(self, *, fail_part: bool = False, fail_abort: bool = False) -> None:
        self.fail_part = fail_part
        self.fail_abort = fail_abort
        self.uploaded_parts: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []
        self.aborted: list[dict[str, object]] = []
        self.presigned: list[tuple[str, dict[str, object]]] = []

    def head_bucket(self, **kwargs: object) -> dict[str, object]:
        return {}

    def create_multipart_upload(self, **kwargs: object) -> dict[str, object]:
        return {"UploadId": "upload-id"}

    def upload_part(self, **kwargs: object) -> dict[str, object]:
        self.uploaded_parts.append(kwargs)
        if self.fail_part:
            raise OSError("part failed")
        return {"ETag": f"etag-{kwargs['PartNumber']}"}

    def complete_multipart_upload(self, **kwargs: object) -> dict[str, object]:
        self.completed.append(kwargs)
        return {}

    def abort_multipart_upload(self, **kwargs: object) -> dict[str, object]:
        self.aborted.append(kwargs)
        if self.fail_abort:
            raise OSError("abort failed")
        return {}

    def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
        self.presigned.append((operation, kwargs))
        return "http://minio:9000/pnx-training/knowledge/generated/installer.exe?signature=test"


def object_store(client: RecordingS3Client) -> MinioObjectStore:
    store = MinioObjectStore(Settings(app_env="test"))
    store._client = cast(S3Client, client)
    return store


async def byte_chunks(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def failing_chunks() -> AsyncIterator[bytes]:
    yield b"first"
    raise RuntimeError("upstream failed")


@pytest.mark.asyncio
async def test_import_stream_uses_ordered_16_mib_parts_and_incremental_digest() -> None:
    client = RecordingS3Client()
    store = object_store(client)
    first = b"a" * (8 * 1024 * 1024)
    second = b"b" * (8 * 1024 * 1024)
    tail = b"tail"
    expected_digest = hashlib.sha256()
    for chunk in (first, second, tail):
        expected_digest.update(chunk)

    inspection = await store.import_stream(
        "knowledge/generated/file.pdf",
        byte_chunks(first, second, tail),
        content_type="application/pdf",
    )

    assert [part["PartNumber"] for part in client.uploaded_parts] == [1, 2]
    assert [part["ContentLength"] for part in client.uploaded_parts] == [
        16 * 1024 * 1024,
        4,
    ]
    assert client.uploaded_parts[0]["Body"] == first + second
    assert client.uploaded_parts[1]["Body"] == tail
    for part in client.uploaded_parts:
        content = cast(bytes, part["Body"])
        expected_checksum = base64.b64encode(hashlib.sha256(content).digest()).decode("ascii")
        assert part["ChecksumSHA256"] == expected_checksum
    assert len(client.completed) == 1
    completed_parts = cast(
        dict[str, list[dict[str, object]]],
        client.completed[0]["MultipartUpload"],
    )["Parts"]
    assert [part["PartNumber"] for part in completed_parts] == [1, 2]
    assert [part["ETag"] for part in completed_parts] == ["etag-1", "etag-2"]
    assert inspection.size_bytes == 16 * 1024 * 1024 + 4
    assert inspection.sha256 == expected_digest.hexdigest()
    assert inspection.first_bytes == first[:32]
    assert inspection.content_type == "application/pdf"
    assert client.aborted == []


@pytest.mark.asyncio
async def test_import_stream_aborts_and_preserves_part_error_when_abort_fails() -> None:
    client = RecordingS3Client(fail_part=True, fail_abort=True)
    store = object_store(client)

    with pytest.raises(ObjectStoreError, match="MULTIPART_PART_FAILED"):
        await store.import_stream(
            "knowledge/generated/file.pdf",
            byte_chunks(b"content"),
            content_type="application/pdf",
        )

    assert len(client.uploaded_parts) == 1
    assert len(client.aborted) == 1
    assert client.completed == []


@pytest.mark.asyncio
async def test_import_stream_aborts_and_preserves_upstream_error() -> None:
    client = RecordingS3Client()
    store = object_store(client)

    with pytest.raises(RuntimeError, match="upstream failed"):
        await store.import_stream(
            "knowledge/generated/file.pdf",
            failing_chunks(),
            content_type="application/pdf",
        )

    assert client.uploaded_parts == []
    assert len(client.aborted) == 1
    assert client.completed == []


@pytest.mark.asyncio
async def test_executable_download_presign_forces_attachment_and_octet_stream() -> None:
    client = RecordingS3Client()
    store = object_store(client)

    await store.presign_download(
        object_key="knowledge/generated/installer.exe",
        file_name="训练客户端.exe",
        expires_seconds=300,
        content_type="application/octet-stream",
    )

    operation, options = client.presigned[0]
    parameters = cast(dict[str, object], options["Params"])
    assert operation == "get_object"
    assert parameters["ResponseContentDisposition"] == (
        "attachment; filename*=UTF-8''%E8%AE%AD%E7%BB%83%E5%AE%A2%E6%88%B7%E7%AB%AF.exe"
    )
    assert parameters["ResponseContentType"] == "application/octet-stream"
