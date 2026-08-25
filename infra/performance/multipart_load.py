#!/usr/bin/env python3
"""Run isolated concurrent multipart uploads with generated streaming content."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import AsyncIterator, Awaitable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from _common import (
    ConfigurationError,
    RequestMetric,
    authenticate,
    capacity_student_email,
    client_for,
    normalize_base_url,
    percentile,
    read_password_file,
    summarize_metrics,
)

MAX_UPLOAD_BYTES = 2_147_483_648


class UploadStageError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PatternSource:
    """Deterministic printable content that supports offset-aware streaming."""

    def __init__(self, seed: str, block_size: int) -> None:
        line = f"PNX-STAGE6-{hashlib.sha256(seed.encode()).hexdigest()}\n".encode()
        self.block = (line * ((block_size + len(line) - 1) // len(line)))[:block_size]

    def iter_range(self, offset: int, length: int) -> Iterator[bytes]:
        position = offset
        remaining = length
        while remaining:
            block_offset = position % len(self.block)
            take = min(remaining, len(self.block) - block_offset)
            yield self.block[block_offset : block_offset + take]
            position += take
            remaining -= take


@dataclass(frozen=True, slots=True)
class DigestPlan:
    full_sha256: str
    part_checksums_base64: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UploadResult:
    success: bool
    latency_ms: float
    error_code: str | None
    request_metrics: tuple[RequestMetric, ...]


def build_digest_plan(
    source: PatternSource,
    *,
    size_bytes: int,
    part_size_bytes: int,
) -> DigestPlan:
    full_hasher = hashlib.sha256()
    checksums: list[str] = []
    offset = 0
    while offset < size_bytes:
        part_length = min(part_size_bytes, size_bytes - offset)
        part_hasher = hashlib.sha256()
        for chunk in source.iter_range(offset, part_length):
            full_hasher.update(chunk)
            part_hasher.update(chunk)
        checksums.append(base64.b64encode(part_hasher.digest()).decode("ascii"))
        offset += part_length
    return DigestPlan(full_hasher.hexdigest(), tuple(checksums))


async def stream_range(
    source: PatternSource,
    *,
    offset: int,
    length: int,
) -> AsyncIterator[bytes]:
    for chunk in source.iter_range(offset, length):
        yield chunk
        await asyncio.sleep(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", required=True, help="Target origin, without /api/v1"
    )
    parser.add_argument(
        "--password-file", required=True, help="Absolute mode-0600 password file"
    )
    parser.add_argument("--uploads", type=int, default=20)
    parser.add_argument("--student-start", type=int, default=1)
    parser.add_argument("--size-bytes", type=int, default=1_048_576)
    parser.add_argument("--expected-part-size-bytes", type=int, default=16_777_216)
    parser.add_argument("--stream-block-size-bytes", type=int, default=1_048_576)
    parser.add_argument("--pattern-seed", default="pnx-stage6-capacity")
    parser.add_argument("--login-interval-ms", type=int, default=220)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for test CA only",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.uploads <= 300:
        raise ConfigurationError("UPLOAD_COUNT_INVALID")
    if (
        not 1 <= args.student_start <= 300
        or args.student_start + args.uploads - 1 > 300
    ):
        raise ConfigurationError("STUDENT_RANGE_INVALID")
    if not 1 <= args.size_bytes <= MAX_UPLOAD_BYTES:
        raise ConfigurationError("UPLOAD_SIZE_INVALID")
    if args.expected_part_size_bytes < 5_242_880:
        raise ConfigurationError("EXPECTED_PART_SIZE_INVALID")
    if not 4_096 <= args.stream_block_size_bytes <= 4_194_304:
        raise ConfigurationError("STREAM_BLOCK_SIZE_INVALID")
    if not args.pattern_seed or len(args.pattern_seed) > 128:
        raise ConfigurationError("PATTERN_SEED_INVALID")
    if args.login_interval_ms < 0 or args.timeout_seconds <= 0:
        raise ConfigurationError("TIMING_CONFIGURATION_INVALID")
    if not 0 < args.max_error_rate <= 1:
        raise ConfigurationError("ERROR_RATE_THRESHOLD_INVALID")


async def _timed_request(
    metrics: list[RequestMetric],
    stage: str,
    request: Awaitable[httpx.Response],
) -> httpx.Response:
    started = time.perf_counter()
    try:
        response = await request
    except httpx.HTTPError as exc:
        metrics.append(
            RequestMetric(
                stage, (time.perf_counter() - started) * 1000, False, "network"
            )
        )
        raise UploadStageError(f"{stage}_network") from exc
    latency_ms = (time.perf_counter() - started) * 1000
    success = 200 <= response.status_code < 300
    metrics.append(
        RequestMetric(
            stage,
            latency_ms,
            success,
            None if success else f"http_{response.status_code}",
        )
    )
    if not success:
        raise UploadStageError(f"{stage}_http_{response.status_code}")
    return response


def _json_object(response: httpx.Response, stage: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise UploadStageError(f"{stage}_invalid_json") from exc
    if not isinstance(payload, dict):
        raise UploadStageError(f"{stage}_invalid_payload")
    return payload


async def _abort_best_effort(
    client: httpx.AsyncClient,
    upload_id: str | None,
    csrf_token: str,
) -> None:
    if upload_id is None:
        return
    try:
        await client.delete(
            f"uploads/{upload_id}",
            headers={"X-CSRF-Token": csrf_token},
        )
    except httpx.HTTPError:
        return


async def upload_one(
    api_client: httpx.AsyncClient,
    storage_client: httpx.AsyncClient,
    *,
    worker_index: int,
    context_id: str,
    csrf_token: str,
    source: PatternSource,
    plan: DigestPlan,
    size_bytes: int,
    part_size_bytes: int,
    start: asyncio.Event,
) -> UploadResult:
    await start.wait()
    started = time.perf_counter()
    metrics: list[RequestMetric] = []
    upload_id: str | None = None
    try:
        init_response = await _timed_request(
            metrics,
            "init",
            api_client.post(
                "uploads/init",
                headers={
                    "Idempotency-Key": str(uuid.uuid4()),
                    "X-CSRF-Token": csrf_token,
                },
                json={
                    "purpose": "assignment_submission",
                    "context_id": context_id,
                    "file_name": f"capacity-load-{worker_index + 1:03d}.txt",
                    "size_bytes": size_bytes,
                    "media_type": "text/plain",
                    "sha256": plan.full_sha256,
                },
            ),
        )
        init_payload = _json_object(init_response, "init")
        upload_id_value = init_payload.get("upload_id")
        server_part_size = init_payload.get("part_size_bytes")
        server_part_count = init_payload.get("part_count")
        if not isinstance(upload_id_value, str):
            raise UploadStageError("init_invalid_payload")
        upload_id = upload_id_value
        if server_part_size != part_size_bytes or server_part_count != len(
            plan.part_checksums_base64
        ):
            raise UploadStageError("server_part_configuration_mismatch")

        completed_parts: list[dict[str, object]] = []
        for batch_start in range(0, server_part_count, 10):
            numbers = list(
                range(batch_start + 1, min(batch_start + 11, server_part_count + 1))
            )
            presign_response = await _timed_request(
                metrics,
                "presign",
                api_client.post(
                    f"uploads/{upload_id}/parts/presign",
                    headers={"X-CSRF-Token": csrf_token},
                    json={"part_numbers": numbers},
                ),
            )
            presign_payload = _json_object(presign_response, "presign")
            raw_parts = presign_payload.get("parts")
            if not isinstance(raw_parts, list) or len(raw_parts) != len(numbers):
                raise UploadStageError("presign_invalid_payload")
            for raw_part in raw_parts:
                if not isinstance(raw_part, dict):
                    raise UploadStageError("presign_invalid_payload")
                part_number = raw_part.get("part_number")
                url = raw_part.get("url")
                if not isinstance(part_number, int) or not isinstance(url, str):
                    raise UploadStageError("presign_invalid_payload")
                offset = (part_number - 1) * part_size_bytes
                part_length = min(part_size_bytes, size_bytes - offset)
                checksum = plan.part_checksums_base64[part_number - 1]
                put_response = await _timed_request(
                    metrics,
                    "upload_part",
                    storage_client.put(
                        url,
                        content=stream_range(source, offset=offset, length=part_length),
                        headers={
                            "Content-Length": str(part_length),
                            "Content-Type": "text/plain",
                            "x-amz-checksum-sha256": checksum,
                        },
                    ),
                )
                etag = put_response.headers.get("etag")
                if not etag:
                    raise UploadStageError("upload_part_missing_etag")
                completed_parts.append(
                    {
                        "part_number": part_number,
                        "etag": etag,
                        "checksum_sha256": checksum,
                    }
                )

        await _timed_request(
            metrics,
            "complete",
            api_client.post(
                f"uploads/{upload_id}/complete",
                headers={
                    "Idempotency-Key": str(uuid.uuid4()),
                    "X-CSRF-Token": csrf_token,
                },
                json={
                    "parts": sorted(
                        completed_parts, key=lambda item: int(item["part_number"])
                    ),
                    "sha256": plan.full_sha256,
                },
            ),
        )
        return UploadResult(
            True, (time.perf_counter() - started) * 1000, None, tuple(metrics)
        )
    except UploadStageError as exc:
        await _abort_best_effort(api_client, upload_id, csrf_token)
        return UploadResult(
            False, (time.perf_counter() - started) * 1000, exc.code, tuple(metrics)
        )


async def _csrf_token(client: httpx.AsyncClient) -> str:
    try:
        response = await client.get("auth/csrf")
    except httpx.HTTPError as exc:
        raise UploadStageError("csrf_network") from exc
    if response.status_code != 200:
        raise UploadStageError(f"csrf_http_{response.status_code}")
    payload = _json_object(response, "csrf")
    token = payload.get("csrf_token")
    if not isinstance(token, str) or not token:
        raise UploadStageError("csrf_invalid_payload")
    return token


async def _find_assignment(client: httpx.AsyncClient, size_bytes: int) -> str:
    try:
        response = await client.get(
            "assignments", params={"status": "all", "page_size": 100}
        )
    except httpx.HTTPError as exc:
        raise UploadStageError("context_network") from exc
    if response.status_code != 200:
        raise UploadStageError(f"context_http_{response.status_code}")
    payload = _json_object(response, "context")
    items = payload.get("items")
    if not isinstance(items, list):
        raise UploadStageError("context_invalid_payload")
    for item in items:
        if not isinstance(item, dict) or item.get("can_submit") is not True:
            continue
        assignment_id = item.get("id")
        if not isinstance(assignment_id, str):
            continue
        detail = await client.get(f"assignments/{assignment_id}")
        if detail.status_code != 200:
            continue
        detail_payload = _json_object(detail, "context")
        extensions = detail_payload.get("allowed_extensions")
        limit = detail_payload.get("max_total_bytes")
        if (
            isinstance(extensions, list)
            and "txt" in extensions
            and isinstance(limit, int)
            and limit >= size_bytes
        ):
            return assignment_id
    raise UploadStageError("NO_COMPATIBLE_ASSIGNMENT")


def _upload_summary(
    results: list[UploadResult], duration_seconds: float
) -> dict[str, Any]:
    latencies = [result.latency_ms for result in results]
    errors = Counter(
        result.error_code or "unknown_error" for result in results if not result.success
    )
    successful = sum(result.success for result in results)
    total = len(results)
    return {
        "total": total,
        "successful": successful,
        "errors": total - successful,
        "error_rate": round((total - successful) / total, 6) if total else 1.0,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50) or 0.0, 3),
            "p95": round(percentile(latencies, 0.95) or 0.0, 3),
            "p99": round(percentile(latencies, 0.99) or 0.0, 3),
            "max": round(max(latencies), 3) if latencies else None,
        },
        "throughput_uploads_per_second": round(total / duration_seconds, 3),
        "error_codes": dict(sorted(errors.items())),
    }


def _request_summary(
    results: list[UploadResult], duration_seconds: float
) -> dict[str, Any]:
    metrics = [metric for result in results for metric in result.request_metrics]
    grouped: defaultdict[str, list[RequestMetric]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.stage].append(metric)
    summary = summarize_metrics(metrics, duration_seconds)
    summary["by_stage"] = {
        stage: summarize_metrics(stage_metrics, duration_seconds)
        for stage, stage_metrics in sorted(grouped.items())
    }
    return summary


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    validate_args(args)
    base_url = normalize_base_url(args.base_url)
    password = read_password_file(args.password_file)
    source = PatternSource(args.pattern_seed, args.stream_block_size_bytes)
    digest_started = time.perf_counter()
    plan = await asyncio.to_thread(
        build_digest_plan,
        source,
        size_bytes=args.size_bytes,
        part_size_bytes=args.expected_part_size_bytes,
    )
    digest_duration = time.perf_counter() - digest_started
    api_clients: list[httpx.AsyncClient] = []
    login_metrics: list[RequestMetric] = []
    login_started = time.perf_counter()
    storage_client = httpx.AsyncClient(
        follow_redirects=False,
        headers={"User-Agent": "pnx-isolated-multipart-performance/1"},
        limits=httpx.Limits(
            max_connections=args.uploads,
            max_keepalive_connections=args.uploads,
        ),
        timeout=httpx.Timeout(args.timeout_seconds),
        trust_env=False,
        verify=not args.insecure,
    )
    try:
        csrf_tokens: list[str] = []
        for offset in range(args.uploads):
            client = client_for(
                base_url,
                timeout_seconds=args.timeout_seconds,
                verify_tls=not args.insecure,
            )
            client.headers["Origin"] = base_url
            api_clients.append(client)
            metric, valid = await authenticate(
                client,
                email=capacity_student_email(args.student_start + offset),
                password=password,
                origin=base_url,
            )
            login_metrics.append(metric)
            if not valid:
                break
            csrf_tokens.append(await _csrf_token(client))
            if offset + 1 < args.uploads and args.login_interval_ms:
                await asyncio.sleep(args.login_interval_ms / 1000)
        login_duration = time.perf_counter() - login_started
        if len(api_clients) != args.uploads or any(
            not metric.success for metric in login_metrics
        ):
            report = {
                "status": "error",
                "tool": "multipart_load",
                "generated_at": datetime.now(UTC).isoformat(),
                "error_code": "AUTHENTICATED_SESSION_SETUP_FAILED",
                "authentication": summarize_metrics(login_metrics, login_duration),
            }
            return report, 2

        context_id = await _find_assignment(api_clients[0], args.size_bytes)
        start = asyncio.Event()
        tasks = [
            asyncio.create_task(
                upload_one(
                    client,
                    storage_client,
                    worker_index=index,
                    context_id=context_id,
                    csrf_token=csrf_tokens[index],
                    source=source,
                    plan=plan,
                    size_bytes=args.size_bytes,
                    part_size_bytes=args.expected_part_size_bytes,
                    start=start,
                )
            )
            for index, client in enumerate(api_clients)
        ]
        await asyncio.sleep(0)
        workload_started = time.perf_counter()
        start.set()
        results = await asyncio.gather(*tasks)
        duration_seconds = time.perf_counter() - workload_started
        upload_summary = _upload_summary(results, duration_seconds)
        threshold_met = upload_summary["error_rate"] < args.max_error_rate
        successful_bytes = args.size_bytes * upload_summary["successful"]
        report = {
            "status": "ok" if threshold_met else "error",
            "tool": "multipart_load",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": {"origin": base_url, "api_prefix": "/api/v1"},
            "configuration": {
                "concurrent_uploads": args.uploads,
                "bytes_per_upload": args.size_bytes,
                "part_size_bytes": args.expected_part_size_bytes,
                "part_count_per_upload": len(plan.part_checksums_base64),
                "stream_block_size_bytes": args.stream_block_size_bytes,
                "tls_verification": not args.insecure,
            },
            "preparation": {
                "digest_duration_seconds": round(digest_duration, 3),
                "peak_generated_block_bytes": len(source.block),
            },
            "authentication": summarize_metrics(login_metrics, login_duration),
            "workload": {
                "duration_seconds": round(duration_seconds, 3),
                "successful_bytes": successful_bytes,
                "aggregate_mib_per_second": round(
                    successful_bytes / 1_048_576 / duration_seconds,
                    3,
                ),
                "uploads": upload_summary,
                "requests": _request_summary(results, duration_seconds),
            },
            "acceptance": {
                "error_rate_must_be_below": args.max_error_rate,
                "met": threshold_met,
            },
        }
        return report, 0 if threshold_met else 2
    finally:
        await storage_client.aclose()
        await asyncio.gather(*(client.aclose() for client in api_clients))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report, exit_code = asyncio.run(run(args))
    except ConfigurationError as exc:
        report = {"status": "error", "tool": "multipart_load", "error_code": exc.code}
        exit_code = 2
    except UploadStageError as exc:
        report = {"status": "error", "tool": "multipart_load", "error_code": exc.code}
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
