from __future__ import annotations

import asyncio
import hashlib
import io
import json
import mimetypes
import secrets
import uuid
from datetime import timedelta

import msal
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.config import get_settings
from backend.api.database import SessionLocal
from backend.api.messaging_models import (
    MessagingAttachment, MessagingClient, MessagingClientPushSubscription, MessagingConversation, MessagingDevice, MessagingDownload,
    MessagingEvent, MessagingInvitation, MessagingMessage, MessagingOrganization,
    MessagingPasswordReset, MessagingPresence, MessagingRead, MessagingSession, MessagingStaff,
    MessagingPushSubscription, MessagingStaffAuthFlow, MessagingStaffChannel, MessagingStaffSession,
    MessagingStaffThread, MessagingStaffThreadMessage, MessagingStaffThreadRead,
)
from backend.api.messaging_mail import (
    configured as mail_configured, send_invitation, send_message_notice,
    send_password_reset,
)
from backend.api.messaging_security import (
    hash_password, hash_token, invitation_expiry, new_token, session_expiry,
    is_expired, utcnow, verify_password,
)
from backend.api.messaging_storage import MessagingStorage, safe_name
from backend.api.messaging_push import configured as push_configured, send_push
from backend.api.security import require_internal_key


router = APIRouter(prefix="/api/v1/messaging", tags=["messaging"])
MAX_ATTACHMENT = 50 * 1024 * 1024
MAX_AVATAR = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff",
    ".txt", ".xml", ".csv", ".xls", ".xlsx", ".doc", ".docx", ".zip",
}
STAFF_CHANNELS = {"laboral", "fiscal"}
STAFF_ROLES = {"admin", "empleado"}
TEST_COMPANY_CODES = {"E0000", "E00000"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OrganizationIn(BaseModel):
    company_code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    private_owner_external_id: str | None = None
    active: bool = True


class StaffIn(BaseModel):
    external_id: str
    name: str
    email: str = ""
    chat_alias: str = ""
    role: str = "empleado"
    active: bool = True
    channels: list[str] | None = None


class InviteIn(BaseModel):
    company_code: str
    name: str
    email: str
    send_email: bool = True


class AcceptInviteIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)


class ConversationPatch(BaseModel):
    state: str | None = None
    assigned_staff_external_id: str | None = None


class StaffPermissionsIn(BaseModel):
    channels: list[str] = Field(default_factory=list)
    active: bool = True
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    role: str | None = None
    chat_alias: str | None = Field(default=None, max_length=160)


class StaffCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    role: str = "empleado"
    chat_alias: str = Field(default="", max_length=160)
    active: bool = True
    channels: list[str] = Field(default_factory=list)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=4000)
    p256dh: str = Field(min_length=10, max_length=1000)
    auth: str = Field(min_length=5, max_length=1000)


def _staff_from_request(db: Session, request: Request) -> MessagingStaff:
    # Camino 1: token de sesion del despacho (Bearer o cookie)
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    token = token or request.cookies.get("msg_staff_session", "")
    if token:
        staff_session = db.scalar(select(MessagingStaffSession).where(
            MessagingStaffSession.token_hash == hash_token(token),
        ))
        if not staff_session or staff_session.revoked_at or is_expired(staff_session.expires_at):
            raise HTTPException(401, "Sesion del despacho caducada")
        staff = db.get(MessagingStaff, staff_session.staff_external_id)
        if not staff or not staff.active:
            raise HTTPException(403, "Usuario del despacho no autorizado")
        return staff

    # Camino 2: clave interna de administracion O WorkstationToken del puesto
    supplied = request.headers.get("x-api-key", "")
    settings = get_settings()

    key_valid = bool(settings.internal_api_key and secrets.compare_digest(supplied, settings.internal_api_key))

    if not key_valid and supplied.startswith("g2a3_wks_"):
        from backend.api.models import Workstation
        from backend.api.security import hash_token as _wks_hash
        ws = db.scalar(
            select(Workstation).where(
                Workstation.token_hash == _wks_hash(supplied),
                Workstation.active.is_(True),
            )
        )
        if ws:
            ws.last_seen_at = utcnow()
            key_valid = True

    if not key_valid:
        raise HTTPException(401, "Credencial interna no valida")

    device_id = request.headers.get("x-device-id", "")
    device_token = request.headers.get("x-device-token", "")
    device = db.get(MessagingDevice, device_id)
    if not device or not device.active or not device_token or not hmac_compare(device.token_hash, hash_token(device_token)):
        raise HTTPException(403, "Puesto del despacho no autorizado")
    device.last_used_at = utcnow()
    staff = db.get(MessagingStaff, request.headers.get("x-staff-id", ""))
    if not staff or not staff.active or staff.role not in {"admin", "empleado"}:
        raise HTTPException(403, "Usuario del despacho no autorizado")
    return staff


def _staff(
    request: Request,
    db: Session = Depends(get_db),
) -> MessagingStaff:
    return _staff_from_request(db, request)


def _channels_for_staff(db: Session, staff: MessagingStaff) -> set[str]:
    return set(db.scalars(select(MessagingStaffChannel.channel).where(
        MessagingStaffChannel.staff_external_id == staff.external_id,
    )))


def _validated_staff_email(value: str) -> str:
    email = value.strip().lower()
    domain = get_settings().messaging_staff_allowed_domain.strip().lower()
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
        raise HTTPException(422, "Email corporativo no valido")
    if domain and not email.endswith(f"@{domain}"):
        raise HTTPException(422, f"El usuario debe pertenecer a @{domain}")
    return email


def _set_staff_channels(db: Session, external_id: str, channels: set[str]) -> None:
    if not channels <= STAFF_CHANNELS:
        raise HTTPException(422, "Canal no valido")
    db.query(MessagingStaffChannel).filter(
        MessagingStaffChannel.staff_external_id == external_id,
    ).delete(synchronize_session=False)
    db.add_all([
        MessagingStaffChannel(staff_external_id=external_id, channel=channel)
        for channel in sorted(channels)
    ])


def _revoke_staff_access(db: Session, external_id: str) -> None:
    now = utcnow()
    db.query(MessagingStaffSession).filter(
        MessagingStaffSession.staff_external_id == external_id,
        MessagingStaffSession.revoked_at.is_(None),
    ).update({MessagingStaffSession.revoked_at: now}, synchronize_session=False)
    db.query(MessagingPushSubscription).filter(
        MessagingPushSubscription.staff_external_id == external_id,
    ).update({MessagingPushSubscription.active: False}, synchronize_session=False)


def _ensure_staff_group_threads(db: Session) -> None:
    changed = False
    for channel in sorted(STAFF_CHANNELS):
        key = f"group:{channel}"
        if not db.scalar(select(MessagingStaffThread).where(MessagingStaffThread.key == key)):
            db.add(MessagingStaffThread(key=key, kind="group", channel=channel))
            changed = True
    if changed:
        db.commit()


def _can_access_staff_thread(
    db: Session, thread: MessagingStaffThread, staff: MessagingStaff,
) -> bool:
    if thread.kind == "group":
        return staff.role == "admin" or thread.channel in _channels_for_staff(db, staff)
    return staff.external_id in {
        thread.admin_staff_external_id, thread.member_staff_external_id,
    }


def _staff_thread(
    db: Session, thread_id: str, staff: MessagingStaff,
) -> MessagingStaffThread:
    thread = db.get(MessagingStaffThread, thread_id)
    if not thread:
        raise HTTPException(404, "Chat interno no encontrado")
    if not _can_access_staff_thread(db, thread, staff):
        raise HTTPException(403, "Chat interno no autorizado")
    return thread


def _can_access_conversation(
    db: Session, conv: MessagingConversation, staff: MessagingStaff,
) -> bool:
    org = db.get(MessagingOrganization, conv.organization_id)
    if org and org.company_code.strip().upper() in TEST_COMPANY_CODES:
        return bool(org.private_owner_external_id == staff.external_id)
    if conv.kind == "private":
        return bool(org and org.private_owner_external_id == staff.external_id)
    return conv.kind in _channels_for_staff(db, staff)


def _require_admin(staff: MessagingStaff = Depends(_staff)) -> MessagingStaff:
    if staff.role != "admin":
        raise HTTPException(403, "Se requiere un administrador de mensajeria")
    return staff


def _sync_worker(x_sync_token: str = Header(default="")) -> str:
    expected = get_settings().messaging_sync_token
    if not expected or not secrets.compare_digest(x_sync_token, expected):
        raise HTTPException(401, "Sincronizador no autorizado")
    return "synology"


def _client(
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
    msg_session: str = Cookie(default=""),
) -> MessagingClient:
    token = authorization.removeprefix("Bearer ").strip() or msg_session
    if not token:
        raise HTTPException(401, "Sesion requerida")
    session = db.scalar(select(MessagingSession).where(MessagingSession.token_hash == hash_token(token)))
    if not session or session.revoked_at or is_expired(session.expires_at):
        raise HTTPException(401, "Sesion caducada")
    client = db.get(MessagingClient, session.client_id)
    if not client or not client.active:
        raise HTTPException(403, "Cuenta inactiva")
    return client


def _organization(db: Session, code: str) -> MessagingOrganization:
    item = db.scalar(select(MessagingOrganization).where(MessagingOrganization.company_code == code))
    if not item:
        raise HTTPException(404, "Empresa no encontrada")
    return item


def _conversation_for_staff(db: Session, conversation_id: str, staff: MessagingStaff) -> MessagingConversation:
    conv = db.get(MessagingConversation, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversacion no encontrada")
    if not _can_access_conversation(db, conv, staff):
        raise HTTPException(403, "Canal no autorizado")
    return conv


def _conversation_for_client(db: Session, conversation_id: str, client: MessagingClient) -> MessagingConversation:
    conv = db.get(MessagingConversation, conversation_id)
    if not conv or conv.organization_id != client.organization_id:
        raise HTTPException(404, "Conversacion no encontrada")
    return conv


def _event(db: Session, conv: MessagingConversation, event_type: str) -> None:
    db.add(MessagingEvent(
        organization_id=conv.organization_id,
        conversation_id=conv.id,
        event_type=event_type,
    ))


def _serialize_conversation(db: Session, conv: MessagingConversation) -> dict:
    org = db.get(MessagingOrganization, conv.organization_id)
    last = db.scalar(
        select(MessagingMessage).where(MessagingMessage.conversation_id == conv.id)
        .order_by(MessagingMessage.created_at.desc()).limit(1)
    )
    active_client_count = int(db.scalar(select(func.count(MessagingClient.id)).where(
        MessagingClient.organization_id == conv.organization_id,
        MessagingClient.active.is_(True),
        MessagingClient.password_hash != "",
    )) or 0)
    return {
        "id": conv.id, "company_code": org.company_code, "company_name": org.name,
        "kind": conv.kind, "state": conv.state,
        "active_client_count": active_client_count,
        "assigned_staff_external_id": conv.assigned_staff_external_id,
        "updated_at": conv.updated_at.isoformat(),
        "last_message": _serialize_message(db, last) if last else None,
    }


def _serialize_message(db: Session, item: MessagingMessage, audience: str = "") -> dict:
    attachments = list(db.scalars(select(MessagingAttachment).where(MessagingAttachment.message_id == item.id)))
    author_name = item.author_name
    author_avatar_url = ""
    if item.author_type == "staff":
        author = db.get(MessagingStaff, item.author_id)
        if author:
            author_name = author.chat_alias.strip() or item.author_name
            if author.avatar_storage_key and audience in {"client", "staff"}:
                author_avatar_url = f"/api/v1/messaging/{audience}/avatars/{author.external_id}"
    return {
        "id": item.id, "conversation_id": item.conversation_id,
        "author_type": item.author_type, "author_id": item.author_id,
        "author_name": author_name, "author_avatar_url": author_avatar_url,
        "body": item.body,
        "created_at": item.created_at.isoformat(),
        "attachments": [{
            "id": a.id, "name": a.name, "content_type": a.content_type,
            "size": a.size, "sha256": a.sha256, "direction": a.direction,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "local_confirmed": bool(a.local_confirmed_at),
        } for a in attachments],
    }


def _unread_count(db: Session, conv: MessagingConversation, actor_type: str, actor_id: str) -> int:
    read = db.scalar(select(MessagingRead).where(
        MessagingRead.conversation_id == conv.id,
        MessagingRead.actor_type == actor_type,
        MessagingRead.actor_id == actor_id,
    ))
    stmt = select(func.count(MessagingMessage.id)).where(
        MessagingMessage.conversation_id == conv.id,
        MessagingMessage.author_type != actor_type,
    )
    if read:
        stmt = stmt.where(MessagingMessage.created_at > read.read_at)
    return int(db.scalar(stmt) or 0)


def _queue_staff_pushes(
    db: Session, background: BackgroundTasks, conv: MessagingConversation,
) -> None:
    if not push_configured():
        return
    org = db.get(MessagingOrganization, conv.organization_id)
    if org.company_code.strip().upper() in TEST_COMPANY_CODES or conv.kind == "private":
        staff_ids = {org.private_owner_external_id} if org.private_owner_external_id else set()
    else:
        staff_ids = set(db.scalars(select(MessagingStaffChannel.staff_external_id).where(
            MessagingStaffChannel.channel == conv.kind,
        )))
    if not staff_ids:
        return
    subscriptions = db.scalars(select(MessagingPushSubscription).where(
        MessagingPushSubscription.staff_external_id.in_(staff_ids),
        MessagingPushSubscription.active.is_(True),
    )).all()
    labels = {"laboral": "Laboral", "fiscal": "Contable / Fiscal", "private": "Directo"}
    payload = {
        "title": f"Nuevo mensaje · {org.name}",
        "body": f"Canal {labels.get(conv.kind, conv.kind)}",
        "url": f"/equipo/mensajes?conversation={conv.id}",
        "tag": f"conversation-{conv.id}",
    }
    for subscription in subscriptions:
        background.add_task(send_push, {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }, payload)


def _queue_client_pushes(
    db: Session, background: BackgroundTasks, conv: MessagingConversation,
) -> None:
    if not push_configured():
        return
    client_ids = list(db.scalars(select(MessagingClient.id).where(
        MessagingClient.organization_id == conv.organization_id,
        MessagingClient.active.is_(True),
    )))
    if not client_ids:
        return
    subscriptions = db.scalars(select(MessagingClientPushSubscription).where(
        MessagingClientPushSubscription.client_id.in_(client_ids),
        MessagingClientPushSubscription.active.is_(True),
    )).all()
    payload = {
        "title": "Nuevo mensaje de Gestinem",
        "body": "Tienes una nueva respuesta del despacho.",
        "url": f"/mensajes?conversation={conv.id}",
        "tag": f"client-conversation-{conv.id}",
    }
    for subscription in subscriptions:
        background.add_task(send_push, {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }, payload)


def _create_message(
    db: Session, conv: MessagingConversation, *, actor_type: str, actor_id: str,
    actor_name: str, body: str, idempotency_key: str, files: list[UploadFile],
) -> MessagingMessage:
    existing = db.scalar(select(MessagingMessage).where(
        MessagingMessage.conversation_id == conv.id,
        MessagingMessage.idempotency_key == idempotency_key,
    ))
    if existing:
        return existing
    message = MessagingMessage(
        conversation_id=conv.id, author_type=actor_type, author_id=actor_id,
        author_name=actor_name, body=body.strip(), idempotency_key=idempotency_key,
    )
    db.add(message)
    db.flush()
    storage = MessagingStorage() if files else None
    for upload in files:
        content = upload.file.read(MAX_ATTACHMENT + 1)
        if len(content) > MAX_ATTACHMENT:
            raise HTTPException(413, "El adjunto supera 50 MB")
        name = safe_name(upload.filename or "adjunto")
        suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(415, f"Formato no permitido: {suffix or '(sin extension)'}")
        key = storage.put(content, name)
        outgoing = actor_type == "staff"
        db.add(MessagingAttachment(
            message_id=message.id, name=name,
            content_type=upload.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream",
            size=len(content), sha256=hashlib.sha256(content).hexdigest(), storage_key=key,
            direction="outgoing" if outgoing else "incoming",
            expires_at=(utcnow() + timedelta(days=get_settings().messaging_attachment_days)) if outgoing else None,
        ))
    conv.state = "pendiente"
    conv.updated_at = utcnow()
    _event(db, conv, "message_created")
    db.commit()
    db.refresh(message)
    return message


@router.put("/internal/staff/{external_id}", dependencies=[Depends(require_internal_key)])
def put_staff(external_id: str, payload: StaffIn, db: Session = Depends(get_db)):
    if external_id != payload.external_id:
        raise HTTPException(422, "Identificador incoherente")
    item = db.get(MessagingStaff, external_id) or MessagingStaff(external_id=external_id)
    item.name, item.email = payload.name, payload.email.strip().lower()
    item.chat_alias = payload.chat_alias.strip()
    item.role, item.active = payload.role, payload.active
    if payload.channels is not None:
        channels = set(payload.channels)
        if not channels <= STAFF_CHANNELS:
            raise HTTPException(422, "Canal no valido")
        db.query(MessagingStaffChannel).filter(
            MessagingStaffChannel.staff_external_id == external_id,
        ).delete(synchronize_session=False)
        db.add_all([
            MessagingStaffChannel(staff_external_id=external_id, channel=channel)
            for channel in sorted(channels)
        ])
    db.add(item); db.commit()
    return {"ok": True}


@router.post("/internal/devices/{device_id}", dependencies=[Depends(require_internal_key)])
def enroll_device(device_id: str, db: Session = Depends(get_db)):
    token = new_token()
    item = db.get(MessagingDevice, device_id) or MessagingDevice(
        id=device_id[:120], name=device_id[:160], token_hash="",
    )
    item.token_hash = hash_token(token); item.active = True
    db.add(item); db.commit()
    return {"device_id": item.id, "device_token": token}


@router.put("/internal/organizations/{company_code}", dependencies=[Depends(require_internal_key)])
def put_organization(company_code: str, payload: OrganizationIn, db: Session = Depends(get_db)):
    if company_code != payload.company_code:
        raise HTTPException(422, "Codigo incoherente")
    item = db.scalar(select(MessagingOrganization).where(MessagingOrganization.company_code == company_code))
    if not item:
        item = MessagingOrganization(company_code=company_code, name=payload.name)
        db.add(item); db.flush()
        db.add_all([
            MessagingConversation(organization_id=item.id, kind="laboral"),
            MessagingConversation(organization_id=item.id, kind="fiscal"),
            MessagingConversation(organization_id=item.id, kind="private"),
        ])
    item.name = payload.name
    item.active = payload.active
    if payload.private_owner_external_id is not None:
        item.private_owner_external_id = payload.private_owner_external_id
    db.commit()
    return {"id": item.id, "ok": True}


@router.post("/internal/invitations", dependencies=[Depends(require_internal_key)])
def create_invitation(payload: InviteIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    org = _organization(db, payload.company_code)
    email = payload.email.strip().lower()
    client = db.scalar(select(MessagingClient).where(
        MessagingClient.email == email,
    ))
    if not client:
        client = MessagingClient(organization_id=org.id, name=payload.name.strip(), email=email)
        db.add(client); db.flush()
    else:
        if client.organization_id != org.id:
            raise HTTPException(409, "El email ya pertenece a otra empresa")
        client.name, client.active = payload.name.strip(), True
    token = new_token()
    invitation = MessagingInvitation(
        client_id=client.id, token_hash=hash_token(token), expires_at=invitation_expiry(),
    )
    db.add(invitation); db.commit()
    url = f"{get_settings().messaging_public_base_url}/mensajes?invite={token}"
    email_queued = payload.send_email and mail_configured()
    if email_queued:
        background.add_task(send_invitation, client.email, client.name, url)
    return {
        "invitation_id": invitation.id,
        "url": url, "email_queued": email_queued,
        "expires_at": invitation.expires_at.isoformat(),
    }


def _staff_msal_app():
    cfg = get_settings()
    if not (cfg.messaging_staff_tenant_id and cfg.messaging_staff_client_id and cfg.messaging_staff_client_secret):
        raise HTTPException(503, "Acceso Microsoft del despacho no configurado")
    return msal.ConfidentialClientApplication(
        cfg.messaging_staff_client_id,
        authority=f"https://login.microsoftonline.com/{cfg.messaging_staff_tenant_id}",
        client_credential=cfg.messaging_staff_client_secret,
    )


def _staff_redirect_uri() -> str:
    return f"{get_settings().messaging_public_base_url}/api/v1/messaging/staff-auth/callback"


@router.get("/staff-auth/login")
def staff_auth_login(db: Session = Depends(get_db)):
    flow = _staff_msal_app().initiate_auth_code_flow(
        # MSAL agrega automaticamente openid/profile/offline_access.
        scopes=["email"],
        redirect_uri=_staff_redirect_uri(),
    )
    state = str(flow.get("state") or "")
    if not state or not flow.get("auth_uri"):
        raise HTTPException(502, "Microsoft no pudo iniciar el acceso")
    db.add(MessagingStaffAuthFlow(
        state=state,
        flow_json=json.dumps(flow),
        expires_at=utcnow() + timedelta(minutes=10),
    ))
    db.commit()
    return RedirectResponse(str(flow["auth_uri"]), status_code=302)


@router.get("/staff-auth/callback")
def staff_auth_callback(request: Request, db: Session = Depends(get_db)):
    state = str(request.query_params.get("state") or "")
    stored = db.get(MessagingStaffAuthFlow, state)
    if not stored or is_expired(stored.expires_at):
        raise HTTPException(400, "El acceso de Microsoft ha caducado")
    try:
        result = _staff_msal_app().acquire_token_by_auth_code_flow(
            json.loads(stored.flow_json), dict(request.query_params),
        )
    except ValueError as exc:
        raise HTTPException(400, "Microsoft no pudo validar el acceso") from exc
    finally:
        db.delete(stored)
        db.commit()
    claims = result.get("id_token_claims") or {}
    email = str(claims.get("preferred_username") or claims.get("email") or "").strip().lower()
    external_id = str(claims.get("oid") or claims.get("sub") or "").strip()
    name = str(claims.get("name") or email).strip()
    domain = get_settings().messaging_staff_allowed_domain
    if not email or not external_id or (domain and not email.endswith(f"@{domain}")):
        raise HTTPException(403, "La cuenta no pertenece al despacho")
    admin_emails = {
        value.strip().lower()
        for value in get_settings().messaging_staff_admin_emails.replace(";", ",").split(",")
        if value.strip()
    }
    staff = db.scalar(select(MessagingStaff).where(MessagingStaff.entra_oid == external_id))
    if not staff:
        # Compatibilidad con empleados creados antes de separar el identificador
        # interno del OID de Microsoft Entra.
        staff = db.get(MessagingStaff, external_id)
    if not staff:
        staff = db.scalar(select(MessagingStaff).where(MessagingStaff.email == email))
    if not staff:
        if email not in admin_emails:
            raise HTTPException(403, "Tu cuenta todavia no ha sido autorizada por un administrador")
        staff = MessagingStaff(
            external_id=str(uuid.uuid4()), name=name, email=email, entra_oid=external_id,
            role="admin", active=True,
        )
    else:
        if staff.entra_oid and staff.entra_oid != external_id:
            raise HTTPException(403, "La cuenta esta vinculada a otra identidad de Microsoft")
        if not staff.active:
            raise HTTPException(403, "Usuario del despacho suspendido")
        staff.name, staff.email = name, email
        staff.entra_oid = external_id
        if email in admin_emails:
            staff.role = "admin"
    db.add(staff)
    token = new_token()
    db.add(MessagingStaffSession(
        staff_external_id=staff.external_id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=30),
    ))
    db.commit()
    response = RedirectResponse("/equipo/mensajes", status_code=302)
    response.set_cookie(
        "msg_staff_session", token, httponly=True, secure=True,
        samesite="lax", max_age=30 * 86400,
    )
    return response


@router.post("/staff-auth/logout")
def staff_auth_logout(
    response: Response, request: Request, db: Session = Depends(get_db),
):
    token = request.cookies.get("msg_staff_session", "")
    if token:
        item = db.scalar(select(MessagingStaffSession).where(
            MessagingStaffSession.token_hash == hash_token(token),
        ))
        if item:
            item.revoked_at = utcnow()
            db.commit()
    response.delete_cookie("msg_staff_session")
    return {"ok": True}


@router.get("/staff/me")
def staff_me(staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    return {
        "id": staff.external_id, "name": staff.name, "email": staff.email,
        "role": staff.role, "chat_alias": staff.chat_alias,
        "avatar_configured": bool(staff.avatar_storage_key),
        "channels": sorted(_channels_for_staff(db, staff)),
    }


@router.get("/staff/push/config")
def staff_push_config(_staff_user: MessagingStaff = Depends(_staff)):
    return {
        "enabled": push_configured(),
        "public_key": get_settings().messaging_vapid_public_key if push_configured() else "",
    }


@router.post("/staff/push/subscriptions")
def subscribe_staff_push(
    payload: PushSubscriptionIn, staff: MessagingStaff = Depends(_staff),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(MessagingPushSubscription).where(
        MessagingPushSubscription.endpoint == payload.endpoint,
    ))
    if not item:
        item = MessagingPushSubscription(
            staff_external_id=staff.external_id, endpoint=payload.endpoint,
            p256dh=payload.p256dh, auth=payload.auth,
        )
    else:
        item.staff_external_id = staff.external_id
        item.p256dh, item.auth, item.active = payload.p256dh, payload.auth, True
    db.add(item)
    db.commit()
    return {"ok": True}


@router.post("/staff/push/test")
def test_staff_push(
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    if not push_configured():
        raise HTTPException(503, "Los avisos push no estan configurados")
    subscriptions = db.scalars(select(MessagingPushSubscription).where(
        MessagingPushSubscription.staff_external_id == staff.external_id,
        MessagingPushSubscription.active.is_(True),
    )).all()
    if not subscriptions:
        raise HTTPException(409, "Este dispositivo no tiene los avisos activados")
    payload = {
        "title": "Avisos de Gestinem activados",
        "body": "Este equipo recibira los nuevos mensajes asignados.",
        "url": "/equipo/mensajes",
        "tag": "gestinem-push-test",
    }
    delivered = sum(bool(send_push({
        "endpoint": item.endpoint,
        "keys": {"p256dh": item.p256dh, "auth": item.auth},
    }, payload)) for item in subscriptions)
    if not delivered:
        raise HTTPException(502, "El navegador no ha aceptado la notificacion de prueba")
    return {"ok": True, "delivered": delivered}


@router.get("/client/push/config")
def client_push_config(_client_user: MessagingClient = Depends(_client)):
    return {
        "enabled": push_configured(),
        "public_key": get_settings().messaging_vapid_public_key if push_configured() else "",
    }


@router.post("/client/push/subscriptions")
def subscribe_client_push(
    payload: PushSubscriptionIn, client: MessagingClient = Depends(_client),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(MessagingClientPushSubscription).where(
        MessagingClientPushSubscription.endpoint == payload.endpoint,
    ))
    if not item:
        item = MessagingClientPushSubscription(
            client_id=client.id, endpoint=payload.endpoint,
            p256dh=payload.p256dh, auth=payload.auth,
        )
    else:
        item.client_id = client.id
        item.p256dh, item.auth, item.active = payload.p256dh, payload.auth, True
    db.add(item)
    db.commit()
    return {"ok": True}


@router.post("/client/push/test")
def test_client_push(
    client: MessagingClient = Depends(_client), db: Session = Depends(get_db),
):
    if not push_configured():
        raise HTTPException(503, "Los avisos push no estan configurados")
    subscriptions = db.scalars(select(MessagingClientPushSubscription).where(
        MessagingClientPushSubscription.client_id == client.id,
        MessagingClientPushSubscription.active.is_(True),
    )).all()
    if not subscriptions:
        raise HTTPException(409, "Este dispositivo no tiene los avisos activados")
    payload = {
        "title": "Avisos de Gestinem activados",
        "body": "Recibiras un aviso cuando el despacho te responda.",
        "url": "/mensajes",
        "tag": "gestinem-client-push-test",
    }
    delivered = sum(bool(send_push({
        "endpoint": item.endpoint,
        "keys": {"p256dh": item.p256dh, "auth": item.auth},
    }, payload)) for item in subscriptions)
    if not delivered:
        raise HTTPException(502, "El navegador no ha aceptado la notificacion de prueba")
    return {"ok": True, "delivered": delivered}


def _serialize_staff_thread_message(db: Session, item: MessagingStaffThreadMessage) -> dict:
    author = db.get(MessagingStaff, item.author_staff_external_id)
    return {
        "id": item.id, "thread_id": item.thread_id,
        "author_id": item.author_staff_external_id,
        "author_name": (author.chat_alias.strip() or author.name) if author else item.author_name,
        "author_avatar_url": (
            f"/api/v1/messaging/staff/avatars/{author.external_id}"
            if author and author.avatar_storage_key else ""
        ),
        "body": item.body, "created_at": item.created_at.isoformat(),
    }


def _staff_thread_title(db: Session, thread: MessagingStaffThread, staff: MessagingStaff) -> str:
    if thread.kind == "group":
        return "Equipo Laboral" if thread.channel == "laboral" else "Equipo Contable / Fiscal"
    other_id = (
        thread.member_staff_external_id
        if staff.external_id == thread.admin_staff_external_id
        else thread.admin_staff_external_id
    )
    other = db.get(MessagingStaff, other_id)
    return (other.chat_alias.strip() or other.name) if other else "Chat privado"


def _staff_thread_counterpart(
    db: Session, thread: MessagingStaffThread, staff: MessagingStaff,
) -> MessagingStaff | None:
    if thread.kind != "direct":
        return None
    other_id = (
        thread.member_staff_external_id
        if staff.external_id == thread.admin_staff_external_id
        else thread.admin_staff_external_id
    )
    return db.get(MessagingStaff, other_id)


def _staff_thread_unread(db: Session, thread: MessagingStaffThread, staff: MessagingStaff) -> int:
    read = db.scalar(select(MessagingStaffThreadRead).where(
        MessagingStaffThreadRead.thread_id == thread.id,
        MessagingStaffThreadRead.staff_external_id == staff.external_id,
    ))
    stmt = select(func.count(MessagingStaffThreadMessage.id)).where(
        MessagingStaffThreadMessage.thread_id == thread.id,
        MessagingStaffThreadMessage.author_staff_external_id != staff.external_id,
    )
    if read:
        stmt = stmt.where(MessagingStaffThreadMessage.created_at > read.read_at)
    return int(db.scalar(stmt) or 0)


def _serialize_staff_thread(
    db: Session, thread: MessagingStaffThread, staff: MessagingStaff,
) -> dict:
    last = db.scalar(select(MessagingStaffThreadMessage).where(
        MessagingStaffThreadMessage.thread_id == thread.id,
    ).order_by(MessagingStaffThreadMessage.created_at.desc()).limit(1))
    counterpart = _staff_thread_counterpart(db, thread, staff)
    return {
        "id": thread.id, "kind": thread.kind, "channel": thread.channel,
        "title": _staff_thread_title(db, thread, staff),
        "counterpart_id": counterpart.external_id if counterpart else "",
        "counterpart_name": (
            counterpart.chat_alias.strip() or counterpart.name
        ) if counterpart else "",
        "counterpart_avatar_url": (
            f"/api/v1/messaging/staff/avatars/{counterpart.external_id}"
            if counterpart and counterpart.avatar_storage_key else ""
        ),
        "unread_count": _staff_thread_unread(db, thread, staff),
        "updated_at": thread.updated_at.isoformat(),
        "last_message": _serialize_staff_thread_message(db, last) if last else None,
    }


@router.get("/staff/internal/threads")
def list_staff_threads(
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    _ensure_staff_group_threads(db)
    rows = db.scalars(select(MessagingStaffThread).order_by(
        MessagingStaffThread.updated_at.desc(), MessagingStaffThread.kind,
    )).all()
    return [
        _serialize_staff_thread(db, row, staff)
        for row in rows if _can_access_staff_thread(db, row, staff)
    ]


@router.post("/staff/internal/direct/{member_external_id}", status_code=201)
def create_staff_direct_thread(
    member_external_id: str, admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    member = db.get(MessagingStaff, member_external_id)
    if not member or not member.active or member.external_id == admin.external_id:
        raise HTTPException(404, "Empleado no disponible")
    key = f"direct:{admin.external_id}:{member.external_id}"
    thread = db.scalar(select(MessagingStaffThread).where(MessagingStaffThread.key == key))
    if not thread:
        thread = MessagingStaffThread(
            key=key, kind="direct", admin_staff_external_id=admin.external_id,
            member_staff_external_id=member.external_id,
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return _serialize_staff_thread(db, thread, admin)


@router.get("/staff/internal/threads/{thread_id}/messages")
def staff_thread_messages(
    thread_id: str, staff: MessagingStaff = Depends(_staff),
    db: Session = Depends(get_db),
):
    thread = _staff_thread(db, thread_id, staff)
    rows = db.scalars(select(MessagingStaffThreadMessage).where(
        MessagingStaffThreadMessage.thread_id == thread.id,
    ).order_by(MessagingStaffThreadMessage.created_at).limit(500)).all()
    return [_serialize_staff_thread_message(db, row) for row in rows]


@router.post("/staff/internal/threads/{thread_id}/read")
def mark_staff_thread_read(
    thread_id: str, staff: MessagingStaff = Depends(_staff),
    db: Session = Depends(get_db),
):
    thread = _staff_thread(db, thread_id, staff)
    last = db.scalar(select(MessagingStaffThreadMessage).where(
        MessagingStaffThreadMessage.thread_id == thread.id,
    ).order_by(MessagingStaffThreadMessage.created_at.desc()).limit(1))
    read = db.scalar(select(MessagingStaffThreadRead).where(
        MessagingStaffThreadRead.thread_id == thread.id,
        MessagingStaffThreadRead.staff_external_id == staff.external_id,
    )) or MessagingStaffThreadRead(thread_id=thread.id, staff_external_id=staff.external_id)
    read.last_message_id = last.id if last else ""
    read.read_at = utcnow()
    db.add(read)
    db.commit()
    return {"ok": True}


def _queue_internal_pushes(
    db: Session, background: BackgroundTasks, thread: MessagingStaffThread,
    sender: MessagingStaff,
) -> None:
    if not push_configured():
        return
    if thread.kind == "direct":
        recipient_ids = {
            thread.admin_staff_external_id, thread.member_staff_external_id,
        }
    else:
        recipient_ids = set(db.scalars(select(MessagingStaff.external_id).where(
            MessagingStaff.active.is_(True), MessagingStaff.role == "admin",
        )))
        recipient_ids.update(db.scalars(select(MessagingStaffChannel.staff_external_id).where(
            MessagingStaffChannel.channel == thread.channel,
        )))
    recipient_ids.discard(sender.external_id)
    if not recipient_ids:
        return
    subscriptions = db.scalars(select(MessagingPushSubscription).where(
        MessagingPushSubscription.staff_external_id.in_(recipient_ids),
        MessagingPushSubscription.active.is_(True),
    )).all()
    title = (
        _staff_thread_title(db, thread, sender)
        if thread.kind == "group" else (sender.chat_alias.strip() or sender.name)
    )
    payload = {
        "title": f"Nuevo mensaje interno · {title}",
        "body": sender.chat_alias.strip() or sender.name,
        "url": f"/equipo/mensajes?internal={thread.id}",
        "tag": f"internal-{thread.id}",
    }
    for subscription in subscriptions:
        background.add_task(send_push, {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }, payload)


@router.post("/staff/internal/threads/{thread_id}/messages")
def post_staff_thread_message(
    thread_id: str, background: BackgroundTasks,
    body: str = Form(...), idempotency_key: str = Form(default=""),
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    thread = _staff_thread(db, thread_id, staff)
    text_body = body.strip()
    if not text_body:
        raise HTTPException(422, "El mensaje esta vacio")
    if len(text_body) > 10000:
        raise HTTPException(422, "El mensaje es demasiado largo")
    key = idempotency_key.strip() or str(uuid.uuid4())
    existing = db.scalar(select(MessagingStaffThreadMessage).where(
        MessagingStaffThreadMessage.thread_id == thread.id,
        MessagingStaffThreadMessage.idempotency_key == key,
    ))
    if existing:
        return _serialize_staff_thread_message(db, existing)
    item = MessagingStaffThreadMessage(
        thread_id=thread.id, author_staff_external_id=staff.external_id,
        author_name=staff.chat_alias.strip() or staff.name,
        body=text_body, idempotency_key=key,
    )
    thread.updated_at = utcnow()
    db.add(item)
    db.add(MessagingEvent(
        organization_id="", conversation_id=thread.id, event_type="internal_message",
    ))
    db.commit()
    db.refresh(item)
    _queue_internal_pushes(db, background, thread, staff)
    return _serialize_staff_thread_message(db, item)


@router.get("/staff/admin/directory")
def staff_directory(
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    rows = db.scalars(select(MessagingStaff).where(
        MessagingStaff.email != "",
    ).order_by(MessagingStaff.name)).all()
    return [{
        "id": row.external_id, "name": row.name, "email": row.email,
        "role": row.role, "active": row.active,
        "linked": bool(row.entra_oid),
        "chat_alias": row.chat_alias,
        "avatar_configured": bool(row.avatar_storage_key),
        "channels": sorted(_channels_for_staff(db, row)),
    } for row in rows]


@router.post("/staff/admin/directory", status_code=201)
def create_staff_user(
    payload: StaffCreateIn,
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    email = _validated_staff_email(payload.email)
    if payload.role not in STAFF_ROLES:
        raise HTTPException(422, "Rol no valido")
    channels = set(payload.channels)
    if not channels <= STAFF_CHANNELS:
        raise HTTPException(422, "Canal no valido")
    if db.scalar(select(MessagingStaff).where(MessagingStaff.email == email)):
        raise HTTPException(409, "Ya existe un usuario con ese email")
    staff = MessagingStaff(
        external_id=str(uuid.uuid4()), name=payload.name.strip(), email=email,
        entra_oid="", chat_alias=payload.chat_alias.strip(),
        role=payload.role, active=payload.active,
    )
    db.add(staff)
    db.flush()
    _set_staff_channels(db, staff.external_id, channels)
    db.commit()
    return {
        "id": staff.external_id, "name": staff.name, "email": staff.email,
        "role": staff.role, "active": staff.active, "linked": False,
        "chat_alias": staff.chat_alias, "avatar_configured": False,
        "channels": sorted(channels),
    }


@router.put("/staff/admin/directory/{external_id}")
def update_staff_permissions(
    external_id: str, payload: StaffPermissionsIn,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    staff = db.get(MessagingStaff, external_id)
    if not staff:
        raise HTTPException(404, "Empleado no encontrado")
    channels = set(payload.channels)
    role = payload.role or staff.role
    if role not in STAFF_ROLES:
        raise HTTPException(422, "Rol no valido")
    if staff.external_id == admin.external_id and (not payload.active or role != "admin"):
        raise HTTPException(409, "No puedes suspender ni retirar tu propio acceso de administrador")
    if staff.role == "admin" and staff.active and (not payload.active or role != "admin"):
        other_admins = int(db.scalar(select(func.count(MessagingStaff.external_id)).where(
            MessagingStaff.role == "admin", MessagingStaff.active.is_(True),
            MessagingStaff.external_id != external_id,
        )) or 0)
        if not other_admins:
            raise HTTPException(409, "Debe permanecer al menos un administrador activo")
    if payload.email is not None:
        email = _validated_staff_email(payload.email)
        duplicate = db.scalar(select(MessagingStaff).where(
            MessagingStaff.email == email,
            MessagingStaff.external_id != external_id,
        ))
        if duplicate:
            raise HTTPException(409, "Ya existe un usuario con ese email")
        staff.email = email
    if payload.name is not None:
        staff.name = payload.name.strip()
    if payload.chat_alias is not None:
        staff.chat_alias = payload.chat_alias.strip()
    _set_staff_channels(db, external_id, channels)
    staff.role = role
    staff.active = payload.active
    if not staff.active:
        _revoke_staff_access(db, external_id)
    db.commit()
    return {
        "ok": True, "channels": sorted(channels), "role": staff.role,
        "active": staff.active, "linked": bool(staff.entra_oid),
        "chat_alias": staff.chat_alias,
    }


def _normalized_avatar(upload: UploadFile) -> bytes:
    content = upload.file.read(MAX_AVATAR + 1)
    if len(content) > MAX_AVATAR:
        raise HTTPException(413, "La imagen supera 5 MB")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > 25_000_000:
                raise HTTPException(413, "La imagen tiene demasiada resolucion")
            # Las fotos tomadas con el movil suelen guardar la orientacion en
            # EXIF sin girar fisicamente los pixeles. Hay que aplicarla antes
            # de recortar el avatar, porque los navegadores no conservan ese
            # metadato al recibir el WEBP normalizado.
            source = ImageOps.exif_transpose(source)
            avatar = ImageOps.fit(
                source.convert("RGB"), (256, 256), method=Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            avatar.save(output, format="WEBP", quality=86, method=6)
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(415, "El archivo no es una imagen valida") from exc


@router.put("/staff/admin/directory/{external_id}/avatar")
def update_staff_avatar(
    external_id: str, avatar: UploadFile = File(...),
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    staff = db.get(MessagingStaff, external_id)
    if not staff:
        raise HTTPException(404, "Empleado no encontrado")
    content = _normalized_avatar(avatar)
    storage = MessagingStorage()
    old_key = staff.avatar_storage_key
    staff.avatar_storage_key = storage.put(content, f"avatar-{external_id}.webp")
    staff.avatar_content_type = "image/webp"
    db.commit()
    if old_key:
        try:
            storage.delete(old_key)
        except Exception:
            pass
    return {"ok": True, "avatar_configured": True}


@router.delete("/staff/admin/directory/{external_id}/avatar")
def delete_staff_avatar(
    external_id: str,
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    staff = db.get(MessagingStaff, external_id)
    if not staff:
        raise HTTPException(404, "Empleado no encontrado")
    key = staff.avatar_storage_key
    staff.avatar_storage_key = ""
    staff.avatar_content_type = ""
    db.commit()
    if key:
        try:
            MessagingStorage().delete(key)
        except Exception:
            pass
    return {"ok": True}


@router.post("/staff/admin/directory/{external_id}/revoke-sessions")
def revoke_staff_sessions(
    external_id: str,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    staff = db.get(MessagingStaff, external_id)
    if not staff:
        raise HTTPException(404, "Empleado no encontrado")
    if staff.external_id == admin.external_id:
        raise HTTPException(409, "Usa Salir para cerrar tu sesion actual")
    _revoke_staff_access(db, external_id)
    db.commit()
    return {"ok": True}


@router.get("/staff/admin/organizations")
def staff_organizations(
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    rows = db.scalars(select(MessagingOrganization).order_by(MessagingOrganization.name)).all()
    return [{
        "company_code": row.company_code, "name": row.name, "active": row.active,
        "private_owner_external_id": row.private_owner_external_id,
    } for row in rows if (
        row.company_code.strip().upper() not in TEST_COMPANY_CODES
        or row.private_owner_external_id == admin.external_id
    )]


@router.put("/staff/admin/organizations/{company_code}")
def staff_put_organization(
    company_code: str, payload: OrganizationIn,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    if company_code.strip().upper() in TEST_COMPANY_CODES:
        current = db.scalar(select(MessagingOrganization).where(
            MessagingOrganization.company_code == company_code,
        ))
        if current and current.private_owner_external_id != admin.external_id:
            raise HTTPException(403, "Cliente de pruebas privado")
        if not current and payload.private_owner_external_id not in {None, admin.external_id}:
            raise HTTPException(403, "Cliente de pruebas privado")
        if payload.private_owner_external_id is None:
            payload.private_owner_external_id = admin.external_id
    return put_organization(company_code, payload, db)


@router.post("/staff/admin/invitations")
def staff_create_invitation(
    payload: InviteIn, background: BackgroundTasks,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    org = _organization(db, payload.company_code)
    if (
        org.company_code.strip().upper() in TEST_COMPANY_CODES
        and org.private_owner_external_id != admin.external_id
    ):
        raise HTTPException(403, "Cliente de pruebas privado")
    return create_invitation(payload, background, db)


@router.post("/auth/accept-invite")
def accept_invite(payload: AcceptInviteIn, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(MessagingInvitation).where(
        MessagingInvitation.token_hash == hash_token(payload.token),
    ))
    if not invitation or invitation.used_at or invitation.revoked_at or is_expired(invitation.expires_at):
        raise HTTPException(400, "Invitacion no valida o caducada")
    client = db.get(MessagingClient, invitation.client_id)
    client.password_hash = hash_password(payload.password)
    invitation.used_at = utcnow()
    token = _new_session(db, client)
    db.commit()
    _set_cookie(response, token)
    return {"token": token, "client": {"id": client.id, "name": client.name, "email": client.email}}


@router.post("/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    client = db.scalar(select(MessagingClient).where(MessagingClient.email == payload.email.strip().lower()))
    if not client or not client.active or not verify_password(payload.password, client.password_hash):
        raise HTTPException(401, "Credenciales no validas")
    token = _new_session(db, client); db.commit(); _set_cookie(response, token)
    return {"token": token, "client": {"id": client.id, "name": client.name, "email": client.email}}


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    client = db.scalar(select(MessagingClient).where(
        MessagingClient.email == payload.email.strip().lower(),
        MessagingClient.active.is_(True),
    ))
    if client:
        token = new_token()
        db.add(MessagingPasswordReset(
            client_id=client.id, token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=1),
        ))
        db.commit()
        if mail_configured():
            url = f"{get_settings().messaging_public_base_url}/mensajes?reset={token}"
            background.add_task(send_password_reset, client.email, client.name, url)
    # Respuesta deliberadamente identica para no revelar cuentas existentes.
    return {"ok": True, "email_queued": mail_configured()}


@router.post("/auth/reset-password")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    reset = db.scalar(select(MessagingPasswordReset).where(
        MessagingPasswordReset.token_hash == hash_token(payload.token),
    ))
    if not reset or reset.used_at or is_expired(reset.expires_at):
        raise HTTPException(400, "El enlace no es valido o ha caducado")
    client = db.get(MessagingClient, reset.client_id)
    if not client or not client.active:
        raise HTTPException(400, "La cuenta ya no esta disponible")
    client.password_hash = hash_password(payload.password)
    reset.used_at = utcnow()
    for session in db.scalars(select(MessagingSession).where(
        MessagingSession.client_id == client.id,
        MessagingSession.revoked_at.is_(None),
    )).all():
        session.revoked_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def logout(
    response: Response, authorization: str = Header(default=""),
    msg_session: str = Cookie(default=""), db: Session = Depends(get_db),
):
    token = authorization.removeprefix("Bearer ").strip() or msg_session
    if token:
        session = db.scalar(select(MessagingSession).where(MessagingSession.token_hash == hash_token(token)))
        if session:
            session.revoked_at = utcnow(); db.commit()
    response.delete_cookie("msg_session")
    return {"ok": True}


def _new_session(db: Session, client: MessagingClient) -> str:
    token = new_token()
    db.add(MessagingSession(client_id=client.id, token_hash=hash_token(token), expires_at=session_expiry()))
    return token


def _set_cookie(response: Response, token: str) -> None:
    secure = get_settings().messaging_public_base_url.lower().startswith("https://")
    response.set_cookie("msg_session", token, httponly=True, secure=secure, samesite="lax", max_age=30 * 86400)


@router.get("/client/conversations")
def client_conversations(client: MessagingClient = Depends(_client), db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingConversation).where(
        MessagingConversation.organization_id == client.organization_id,
    ).order_by(MessagingConversation.kind)).all()
    result = []
    for row in rows:
        item = _serialize_conversation(db, row)
        item["unread_count"] = _unread_count(db, row, "client", client.id)
        result.append(item)
    return result


@router.get("/staff/conversations")
def staff_conversations(
    active_only: bool = False,
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    stmt = select(MessagingConversation)
    if active_only:
        stmt = stmt.where(
            select(MessagingMessage.id).where(
                MessagingMessage.conversation_id == MessagingConversation.id,
            ).exists()
        )
    rows = db.scalars(stmt.order_by(MessagingConversation.updated_at.desc())).all()
    result = []
    for row in rows:
        if not _can_access_conversation(db, row, staff):
            continue
        item = _serialize_conversation(db, row)
        item["unread_count"] = _unread_count(db, row, "staff", staff.external_id)
        result.append(item)
    return result


@router.get("/{audience}/conversations/{conversation_id}/messages")
def messages(audience: str, conversation_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _resolve_actor(audience, request, db)
    conv = _conversation_for_client(db, conversation_id, actor) if audience == "client" else _conversation_for_staff(db, conversation_id, actor)
    rows = db.scalars(select(MessagingMessage).where(
        MessagingMessage.conversation_id == conv.id,
    ).order_by(MessagingMessage.created_at.asc()).limit(500)).all()
    return [_serialize_message(db, row, audience) for row in rows]


def _resolve_actor(audience: str, request: Request, db: Session):
    if audience == "client":
        return _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
    if audience == "staff":
        return _staff_from_request(db, request)
    raise HTTPException(404)


@router.get("/{audience}/avatars/{external_id}")
def staff_avatar(
    audience: str, external_id: str, request: Request, db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    staff = db.get(MessagingStaff, external_id)
    if not staff or not staff.avatar_storage_key:
        raise HTTPException(404, "Avatar no disponible")
    if audience == "client":
        authored = int(db.scalar(
            select(func.count(MessagingMessage.id))
            .join(MessagingConversation, MessagingConversation.id == MessagingMessage.conversation_id)
            .where(
                MessagingMessage.author_type == "staff",
                MessagingMessage.author_id == external_id,
                MessagingConversation.organization_id == actor.organization_id,
            )
        ) or 0)
        if not authored:
            raise HTTPException(403, "Avatar no autorizado")
    return Response(
        content=MessagingStorage().get(staff.avatar_storage_key),
        media_type=staff.avatar_content_type or "image/webp",
        headers={"Cache-Control": "private, no-cache"},
    )


@router.post("/{audience}/conversations/{conversation_id}/read")
def mark_read(audience: str, conversation_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _resolve_actor(audience, request, db)
    conv = _conversation_for_client(db, conversation_id, actor) if audience == "client" else _conversation_for_staff(db, conversation_id, actor)
    actor_id = actor.id if audience == "client" else actor.external_id
    last = db.scalar(select(MessagingMessage).where(
        MessagingMessage.conversation_id == conv.id,
    ).order_by(MessagingMessage.created_at.desc()).limit(1))
    read = db.scalar(select(MessagingRead).where(
        MessagingRead.conversation_id == conv.id,
        MessagingRead.actor_type == audience,
        MessagingRead.actor_id == actor_id,
    ))
    last_id = last.id if last else ""
    if read and read.last_message_id == last_id:
        return {"ok": True, "changed": False}
    read = read or MessagingRead(conversation_id=conv.id, actor_type=audience, actor_id=actor_id)
    read.last_message_id = last_id
    read.read_at = utcnow(); db.add(read); _event(db, conv, "read_updated"); db.commit()
    return {"ok": True, "changed": True}


@router.post("/{audience}/conversations/{conversation_id}/messages")
def post_message(
    audience: str, conversation_id: str, request: Request,
    background: BackgroundTasks,
    body: str = Form(default=""), idempotency_key: str = Form(default=""),
    files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    conv = _conversation_for_client(db, conversation_id, actor) if audience == "client" else _conversation_for_staff(db, conversation_id, actor)
    if not body.strip() and not files:
        raise HTTPException(422, "El mensaje esta vacio")
    key = idempotency_key.strip() or str(uuid.uuid4())
    item = _create_message(
        db, conv, actor_type=audience, actor_id=(actor.id if audience == "client" else actor.external_id),
        actor_name=(actor.chat_alias.strip() or actor.name) if audience == "staff" else actor.name,
        body=body, idempotency_key=key, files=files,
    )
    if audience == "client":
        _queue_staff_pushes(db, background, conv)
    if audience == "staff":
        _queue_client_pushes(db, background, conv)
    if audience == "staff" and mail_configured():
        clients = db.scalars(select(MessagingClient).where(
            MessagingClient.organization_id == conv.organization_id,
            MessagingClient.active.is_(True),
        )).all()
        for recipient in clients:
            presence = db.get(MessagingPresence, recipient.id)
            if not presence or is_expired(presence.connected_until):
                background.add_task(
                    send_message_notice, recipient.email, recipient.name,
                    f"{get_settings().messaging_public_base_url}/mensajes",
                )
    return _serialize_message(db, item, audience)


@router.patch("/staff/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, payload: ConversationPatch, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    conv = _conversation_for_staff(db, conversation_id, staff)
    if payload.state is not None:
        if payload.state not in {"pendiente", "en_curso", "resuelta"}:
            raise HTTPException(422, "Estado no valido")
        conv.state = payload.state
    if payload.assigned_staff_external_id is not None:
        conv.assigned_staff_external_id = payload.assigned_staff_external_id
    conv.updated_at = utcnow(); _event(db, conv, "conversation_updated"); db.commit()
    return _serialize_conversation(db, conv)


@router.get("/staff/attachments/pending")
def pending_attachments(staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingAttachment).where(
        MessagingAttachment.direction == "incoming",
        MessagingAttachment.local_confirmed_at.is_(None),
    ).order_by(MessagingAttachment.created_at)).all()
    result = []
    for item in rows:
        message = db.get(MessagingMessage, item.message_id)
        conv = db.get(MessagingConversation, message.conversation_id)
        org = db.get(MessagingOrganization, conv.organization_id)
        if not _can_access_conversation(db, conv, staff):
            continue
        result.append({
            "id": item.id, "message_id": message.id, "conversation_id": conv.id,
            "company_code": org.company_code, "company_name": org.name,
            "name": item.name, "size": item.size, "sha256": item.sha256,
            "content_type": item.content_type, "author_name": message.author_name,
            "created_at": item.created_at.isoformat(),
        })
    return result


@router.post("/staff/attachments/{attachment_id}/claim")
def claim_attachment(attachment_id: str, workstation: str = Form(...), staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.direction != "incoming" or item.local_confirmed_at:
        raise HTTPException(404, "Adjunto no disponible")
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_staff(db, message.conversation_id, staff)
    if item.claim_expires_at and not is_expired(item.claim_expires_at) and item.claimed_by != workstation:
        raise HTTPException(409, "Adjunto reclamado por otro puesto")
    item.claimed_by = workstation[:120]
    item.claim_expires_at = utcnow() + timedelta(minutes=10)
    db.commit()
    return {"ok": True, "claim_expires_at": item.claim_expires_at.isoformat()}


@router.get("/staff/attachments/{attachment_id}/content")
def staff_attachment_content(attachment_id: str, workstation: str, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.claimed_by != workstation or is_expired(item.claim_expires_at):
        raise HTTPException(409, "Concesion de descarga no valida")
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_staff(db, message.conversation_id, staff)
    content = MessagingStorage().get(item.storage_key)
    if hashlib.sha256(content).hexdigest() != item.sha256:
        raise HTTPException(500, "La integridad del adjunto no es valida")
    return Response(content, media_type=item.content_type, headers={"Content-Disposition": f'attachment; filename="{safe_name(item.name)}"'})


@router.post("/staff/attachments/{attachment_id}/confirm-local")
def confirm_local(attachment_id: str, workstation: str = Form(...), sha256: str = Form(...), staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.claimed_by != workstation or not hmac_compare(item.sha256, sha256):
        raise HTTPException(409, "Confirmacion no valida")
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_staff(db, message.conversation_id, staff)
    # Confirmar primero la recepcion local evita redescargas si el borrado cloud
    # funciona pero se pierde la conexion antes de confirmar la transaccion.
    item.local_confirmed_at = utcnow(); item.claim_expires_at = None; db.commit()
    cleanup_pending = False
    try:
        MessagingStorage().delete(item.storage_key)
        item.storage_deleted_at = utcnow(); item.storage_key = ""; db.commit()
    except Exception:
        cleanup_pending = True
    return {"ok": True, "storage_cleanup_pending": cleanup_pending}


def hmac_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(str(left), str(right))


@router.get("/client/attachments/{attachment_id}")
def client_download(attachment_id: str, request: Request, client: MessagingClient = Depends(_client), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.direction != "outgoing" or item.storage_deleted_at or is_expired(item.expires_at):
        raise HTTPException(404, "Adjunto caducado o no disponible")
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_client(db, message.conversation_id, client)
    content = MessagingStorage().get(item.storage_key)
    valid = hmac_compare(hashlib.sha256(content).hexdigest(), item.sha256)
    db.add(MessagingDownload(
        attachment_id=item.id, client_id=client.id,
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:500], sha256=item.sha256, success=valid,
    ))
    db.commit()
    if not valid:
        raise HTTPException(500, "La integridad del adjunto no es valida")
    return Response(content, media_type=item.content_type, headers={"Content-Disposition": f'attachment; filename="{safe_name(item.name)}"'})


@router.get("/staff/attachments/{attachment_id}/downloads")
def download_audit(attachment_id: str, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item:
        raise HTTPException(404)
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_staff(db, message.conversation_id, staff)
    rows = db.scalars(select(MessagingDownload).where(MessagingDownload.attachment_id == item.id).order_by(MessagingDownload.downloaded_at)).all()
    return [{
        "client_id": row.client_id,
        "client_name": (db.get(MessagingClient, row.client_id).name if db.get(MessagingClient, row.client_id) else ""),
        "downloaded_at": row.downloaded_at.isoformat(), "ip": row.ip,
        "user_agent": row.user_agent, "sha256": row.sha256, "success": row.success,
    } for row in rows]


@router.get("/staff/attachments/{attachment_id}/download")
def staff_download_attachment(
    attachment_id: str, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.storage_deleted_at or not item.storage_key:
        raise HTTPException(404, "Adjunto no disponible")
    message = db.get(MessagingMessage, item.message_id)
    _conversation_for_staff(db, message.conversation_id, staff)
    content = MessagingStorage().get(item.storage_key)
    if not hmac_compare(hashlib.sha256(content).hexdigest(), item.sha256):
        raise HTTPException(500, "La integridad del adjunto no es valida")
    return Response(content, media_type=item.content_type, headers={
        "Content-Disposition": f'attachment; filename="{safe_name(item.name)}"',
    })


@router.get("/sync/attachments/pending", dependencies=[Depends(_sync_worker)])
def sync_pending_attachments(db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingAttachment).where(
        MessagingAttachment.direction == "incoming",
        MessagingAttachment.local_confirmed_at.is_(None),
    ).order_by(MessagingAttachment.created_at)).all()
    result = []
    for item in rows:
        message = db.get(MessagingMessage, item.message_id)
        conv = db.get(MessagingConversation, message.conversation_id)
        org = db.get(MessagingOrganization, conv.organization_id)
        result.append({
            "id": item.id, "message_id": message.id, "conversation_id": conv.id,
            "channel": conv.kind, "company_code": org.company_code,
            "company_name": org.name, "name": item.name, "size": item.size,
            "sha256": item.sha256, "content_type": item.content_type,
            "author_name": message.author_name, "created_at": item.created_at.isoformat(),
        })
    return result


@router.put("/sync/organizations", dependencies=[Depends(_sync_worker)])
def sync_organizations(payload: list[OrganizationIn], db: Session = Depends(get_db)):
    synchronized = 0
    for row in payload:
        code = row.company_code.strip()
        item = db.scalar(select(MessagingOrganization).where(
            MessagingOrganization.company_code == code,
        ))
        if not item:
            item = MessagingOrganization(company_code=code, name=row.name.strip())
            db.add(item); db.flush()
            db.add_all([
                MessagingConversation(organization_id=item.id, kind="laboral"),
                MessagingConversation(organization_id=item.id, kind="fiscal"),
                MessagingConversation(organization_id=item.id, kind="private"),
            ])
        item.name = row.name.strip()
        item.active = row.active
        db.add(item)
        synchronized += 1
    db.commit()
    return {"ok": True, "synchronized": synchronized}


@router.post("/sync/attachments/{attachment_id}/claim", dependencies=[Depends(_sync_worker)])
def sync_claim_attachment(
    attachment_id: str, worker: str = Form(...), db: Session = Depends(get_db),
):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.direction != "incoming" or item.local_confirmed_at:
        raise HTTPException(404, "Adjunto no disponible")
    if item.claim_expires_at and not is_expired(item.claim_expires_at) and item.claimed_by != worker:
        raise HTTPException(409, "Adjunto reclamado por otro sincronizador")
    item.claimed_by = worker[:120]
    item.claim_expires_at = utcnow() + timedelta(minutes=10)
    db.commit()
    return {"ok": True, "claim_expires_at": item.claim_expires_at.isoformat()}


@router.get("/sync/attachments/{attachment_id}/content", dependencies=[Depends(_sync_worker)])
def sync_attachment_content(
    attachment_id: str, worker: str, db: Session = Depends(get_db),
):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.claimed_by != worker or is_expired(item.claim_expires_at):
        raise HTTPException(409, "Concesion de descarga no valida")
    content = MessagingStorage().get(item.storage_key)
    if not hmac_compare(hashlib.sha256(content).hexdigest(), item.sha256):
        raise HTTPException(500, "La integridad del adjunto no es valida")
    return Response(content, media_type=item.content_type)


@router.post("/sync/attachments/{attachment_id}/confirm", dependencies=[Depends(_sync_worker)])
def sync_confirm_attachment(
    attachment_id: str, worker: str = Form(...), sha256: str = Form(...),
    db: Session = Depends(get_db),
):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.claimed_by != worker or not hmac_compare(item.sha256, sha256):
        raise HTTPException(409, "Confirmacion no valida")
    item.local_confirmed_at = utcnow()
    item.claim_expires_at = None
    db.commit()
    cleanup_pending = False
    try:
        MessagingStorage().delete(item.storage_key)
        item.storage_deleted_at = utcnow()
        item.storage_key = ""
        db.commit()
    except Exception:
        cleanup_pending = True
    return {"ok": True, "storage_cleanup_pending": cleanup_pending}


@router.get("/{audience}/events")
async def events(audience: str, request: Request, after: int = 0, db: Session = Depends(get_db)):
    actor = _resolve_actor(audience, request, db)
    org_id = actor.organization_id if audience == "client" else None
    staff_id = actor.external_id if audience == "staff" else ""
    if audience == "client":
        presence = db.get(MessagingPresence, actor.id) or MessagingPresence(client_id=actor.id, connected_until=utcnow())
        presence.connected_until = utcnow() + timedelta(seconds=35)
        db.add(presence); db.commit()

    async def stream():
        cursor = after
        for _ in range(25):
            with SessionLocal() as event_db:
                if audience == "client":
                    presence = event_db.get(MessagingPresence, actor.id)
                    if presence:
                        presence.connected_until = utcnow() + timedelta(seconds=35)
                        event_db.commit()
                rows = event_db.scalars(select(MessagingEvent).where(MessagingEvent.id > cursor).order_by(MessagingEvent.id).limit(100)).all()
                for row in rows:
                    cursor = max(cursor, row.id)
                    if org_id and row.organization_id != org_id:
                        continue
                    if audience == "staff" and row.event_type == "internal_message":
                        thread = event_db.get(MessagingStaffThread, row.conversation_id)
                        event_staff = event_db.get(MessagingStaff, staff_id)
                        if not thread or not event_staff or not _can_access_staff_thread(
                            event_db, thread, event_staff,
                        ):
                            continue
                        yield f"id: {row.id}\nevent: {row.event_type}\ndata: {json.dumps({'thread_id': row.conversation_id})}\n\n"
                        continue
                    conv = event_db.get(MessagingConversation, row.conversation_id) if row.conversation_id else None
                    if audience == "staff" and conv:
                        event_staff = event_db.get(MessagingStaff, staff_id)
                        if not event_staff or not _can_access_conversation(
                            event_db, conv, event_staff,
                        ):
                            continue
                    yield f"id: {row.id}\nevent: {row.event_type}\ndata: {json.dumps({'conversation_id': row.conversation_id})}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def cleanup_expired_attachments() -> int:
    """Elimina copias cloud de salida caducadas conservando metadatos y auditoria."""
    removed = 0
    with SessionLocal() as db:
        rows = db.scalars(select(MessagingAttachment).where(
            MessagingAttachment.direction == "outgoing",
            MessagingAttachment.storage_deleted_at.is_(None),
            MessagingAttachment.expires_at.is_not(None),
            MessagingAttachment.expires_at <= utcnow(),
        )).all()
        rows += db.scalars(select(MessagingAttachment).where(
            MessagingAttachment.direction == "incoming",
            MessagingAttachment.local_confirmed_at.is_not(None),
            MessagingAttachment.storage_deleted_at.is_(None),
        )).all()
        storage = MessagingStorage()
        for item in rows:
            try:
                storage.delete(item.storage_key)
            except Exception:
                continue
            item.storage_key = ""; item.storage_deleted_at = utcnow(); removed += 1
        db.commit()
    return removed
