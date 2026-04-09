from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import (
    AccountingBatchItemStatus,
    AccountingBatchStatus,
    AccountingBatchType,
    DocumentWorkflowStatus,
)


class AccountingPendingItemRead(BaseModel):
    document_id: UUID
    invoice_review_id: UUID
    original_filename: str
    supplier_name: str | None
    supplier_tax_id: str | None
    invoice_number: str | None
    invoice_date: datetime | None = None
    total_amount: float | None
    company_account_code: str | None
    workflow_status: DocumentWorkflowStatus
    latest_batch_id: UUID | None = None
    latest_batch_status: AccountingBatchStatus | None = None


class AccountingBatchCreate(BaseModel):
    document_ids: list[UUID]
    notes: str | None = None


class AccountingBatchGenerateRequest(BaseModel):
    notes: str | None = None


class AccountingBatchExportMarkRequest(BaseModel):
    notes: str | None = None


class AccountingBatchDownloadResponse(BaseModel):
    batch_id: UUID
    status: AccountingBatchStatus
    downloaded_at: datetime | None
    downloaded_by_user_id: UUID | None


class AccountingBatchItemRead(BaseModel):
    id: UUID
    batch_id: UUID
    document_id: UUID
    invoice_review_id: UUID | None
    status: AccountingBatchItemStatus
    error_message: str | None
    created_at: datetime
    original_filename: str | None = None
    invoice_number: str | None = None
    workflow_status: DocumentWorkflowStatus | None = None


class AccountingBatchListItem(BaseModel):
    id: UUID
    company_id: UUID
    batch_type: AccountingBatchType
    status: AccountingBatchStatus
    a3_company_code_snapshot: str | None
    file_name: str | None
    file_path: str | None
    file_hash: str | None
    created_by_user_id: UUID | None
    generated_by_user_id: UUID | None
    downloaded_by_user_id: UUID | None
    exported_by_user_id: UUID | None
    created_by_name: str | None = None
    generated_by_name: str | None = None
    downloaded_by_name: str | None = None
    exported_by_name: str | None = None
    created_at: datetime
    generated_at: datetime | None
    downloaded_at: datetime | None
    exported_at: datetime | None
    total_documents: int
    total_entries: int
    notes: str | None
    error_message: str | None


class AccountingBatchRead(AccountingBatchListItem):
    items: list[AccountingBatchItemRead]
