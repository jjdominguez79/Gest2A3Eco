from __future__ import annotations

import hashlib
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


def require_aapp_worker_key(x_api_key: str = Header(default="")) -> str:
    """Credencial exclusiva del worker que maneja certificados privados."""
    expected = get_settings().aapp_worker_api_key
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial del worker AAPP no valida",
        )
    return "aapp-worker"


def require_aapp_worker_claim_protocol(
    x_aapp_worker_protocol: str = Header(default=""),
) -> str:
    """Impide que workers obsoletos reclamen nuevas solicitudes."""
    if not secrets.compare_digest(x_aapp_worker_protocol, "3"):
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail="El worker AAPP debe actualizarse antes de reclamar solicitudes",
        )
    return "aapp-worker-protocol-3"


def require_document_publisher(x_api_key: str = Header(default="")) -> str:
    """Publicadores autorizados: escritorio/interno y worker AAPP."""
    worker_key = get_settings().aapp_worker_api_key
    if worker_key and secrets.compare_digest(x_api_key, worker_key):
        return "aapp-worker"
    return require_workstation_or_internal(x_api_key)


def require_master_sync_or_workstation_internal(
    x_api_key: str = Header(default=""),
) -> str:
    """Acepta la clave exclusiva del replicador maestro o credenciales existentes."""
    expected = get_settings().client_master_sync_api_key
    if expected and secrets.compare_digest(x_api_key, expected):
        return "client-master-sync"
    return require_workstation_or_internal(x_api_key)


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
