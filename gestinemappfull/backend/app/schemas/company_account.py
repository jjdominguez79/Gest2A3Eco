from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import AccountSource, AccountSyncStatus, AccountType


class CompanyAccountCreate(BaseModel):
    account_code: str
    name: str
    account_type: AccountType
    global_third_party_id: UUID | None = None
    tax_id: str | None = None
    legal_name: str | None = None
    source: AccountSource = AccountSource.MANUAL_APP
    sync_status: AccountSyncStatus = AccountSyncStatus.NOT_SYNCED


class CompanyAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    account_code: str
    name: str
    account_type: AccountType
    global_third_party_id: UUID | None
    tax_id: str | None
    legal_name: str | None
    source: AccountSource
    sync_status: AccountSyncStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime
