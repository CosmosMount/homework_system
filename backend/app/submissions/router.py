from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.submissions.schemas import (
    FeedbackPutRequest,
    FeedbackResponse,
    SubmissionResponse,
    SubmissionVersionCreatedResponse,
    SubmissionVersionCreateRequest,
    SubmissionVersionResponse,
)
from app.submissions.service import (
    SubmissionAuditContext,
    SubmissionService,
)

router = APIRouter(tags=["submissions"])


def get_submission_service(session: SessionDependency) -> SubmissionService:
    return SubmissionService(session)


SubmissionServiceDependency = Annotated[
    SubmissionService,
    Depends(get_submission_service),
]


def _audit_context(
    request: Request,
    admin: AdminContextDependency,
) -> SubmissionAuditContext:
    return SubmissionAuditContext(
        actor=admin,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.post(
    "/assignments/{assignment_id}/submission-versions",
    response_model=SubmissionVersionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment_submission_version(
    assignment_id: UUID,
    payload: SubmissionVersionCreateRequest,
    request: Request,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> SubmissionVersionCreatedResponse:
    return await service.create_assignment_version(
        assignment_id,
        payload,
        context=context,
        idempotency_key=idempotency_key,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get(
    "/assignments/{assignment_id}/submission",
    response_model=SubmissionResponse,
)
async def get_assignment_submission(
    assignment_id: UUID,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
) -> SubmissionResponse:
    return await service.get_assignment_submission(
        assignment_id,
        context=context,
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: UUID,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
) -> SubmissionResponse:
    return await service.get_submission(submission_id, context=context)


@router.get(
    "/submissions/{submission_id}/versions/{version_id}",
    response_model=SubmissionVersionResponse,
)
async def get_submission_version(
    submission_id: UUID,
    version_id: UUID,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
) -> SubmissionVersionResponse:
    return await service.get_version(
        submission_id,
        version_id,
        context=context,
    )


@router.put(
    "/admin/submissions/{submission_id}/versions/{version_id}/feedback",
    response_model=FeedbackResponse,
)
async def put_submission_feedback(
    submission_id: UUID,
    version_id: UUID,
    payload: FeedbackPutRequest,
    request: Request,
    service: SubmissionServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> FeedbackResponse:
    return await service.put_feedback(
        submission_id,
        version_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.post(
    "/competitions/{competition_id}/tasks/{task_id}/submission-versions",
    response_model=SubmissionVersionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_competition_submission_version(
    competition_id: UUID,
    task_id: UUID,
    payload: SubmissionVersionCreateRequest,
    request: Request,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> SubmissionVersionCreatedResponse:
    return await service.create_competition_version(
        competition_id,
        task_id,
        payload,
        context=context,
        idempotency_key=idempotency_key,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get(
    "/competitions/{competition_id}/tasks/{task_id}/submission",
    response_model=SubmissionResponse,
)
async def get_competition_submission(
    competition_id: UUID,
    task_id: UUID,
    service: SubmissionServiceDependency,
    context: AuthenticatedContextDependency,
) -> SubmissionResponse:
    return await service.get_competition_submission(
        competition_id,
        task_id,
        context=context,
    )
