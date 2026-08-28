#!/usr/bin/env python3
"""Run an isolated concurrent read workload against the capacity dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
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
    read_password_file,
    summarize_metrics,
)

QueryValue = str | int | float | bool | None

ENDPOINTS: tuple[tuple[str, str, dict[str, QueryValue]], ...] = (
    ("dashboard", "dashboard", {}),
    ("notifications", "notifications", {"status": "unread", "page_size": 20}),
    ("assignments", "assignments", {"status": "all", "page_size": 20}),
    ("competitions", "competitions", {"page_size": 20}),
)
EXPECTED_KEYS: dict[str, set[str]] = {
    "dashboard": {"current_user", "unread_count", "assignments", "competitions"},
    "notifications": {"items", "total"},
    "assignments": {"items", "total"},
    "competitions": {"items", "total"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Target origin, without /api/v1")
    parser.add_argument(
        "--origin",
        help="Application Origin header when it differs from the container target",
    )
    parser.add_argument("--password-file", required=True, help="Absolute mode-0600 password file")
    parser.add_argument("--sessions", type=int, default=100)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--student-start", type=int, default=1)
    parser.add_argument("--login-interval-ms", type=int, default=220)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification for test CA only",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.sessions <= 300:
        raise ConfigurationError("SESSION_COUNT_INVALID")
    if not 1 <= args.student_start <= 300 or args.student_start + args.sessions - 1 > 300:
        raise ConfigurationError("STUDENT_RANGE_INVALID")
    if args.rounds < 1:
        raise ConfigurationError("ROUND_COUNT_INVALID")
    if args.login_interval_ms < 0:
        raise ConfigurationError("LOGIN_INTERVAL_INVALID")
    if args.timeout_seconds <= 0 or args.max_p95_ms <= 0:
        raise ConfigurationError("TIMEOUT_OR_THRESHOLD_INVALID")
    if not 0 < args.max_error_rate <= 1:
        raise ConfigurationError("ERROR_RATE_THRESHOLD_INVALID")


async def request_endpoint(
    client: httpx.AsyncClient,
    *,
    label: str,
    path: str,
    params: dict[str, QueryValue],
) -> RequestMetric:
    started = time.perf_counter()
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPError:
        return RequestMetric(label, (time.perf_counter() - started) * 1000, False, "network")
    latency_ms = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        return RequestMetric(label, latency_ms, False, f"http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        return RequestMetric(label, latency_ms, False, "invalid_json")
    if not isinstance(payload, dict) or not EXPECTED_KEYS[label] <= payload.keys():
        return RequestMetric(label, latency_ms, False, "invalid_payload")
    return RequestMetric(label, latency_ms, True)


async def read_worker(
    client: httpx.AsyncClient,
    *,
    worker_index: int,
    rounds: int,
    start: asyncio.Event,
) -> list[RequestMetric]:
    await start.wait()
    metrics: list[RequestMetric] = []
    for round_index in range(rounds):
        rotation = (worker_index + round_index) % len(ENDPOINTS)
        ordered = ENDPOINTS[rotation:] + ENDPOINTS[:rotation]
        for label, path, params in ordered:
            metrics.append(await request_endpoint(client, label=label, path=path, params=params))
    return metrics


def _by_endpoint(metrics: list[RequestMetric], duration_seconds: float) -> dict[str, Any]:
    grouped: defaultdict[str, list[RequestMetric]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.stage].append(metric)
    return {label: summarize_metrics(grouped[label], duration_seconds) for label, _, _ in ENDPOINTS}


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    validate_args(args)
    base_url = normalize_base_url(args.base_url)
    origin = normalize_base_url(args.origin) if args.origin else base_url
    password = read_password_file(args.password_file)
    clients: list[httpx.AsyncClient] = []
    login_metrics: list[RequestMetric] = []
    login_started = time.perf_counter()
    try:
        for offset in range(args.sessions):
            client = client_for(
                base_url,
                timeout_seconds=args.timeout_seconds,
                verify_tls=not args.insecure,
            )
            clients.append(client)
            metric, valid = await authenticate(
                client,
                email=capacity_student_email(args.student_start + offset),
                password=password,
                origin=origin,
            )
            login_metrics.append(metric)
            if not valid:
                break
            if offset + 1 < args.sessions and args.login_interval_ms:
                await asyncio.sleep(args.login_interval_ms / 1000)
        login_duration = time.perf_counter() - login_started
        if len(clients) != args.sessions or any(not metric.success for metric in login_metrics):
            report = {
                "status": "error",
                "tool": "read_load",
                "generated_at": datetime.now(UTC).isoformat(),
                "error_code": "AUTHENTICATED_SESSION_SETUP_FAILED",
                "authentication": summarize_metrics(login_metrics, login_duration),
            }
            return report, 2

        start = asyncio.Event()
        tasks = [
            asyncio.create_task(
                read_worker(
                    client,
                    worker_index=index,
                    rounds=args.rounds,
                    start=start,
                )
            )
            for index, client in enumerate(clients)
        ]
        await asyncio.sleep(0)
        workload_started = time.perf_counter()
        start.set()
        nested_metrics = await asyncio.gather(*tasks)
        duration_seconds = time.perf_counter() - workload_started
        metrics = [metric for worker_metrics in nested_metrics for metric in worker_metrics]
        summary = summarize_metrics(metrics, duration_seconds)
        p95 = summary["latency_ms"]["p95"]
        threshold_met = (
            p95 is not None
            and p95 < args.max_p95_ms
            and summary["error_rate"] < args.max_error_rate
        )
        report = {
            "status": "ok" if threshold_met else "error",
            "tool": "read_load",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": {
                "base_url": base_url,
                "application_origin": origin,
                "api_prefix": "/api/v1",
            },
            "configuration": {
                "independent_sessions": args.sessions,
                "rounds": args.rounds,
                "planned_requests": args.sessions * args.rounds * len(ENDPOINTS),
                "tls_verification": not args.insecure,
            },
            "authentication": summarize_metrics(login_metrics, login_duration),
            "workload": {
                "duration_seconds": round(duration_seconds, 3),
                **summary,
                "by_endpoint": _by_endpoint(metrics, duration_seconds),
            },
            "acceptance": {
                "p95_must_be_below_ms": args.max_p95_ms,
                "error_rate_must_be_below": args.max_error_rate,
                "met": threshold_met,
            },
        }
        return report, 0 if threshold_met else 2
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report, exit_code = asyncio.run(run(args))
    except ConfigurationError as exc:
        report = {"status": "error", "tool": "read_load", "error_code": exc.code}
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
