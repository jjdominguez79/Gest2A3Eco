from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company import Company
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService


router = APIRouter(prefix="/dashboard")


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    active_membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    company = db.get(Company, active_membership.company_id)
    return DashboardService().build_summary(
        company=company,
        user=current_user,
        membership=active_membership,
    )
