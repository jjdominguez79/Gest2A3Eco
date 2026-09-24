"""API de perfil empresarial del cliente (solo lectura) y sincronizacion interna."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.client_access import revoke_organization_client_access
from backend.api.client_validation import normalize_tax_id
from backend.api.config import get_settings
from backend.api.database import SessionLocal
from backend.api.messaging_models import (
    MessagingClient,
    MessagingAttachment,
    MessagingConversation,
    MessagingOrganization,
    MessagingProfileChangeRequest,
    MessagingSession,
    MessagingStaff,
    MessagingStaffPresenceConnection,
    MessagingStaffSession,
)
from backend.api.messaging_security import hash_token, is_expired, utcnow
from backend.api.messaging_storage import MessagingStorage
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
        "logo_url": (
            "/api/v1/messaging/client/company-logo"
            if org.logo_storage_key else ""
        ),
        "active": org.active,
        "profile_synced_at": (
            org.profile_synced_at.isoformat() if org.profile_synced_at else None
        ),
    }
    return {k: v for k, v in profile.items() if v not in ("", None)}


@router.get("/company-logo")
def get_company_logo(request: Request, db: Session = Depends(_db)):
    """Entrega el logotipo corporativo aprobado al usuario de la empresa."""
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active or not org.logo_storage_key:
        raise HTTPException(status_code=404, detail="Logotipo no configurado")
    try:
        content = MessagingStorage().get(org.logo_storage_key)
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail="Logotipo no disponible") from exc
    return Response(
        content=content,
        media_type=org.logo_content_type or "image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _internal_change_request_data(
    db: Session, item: MessagingProfileChangeRequest,
) -> dict:
    org = db.get(MessagingOrganization, item.organization_id)
    logo = None
    if item.message_id:
        logo = db.scalar(
            select(MessagingAttachment).where(
                MessagingAttachment.message_id == item.message_id,
                MessagingAttachment.content_type.like("image/%"),
                MessagingAttachment.storage_deleted_at.is_(None),
            ).order_by(MessagingAttachment.created_at.desc())
        )
    return {
        "id": item.id,
        "company_code": org.company_code if org else "",
        "company_name": org.name if org else "",
        "changes": json.loads(item.changes_json or "{}"),
        "current_values": json.loads(item.current_values_json or "{}"),
        "notes": item.notes,
        "status": item.status,
        "review_note": item.review_note,
        "has_logo": logo is not None,
        "logo_name": logo.name if logo else "",
        "created_at": item.created_at.isoformat(),
    }


@router.get("/internal/profile-change-requests")
def internal_profile_change_requests(
    status: str = "pending",
    db: Session = Depends(_db),
    _auth: str = Depends(require_master_sync_or_workstation_internal),
):
    stmt = select(MessagingProfileChangeRequest)
    if status:
        stmt = stmt.where(MessagingProfileChangeRequest.status == status)
    rows = db.scalars(
        stmt.order_by(MessagingProfileChangeRequest.created_at.desc())
    ).all()
    return [_internal_change_request_data(db, item) for item in rows]


@router.get("/internal/profile-change-requests/{request_id}/logo")
def internal_profile_change_request_logo(
    request_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_master_sync_or_workstation_internal),
):
    item = db.get(MessagingProfileChangeRequest, request_id)
    if not item or not item.message_id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    logo = db.scalar(
        select(MessagingAttachment).where(
            MessagingAttachment.message_id == item.message_id,
            MessagingAttachment.content_type.like("image/%"),
            MessagingAttachment.storage_deleted_at.is_(None),
        ).order_by(MessagingAttachment.created_at.desc())
    )
    if not logo:
        raise HTTPException(status_code=404, detail="La solicitud no tiene logotipo")
    try:
        content = MessagingStorage().get(logo.storage_key)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Logotipo no disponible") from exc
    extension = {
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(str(logo.content_type or "").split(";", 1)[0].lower(), "png")
    download_name = f"logotipo_empresa.{extension}"
    return Response(
        content=content,
        media_type=logo.content_type or "image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Logo-Filename": download_name,
        },
    )


@router.patch("/internal/profile-change-requests/{request_id}")
def internal_review_profile_change_request(
    request_id: str,
    payload: dict = Body(...),
    db: Session = Depends(_db),
    reviewer: str = Depends(require_master_sync_or_workstation_internal),
):
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"applied", "rejected"}:
        raise HTTPException(status_code=422, detail="Estado de revision no valido")
    item = db.get(MessagingProfileChangeRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="La solicitud ya fue revisada")
    item.status = status
    item.review_note = str(payload.get("note") or "").strip()[:2000]
    item.reviewed_by = str(reviewer or "desktop")[:64]
    item.reviewed_at = utcnow()
    if status == "applied" and item.message_id:
        logo = db.scalar(
            select(MessagingAttachment).where(
                MessagingAttachment.message_id == item.message_id,
                MessagingAttachment.content_type.like("image/%"),
                MessagingAttachment.storage_deleted_at.is_(None),
            ).order_by(MessagingAttachment.created_at.desc())
        )
        org = db.get(MessagingOrganization, item.organization_id)
        if logo and org:
            org.logo_storage_key = logo.storage_key
            org.logo_content_type = logo.content_type
            logo.expires_at = None
    db.commit()
    return _internal_change_request_data(db, item)


@router.get("/features")
def get_client_features(request: Request, db: Session = Depends(_db)):
    """Devuelve las funciones activas para el cliente autenticado."""
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")

    from backend.api.feature_flags import (
        is_certificates_enabled,
        is_documents_enabled,
        is_invoicing_enabled,
    )
    return {
        "company_profile": True,
        "documents": is_documents_enabled(org),
        "invoicing": is_invoicing_enabled(org),
        "certificates": is_certificates_enabled(org),
    }


@router.put("/internal/staff-snapshot")
def sync_staff_snapshot(
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_master_sync_or_workstation_internal),
):
    """Proyecta los empleados del escritorio sin borrar su historial."""
    rows = payload.get("staff")
    if not isinstance(rows, list):
        raise HTTPException(status_code=422, detail="staff debe ser una lista")
    seen_ids: set[str] = set()
    seen_emails: set[str] = set()
    mappings: list[dict] = []
    now = utcnow()
    allowed_domain = get_settings().messaging_staff_allowed_domain.strip().lower()

    for raw in rows:
        desktop_user_id = str(raw.get("desktop_user_id") or "").strip()
        email = str(raw.get("email") or "").strip().lower()
        name = str(raw.get("name") or "").strip()
        role = str(raw.get("role") or "empleado").strip().lower()
        if not desktop_user_id or not email or not name:
            raise HTTPException(422, "Cada empleado necesita id, nombre y correo")
        if allowed_domain and not email.endswith(f"@{allowed_domain}"):
            raise HTTPException(422, f"El empleado debe pertenecer a @{allowed_domain}")
        if role not in {"admin", "empleado"}:
            raise HTTPException(422, "Rol de empleado no valido")
        if desktop_user_id in seen_ids or email in seen_emails:
            raise HTTPException(409, "La fotografia contiene empleados duplicados")
        seen_ids.add(desktop_user_id)
        seen_emails.add(email)

        staff = db.scalar(select(MessagingStaff).where(
            MessagingStaff.desktop_user_id == desktop_user_id,
        ))
        if not staff:
            staff = db.scalar(select(MessagingStaff).where(MessagingStaff.email == email))
        if staff and staff.desktop_user_id and staff.desktop_user_id != desktop_user_id:
            raise HTTPException(409, f"El correo {email} pertenece a otro usuario del escritorio")
        if not staff:
            staff = MessagingStaff(external_id=str(uuid.uuid4()))
            db.add(staff)

        staff.desktop_user_id = desktop_user_id
        staff.name = name
        staff.email = email
        staff.role = role
        staff.active = bool(raw.get("active", True))
        if not staff.active:
            db.query(MessagingStaffSession).filter(
                MessagingStaffSession.staff_external_id == staff.external_id,
                MessagingStaffSession.revoked_at.is_(None),
            ).update({MessagingStaffSession.revoked_at: now}, synchronize_session=False)
            db.query(MessagingStaffPresenceConnection).filter(
                MessagingStaffPresenceConnection.staff_external_id == staff.external_id,
            ).delete(synchronize_session=False)
        mappings.append({
            "desktop_user_id": desktop_user_id,
            "staff_id": staff.external_id,
            "email": email,
            "active": staff.active,
        })

    if bool(payload.get("full_snapshot", True)):
        stmt = select(MessagingStaff).where(MessagingStaff.desktop_user_id != "")
        if seen_ids:
            stmt = stmt.where(MessagingStaff.desktop_user_id.not_in(seen_ids))
        for staff in db.scalars(stmt).all():
            staff.active = False
            db.query(MessagingStaffSession).filter(
                MessagingStaffSession.staff_external_id == staff.external_id,
                MessagingStaffSession.revoked_at.is_(None),
            ).update({MessagingStaffSession.revoked_at: now}, synchronize_session=False)
            db.query(MessagingStaffPresenceConnection).filter(
                MessagingStaffPresenceConnection.staff_external_id == staff.external_id,
            ).delete(synchronize_session=False)

    db.commit()
    return {"ok": True, "staff": mappings}


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
            for kind in ("general", "private")
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
        if not active:
            revoke_organization_client_access(db, org.id)

    org.profile_synced_at = utcnow()
    db.commit()

    return {
        "status": "ok",
        "changed": changed,
        "company_code": company_code,
        "organization_id": org.id,
    }
