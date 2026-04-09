from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.company_membership import CompanyMembership, CompanyRole
from app.models.user import User
from app.schemas.company import CompanyCreate


class CompanyService:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user: User) -> list[CompanyMembership]:
        return (
            self.db.query(CompanyMembership)
            .join(Company)
            .filter(
                CompanyMembership.user_id == user.id,
                CompanyMembership.is_active.is_(True),
                Company.is_active.is_(True),
            )
            .order_by(Company.name.asc())
            .all()
        )

    def create_for_user(self, payload: CompanyCreate, user: User) -> CompanyMembership:
        company = Company(name=payload.name.strip(), cif=(payload.cif or "").strip() or None, is_active=True)
        membership = CompanyMembership(user=user, company=company, role=CompanyRole.ADMIN, is_active=True)
        self.db.add(company)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership
