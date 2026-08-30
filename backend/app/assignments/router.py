from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.assignments.schemas import (
    AssignmentAdminPage,
    AssignmentAdminResponse,
    AssignmentCreateRequest,
    AssignmentDetailResponse,
    AssignmentExtensionRequest,
    AssignmentExtensionResponse,
    AssignmentPage,
    AssignmentPatchRequest,
    AssignmentSubmissionAdminPage,
    ExcellentSubmissionDetailResponse,
    ExcellentSubmissionSummaryResponse,
)
from app.assignments.service import (
    AssignmentAuditContext,
    AssignmentService,
)
from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id

router = APIRouter(tags=["assignments"])


def get_assignment_service(session: SessionDependency) -> AssignmentService:
    return AssignmentService(session)


AssignmentServiceDependency = Annotated[
    AssignmentService,
    Depends(get_assignment_service),
]


def _audit_context(
    request: Request,
    admin: AdminContextDependency,
) -> AssignmentAuditContext:
    return AssignmentAuditContext(
        actor=admin,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/assignments", response_model=AssignmentPage)
async def list_assignments(
    service: AssignmentServiceDependency,
    context: AuthenticatedContextDependency,
    assignment_status: Annotated[
        Literal["pending", "submitted", "closed", "all"] | None,
        Query(alias="status"),
    ] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AssignmentPage:
    return await service.list_student(
        context=context,
        page=page,
        page_size=page_size,
        status=None if assignment_status == "all" else assignment_status,
        query=query,
    )


@router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentDetailResponse,
)
async def get_assignment(
    assignment_id: UUID,
    service: AssignmentServiceDependency,
    context: AuthenticatedContextDependency,
) -> AssignmentDetailResponse:
    return await service.get_student(assignment_id, context=context)


@router.get(
    "/assignments/{assignment_id}/excellent-submissions",
    response_model=list[ExcellentSubmissionSummaryResponse],
)
async def list_excellent_submissions(
    assignment_id: UUID,
    service: AssignmentServiceDependency,
    context: AuthenticatedContextDependency,
) -> list[ExcellentSubmissionSummaryResponse]:
    return await service.list_excellent(assignment_id, context=context)


@router.get(
    "/assignments/{assignment_id}/excellent-submissions/{version_id}",
    response_model=ExcellentSubmissionDetailResponse,
)
async def get_excellent_submission(
    assignment_id: UUID,
    version_id: UUID,
    service: AssignmentServiceDependency,
    context: AuthenticatedContextDependency,
) -> ExcellentSubmissionDetailResponse:
    return await service.get_excellent(
        assignment_id,
        version_id,
        context=context,
    )


@router.get("/admin/assignments", response_model=AssignmentAdminPage)
async def list_admin_assignments(
    service: AssignmentServiceDependency,
    _admin: AdminContextDependency,
    assignment_status: Annotated[
        Literal["draft", "published", "closed", "archived"] | None,
        Query(alias="status"),
    ] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AssignmentAdminPage:
    return await service.list_admin(
        page=page,
        page_size=page_size,
        status=assignment_status,
        query=query,
    )


@router.post(
    "/admin/assignments",
    response_model=AssignmentAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    payload: AssignmentCreateRequest,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AssignmentAdminResponse:
    return await service.create_draft(
        payload,
        audit=_audit_context(request, admin),
    )


@router.get(
    "/admin/assignments/{assignment_id}",
    response_model=AssignmentAdminResponse,
)
async def get_admin_assignment(
    assignment_id: UUID,
    service: AssignmentServiceDependency,
    _admin: AdminContextDependency,
) -> AssignmentAdminResponse:
    return await service.get_admin(assignment_id)


@router.patch(
    "/admin/assignments/{assignment_id}",
    response_model=AssignmentAdminResponse,
)
async def patch_assignment(
    assignment_id: UUID,
    payload: AssignmentPatchRequest,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AssignmentAdminResponse:
    return await service.patch(
        assignment_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.delete(
    "/admin/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_assignment(
    assignment_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.remove(
        assignment_id,
        audit=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/assignments/{assignment_id}/publish",
    response_model=AssignmentAdminResponse,
)
async def publish_assignment(
    assignment_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
    _idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> AssignmentAdminResponse:
    return await service.publish(
        assignment_id,
        audit=_audit_context(request, admin),
    )


@router.post(
    "/admin/assignments/{assignment_id}/close",
    response_model=AssignmentAdminResponse,
)
async def close_assignment(
    assignment_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AssignmentAdminResponse:
    return await service.close(
        assignment_id,
        audit=_audit_context(request, admin),
    )


@router.post(
    "/admin/assignments/{assignment_id}/archive",
    response_model=AssignmentAdminResponse,
)
async def archive_assignment(
    assignment_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AssignmentAdminResponse:
    return await service.archive(
        assignment_id,
        audit=_audit_context(request, admin),
    )


@router.put(
    "/admin/assignments/{assignment_id}/extensions/{user_id}",
    response_model=AssignmentExtensionResponse,
)
async def put_assignment_extension(
    assignment_id: UUID,
    user_id: UUID,
    payload: AssignmentExtensionRequest,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> AssignmentExtensionResponse:
    return await service.put_extension(
        assignment_id,
        user_id,
        payload,
        audit=_audit_context(request, admin),
    )


@router.delete(
    "/admin/assignments/{assignment_id}/extensions/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_assignment_extension(
    assignment_id: UUID,
    user_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.delete_extension(
        assignment_id,
        user_id,
        audit=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/assignments/{assignment_id}/submissions",
    response_model=AssignmentSubmissionAdminPage,
)
async def list_assignment_submissions(
    assignment_id: UUID,
    service: AssignmentServiceDependency,
    _admin: AdminContextDependency,
    cohort_id: UUID | None = None,
    direction_id: UUID | None = None,
    submission_status: Literal["submitted", "unsubmitted"] | None = None,
    feedback_status: Literal["feedback", "no_feedback"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AssignmentSubmissionAdminPage:
    return await service.list_submissions_admin(
        assignment_id,
        page=page,
        page_size=page_size,
        cohort_id=cohort_id,
        direction_id=direction_id,
        submission_status=submission_status,
        feedback_status=feedback_status,
    )


@router.post(
    "/admin/assignments/{assignment_id}/excellent-submissions/{version_id}",
    response_model=ExcellentSubmissionSummaryResponse,
)
async def mark_excellent_submission(
    assignment_id: UUID,
    version_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> ExcellentSubmissionSummaryResponse:
    return await service.mark_excellent(
        assignment_id,
        version_id,
        audit=_audit_context(request, admin),
    )


@router.delete(
    "/admin/assignments/{assignment_id}/excellent-submissions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def unmark_excellent_submission(
    assignment_id: UUID,
    version_id: UUID,
    request: Request,
    service: AssignmentServiceDependency,
    admin: AdminContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.unmark_excellent(
        assignment_id,
        version_id,
        audit=_audit_context(request, admin),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
