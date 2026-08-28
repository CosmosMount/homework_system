#!/usr/bin/env python3
"""Run a synchronized login burst for one isolated source-IP shard."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime

import httpx
from _common import (
    ConfigurationError,
    RequestMetric,
    authenticate,
    capacity_student_email,
    client_for,
    normalize_base_url,
    read_password_file,
    summarize_metrics,
)

MAX_START_DELAY_SECONDS = 300.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Target origin, without /api/v1")
    parser.add_argument(
        "--origin",
        help="Application Origin header when it differs from the container target",
    )
    parser.add_argument("--password-file", required=True, help="Absolute mode-0600 password file")
    parser.add_argument("--accounts", type=int, default=15)
    parser.add_argument("--student-start", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--start-at-epoch-ms",
        type=int,
        help="Optional shared UTC epoch in milliseconds for distributed shards",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for test CA only",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.accounts <= 300:
        raise ConfigurationError("ACCOUNT_COUNT_INVALID")
    if not 1 <= args.student_start <= 300 or args.student_start + args.accounts - 1 > 300:
        raise ConfigurationError("STUDENT_RANGE_INVALID")
    if args.timeout_seconds <= 0:
        raise ConfigurationError("TIMEOUT_INVALID")
    if args.start_at_epoch_ms is not None:
        delay_seconds = args.start_at_epoch_ms / 1000 - time.time()
        if delay_seconds > MAX_START_DELAY_SECONDS:
            raise ConfigurationError("START_TIME_TOO_FAR_IN_FUTURE")


async def _login_one(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    origin: str,
    start: asyncio.Event,
) -> RequestMetric:
    await start.wait()
    metric, _ = await authenticate(
        client,
        email=email,
        password=password,
        origin=origin,
    )
    return metric


async def run(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    validate_args(args)
    base_url = normalize_base_url(args.base_url)
    origin = normalize_base_url(args.origin) if args.origin else base_url
    password = read_password_file(args.password_file)
    clients = [
        client_for(
            base_url,
            timeout_seconds=args.timeout_seconds,
            verify_tls=not args.insecure,
        )
        for _ in range(args.accounts)
    ]
    try:
        start = asyncio.Event()
        tasks = [
            asyncio.create_task(
                _login_one(
                    client,
                    email=capacity_student_email(args.student_start + offset),
                    password=password,
                    origin=origin,
                    start=start,
                )
            )
            for offset, client in enumerate(clients)
        ]
        await asyncio.sleep(0)
        if args.start_at_epoch_ms is not None:
            delay_seconds = args.start_at_epoch_ms / 1000 - time.time()
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
        started = time.perf_counter()
        start.set()
        metrics = await asyncio.gather(*tasks)
        duration_seconds = time.perf_counter() - started
        summary = summarize_metrics(metrics, duration_seconds)
        accepted = summary["errors"] == 0
        report: dict[str, object] = {
            "status": "ok" if accepted else "error",
            "tool": "login_burst",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": {
                "base_url": base_url,
                "application_origin": origin,
                "api_prefix": "/api/v1",
            },
            "configuration": {
                "accounts": args.accounts,
                "student_start": args.student_start,
                "student_end": args.student_start + args.accounts - 1,
                "tls_verification": not args.insecure,
                "synchronized_start": args.start_at_epoch_ms is not None,
            },
            "workload": {
                "duration_seconds": round(duration_seconds, 3),
                **summary,
            },
            "acceptance": {
                "all_logins_must_succeed": True,
                "met": accepted,
            },
        }
        return report, 0 if accepted else 2
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report, exit_code = asyncio.run(run(args))
    except ConfigurationError as exc:
        report = {"status": "error", "tool": "login_burst", "error_code": exc.code}
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
