from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import A3ImportMode
from app.models.sqlalchemy_types import enum_column


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cif: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    a3_company_code: Mapped[str | None] = mapped_column(String(5), nullable=True, unique=True, index=True)
    a3_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    a3_export_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    a3_import_mode: Mapped[A3ImportMode | None] = mapped_column(
        enum_column(A3ImportMode, "a3_import_mode"),
        nullable=True,
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

    memberships: Mapped[list["CompanyMembership"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    accounts: Mapped[list["CompanyAccount"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    accounting_batches: Mapped[list["AccountingBatch"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
