"""API de perfil empresarial del cliente (solo lectura)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.database import SessionLocal
from backend.api.messaging_models import MessagingClient, MessagingOrganization, MessagingSession
from backend.api.messaging_security import hash_token, is_expired

router = APIRouter(prefix="/api/v1/messaging/client", tags=["client-profile"])


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _authenticated_client(request, db: Session) -> MessagingClient:
    """Extrae el cliente autenticado de la sesion."""
    from fastapi import Request
    token = ""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.cookies.get("msg_session", "")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")

    session = db.scalar(
        select(MessagingSession).where(
            MessagingSession.token_hash == hash_token(token),
        )
    )
    if not session or session.revoked_at or is_expired(session.expires_at):
        raise HTTPException(status_code=401, detail="Sesion no valida")

    client = db.get(MessagingClient, session.client_id)
    if not client or not client.active:
        raise HTTPException(status_code=403, detail="Cliente inactivo")
    return client


@router.get("/company-profile")
def get_company_profile(request, db: Session = Depends(_db)):
    """Devuelve la ficha empresarial de la organizacion del cliente."""
    from fastapi import Request
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")

    # Campos visibles de solo lectura
    profile = {
        "company_code": org.company_code,
        "name": org.name,
        "legal_name": org.legal_name or org.name,
        "tax_id": org.tax_id,
        "address": org.address,
        "postal_code": org.postal_code,
        "city": org.city,
        "province": org.province,
        "country": org.country,
        "phone": org.phone,
        "email": org.email,
        "active": org.active,
        "profile_synced_at": (
            org.profile_synced_at.isoformat() if org.profile_synced_at else None
        ),
    }
    # Omitir campos vacios
    return {k: v for k, v in profile.items() if v not in ("", None)}
