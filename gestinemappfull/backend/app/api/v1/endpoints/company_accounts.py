from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.enums import AccountType
from app.models.user import User
from app.schemas.quick_actions import (
    NextAccountCodeResponse,
    QuickCreateCompanyAccountRequest,
    QuickCreateCompanyAccountResponse,
)
from app.schemas.company_account import CompanyAccountCreate, CompanyAccountRead
from app.services.document_event_service import DocumentEventService
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


@router.post("/quick-create", response_model=QuickCreateCompanyAccountResponse, status_code=status.HTTP_201_CREATED)
def quick_create_company_account(
    payload: QuickCreateCompanyAccountRequest,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> QuickCreateCompanyAccountResponse:
    del membership
    item, reused, proposed_account_code = CompanyAccountService(db).quick_create(
        company_id=company_id,
        payload=payload,
    )
    if payload.document_id:
        DocumentEventService(db).create(
            document_id=payload.document_id,
            user_id=current_user.id,
            action="company_account_quick_created" if not reused else "company_account_quick_reused",
            details={
                "company_account_id": str(item.id),
                "account_code": item.account_code,
                "global_third_party_id": str(item.global_third_party_id) if item.global_third_party_id else None,
            },
        )
        db.commit()
    return QuickCreateCompanyAccountResponse(
        item=CompanyAccountRead.model_validate(item),
        proposed_account_code=proposed_account_code,
        reused=reused,
    )


@router.get("/next-code", response_model=NextAccountCodeResponse)
def get_next_company_account_code(
    account_type: AccountType,
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> NextAccountCodeResponse:
    del membership
    next_code = CompanyAccountService(db).next_code(company_id=company_id, account_type=account_type)
    return NextAccountCodeResponse(account_type=account_type, next_code=next_code)
