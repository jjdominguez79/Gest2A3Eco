from uuid import UUID

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    company_id: UUID
    company_name: str
    user_full_name: str
    user_role: str
    pending_tasks: int
    recent_documents: int
    alerts: int
