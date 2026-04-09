from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AccountType, ThirdPartyType
from app.schemas.company_account import CompanyAccountRead
from app.schemas.third_party import GlobalThirdPartyRead


class QuickCreateThirdPartyRequest(BaseModel):
    third_party_type: ThirdPartyType = ThirdPartyType.SUPPLIER
    tax_id: str | None = None
    legal_name: str
    trade_name: str | None = None
    document_id: UUID | None = None


class QuickCreateThirdPartyResponse(BaseModel):
    item: GlobalThirdPartyRead
    reused: bool


class QuickCreateCompanyAccountRequest(BaseModel):
    account_type: AccountType
    name: str
    global_third_party_id: UUID | None = None
    tax_id: str | None = None
    legal_name: str | None = None
    account_code: str | None = None
    document_id: UUID | None = None


class QuickCreateCompanyAccountResponse(BaseModel):
    item: CompanyAccountRead
    proposed_account_code: str
    reused: bool


class NextAccountCodeResponse(BaseModel):
    account_type: AccountType
    next_code: str
