from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import get_session
from app.health.repository import HealthRepository
from app.health.schemas import LiveHealthResponse, ReadyHealthResponse, WorkerHealthResponse
from app.health.service import HealthService

router = APIRouter(prefix="/health", tags=["health"])


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_health_service(session: SessionDependency) -> HealthService:
    settings = get_settings()
    return HealthService(
        HealthRepository(session),
        worker_name=settings.worker_name,
        worker_stale_after_seconds=settings.worker_stale_after_seconds,
    )


HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


@router.get("/live", response_model=LiveHealthResponse)
async def live() -> LiveHealthResponse:
    return LiveHealthResponse()


@router.get("/ready", response_model=ReadyHealthResponse)
async def ready(service: HealthServiceDependency) -> ReadyHealthResponse:
    return await service.readiness()


@router.get("/worker", response_model=WorkerHealthResponse)
async def worker(service: HealthServiceDependency) -> WorkerHealthResponse:
    return await service.worker_health()
