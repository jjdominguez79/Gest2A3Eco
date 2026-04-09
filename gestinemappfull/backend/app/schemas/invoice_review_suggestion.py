from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SuggestedThirdPartyRead(BaseModel):
    id: UUID
    legal_name: str
    tax_id: str | None
    score: float
    reason: str


class SuggestedCompanyAccountRead(BaseModel):
    id: UUID
    account_code: str
    name: str
    tax_id: str | None
    global_third_party_id: UUID | None
    score: float
    reason: str


class InvoiceReviewSuggestionsRead(BaseModel):
    best_third_party_id: UUID | None = None
    best_company_account_id: UUID | None = None
    suggested_third_parties: list[SuggestedThirdPartyRead]
    suggested_company_accounts: list[SuggestedCompanyAccountRead]
