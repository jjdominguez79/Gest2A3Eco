from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentType, DocumentWorkflowStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    original_filename: str
    stored_filename: str
    storage_path: str
    mime_type: str | None
    extension: str | None
    file_size: int
    sha256_hash: str
    source: str
    document_type: DocumentType
    workflow_status: DocumentWorkflowStatus
    uploaded_by_user_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DocumentUpdate(BaseModel):
    document_type: DocumentType | None = None
    workflow_status: DocumentWorkflowStatus | None = None
