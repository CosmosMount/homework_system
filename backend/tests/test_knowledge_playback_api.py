from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_authenticated_context
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.knowledge.router import get_knowledge_service
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_playback_requires_login_and_redirects_without_cache(authenticated: bool) -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    asset_id = uuid4()
    service = SimpleNamespace(asset_url=AsyncMock(return_value="/storage/signed-video"))
    app.dependency_overrides[get_knowledge_service] = lambda: service

    def context() -> SimpleNamespace:
        if not authenticated:
            raise ApplicationError(
                status_code=401, code="AUTHENTICATION_REQUIRED", message="请登录"
            )
        return SimpleNamespace()

    app.dependency_overrides[get_authenticated_context] = context
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/v1/knowledge/assets/{asset_id}/content?playback=true")
    if authenticated:
        assert response.status_code == 307
        assert response.headers["location"] == "/storage/signed-video"
        assert response.headers["cache-control"] == "private, no-store"
        service.asset_url.assert_awaited_once_with(asset_id, playback=True)
    else:
        assert response.status_code == 401
        service.asset_url.assert_not_awaited()
