from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.company_account import CompanyAccount
from app.models.enums import AccountType
from app.models.global_third_party import GlobalThirdParty
from app.schemas.company_account import CompanyAccountCreate


class CompanyAccountService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        *,
        company_id,
        account_code: str | None = None,
        name: str | None = None,
        account_type: AccountType | None = None,
    ) -> list[CompanyAccount]:
        query = self.db.query(CompanyAccount).filter(
            CompanyAccount.company_id == company_id,
            CompanyAccount.is_active.is_(True),
        )
        if account_code:
            query = query.filter(CompanyAccount.account_code.ilike(f"%{account_code.strip()}%"))
        if name:
            query = query.filter(CompanyAccount.name.ilike(f"%{name.strip()}%"))
        if account_type:
            query = query.filter(CompanyAccount.account_type == account_type)
        return query.order_by(CompanyAccount.account_code.asc()).all()

    def create(self, *, company_id, payload: CompanyAccountCreate) -> CompanyAccount:
        existing = (
            self.db.query(CompanyAccount)
            .filter(
                CompanyAccount.company_id == company_id,
                CompanyAccount.account_code == payload.account_code.strip(),
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account code already exists for the active company.",
            )

        if payload.global_third_party_id:
            third_party = self.db.get(GlobalThirdParty, payload.global_third_party_id)
            if third_party is None or not third_party.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global third party not found.")

        account = CompanyAccount(
            company_id=company_id,
            account_code=payload.account_code.strip(),
            name=payload.name.strip(),
            account_type=payload.account_type,
            global_third_party_id=payload.global_third_party_id,
            tax_id=(payload.tax_id or "").strip() or None,
            legal_name=(payload.legal_name or "").strip() or None,
            source=payload.source,
            sync_status=payload.sync_status,
            is_active=True,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account
