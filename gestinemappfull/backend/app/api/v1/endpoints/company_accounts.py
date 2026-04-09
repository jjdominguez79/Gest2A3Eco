from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.enums import AccountType
from app.schemas.company_account import CompanyAccountCreate, CompanyAccountRead
from app.services.company_account_service import CompanyAccountService


router = APIRouter(prefix="/company-accounts")


@router.get("", response_model=list[CompanyAccountRead])
def list_company_accounts(
    account_code: str | None = Query(default=None),
    name: str | None = Query(default=None),
    account_type: AccountType | None = Query(default=None),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> list[CompanyAccountRead]:
    del membership
    items = CompanyAccountService(db).list(
        company_id=company_id,
        account_code=account_code,
        name=name,
        account_type=account_type,
    )
    return [CompanyAccountRead.model_validate(item) for item in items]


@router.post("", response_model=CompanyAccountRead, status_code=status.HTTP_201_CREATED)
def create_company_account(
    payload: CompanyAccountCreate,
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> CompanyAccountRead:
    del membership
    item = CompanyAccountService(db).create(company_id=company_id, payload=payload)
    return CompanyAccountRead.model_validate(item)
