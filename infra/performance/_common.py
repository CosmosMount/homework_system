"""Shared, secret-safe helpers for isolated performance exercises."""

from __future__ import annotations

import math
import stat
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

API_PREFIX = "/api/v1/"


class ConfigurationError(ValueError):
    """Raised for a configuration problem that is safe to report by code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RequestMetric:
    stage: str
    latency_ms: float
    success: bool
    error_code: str | None = None


def read_password_file(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        raise ConfigurationError("PASSWORD_FILE_MUST_BE_ABSOLUTE")
    try:
        resolved = path.resolve(strict=True)
        file_stat = resolved.stat()
    except OSError as exc:
        raise ConfigurationError("PASSWORD_FILE_UNREADABLE") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise ConfigurationError("PASSWORD_FILE_NOT_REGULAR")
    if file_stat.st_mode & 0o077:
        raise ConfigurationError("PASSWORD_FILE_PERMISSIONS_TOO_OPEN")
    try:
        password = resolved.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError("PASSWORD_FILE_UNREADABLE") from exc
    if not password or "\n" in password or "\r" in password or len(password) > 128:
        raise ConfigurationError("PASSWORD_FILE_CONTENT_INVALID")
    return password


def normalize_base_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError("BASE_URL_INVALID")
    return raw_url.rstrip("/")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def summarize_metrics(
    metrics: list[RequestMetric], duration_seconds: float
) -> dict[str, Any]:
    successful = [metric for metric in metrics if metric.success]
    latencies = [metric.latency_ms for metric in metrics]
    errors = Counter(
        metric.error_code or "unknown_error" for metric in metrics if not metric.success
    )
    total = len(metrics)
    return {
        "total": total,
        "successful": len(successful),
        "errors": total - len(successful),
        "error_rate": round((total - len(successful)) / total, 6) if total else 1.0,
        "throughput_rps": round(total / duration_seconds, 3)
        if duration_seconds > 0
        else 0.0,
        "latency_ms": {
            "p50": _rounded(percentile(latencies, 0.50)),
            "p95": _rounded(percentile(latencies, 0.95)),
            "p99": _rounded(percentile(latencies, 0.99)),
            "max": _rounded(max(latencies) if latencies else None),
        },
        "error_codes": dict(sorted(errors.items())),
    }


def client_for(
    base_url: str,
    *,
    timeout_seconds: float,
    verify_tls: bool,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{base_url}{API_PREFIX}",
        follow_redirects=False,
        headers={"User-Agent": "pnx-isolated-performance/1"},
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        timeout=httpx.Timeout(timeout_seconds),
        trust_env=False,
        verify=verify_tls,
    )


async def authenticate(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    origin: str,
) -> tuple[RequestMetric, bool]:
    started = time.perf_counter()
    try:
        response = await client.post(
            "auth/login",
            headers={"Origin": origin},
            json={"email": email, "password": password},
        )
    except httpx.HTTPError:
        return RequestMetric(
            "login", (time.perf_counter() - started) * 1000, False, "network"
        ), False
    latency_ms = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        return RequestMetric(
            "login", latency_ms, False, f"http_{response.status_code}"
        ), False
    try:
        payload = response.json()
    except ValueError:
        return RequestMetric("login", latency_ms, False, "invalid_json"), False
    valid = isinstance(payload, dict) and isinstance(payload.get("user"), dict)
    return RequestMetric(
        "login", latency_ms, valid, None if valid else "invalid_payload"
    ), valid


def capacity_student_email(one_based_index: int) -> str:
    if not 1 <= one_based_index <= 300:
        raise ConfigurationError("STUDENT_INDEX_OUT_OF_RANGE")
    return f"capacity-student-{one_based_index:03d}@connect.hkust-gz.edu.cn"
