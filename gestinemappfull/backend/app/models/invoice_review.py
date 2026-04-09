from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import InvoiceReviewStatus
from app.models.sqlalchemy_types import enum_column


class InvoiceReview(Base):
    __tablename__ = "invoice_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    supplier_third_party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_third_parties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_company_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_name_detected: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_tax_id_detected: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    taxable_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    concept: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[InvoiceReviewStatus] = mapped_column(
        enum_column(InvoiceReviewStatus, "invoice_review_status"),
        nullable=False,
        default=InvoiceReviewStatus.PENDING,
        index=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped["Document"] = relationship(back_populates="invoice_review")
    supplier_third_party: Mapped["GlobalThirdParty"] = relationship()
    supplier_company_account: Mapped["CompanyAccount"] = relationship()
    reviewed_by: Mapped["User"] = relationship()
