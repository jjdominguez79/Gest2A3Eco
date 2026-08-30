"""API de perfil empresarial del cliente (solo lectura) y sincronizacion interna."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.database import SessionLocal
from backend.api.client_validation import normalize_tax_id
from backend.api.messaging_models import (
    MessagingClient,
    MessagingConversation,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token, is_expired, utcnow
from backend.api.security import require_master_sync_or_workstation_internal

router = APIRouter(prefix="/api/v1/messaging/client", tags=["client-profile"])


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _authenticated_client(request: Request, db: Session) -> MessagingClient:
    """Extrae el cliente autenticado de la sesion."""
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
def get_company_profile(request: Request, db: Session = Depends(_db)):
    """Devuelve la ficha empresarial de la organizacion del cliente."""
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")

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
    return {k: v for k, v in profile.items() if v not in ("", None)}


@router.get("/features")
def get_client_features(request: Request, db: Session = Depends(_db)):
    """Devuelve las funciones activas para el cliente autenticado."""
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")

    from backend.api.feature_flags import is_documents_enabled, is_invoicing_enabled
    return {
        "company_profile": True,
        "documents": is_documents_enabled(org),
        "invoicing": is_invoicing_enabled(org),
    }


@router.put("/internal/sync-profile")
def sync_company_profile(
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_master_sync_or_workstation_internal),
):
    """Sincroniza perfil empresarial desde el escritorio.

    Recibe company_code y campos de perfil. Actualiza msg_organizations.
    No sincroniza cuentas bancarias, series, subcuentas ni config contable.
    """
    company_code = payload.get("company_code", "").strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code es obligatorio")

    org = db.scalar(
        select(MessagingOrganization).where(
            MessagingOrganization.company_code == company_code,
        )
    )
    if not org:
        name = str(payload.get("name") or company_code).strip()
        org = MessagingOrganization(
            company_code=company_code,
            name=name,
            active=bool(payload.get("active", True)),
        )
        db.add(org)
        db.flush()
        db.add_all([
            MessagingConversation(organization_id=org.id, kind=kind)
            for kind in ("laboral", "fiscal", "private")
        ])

    # Campos sincronizables
    _SYNC_FIELDS = (
        "tax_id", "legal_name", "address", "postal_code",
        "city", "province", "country", "phone", "email",
    )
    changed = False
    for field in _SYNC_FIELDS:
        if field in payload:
            value = str(payload[field]).strip()
            if field == "tax_id":
                value = normalize_tax_id(value)
            if getattr(org, field) != value:
                setattr(org, field, value)
                changed = True

    if "name" in payload and payload["name"].strip():
        name = payload["name"].strip()
        if org.name != name:
            org.name = name
            changed = True

    if "active" in payload:
        active = bool(payload["active"])
        if org.active != active:
            org.active = active
            changed = True

    org.profile_synced_at = utcnow()
    db.commit()

    return {
        "status": "ok",
        "changed": changed,
        "company_code": company_code,
        "organization_id": org.id,
    }
