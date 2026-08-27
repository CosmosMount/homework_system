from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

KnowledgeRunStatus = Literal["pending", "running", "succeeded", "failed"]


class KnowledgeSnapshotMetadata(BaseModel):
    run_id: UUID
    synced_at: datetime
    source_url: str
    document_count: int
    asset_count: int


class KnowledgeNodeResponse(BaseModel):
    id: UUID
    parent_id: UUID | None
    document_id: UUID | None
    title: str
    node_type: Literal["document", "folder", "unsupported"]
    depth: int
    display_order: int
    source_url: str | None


class KnowledgeDocumentSummary(BaseModel):
    id: UUID
    title: str
    source_url: str
    source_token: str
    display_order: int


class KnowledgeOverviewResponse(BaseModel):
    snapshot: KnowledgeSnapshotMetadata | None
    nodes: list[KnowledgeNodeResponse] = Field(default_factory=list)
    documents: list[KnowledgeDocumentSummary] = Field(default_factory=list)


class KnowledgeDocumentResponse(KnowledgeDocumentSummary):
    synced_at: datetime
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeSyncRunResponse(BaseModel):
    id: UUID
    status: KnowledgeRunStatus
    source_url: str
    started_at: datetime | None
    finished_at: datetime | None
    document_count: int
    asset_count: int
    error_code: str | None
    error_summary: str | None
    created_at: datetime


class KnowledgeAdminResponse(BaseModel):
    configured: bool
    current_snapshot: KnowledgeSnapshotMetadata | None
    latest_run: KnowledgeSyncRunResponse | None


class KnowledgeSyncCreatedResponse(BaseModel):
    run: KnowledgeSyncRunResponse
