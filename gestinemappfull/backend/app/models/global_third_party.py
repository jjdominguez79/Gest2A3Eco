from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ThirdPartyType
from app.models.sqlalchemy_types import enum_column


class GlobalThirdParty(Base):
    __tablename__ = "global_third_parties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    third_party_type: Mapped[ThirdPartyType] = mapped_column(
        enum_column(ThirdPartyType, "third_party_type"),
        nullable=False,
        default=ThirdPartyType.OTHER,
        index=True,
    )
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
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

    company_accounts: Mapped[list["CompanyAccount"]] = relationship(back_populates="global_third_party")
