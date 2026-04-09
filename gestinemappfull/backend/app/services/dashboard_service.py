from app.models.company import Company
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.schemas.dashboard import DashboardSummary


class DashboardService:
    def build_summary(self, *, company: Company, user: User, membership: CompanyMembership) -> DashboardSummary:
        return DashboardSummary(
            company_id=company.id,
            company_name=company.name,
            user_full_name=user.full_name,
            user_role=membership.role.value,
            pending_tasks=0,
            recent_documents=0,
            alerts=0,
        )
