from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.intentions.schemas import (
    AdminIntentionSurvey,
    AdminIntentionSurveyPage,
    IntentionQrResponse,
    IntentionResponseRequest,
    IntentionResponseResponse,
    IntentionStatsResponse,
    IntentionSurveyCreateRequest,
    IntentionSurveyDetail,
    IntentionSurveyPage,
    IntentionSurveyPatchRequest,
)
from app.intentions.service import IntentionAuditContext, IntentionService

router = APIRouter(tags=["intentions"])


def get_intention_service(session: SessionDependency, request: Request) -> IntentionService:
    return IntentionService(session, request.app.state.settings)


IntentionServiceDependency = Annotated[IntentionService, Depends(get_intention_service)]


def _audit_context(
    request: Request, context: AuthenticatedContextDependency
) -> IntentionAuditContext:
    return IntentionAuditContext(
        actor=context,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/intentions", response_model=IntentionSurveyPage)
async def list_intentions(
    service: IntentionServiceDependency,
    context: AuthenticatedContextDependency,
) -> IntentionSurveyPage:
    return await service.list_student(context=context)


@router.get("/intentions/{survey_id}", response_model=IntentionSurveyDetail)
async def get_intention(
    survey_id: UUID,
    service: IntentionServiceDependency,
    context: AuthenticatedContextDependency,
    token: Annotated[str | None, Query(max_length=256)] = None,
) -> IntentionSurveyDetail:
    return await service.student_detail(survey_id, context=context, token=token)


@router.put("/intentions/{survey_id}/response", response_model=IntentionResponseResponse)
async def submit_intention_response(
    survey_id: UUID,
    payload: IntentionResponseRequest,
    request: Request,
    service: IntentionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> IntentionResponseResponse:
    return await service.submit_response(
        survey_id, payload, audit_context=_audit_context(request, context)
    )


@router.get("/admin/intentions", response_model=AdminIntentionSurveyPage)
async def list_admin_intentions(
    service: IntentionServiceDependency,
    context: AdminContextDependency,
) -> AdminIntentionSurveyPage:
    return await service.list_admin(context=context)


@router.post(
    "/admin/intentions", response_model=AdminIntentionSurvey, status_code=status.HTTP_201_CREATED
)
async def create_admin_intention(
    payload: IntentionSurveyCreateRequest,
    request: Request,
    service: IntentionServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AdminIntentionSurvey:
    return await service.create(payload, audit_context=_audit_context(request, context))


@router.patch("/admin/intentions/{survey_id}", response_model=AdminIntentionSurvey)
async def patch_admin_intention(
    survey_id: UUID,
    payload: IntentionSurveyPatchRequest,
    request: Request,
    service: IntentionServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AdminIntentionSurvey:
    return await service.patch(survey_id, payload, audit_context=_audit_context(request, context))


@router.get("/admin/intentions/{survey_id}/stats", response_model=IntentionStatsResponse)
async def intention_stats(
    survey_id: UUID,
    service: IntentionServiceDependency,
    context: AdminContextDependency,
) -> IntentionStatsResponse:
    return await service.stats(survey_id, context=context)


@router.post("/admin/intentions/{survey_id}/qr-token", response_model=IntentionQrResponse)
async def generate_intention_qr_token(
    survey_id: UUID,
    request: Request,
    service: IntentionServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> IntentionQrResponse:
    return await service.qr_token(survey_id, audit_context=_audit_context(request, context))


@router.post("/admin/intentions/{survey_id}/{action}", response_model=AdminIntentionSurvey)
async def transition_admin_intention(
    survey_id: UUID,
    action: Literal["open", "closed", "archived"],
    request: Request,
    service: IntentionServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AdminIntentionSurvey:
    return await service.transition(
        survey_id, action, audit_context=_audit_context(request, context)
    )
