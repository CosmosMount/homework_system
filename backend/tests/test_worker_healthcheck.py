from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import DependencyUnavailableError
from app.worker_healthcheck import worker_is_healthy


@pytest.mark.asyncio
async def test_worker_healthcheck_returns_true_for_fresh_heartbeat() -> None:
    with patch("app.worker_healthcheck.HealthService.worker_health", new=AsyncMock()):
        assert await worker_is_healthy() is True


@pytest.mark.asyncio
async def test_worker_healthcheck_returns_false_for_unavailable_worker() -> None:
    unavailable = DependencyUnavailableError(field="worker", reason="STALE_HEARTBEAT")
    with patch(
        "app.worker_healthcheck.HealthService.worker_health",
        new=AsyncMock(side_effect=unavailable),
    ):
        assert await worker_is_healthy() is False
