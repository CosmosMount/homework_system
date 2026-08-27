import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import quote, urlsplit

import boto3  # type: ignore[import-untyped]
from botocore.client import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings


class ObjectStoreError(Exception):
    pass


class StreamingBody(Protocol):
    def read(self, amt: int = -1) -> bytes: ...

    def close(self) -> None: ...


class S3Client(Protocol):
    def head_bucket(self, **kwargs: object) -> dict[str, object]: ...

    def create_bucket(self, **kwargs: object) -> dict[str, object]: ...

    def create_multipart_upload(self, **kwargs: object) -> dict[str, object]: ...

    def generate_presigned_url(self, *args: object, **kwargs: object) -> str: ...

    def list_parts(self, **kwargs: object) -> dict[str, object]: ...

    def complete_multipart_upload(self, **kwargs: object) -> dict[str, object]: ...

    def abort_multipart_upload(self, **kwargs: object) -> dict[str, object]: ...
    def list_objects_v2(self, **kwargs: object) -> dict[str, object]: ...

    def put_object(self, **kwargs: object) -> dict[str, object]: ...

    def head_object(self, **kwargs: object) -> dict[str, object]: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...

    def delete_object(self, **kwargs: object) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class ObjectPart:
    part_number: int
    etag: str
    checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ObjectInspection:
    size_bytes: int
    sha256: str
    first_bytes: bytes
    content_type: str | None


def _client(settings: Settings) -> S3Client:
    return cast(
        S3Client,
        boto3.client(
            "s3",
            endpoint_url=settings.minio_internal_endpoint,
            aws_access_key_id=settings.minio_access_key.get_secret_value(),
            aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
            region_name=settings.minio_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        ),
    )


class MinioObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._client = _client(settings)
        self._bucket = settings.minio_bucket
        self._public_base_url = str(settings.minio_public_base_url).rstrip("/")

    @staticmethod
    def _error_code(error: ClientError) -> str:
        response = cast(dict[str, object], error.response)
        error_detail = response.get("Error")
        if isinstance(error_detail, dict):
            code = error_detail.get("Code")
            if isinstance(code, str):
                return code
        return "OBJECT_STORE_ERROR"

    async def ensure_bucket(self) -> None:
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except ClientError as exc:
            if self._error_code(exc) not in {"404", "NoSuchBucket", "NotFound"}:
                raise ObjectStoreError("BUCKET_UNAVAILABLE") from exc
            try:
                await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)
            except ClientError as create_exc:
                if self._error_code(create_exc) not in {
                    "BucketAlreadyExists",
                    "BucketAlreadyOwnedByYou",
                }:
                    raise ObjectStoreError("BUCKET_CREATE_FAILED") from create_exc
        except BotoCoreError as exc:
            raise ObjectStoreError("OBJECT_STORE_UNAVAILABLE") from exc

    async def list_object_keys(self) -> list[str]:
        await self.ensure_bucket()
        continuation_token: str | None = None
        keys: list[str] = []
        try:
            while True:
                parameters: dict[str, object] = {
                    "Bucket": self._bucket,
                    "MaxKeys": 1000,
                }
                if continuation_token is not None:
                    parameters["ContinuationToken"] = continuation_token
                response = await asyncio.to_thread(
                    self._client.list_objects_v2,
                    **parameters,
                )
                raw_contents = response.get("Contents")
                if isinstance(raw_contents, list):
                    for item in raw_contents:
                        if not isinstance(item, dict):
                            continue
                        key = item.get("Key")
                        if isinstance(key, str) and key:
                            keys.append(key)
                if not response.get("IsTruncated"):
                    break
                next_token = response.get("NextContinuationToken")
                if not isinstance(next_token, str) or not next_token:
                    raise ObjectStoreError("INVALID_OBJECT_LIST")
                continuation_token = next_token
        except ObjectStoreError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStoreError("OBJECT_LIST_FAILED") from exc
        return sorted(set(keys))

    async def create_multipart(
        self,
        *,
        object_key: str,
        media_type: str,
    ) -> str:
        await self.ensure_bucket()
        try:
            response = await asyncio.to_thread(
                self._client.create_multipart_upload,
                Bucket=self._bucket,
                Key=object_key,
                ContentType=media_type,
                ChecksumAlgorithm="SHA256",
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStoreError("MULTIPART_INIT_FAILED") from exc
        upload_id = response.get("UploadId")
        if not isinstance(upload_id, str) or not upload_id:
            raise ObjectStoreError("INVALID_MULTIPART_RESPONSE")
        return upload_id

    def _public_url(self, internal_url: str) -> str:
        parts = urlsplit(internal_url)
        suffix = f"?{parts.query}" if parts.query else ""
        return f"{self._public_base_url}{parts.path}{suffix}"

    async def presign_parts(
        self,
        *,
        object_key: str,
        upload_id: str,
        part_numbers: Sequence[int],
        expires_seconds: int,
    ) -> list[tuple[int, str]]:
        try:
            return [
                (
                    part_number,
                    self._public_url(
                        self._client.generate_presigned_url(
                            "upload_part",
                            Params={
                                "Bucket": self._bucket,
                                "Key": object_key,
                                "UploadId": upload_id,
                                "PartNumber": part_number,
                            },
                            ExpiresIn=expires_seconds,
                            HttpMethod="PUT",
                        )
                    ),
                )
                for part_number in part_numbers
            ]
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ObjectStoreError("PRESIGN_FAILED") from exc

    async def list_parts(
        self,
        *,
        object_key: str,
        upload_id: str,
    ) -> list[ObjectPart]:
        marker = 0
        parts: list[ObjectPart] = []
        try:
            while True:
                response = await asyncio.to_thread(
                    self._client.list_parts,
                    Bucket=self._bucket,
                    Key=object_key,
                    UploadId=upload_id,
                    PartNumberMarker=marker,
                    MaxParts=1000,
                )
                raw_parts = response.get("Parts")
                if isinstance(raw_parts, list):
                    for raw_part in raw_parts:
                        if not isinstance(raw_part, dict):
                            continue
                        number = raw_part.get("PartNumber")
                        etag = raw_part.get("ETag")
                        size = raw_part.get("Size")
                        checksum = raw_part.get("ChecksumSHA256")
                        if (
                            isinstance(number, int)
                            and isinstance(etag, str)
                            and isinstance(size, int)
                        ):
                            parts.append(
                                ObjectPart(
                                    part_number=number,
                                    etag=etag,
                                    checksum_sha256=(checksum if isinstance(checksum, str) else ""),
                                    size_bytes=size,
                                )
                            )
                if not response.get("IsTruncated"):
                    break
                next_marker = response.get("NextPartNumberMarker")
                if not isinstance(next_marker, int) or next_marker <= marker:
                    raise ObjectStoreError("INVALID_PART_LIST")
                marker = next_marker
        except ClientError as exc:
            if self._error_code(exc) == "NoSuchUpload":
                return []
            raise ObjectStoreError("LIST_PARTS_FAILED") from exc
        except BotoCoreError as exc:
            raise ObjectStoreError("LIST_PARTS_FAILED") from exc
        return parts

    async def complete_multipart(
        self,
        *,
        object_key: str,
        upload_id: str,
        parts: Sequence[ObjectPart],
    ) -> None:
        payload_parts = [
            {
                "ETag": part.etag,
                "PartNumber": part.part_number,
                "ChecksumSHA256": part.checksum_sha256,
            }
            for part in parts
        ]
        try:
            await asyncio.to_thread(
                self._client.complete_multipart_upload,
                Bucket=self._bucket,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": payload_parts},
            )
        except ClientError as exc:
            if self._error_code(exc) == "NoSuchUpload":
                try:
                    await asyncio.to_thread(
                        self._client.head_object,
                        Bucket=self._bucket,
                        Key=object_key,
                    )
                except (BotoCoreError, ClientError) as head_exc:
                    raise ObjectStoreError("MULTIPART_COMPLETE_FAILED") from head_exc
                return
            raise ObjectStoreError("MULTIPART_COMPLETE_FAILED") from exc
        except BotoCoreError as exc:
            raise ObjectStoreError("MULTIPART_COMPLETE_FAILED") from exc

    def _consume_object_sync(
        self,
        object_key: str,
        destination: Path | None,
    ) -> ObjectInspection:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        raw_body = response.get("Body")
        if raw_body is None or not hasattr(raw_body, "read"):
            raise ObjectStoreError("INVALID_OBJECT_RESPONSE")
        body = cast(StreamingBody, raw_body)
        output = None
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            output = destination.open("xb")
        digest = hashlib.sha256()
        first_bytes = b""
        size_bytes = 0
        try:
            while True:
                chunk = body.read(8 * 1024 * 1024)
                if not chunk:
                    break
                if not first_bytes:
                    first_bytes = chunk[:32]
                if output is not None:
                    output.write(chunk)
                size_bytes += len(chunk)
                digest.update(chunk)
        finally:
            body.close()
            if output is not None:
                output.close()
        raw_content_type = response.get("ContentType")
        content_type = raw_content_type if isinstance(raw_content_type, str) else None
        return ObjectInspection(
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            first_bytes=first_bytes,
            content_type=content_type,
        )

    def _inspect_sync(self, object_key: str) -> ObjectInspection:
        return self._consume_object_sync(object_key, None)

    async def inspect(self, object_key: str) -> ObjectInspection:
        try:
            return await asyncio.to_thread(self._inspect_sync, object_key)
        except ObjectStoreError:
            raise
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ObjectStoreError("OBJECT_INSPECTION_FAILED") from exc

    async def export_to_path(
        self,
        object_key: str,
        destination: Path,
    ) -> ObjectInspection:
        try:
            return await asyncio.to_thread(
                self._consume_object_sync,
                object_key,
                destination,
            )
        except ObjectStoreError:
            raise
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ObjectStoreError("OBJECT_EXPORT_FAILED") from exc

    def _import_from_path_sync(
        self,
        object_key: str,
        source: Path,
        content_type: str | None,
    ) -> None:
        with source.open("rb") as body:
            parameters: dict[str, object] = {
                "Bucket": self._bucket,
                "Key": object_key,
                "Body": body,
            }
            if content_type is not None:
                parameters["ContentType"] = content_type
            self._client.put_object(**parameters)

    async def import_from_path(
        self,
        object_key: str,
        source: Path,
        *,
        content_type: str | None,
    ) -> ObjectInspection:
        try:
            await asyncio.to_thread(
                self._import_from_path_sync,
                object_key,
                source,
                content_type,
            )
            return await self.inspect(object_key)
        except ObjectStoreError:
            raise
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ObjectStoreError("OBJECT_IMPORT_FAILED") from exc

    async def import_bytes(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str,
    ) -> ObjectInspection:
        await self.ensure_bucket()
        parameters: dict[str, object] = {
            "Bucket": self._bucket,
            "Key": object_key,
            "Body": content,
            "ContentType": content_type,
        }
        try:
            await asyncio.to_thread(self._client.put_object, **parameters)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ObjectStoreError("OBJECT_IMPORT_FAILED") from exc
        return ObjectInspection(
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            first_bytes=content[:32],
            content_type=content_type,
        )

    async def abort_multipart(self, *, object_key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.abort_multipart_upload,
                Bucket=self._bucket,
                Key=object_key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            if self._error_code(exc) != "NoSuchUpload":
                raise ObjectStoreError("MULTIPART_ABORT_FAILED") from exc
        except BotoCoreError as exc:
            raise ObjectStoreError("MULTIPART_ABORT_FAILED") from exc

    async def delete_object(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStoreError("OBJECT_DELETE_FAILED") from exc

    async def presign_download(
        self,
        *,
        object_key: str,
        file_name: str,
        expires_seconds: int,
    ) -> str:
        disposition = f"attachment; filename*=UTF-8''{quote(file_name, safe='')}"
        try:
            internal_url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ResponseContentDisposition": disposition,
                },
                ExpiresIn=expires_seconds,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ObjectStoreError("DOWNLOAD_PRESIGN_FAILED") from exc
        return self._public_url(internal_url)

    async def presign_inline(
        self,
        *,
        object_key: str,
        file_name: str,
        content_type: str,
        expires_seconds: int,
    ) -> str:
        disposition = f"inline; filename*=UTF-8''{quote(file_name, safe='')}"
        try:
            internal_url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ResponseContentDisposition": disposition,
                    "ResponseContentType": content_type,
                },
                ExpiresIn=expires_seconds,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ObjectStoreError("DOWNLOAD_PRESIGN_FAILED") from exc
        return self._public_url(internal_url)
