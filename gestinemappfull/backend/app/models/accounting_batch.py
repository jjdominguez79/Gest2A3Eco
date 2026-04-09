from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountingBatchStatus, AccountingBatchType
from app.models.sqlalchemy_types import enum_column


class AccountingBatch(Base):
    __tablename__ = "accounting_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_type: Mapped[AccountingBatchType] = mapped_column(
        enum_column(AccountingBatchType, "accounting_batch_type"),
        nullable=False,
        default=AccountingBatchType.INVOICE_RECEIVED,
    )
    status: Mapped[AccountingBatchStatus] = mapped_column(
        enum_column(AccountingBatchStatus, "accounting_batch_status"),
        nullable=False,
        default=AccountingBatchStatus.DRAFT,
        index=True,
    )
    a3_company_code_snapshot: Mapped[str | None] = mapped_column(String(5), nullable=True, index=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    downloaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    exported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="accounting_batches")
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_user_id])
    generated_by: Mapped["User"] = relationship(foreign_keys=[generated_by_user_id])
    downloaded_by: Mapped["User"] = relationship(foreign_keys=[downloaded_by_user_id])
    exported_by: Mapped["User"] = relationship(foreign_keys=[exported_by_user_id])
    items: Mapped[list["AccountingBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
