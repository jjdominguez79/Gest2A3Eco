from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountingBatchItemStatus
from app.models.sqlalchemy_types import enum_column


class AccountingBatchItem(Base):
    __tablename__ = "accounting_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "document_id", name="uq_accounting_batch_items_batch_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounting_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice_reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[AccountingBatchItemStatus] = mapped_column(
        enum_column(AccountingBatchItemStatus, "accounting_batch_item_status"),
        nullable=False,
        default=AccountingBatchItemStatus.INCLUDED,
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch: Mapped["AccountingBatch"] = relationship(back_populates="items")
    document: Mapped["Document"] = relationship(back_populates="accounting_batch_items")
    invoice_review: Mapped["InvoiceReview"] = relationship()
