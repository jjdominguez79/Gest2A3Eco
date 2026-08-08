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
    signrequest_token: str
    signrequest_from_email: str
    signrequest_gestor_email: str
    signrequest_gestor_telefono: str
    signrequest_base_url: str
    dataprius_api_key: str
    dataprius_api_secret: str
    dataprius_base_url: str
    dataprius_base_path: str


def get_settings() -> Settings:
    database_url = os.getenv("DGT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DGT_DATABASE_URL es obligatorio y debe apuntar a PostgreSQL."
        )

    return Settings(
        database_url=database_url,
        internal_api_key=os.getenv("DGT_INTERNAL_API_KEY", ""),
        public_base_url=os.getenv("DGT_PUBLIC_BASE_URL", "https://tramites.gestinem.es").rstrip("/"),
        token_ttl_hours=max(1, int(os.getenv("DGT_TOKEN_TTL_HOURS", "168"))),
        storage_dir=os.getenv("DGT_STORAGE_DIR", "./dgt_private_storage"),
        signrequest_token=os.getenv("SIGNREQUEST_TOKEN", ""),
        signrequest_from_email=os.getenv("SIGNREQUEST_FROM_EMAIL", ""),
        signrequest_gestor_email=os.getenv("SIGNREQUEST_GESTOR_EMAIL", ""),
        signrequest_gestor_telefono=os.getenv("SIGNREQUEST_GESTOR_TELEFONO", ""),
        signrequest_base_url=os.getenv("SIGNREQUEST_BASE_URL", "https://signrequest.com/api/v1").rstrip("/"),
        dataprius_api_key=os.getenv("DATAPRIUS_API_KEY", ""),
        dataprius_api_secret=os.getenv("DATAPRIUS_API_SECRET", ""),
        dataprius_base_url=os.getenv("DATAPRIUS_BASE_URL", "https://api.v2.dataprius.com").rstrip("/"),
        dataprius_base_path=os.getenv("DATAPRIUS_BASE_PATH", "FOLDERS/Gest2A3Eco/Tramites DGT").rstrip("/"),
    )
