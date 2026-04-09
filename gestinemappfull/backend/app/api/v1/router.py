from fastapi import APIRouter

from app.api.v1.endpoints import auth, companies, dashboard, health


router = APIRouter()
router.include_router(auth.router, tags=["auth"])
router.include_router(health.router, tags=["health"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(dashboard.router, tags=["dashboard"])
