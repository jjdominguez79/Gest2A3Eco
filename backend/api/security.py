from __future__ import annotations

import hashlib
import hmac as _hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.api.config import get_settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_workstation_token() -> str:
    """Genera un token de puesto con prefijo reconocible."""
    return f"g2a3_wks_{secrets.token_urlsafe(32)}"


def new_admin_session_token() -> str:
    """Genera un token de sesion admin del escritorio."""
    return f"g2a3_adm_{secrets.token_urlsafe(32)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DESKTOP_ADMIN_SESSION_TTL = timedelta(hours=1)


def _scrypt_verify(plain_password: str, stored_hash: str) -> bool:
    """Verifica una password contra el formato scrypt del escritorio."""
    try:
        prefix, n_raw, r_raw, p_raw, salt_hex, digest_hex = stored_hash.split("$", 5)
        if prefix != "scrypt":
            return False
        digest = hashlib.scrypt(
            plain_password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return _hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except Exception:
        return False


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
        from backend.api.database import SessionLocal
        from backend.api.models import Workstation
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


def _extract_admin_bearer(request: Request) -> str:
    """Extrae el token Bearer de la cabecera Authorization."""
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesion de administrador requerida")
    token = auth[7:].strip()
    if not token.startswith("g2a3_adm_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de sesion admin no valido")
    return token


def verify_desktop_admin_session(token: str, db: Session) -> str:
    """Verifica la sesion admin en la DB proporcionada. Devuelve username."""
    from backend.api.models import DesktopAdminSession

    t_hash = hash_token(token)
    session = db.scalar(
        select(DesktopAdminSession).where(
            DesktopAdminSession.token_hash == t_hash,
        )
    )
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesion de administrador no valida")
    # Comparacion de expiracion en Python para compatibilidad con SQLite en tests
    now = utcnow()
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesion de administrador expirada")
    return session.username
