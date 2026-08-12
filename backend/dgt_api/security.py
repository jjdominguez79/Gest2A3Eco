from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dgt_api.config import get_settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_workstation_token() -> str:
    """Genera un token de puesto con prefijo reconocible."""
    return f"g2a3_wks_{secrets.token_urlsafe(32)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_internal_key(x_api_key: str = Header(default="")) -> str:
    expected = get_settings().internal_api_key
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial interna no valida")
    return "gest2a3eco"


def require_workstation_or_internal(x_api_key: str = Header(default="")) -> str:
    """
    Acepta la clave interna de admin O un token de puesto registrado.

    Orden de verificacion:
      1. Si coincide con internal_api_key → "gest2a3eco" (compatibilidad)
      2. Si tiene prefijo g2a3_wks_ → busca en tabla workstations y actualiza last_seen_at
      3. Si nada coincide → 401
    """
    settings = get_settings()

    # 1. Clave interna de administracion (admin/backend)
    if settings.internal_api_key and secrets.compare_digest(x_api_key, settings.internal_api_key):
        return "gest2a3eco"

    # 2. Token de puesto
    if x_api_key.startswith("g2a3_wks_"):
        from backend.dgt_api.database import SessionLocal
        from backend.dgt_api.models import Workstation
        token_hash = hash_token(x_api_key)
        with SessionLocal() as db:
            ws = db.scalar(
                select(Workstation).where(
                    Workstation.token_hash == token_hash,
                    Workstation.active.is_(True),
                )
            )
            if ws:
                ws.last_seen_at = utcnow()
                db.commit()
                return ws.name

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial no valida")
