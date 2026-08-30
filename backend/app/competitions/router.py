from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.competitions.schemas import (
    AdminCaptainTransferRequest,
    AdminCompetitionDetailResponse,
    AdminMemberAddRequest,
    AdminReasonRequest,
    AdminRegistrationItem,
    AdminRegistrationListResponse,
    AdminTeamDetailResponse,
    AdminTeamListResponse,
    AutoAssignResponse,
    CaptainTransferRequest,
    CompetitionCreateRequest,
    CompetitionDetailResponse,
    CompetitionListResponse,
    CompetitionPatchRequest,
    CompetitionTaskCreateRequest,
    CompetitionTaskPatchRequest,
    CompetitionTaskResponse,
    InviteCodeRotatedResponse,
    OperationResponse,
    RegistrationResponse,
    TeamCreatedResponse,
    TeamCreateRequest,
    TeamDirectoryResponse,
    TeamJoinRequest,
    TeamResponse,
)
from app.competitions.service import (
    CompetitionAuditContext,
    CompetitionService,
)
from app.core.config import Settings
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id

router = APIRouter(tags=["competitions"])


def get_competition_service(
    request: Request,
    session: SessionDependency,
) -> CompetitionService:
    settings: Settings = request.app.state.settings
    return CompetitionService(session, settings)


CompetitionServiceDependency = Annotated[
    CompetitionService,
    Depends(get_competition_service),
]


def _audit_context(
    request: Request,
    context: AuthenticatedContextDependency,
) -> CompetitionAuditContext:
    return CompetitionAuditContext(
        actor=context,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/competitions", response_model=CompetitionListResponse)
async def list_competitions(
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    competition_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CompetitionListResponse:
    return await service.list_competitions(
        context=context,
        page=page,
        page_size=page_size,
        status=competition_status,
        query=query,
    )


@router.get(
    "/competitions/{competition_id}",
    response_model=CompetitionDetailResponse,
)
async def get_competition(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
) -> CompetitionDetailResponse:
    return await service.get_competition(competition_id, context=context)


@router.post(
    "/competitions/{competition_id}/registration",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_for_competition(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> RegistrationResponse:
    return await service.register(
        competition_id,
        audit_context=_audit_context(request, context),
    )


@router.delete(
    "/competitions/{competition_id}/registration",
    response_model=OperationResponse,
)
async def withdraw_competition_registration(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    return await service.withdraw_registration(
        competition_id,
        audit_context=_audit_context(request, context),
    )


@router.get(
    "/competitions/{competition_id}/my-team",
    response_model=TeamResponse,
)
async def get_my_team(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
) -> TeamResponse:
    return await service.my_team(competition_id, context=context)


@router.get(
    "/competitions/{competition_id}/teams",
    response_model=TeamDirectoryResponse,
)
async def list_public_teams(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    query: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TeamDirectoryResponse:
    return await service.public_teams(
        competition_id, context=context, query=query, page=page, page_size=page_size
    )


@router.post(
    "/competitions/{competition_id}/auto-assign",
    response_model=AutoAssignResponse,
)
async def auto_assign_team(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> AutoAssignResponse:
    return await service.auto_assign(competition_id, audit_context=_audit_context(request, context))


@router.post(
    "/competitions/{competition_id}/teams",
    response_model=TeamCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    competition_id: UUID,
    payload: TeamCreateRequest,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamCreatedResponse:
    return await service.create_team(
        competition_id,
        payload.name,
        audit_context=_audit_context(request, context),
    )


@router.post(
    "/competitions/{competition_id}/teams/join",
    response_model=TeamResponse,
)
async def join_team(
    competition_id: UUID,
    payload: TeamJoinRequest,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.join_team(
        competition_id,
        payload.invite_code,
        audit_context=_audit_context(request, context),
    )


@router.post(
    "/teams/{team_id}/invite-code/rotate",
    response_model=InviteCodeRotatedResponse,
)
async def rotate_invite_code(
    team_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> InviteCodeRotatedResponse:
    return await service.rotate_invite_code(
        team_id,
        audit_context=_audit_context(request, context),
    )


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    response_model=OperationResponse,
)
async def remove_or_leave_team(
    team_id: UUID,
    user_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    return await service.remove_member(
        team_id,
        user_id,
        audit_context=_audit_context(request, context),
    )


@router.post(
    "/teams/{team_id}/captain-transfer",
    response_model=TeamResponse,
)
async def transfer_team_captain(
    team_id: UUID,
    payload: CaptainTransferRequest,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.transfer_captain(
        team_id,
        payload,
        audit_context=_audit_context(request, context),
    )


@router.post(
    "/teams/{team_id}/dissolve",
    response_model=OperationResponse,
)
async def dissolve_team(
    team_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    return await service.dissolve_team(
        team_id,
        audit_context=_audit_context(request, context),
    )


@router.get(
    "/competitions/{competition_id}/tasks/{task_id}",
    response_model=CompetitionTaskResponse,
)
async def get_competition_task(
    competition_id: UUID,
    task_id: UUID,
    service: CompetitionServiceDependency,
    context: AuthenticatedContextDependency,
) -> CompetitionTaskResponse:
    return await service.get_task(
        competition_id,
        task_id,
        context=context,
    )


@router.get(
    "/admin/competitions",
    response_model=CompetitionListResponse,
)
async def list_admin_competitions(
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    competition_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CompetitionListResponse:
    return await service.list_competitions(
        context=admin,
        page=page,
        page_size=page_size,
        status=competition_status,
        query=query,
        admin=True,
    )


@router.post(
    "/admin/competitions",
    response_model=CompetitionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_competition(
    payload: CompetitionCreateRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.create_competition(
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.get(
    "/admin/competitions/{competition_id}",
    response_model=AdminCompetitionDetailResponse,
)
async def get_admin_competition(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
) -> AdminCompetitionDetailResponse:
    return await service.admin_detail(competition_id, context=admin)


@router.patch(
    "/admin/competitions/{competition_id}",
    response_model=CompetitionDetailResponse,
)
async def patch_competition(
    competition_id: UUID,
    payload: CompetitionPatchRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.patch_competition(
        competition_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/competitions/{competition_id}/publish",
    response_model=CompetitionDetailResponse,
)
async def publish_competition(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.publish_competition(
        competition_id,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/competitions/{competition_id}/close-registration",
    response_model=CompetitionDetailResponse,
)
async def close_competition_registration(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.close_registration(
        competition_id,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/competitions/{competition_id}/close-submissions",
    response_model=CompetitionDetailResponse,
)
async def close_competition_submissions(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.close_submissions(
        competition_id,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/competitions/{competition_id}/archive",
    response_model=CompetitionDetailResponse,
)
async def archive_competition(
    competition_id: UUID,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionDetailResponse:
    return await service.archive_competition(
        competition_id,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/competitions/{competition_id}/tasks",
    response_model=CompetitionTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_competition_task(
    competition_id: UUID,
    payload: CompetitionTaskCreateRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionTaskResponse:
    return await service.create_task(
        competition_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.patch(
    "/admin/competition-tasks/{task_id}",
    response_model=CompetitionTaskResponse,
)
async def patch_competition_task(
    task_id: UUID,
    payload: CompetitionTaskPatchRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> CompetitionTaskResponse:
    return await service.patch_task(
        task_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.get(
    "/admin/competitions/{competition_id}/teams",
    response_model=AdminTeamListResponse,
)
async def list_admin_teams(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
) -> AdminTeamListResponse:
    return await service.admin_teams(competition_id, context=admin)


@router.get(
    "/admin/competitions/{competition_id}/registrations",
    response_model=AdminRegistrationListResponse,
)
async def list_admin_registrations(
    competition_id: UUID,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
) -> AdminRegistrationListResponse:
    return await service.admin_registrations(competition_id, context=admin)


@router.post(
    "/admin/competitions/{competition_id}/registrations/{user_id}/disqualify",
    response_model=AdminRegistrationItem,
)
async def disqualify_admin_registration(
    competition_id: UUID,
    user_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AdminRegistrationItem:
    return await service.disqualify_registration(
        competition_id,
        user_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.get(
    "/admin/teams/{team_id}",
    response_model=AdminTeamDetailResponse,
)
async def get_admin_team(
    team_id: UUID,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
) -> AdminTeamDetailResponse:
    return await service.admin_team(team_id, context=admin)


@router.delete(
    "/admin/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_admin_team(
    team_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.delete_admin_team(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/teams/{team_id}/members",
    response_model=TeamResponse,
)
async def admin_add_team_member(
    team_id: UUID,
    payload: AdminMemberAddRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_add_member(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.delete(
    "/admin/teams/{team_id}/members/{user_id}",
    response_model=TeamResponse,
)
async def admin_remove_team_member(
    team_id: UUID,
    user_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_remove_member(
        team_id,
        user_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/teams/{team_id}/captain-transfer",
    response_model=TeamResponse,
)
async def admin_transfer_team_captain(
    team_id: UUID,
    payload: AdminCaptainTransferRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_transfer_captain(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/teams/{team_id}/waive-min-size",
    response_model=TeamResponse,
)
async def waive_team_min_size(
    team_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.waive_min_size(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.post(
    "/admin/teams/{team_id}/disqualify",
    response_model=TeamResponse,
)
async def disqualify_team(
    team_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: CompetitionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.disqualify_team(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )
