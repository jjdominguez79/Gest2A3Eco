from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ThirdPartyType


class GlobalThirdPartyCreate(BaseModel):
    third_party_type: ThirdPartyType
    tax_id: str | None = None
    legal_name: str
    trade_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None


class GlobalThirdPartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    third_party_type: ThirdPartyType
    tax_id: str | None
    legal_name: str
    trade_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    postal_code: str | None
    country: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
