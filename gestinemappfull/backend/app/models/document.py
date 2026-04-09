from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DocumentSource, DocumentType, DocumentWorkflowStatus
from app.models.sqlalchemy_types import enum_column


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[DocumentSource] = mapped_column(
        enum_column(DocumentSource, "document_source"),
        nullable=False,
        default=DocumentSource.UPLOAD,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        enum_column(DocumentType, "document_type"),
        nullable=False,
        default=DocumentType.UNASSIGNED,
        index=True,
    )
    workflow_status: Mapped[DocumentWorkflowStatus] = mapped_column(
        enum_column(DocumentWorkflowStatus, "document_workflow_status"),
        nullable=False,
        default=DocumentWorkflowStatus.INBOX,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    company: Mapped["Company"] = relationship(back_populates="documents")
    uploaded_by: Mapped["User | None"] = relationship()
    events: Mapped[list["DocumentEvent"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
