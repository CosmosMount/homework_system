from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import AuthenticatedContextDependency, CsrfDependency, SessionDependency
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.users.direction_service import UserDirectionService
from app.users.schemas import SelfDirectionOptionsResponse, SelfDirectionRequest, UserResponse
from app.users.service import AuditContext

router = APIRouter(prefix="/users/me", tags=["users"])


def get_direction_service(request: Request, session: SessionDependency) -> UserDirectionService:
    return UserDirectionService(session, request.app.state.settings)


DirectionServiceDependency = Annotated[UserDirectionService, Depends(get_direction_service)]


@router.get("/direction-options", response_model=SelfDirectionOptionsResponse)
async def direction_options(
    service: DirectionServiceDependency,
    context: AuthenticatedContextDependency,
) -> SelfDirectionOptionsResponse:
    return await service.options(context)


@router.patch("/direction", response_model=UserResponse)
async def change_direction(
    payload: SelfDirectionRequest,
    request: Request,
    service: DirectionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.change(
        payload,
        audit=AuditContext(
            actor=context,
            request_id=current_request_id() or "unknown",
            ip_prefix=request_ip_prefix(request),
        ),
    )
