from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.knowledge.schemas import (
    KnowledgeAdminResponse,
    KnowledgeDocumentResponse,
    KnowledgeOverviewResponse,
    KnowledgeSyncCreatedResponse,
)
from app.knowledge.service import KnowledgeAuditContext, KnowledgeService

router = APIRouter(tags=["knowledge"])


def get_knowledge_service(
    session: SessionDependency,
    request: Request,
) -> KnowledgeService:
    return KnowledgeService(session, request.app.state.settings)


KnowledgeServiceDependency = Annotated[KnowledgeService, Depends(get_knowledge_service)]


@router.get("/knowledge", response_model=KnowledgeOverviewResponse)
async def knowledge_overview(
    service: KnowledgeServiceDependency,
    _context: AuthenticatedContextDependency,
) -> KnowledgeOverviewResponse:
    return await service.overview()


@router.get(
    "/knowledge/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
)
async def knowledge_document(
    document_id: UUID,
    service: KnowledgeServiceDependency,
    _context: AuthenticatedContextDependency,
) -> KnowledgeDocumentResponse:
    return await service.document(document_id)


@router.get("/knowledge/assets/{asset_id}/content", response_model=None)
async def knowledge_asset(
    asset_id: UUID,
    service: KnowledgeServiceDependency,
    _context: AuthenticatedContextDependency,
) -> RedirectResponse:
    return RedirectResponse(
        await service.asset_url(asset_id),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={
            "cache-control": "private, no-store",
            "referrer-policy": "no-referrer",
        },
    )


@router.get("/admin/knowledge", response_model=KnowledgeAdminResponse)
async def knowledge_admin_status(
    service: KnowledgeServiceDependency,
    context: AdminContextDependency,
) -> KnowledgeAdminResponse:
    return await service.admin_status(context=context)


@router.post(
    "/admin/knowledge/sync",
    response_model=KnowledgeSyncCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_knowledge_sync(
    request: Request,
    service: KnowledgeServiceDependency,
    context: AdminContextDependency,
    _csrf: CsrfDependency,
) -> KnowledgeSyncCreatedResponse:
    return await service.trigger_sync(
        audit_context=KnowledgeAuditContext(
            actor=context,
            request_id=current_request_id() or "unknown",
            ip_prefix=request_ip_prefix(request),
        )
    )
