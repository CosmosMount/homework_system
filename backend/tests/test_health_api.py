from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.health.router import get_health_service
from app.health.schemas import ReadyHealthResponse
from app.main import create_app


class HealthyService:
    async def readiness(self) -> ReadyHealthResponse:
        return ReadyHealthResponse()


class UnavailableService:
    async def readiness(self) -> ReadyHealthResponse:
        raise DependencyUnavailableError(field="postgresql", reason="UNAVAILABLE")


@pytest.fixture
def app() -> FastAPI:
    application = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    application.dependency_overrides[get_health_service] = HealthyService
    return application


@pytest.mark.asyncio
async def test_live_health_returns_request_id(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_valid_request_id_is_preserved(app: FastAPI) -> None:
    request_id = "0196d1a0-4b8e-7c7a-a5cf-3d26b577d7d8"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/health/live",
            headers={"X-Request-ID": request_id},
        )

    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.asyncio
async def test_readiness_uses_unified_dependency_error(app: FastAPI) -> None:
    app.dependency_overrides[get_health_service] = UnavailableService
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/ready")

    payload = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert payload["error"]["details"] == [{"field": "postgresql", "reason": "UNAVAILABLE"}]
    UUID(payload["error"]["request_id"])
