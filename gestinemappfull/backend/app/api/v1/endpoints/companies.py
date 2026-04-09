from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanySummary
from app.services.company_service import CompanyService


router = APIRouter()


@router.get("/", response_model=list[CompanySummary])
def list_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CompanySummary]:
    memberships = CompanyService(db).list_for_user(current_user)
    return [
        CompanySummary(
            id=membership.company.id,
            name=membership.company.name,
            cif=membership.company.cif,
            is_active=membership.company.is_active,
            created_at=membership.company.created_at,
            role=membership.role,
        )
        for membership in memberships
    ]


@router.post("/", response_model=CompanySummary, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanySummary:
    membership = CompanyService(db).create_for_user(payload, current_user)
    return CompanySummary(
        id=membership.company.id,
        name=membership.company.name,
        cif=membership.company.cif,
        is_active=membership.company.is_active,
        created_at=membership.company.created_at,
        role=membership.role,
    )
