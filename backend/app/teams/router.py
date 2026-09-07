from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.config import Settings
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.teams.schemas import (
    AdminCaptainTransferRequest,
    AdminMemberAddRequest,
    AdminReasonRequest,
    AdminTeamListResponse,
    AutoAssignResponse,
    CaptainTransferRequest,
    InviteCodeRotatedResponse,
    OperationResponse,
    TeamCreatedResponse,
    TeamCreateRequest,
    TeamDirectoryResponse,
    TeamInvitationCreateRequest,
    TeamInvitationListResponse,
    TeamInvitationResponse,
    TeamJoinRequest,
    TeamProfilePage,
    TeamProfileResponse,
    TeamProfileUpsertRequest,
    TeamResponse,
)
from app.teams.service import TeamAuditContext, TeamService

router = APIRouter(tags=["teams"])


def get_team_service(request: Request, session: SessionDependency) -> TeamService:
    settings: Settings = request.app.state.settings
    return TeamService(session, settings)


TeamServiceDependency = Annotated[TeamService, Depends(get_team_service)]


def _audit_context(
    request: Request,
    context: AuthenticatedContextDependency,
) -> TeamAuditContext:
    return TeamAuditContext(
        actor=context,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/team-profiles", response_model=TeamProfilePage)
async def list_team_profiles(
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    query: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TeamProfilePage:
    return await service.profiles(context=context, query=query, page=page, page_size=page_size)


@router.get("/team-profiles/me", response_model=TeamProfileResponse | None)
async def get_my_team_profile(
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
) -> TeamProfileResponse | None:
    return await service.my_profile(context=context)


@router.put("/team-profiles/me", response_model=TeamProfileResponse)
async def upsert_my_team_profile(
    payload: TeamProfileUpsertRequest,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamProfileResponse:
    return await service.upsert_profile(payload, audit_context=_audit_context(request, context))


@router.get("/team-invitations", response_model=TeamInvitationListResponse)
async def list_team_invitations(
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
) -> TeamInvitationListResponse:
    return await service.invitations(context=context)


@router.post(
    "/team-invitations",
    response_model=TeamInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_invitation(
    payload: TeamInvitationCreateRequest,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamInvitationResponse:
    return await service.create_invitation(payload, audit_context=_audit_context(request, context))


@router.post("/team-invitations/{invitation_id}/accept", response_model=TeamResponse)
async def accept_team_invitation(
    invitation_id: UUID,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    response = await service.respond_to_invitation(
        invitation_id, accept=True, audit_context=_audit_context(request, context)
    )
    assert isinstance(response, TeamResponse)
    return response


@router.post("/team-invitations/{invitation_id}/decline", response_model=OperationResponse)
async def decline_team_invitation(
    invitation_id: UUID,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    response = await service.respond_to_invitation(
        invitation_id, accept=False, audit_context=_audit_context(request, context)
    )
    assert isinstance(response, OperationResponse)
    return response


@router.get("/teams", response_model=TeamDirectoryResponse)
async def list_public_teams(
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    query: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TeamDirectoryResponse:
    return await service.public_teams(
        context=context,
        query=query,
        page=page,
        page_size=page_size,
    )


@router.get("/teams/me", response_model=TeamResponse | None)
async def get_my_team(
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
) -> TeamResponse | None:
    return await service.my_team(context=context)


@router.post("/teams", response_model=TeamCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreateRequest,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamCreatedResponse:
    return await service.create_team(
        payload.name,
        audit_context=_audit_context(request, context),
    )


@router.post("/teams/join", response_model=TeamResponse)
async def join_team(
    payload: TeamJoinRequest,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.join_team(
        payload.invite_code,
        audit_context=_audit_context(request, context),
    )


@router.post("/teams/auto-assign", response_model=AutoAssignResponse)
async def auto_assign_team(
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> AutoAssignResponse:
    return await service.auto_assign(audit_context=_audit_context(request, context))


@router.post("/teams/{team_id}/invite-code/rotate", response_model=InviteCodeRotatedResponse)
async def rotate_team_invite_code(
    team_id: UUID,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> InviteCodeRotatedResponse:
    return await service.rotate_invite_code(
        team_id,
        audit_context=_audit_context(request, context),
    )


@router.delete("/teams/{team_id}/members/{user_id}", response_model=OperationResponse)
async def remove_team_member(
    team_id: UUID,
    user_id: UUID,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    return await service.remove_member(
        team_id,
        user_id,
        audit_context=_audit_context(request, context),
    )


@router.post("/teams/{team_id}/captain-transfer", response_model=TeamResponse)
async def transfer_team_captain(
    team_id: UUID,
    payload: CaptainTransferRequest,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.transfer_captain(
        team_id,
        payload,
        audit_context=_audit_context(request, context),
    )


@router.post("/teams/{team_id}/dissolve", response_model=OperationResponse)
async def dissolve_team(
    team_id: UUID,
    request: Request,
    service: TeamServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> OperationResponse:
    return await service.dissolve_team(
        team_id,
        audit_context=_audit_context(request, context),
    )


@router.get("/admin/teams", response_model=AdminTeamListResponse)
async def list_admin_teams(
    service: TeamServiceDependency,
    admin: AdminContextDependency,
    query: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminTeamListResponse:
    return await service.admin_teams(
        context=admin,
        query=query,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/teams/{team_id}", response_model=TeamResponse)
async def get_admin_team(
    team_id: UUID,
    service: TeamServiceDependency,
    admin: AdminContextDependency,
) -> TeamResponse:
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
    service: TeamServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.delete_admin_team(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/teams/{team_id}/members", response_model=TeamResponse)
async def admin_add_team_member(
    team_id: UUID,
    payload: AdminMemberAddRequest,
    request: Request,
    service: TeamServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_add_member(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.delete("/admin/teams/{team_id}/members/{user_id}", response_model=TeamResponse)
async def admin_remove_team_member(
    team_id: UUID,
    user_id: UUID,
    payload: AdminReasonRequest,
    request: Request,
    service: TeamServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_remove_member(
        team_id,
        user_id,
        payload,
        audit_context=_audit_context(request, admin),
    )


@router.post("/admin/teams/{team_id}/captain-transfer", response_model=TeamResponse)
async def admin_transfer_team_captain(
    team_id: UUID,
    payload: AdminCaptainTransferRequest,
    request: Request,
    service: TeamServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> TeamResponse:
    return await service.admin_transfer_captain(
        team_id,
        payload,
        audit_context=_audit_context(request, admin),
    )
