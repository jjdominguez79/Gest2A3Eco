from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status

from backend.dgt_api.config import get_settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_internal_key(x_api_key: str = Header(default="")) -> str:
    expected = get_settings().internal_api_key
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial interna no valida")
    return "gest2a3eco"
