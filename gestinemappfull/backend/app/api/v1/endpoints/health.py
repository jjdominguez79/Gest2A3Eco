from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthCheck


router = APIRouter()


@router.get("/health", response_model=HealthCheck)
def healthcheck() -> HealthCheck:
    return HealthCheck(status="ok", service=settings.app_name, version=settings.app_version)
