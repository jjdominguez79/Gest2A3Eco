from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import cast
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import String

from app.models.company_account import CompanyAccount
from app.models.enums import AccountSource, AccountSyncStatus, AccountType
from app.models.global_third_party import GlobalThirdParty
from app.schemas.company_account import CompanyAccountCreate
from app.schemas.quick_actions import QuickCreateCompanyAccountRequest


class CompanyAccountService:
    _ACCOUNT_PREFIXES = {
        AccountType.SUPPLIER: "400",
        AccountType.CLIENT: "430",
    }

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

    def next_code(self, *, company_id, account_type: AccountType) -> str:
        prefix = self._ACCOUNT_PREFIXES.get(account_type)
        if prefix is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Automatic account code is only available for supplier and client accounts.",
            )
        accounts = (
            self.db.query(CompanyAccount.account_code)
            .filter(
                CompanyAccount.company_id == company_id,
                CompanyAccount.is_active.is_(True),
                cast(CompanyAccount.account_code, String).like(f"{prefix}%"),
            )
            .all()
        )
        max_suffix = 0
        for (account_code,) in accounts:
            digits = "".join(ch for ch in str(account_code) if ch.isdigit())
            if not digits.startswith(prefix):
                continue
            digits = digits[:12].ljust(12, "0")
            try:
                max_suffix = max(max_suffix, int(digits))
            except ValueError:
                continue
        next_value = max_suffix + 1 if max_suffix else int(f"{prefix}000000000")
        return str(next_value).zfill(12)[-12:]

    def quick_create(self, *, company_id, payload: QuickCreateCompanyAccountRequest) -> tuple[CompanyAccount, bool, str]:
        proposed_account_code = self.next_code(company_id=company_id, account_type=payload.account_type)
        account_code = (payload.account_code or "").strip() or proposed_account_code

        if payload.global_third_party_id:
            third_party = self.db.get(GlobalThirdParty, payload.global_third_party_id)
            if third_party is None or not third_party.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global third party not found.")

        existing = (
            self.db.query(CompanyAccount)
            .filter(
                CompanyAccount.company_id == company_id,
                CompanyAccount.is_active.is_(True),
                CompanyAccount.account_code == account_code,
            )
            .first()
        )
        if existing is not None:
            return existing, True, proposed_account_code

        if payload.global_third_party_id:
            existing_linked = (
                self.db.query(CompanyAccount)
                .filter(
                    CompanyAccount.company_id == company_id,
                    CompanyAccount.is_active.is_(True),
                    CompanyAccount.global_third_party_id == payload.global_third_party_id,
                    CompanyAccount.account_type == payload.account_type,
                )
                .first()
            )
            if existing_linked is not None:
                return existing_linked, True, proposed_account_code

        account = CompanyAccount(
            company_id=company_id,
            account_code=account_code,
            name=payload.name.strip(),
            account_type=payload.account_type,
            global_third_party_id=payload.global_third_party_id,
            tax_id=(payload.tax_id or "").strip() or None,
            legal_name=(payload.legal_name or "").strip() or None,
            source=AccountSource.MANUAL_APP,
            sync_status=AccountSyncStatus.PENDING_SYNC,
            is_active=True,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account, False, proposed_account_code
