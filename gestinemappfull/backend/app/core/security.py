from datetime import UTC, datetime, timedelta

from app.core.config import settings


def build_token_expiration() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
