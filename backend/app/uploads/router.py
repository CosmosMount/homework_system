from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.auth.dependencies import (
    AuthenticatedContextDependency,
    CsrfDependency,
    SessionDependency,
)
from app.core.config import Settings
from app.uploads.object_store import MinioObjectStore
from app.uploads.schemas import (
    CompletedFileResponse,
    CompleteUploadRequest,
    DownloadUrlResponse,
    PresignPartsRequest,
    PresignPartsResponse,
    UploadInitRequest,
    UploadSessionResponse,
)
from app.uploads.service import UploadService

router = APIRouter(tags=["uploads"])


def get_upload_service(
    request: Request,
    session: SessionDependency,
) -> UploadService:
    settings: Settings = request.app.state.settings
    return UploadService(
        session,
        settings,
        object_store=MinioObjectStore(settings),
    )


UploadServiceDependency = Annotated[UploadService, Depends(get_upload_service)]


@router.post(
    "/uploads/init",
    response_model=UploadSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initialize_upload(
    payload: UploadInitRequest,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> UploadSessionResponse:
    return await service.initialize(
        payload,
        context=context,
        idempotency_key=idempotency_key,
    )


@router.get("/uploads/{upload_id}", response_model=UploadSessionResponse)
async def get_upload(
    upload_id: UUID,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
) -> UploadSessionResponse:
    return await service.get(upload_id, context=context)


@router.post(
    "/uploads/{upload_id}/parts/presign",
    response_model=PresignPartsResponse,
)
async def presign_upload_parts(
    upload_id: UUID,
    payload: PresignPartsRequest,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> PresignPartsResponse:
    return await service.presign(
        upload_id,
        part_numbers=payload.part_numbers,
        context=context,
    )


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=CompletedFileResponse,
)
async def complete_upload(
    upload_id: UUID,
    payload: CompleteUploadRequest,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
    _idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> CompletedFileResponse:
    return await service.complete(upload_id, payload, context=context)


@router.delete(
    "/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def abort_upload(
    upload_id: UUID,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> Response:
    await service.abort(upload_id, context=context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/files/{file_id}/download-url",
    response_model=DownloadUrlResponse,
)
async def create_download_url(
    file_id: UUID,
    service: UploadServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> DownloadUrlResponse:
    return await service.download_url(file_id, context=context)
