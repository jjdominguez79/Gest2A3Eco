from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.company_membership import CompanyRole
from app.models.enums import A3ImportMode


class CompanyCreate(BaseModel):
    name: str
    cif: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    cif: str | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cif: str | None = None
    is_active: bool
    a3_company_code: str | None = None
    a3_enabled: bool
    a3_export_path: str | None = None
    a3_import_mode: A3ImportMode | None = None
    created_at: datetime
    updated_at: datetime


class CompanySummary(CompanyRead):
    role: CompanyRole


class CompanyA3SettingsRead(BaseModel):
    company_id: UUID
    company_name: str
    role: CompanyRole
    can_edit: bool
    a3_company_code: str | None = None
    a3_enabled: bool
    a3_export_path: str | None = None
    a3_import_mode: A3ImportMode | None = None
    updated_at: datetime


class CompanyA3SettingsUpdate(BaseModel):
    a3_company_code: str | None = None
    a3_enabled: bool
    a3_export_path: str | None = None
    a3_import_mode: A3ImportMode | None = None
