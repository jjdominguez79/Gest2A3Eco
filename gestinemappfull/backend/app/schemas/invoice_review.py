from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import InvoiceReviewStatus


class InvoiceReviewPendingItemRead(BaseModel):
    document_id: UUID
    document_original_filename: str
    document_created_at: datetime
    ocr_status: str | None
    ocr_confidence: float | None
    review_status: InvoiceReviewStatus
    supplier_name_detected: str | None = None
    supplier_tax_id_detected: str | None = None
    invoice_number: str | None = None
    total_amount: float | None = None


class InvoiceReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    supplier_third_party_id: UUID | None
    supplier_company_account_id: UUID | None
    supplier_name_detected: str | None
    supplier_tax_id_detected: str | None
    invoice_number: str | None
    invoice_date: date | None
    taxable_base: float | None
    tax_rate: float | None
    tax_amount: float | None
    total_amount: float | None
    concept: str | None
    review_status: InvoiceReviewStatus
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    document_original_filename: str | None = None
    ocr_text: str | None = None
    ocr_status: str | None = None


class InvoiceReviewUpdate(BaseModel):
    supplier_third_party_id: UUID | None = None
    supplier_company_account_id: UUID | None = None
    supplier_name_detected: str | None = None
    supplier_tax_id_detected: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    taxable_base: float | None = None
    tax_rate: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    concept: str | None = None
    review_status: InvoiceReviewStatus | None = None

    @field_validator("invoice_date", mode="before")
    @classmethod
    def validate_invoice_date(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
            try:
                return datetime.strptime(str(value), fmt).date()
            except ValueError:
                continue
        raise ValueError("Invalid invoice_date format.")
