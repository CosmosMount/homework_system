from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import AuthenticatedContextDependency, CsrfDependency, SessionDependency
from app.core.network import request_ip_prefix
from app.core.request_context import current_request_id
from app.materials.schemas import (
    MaterialCreateRequest,
    MaterialCreateResponse,
    MaterialDetail,
    MaterialPage,
    MaterialScanRequest,
    MaterialScanResponse,
    MaterialScanView,
    MaterialTechGroup,
)
from app.materials.service import MAX_RETURN_PHOTO_BYTES, MaterialService
from app.uploads.object_store import MinioObjectStore

router = APIRouter(tags=["materials"])


def get_service(request: Request, session: SessionDependency) -> MaterialService:
    return MaterialService(session, MinioObjectStore(request.app.state.settings))


ServiceDependency = Annotated[MaterialService, Depends(get_service)]


def _audit(request: Request) -> dict[str, str]:
    return {
        "request_id": current_request_id() or "unknown",
        "ip_prefix": request_ip_prefix(request),
    }


@router.get("/materials", response_model=MaterialPage)
async def list_materials(
    service: ServiceDependency,
    _context: AuthenticatedContextDependency,
    query: Annotated[str, Query(max_length=200)] = "",
    tech_group: MaterialTechGroup | None = None,
    status_filter: Annotated[Literal["AVAILABLE", "IN_USE"] | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
) -> MaterialPage:
    return await service.list_materials(
        query=query, tech_group=tech_group, status=status_filter, page=page
    )


@router.post("/materials", response_model=MaterialCreateResponse, status_code=201)
async def create_material(
    payload: MaterialCreateRequest,
    request: Request,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> MaterialCreateResponse:
    return await service.create(context, payload, **_audit(request))


@router.get("/materials/scan/{qr_token}", response_model=MaterialScanView)
async def scan_view(
    qr_token: UUID,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
) -> MaterialScanView:
    return await service.scan_view(qr_token, context)


@router.post("/materials/scan", response_model=MaterialScanResponse)
async def checkout_material(
    payload: MaterialScanRequest,
    request: Request,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> MaterialScanResponse:
    return await service.checkout(context, payload, **_audit(request))


@router.post("/materials/scan/return", response_model=MaterialScanResponse)
async def return_material(
    request: Request,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
    qr_token: Annotated[UUID, Header(alias="X-Material-Qr-Token")],
    operation: Annotated[Literal["RETURN", "RECLAIM"], Header(alias="X-Material-Operation")],
    expected_active_loan_id: Annotated[UUID, Header(alias="X-Material-Loan-Id")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> MaterialScanResponse:
    payload = MaterialScanRequest(
        qr_token=qr_token,
        operation=operation,
        expected_active_loan_id=expected_active_loan_id,
        idempotency_key=idempotency_key,
    )
    photo = bytearray()
    async for chunk in request.stream():
        photo.extend(chunk)
        if len(photo) > MAX_RETURN_PHOTO_BYTES:
            break
    return await service.return_material(
        context,
        payload,
        photo=bytes(photo),
        declared_mime=request.headers.get("content-type", ""),
        **_audit(request),
    )


@router.get("/materials/loans/{loan_id}/photo")
async def material_return_photo(
    loan_id: UUID,
    service: ServiceDependency,
    _context: AuthenticatedContextDependency,
) -> RedirectResponse:
    return RedirectResponse(
        await service.photo_url(loan_id),
        status_code=307,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/materials/{material_id}", response_model=MaterialDetail)
async def material_detail(
    material_id: UUID,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
) -> MaterialDetail:
    return await service.detail(material_id, context)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: UUID,
    request: Request,
    service: ServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.delete(context, material_id, **_audit(request))
    return Response(status_code=204)
