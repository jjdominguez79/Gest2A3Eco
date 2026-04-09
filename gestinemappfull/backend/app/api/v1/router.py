from fastapi import APIRouter

from app.api.v1.endpoints import accounting, auth, companies, company_accounts, dashboard, documents, health, invoice_reviews, third_parties


router = APIRouter()
router.include_router(auth.router, tags=["auth"])
router.include_router(health.router, tags=["health"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(dashboard.router, tags=["dashboard"])
router.include_router(accounting.router, tags=["accounting"])
router.include_router(third_parties.router, tags=["third-parties"])
router.include_router(company_accounts.router, tags=["company-accounts"])
router.include_router(documents.router, tags=["documents"])
router.include_router(invoice_reviews.router, tags=["invoice-reviews"])
