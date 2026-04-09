from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.schemas.company import CompanyA3SettingsRead, CompanyA3SettingsUpdate, CompanyCreate, CompanySummary
from app.services.company_a3_service import CompanyA3Service
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
            a3_company_code=membership.company.a3_company_code,
            a3_enabled=membership.company.a3_enabled,
            a3_export_path=membership.company.a3_export_path,
            a3_import_mode=membership.company.a3_import_mode,
            created_at=membership.company.created_at,
            updated_at=membership.company.updated_at,
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
        a3_company_code=membership.company.a3_company_code,
        a3_enabled=membership.company.a3_enabled,
        a3_export_path=membership.company.a3_export_path,
        a3_import_mode=membership.company.a3_import_mode,
        created_at=membership.company.created_at,
        updated_at=membership.company.updated_at,
        role=membership.role,
    )


@router.get("/{company_id}/a3-settings", response_model=CompanyA3SettingsRead)
def get_company_a3_settings(
    company_id: UUID,
    active_company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> CompanyA3SettingsRead:
    if company_id != active_company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company mismatch with active context.")
    return CompanyA3Service(db).get_settings(company_id=company_id, membership=membership)


@router.put("/{company_id}/a3-settings", response_model=CompanyA3SettingsRead)
def update_company_a3_settings(
    company_id: UUID,
    payload: CompanyA3SettingsUpdate,
    active_company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> CompanyA3SettingsRead:
    if company_id != active_company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company mismatch with active context.")
    return CompanyA3Service(db).update_settings(company_id=company_id, membership=membership, payload=payload)
