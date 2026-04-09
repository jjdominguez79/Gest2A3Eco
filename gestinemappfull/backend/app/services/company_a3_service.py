from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_membership import CompanyMembership, CompanyRole
from app.schemas.company import CompanyA3SettingsRead, CompanyA3SettingsUpdate


class CompanyA3Service:
    _code_pattern = re.compile(r"^\d{1,5}$")

    def __init__(self, db: Session):
        self.db = db

    def get_settings(self, *, company_id, membership: CompanyMembership) -> CompanyA3SettingsRead:
        company = self._get_company(company_id=company_id)
        return CompanyA3SettingsRead(
            company_id=company.id,
            company_name=company.name,
            role=membership.role,
            can_edit=membership.role == CompanyRole.ADMIN,
            a3_company_code=company.a3_company_code,
            a3_enabled=company.a3_enabled,
            a3_export_path=company.a3_export_path,
            a3_import_mode=company.a3_import_mode,
            updated_at=company.updated_at,
        )

    def update_settings(
        self,
        *,
        company_id,
        membership: CompanyMembership,
        payload: CompanyA3SettingsUpdate,
    ) -> CompanyA3SettingsRead:
        if membership.role != CompanyRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only company administrators can update A3 settings.",
            )

        company = self._get_company(company_id=company_id)
        normalized_code = self._normalize_code(payload.a3_company_code)
        if normalized_code is not None:
            duplicate = (
                self.db.query(Company)
                .filter(
                    Company.a3_company_code == normalized_code,
                    Company.id != company.id,
                )
                .first()
            )
            if duplicate is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A3 company code is already assigned to another company.",
                )

        company.a3_company_code = normalized_code
        company.a3_enabled = payload.a3_enabled
        company.a3_export_path = (payload.a3_export_path or "").strip() or None
        company.a3_import_mode = payload.a3_import_mode
        self.db.commit()
        self.db.refresh(company)
        return self.get_settings(company_id=company_id, membership=membership)

    def _get_company(self, *, company_id) -> Company:
        company = self.db.get(Company, company_id)
        if company is None or not company.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
        return company

    def _normalize_code(self, value: str | None) -> str | None:
        normalized = (value or "").strip()
        if not normalized:
            return None
        if not self._code_pattern.fullmatch(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A3 company code must contain between 1 and 5 digits.",
            )
        return normalized.zfill(5)
