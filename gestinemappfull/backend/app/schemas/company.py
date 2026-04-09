from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.company_membership import CompanyRole


class CompanyCreate(BaseModel):
    name: str
    cif: str | None = None


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cif: str | None = None
    is_active: bool
    created_at: datetime
    role: CompanyRole

