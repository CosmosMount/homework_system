from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_authenticated_context
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.main import create_app
from app.users.direction_router import get_direction_service


@pytest.mark.asyncio
async def test_anonymous_direction_read_and_write_are_rejected() -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    service = SimpleNamespace(options=AsyncMock(), change=AsyncMock())
    app.dependency_overrides[get_direction_service] = lambda: service

    def anonymous() -> None:
        raise ApplicationError(status_code=401, code="AUTHENTICATION_REQUIRED", message="请登录")

    app.dependency_overrides[get_authenticated_context] = anonymous
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/api/v1/users/me/direction-options")).status_code == 401
        response = await client.patch(
            "/api/v1/users/me/direction", json={"direction_id": str(uuid4()), "revision": 1}
        )
    assert response.status_code == 401
    service.change.assert_not_awaited()
    service.options.assert_not_awaited()


@pytest.mark.asyncio
async def test_direction_write_requires_real_csrf_dependency() -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    service = SimpleNamespace(change=AsyncMock())
    app.dependency_overrides[get_direction_service] = lambda: service
    app.dependency_overrides[get_authenticated_context] = lambda: cast(Any, SimpleNamespace())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.patch(
            "/api/v1/users/me/direction", json={"direction_id": str(uuid4()), "revision": 1}
        )
    assert response.status_code == 403
    service.change.assert_not_awaited()
