from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountSource, AccountSyncStatus, AccountType
from app.models.sqlalchemy_types import enum_column


class CompanyAccount(Base):
    __tablename__ = "company_accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_code", name="uq_company_accounts_company_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    account_type: Mapped[AccountType] = mapped_column(
        enum_column(AccountType, "account_type"),
        nullable=False,
        default=AccountType.OTHER,
        index=True,
    )
    global_third_party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_third_parties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[AccountSource] = mapped_column(
        enum_column(AccountSource, "account_source"),
        nullable=False,
        default=AccountSource.MANUAL_APP,
    )
    sync_status: Mapped[AccountSyncStatus] = mapped_column(
        enum_column(AccountSyncStatus, "account_sync_status"),
        nullable=False,
        default=AccountSyncStatus.NOT_SYNCED,
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

    company: Mapped["Company"] = relationship(back_populates="accounts")
    global_third_party: Mapped["GlobalThirdParty | None"] = relationship(back_populates="company_accounts")
