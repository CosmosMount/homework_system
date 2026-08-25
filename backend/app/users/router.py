from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.dependencies import AdminContextDependency, CsrfDependency, SessionDependency
from app.core.config import Settings
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.users.schemas import (
    CohortCreateRequest,
    CohortPatchRequest,
    CohortResponse,
    DirectionCreateRequest,
    DirectionPatchRequest,
    DirectionResponse,
    UserDisableRequest,
    UserPage,
    UserPatchRequest,
    UserResponse,
    UserRestoreRequest,
    UserRoleRequest,
)
from app.users.service import AuditContext, UserAdministrationService

router = APIRouter(prefix="/admin", tags=["administration"])


def get_user_administration_service(
    request: Request,
    session: SessionDependency,
) -> UserAdministrationService:
    settings: Settings = request.app.state.settings
    return UserAdministrationService(session, settings)


UserAdministrationServiceDependency = Annotated[
    UserAdministrationService,
    Depends(get_user_administration_service),
]


def _audit_context(request: Request, admin: AdminContextDependency) -> AuditContext:
    return AuditContext(
        actor=admin,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/users", response_model=UserPage)
async def list_users(
    service: UserAdministrationServiceDependency,
    _admin: AdminContextDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    account_status: Annotated[
        Literal["pending_email", "active", "disabled"] | None,
        Query(alias="status"),
    ] = None,
    role: Literal["student", "admin"] | None = None,
    cohort_id: UUID | None = None,
    direction_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> UserPage:
    return await service.list_users(
        page=page,
        page_size=page_size,
        status=account_status,
        role=role,
        cohort_id=cohort_id,
        direction_id=direction_id,
        search=search,
    )


@router.post("/users/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: UUID,
    payload: UserDisableRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.disable_user(
        user_id,
        reason=payload.reason,
        audit=_audit_context(request, admin),
    )


@router.post("/users/{user_id}/restore", response_model=UserResponse)
async def restore_user(
    user_id: UUID,
    payload: UserRestoreRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.restore_user(
        user_id,
        reason=payload.reason,
        audit=_audit_context(request, admin),
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def patch_user(
    user_id: UUID,
    payload: UserPatchRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.patch_user(
        user_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.post("/users/{user_id}/role", response_model=UserResponse)
async def change_role(
    user_id: UUID,
    payload: UserRoleRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.change_role(
        user_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.get("/cohorts", response_model=list[CohortResponse])
async def list_cohorts(
    service: UserAdministrationServiceDependency,
    _admin: AdminContextDependency,
) -> list[CohortResponse]:
    return await service.list_cohorts()


@router.post(
    "/cohorts",
    response_model=CohortResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cohort(
    payload: CohortCreateRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CohortResponse:
    return await service.create_cohort(
        payload,
        audit=_audit_context(request, admin),
    )


@router.patch("/cohorts/{cohort_id}", response_model=CohortResponse)
async def patch_cohort(
    cohort_id: UUID,
    payload: CohortPatchRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CohortResponse:
    return await service.patch_cohort(
        cohort_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.get("/directions", response_model=list[DirectionResponse])
async def list_directions(
    service: UserAdministrationServiceDependency,
    _admin: AdminContextDependency,
) -> list[DirectionResponse]:
    return await service.list_directions()


@router.post(
    "/directions",
    response_model=DirectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_direction(
    payload: DirectionCreateRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> DirectionResponse:
    return await service.create_direction(
        payload,
        audit=_audit_context(request, admin),
    )


@router.patch("/directions/{direction_id}", response_model=DirectionResponse)
async def patch_direction(
    direction_id: UUID,
    payload: DirectionPatchRequest,
    request: Request,
    service: UserAdministrationServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> DirectionResponse:
    return await service.patch_direction(
        direction_id,
        payload,
        audit=_audit_context(request, admin),
    )
