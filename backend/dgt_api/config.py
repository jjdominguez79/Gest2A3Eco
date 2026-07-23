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


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DGT_DATABASE_URL", "sqlite:///./dgt_api.db"),
        internal_api_key=os.getenv("DGT_INTERNAL_API_KEY", ""),
        public_base_url=os.getenv("DGT_PUBLIC_BASE_URL", "https://tramites.gestinem.es").rstrip("/"),
        token_ttl_hours=max(1, int(os.getenv("DGT_TOKEN_TTL_HOURS", "168"))),
        storage_dir=os.getenv("DGT_STORAGE_DIR", "./dgt_private_storage"),
    )
