from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    internal_api_key: str
    public_base_url: str
    token_ttl_hours: int
    storage_dir: str
    redsys_environment: str
    redsys_merchant_code: str
    redsys_terminal: str
    redsys_secret_key: str
    redsys_notification_url: str
    redsys_timeout: int


def get_settings() -> Settings:
    environment = os.getenv("REDSYS_ENVIRONMENT", "test").strip().lower()
    public_base_url = os.getenv(
        "DGT_PUBLIC_BASE_URL", "https://tramites.gestinem.es"
    ).rstrip("/")
    return Settings(
        database_url=os.getenv("DGT_DATABASE_URL", "sqlite:///./dgt_api.db"),
        internal_api_key=os.getenv("DGT_INTERNAL_API_KEY", ""),
        public_base_url=public_base_url,
        token_ttl_hours=max(1, int(os.getenv("DGT_TOKEN_TTL_HOURS", "168"))),
        storage_dir=os.getenv("DGT_STORAGE_DIR", "./dgt_private_storage"),
        redsys_environment=environment,
        redsys_merchant_code=os.getenv("REDSYS_MERCHANT_CODE", ""),
        redsys_terminal=os.getenv("REDSYS_TERMINAL", "1"),
        redsys_secret_key=os.getenv("REDSYS_SECRET_KEY", ""),
        redsys_notification_url=os.getenv(
            "REDSYS_NOTIFICATION_URL",
            f"{public_base_url}/api/v1/pagos/redsys/notificacion",
        ),
        redsys_timeout=max(40, int(os.getenv("REDSYS_TIMEOUT", "50"))),
    )
