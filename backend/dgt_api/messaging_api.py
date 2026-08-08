from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.dgt_api.config import get_settings
from backend.dgt_api.database import SessionLocal
from backend.dgt_api.messaging_models import (
    MessagingAttachment, MessagingClient, MessagingConversation, MessagingDevice, MessagingDownload,
    MessagingEvent, MessagingInvitation, MessagingMessage, MessagingOrganization,
    MessagingPresence, MessagingRead, MessagingSession, MessagingStaff,
)
from backend.dgt_api.messaging_mail import configured as mail_configured, send_invitation, send_message_notice
from backend.dgt_api.messaging_security import (
    hash_password, hash_token, invitation_expiry, new_token, session_expiry,
    is_expired, utcnow, verify_password,
)
from backend.dgt_api.messaging_storage import MessagingStorage, safe_name
from backend.dgt_api.security import require_internal_key


router = APIRouter(prefix="/api/v1/messaging", tags=["messaging"])
MAX_ATTACHMENT = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff",
    ".txt", ".xml", ".csv", ".xls", ".xlsx", ".doc", ".docx", ".zip",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OrganizationIn(BaseModel):
    company_code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    private_owner_external_id: str = ""
    active: bool = True


class StaffIn(BaseModel):
    external_id: str
    name: str
    role: str = "empleado"
    active: bool = True


class InviteIn(BaseModel):
    company_code: str
    name: str
    email: str


class AcceptInviteIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class ConversationPatch(BaseModel):
    state: str | None = None
    assigned_staff_external_id: str | None = None


def _staff(
    db: Session = Depends(get_db),
    _key: str = Depends(require_internal_key),
    x_staff_id: str = Header(default=""),
    x_device_id: str = Header(default=""),
    x_device_token: str = Header(default=""),
) -> MessagingStaff:
    device = db.get(MessagingDevice, x_device_id)
    if not device or not device.active or not x_device_token or not hmac_compare(device.token_hash, hash_token(x_device_token)):
        raise HTTPException(403, "Puesto del despacho no autorizado")
    device.last_used_at = utcnow()
    staff = db.get(MessagingStaff, x_staff_id)
    if not staff or not staff.active or staff.role not in {"admin", "empleado"}:
        raise HTTPException(403, "Usuario del despacho no autorizado")
    return staff


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
    org = db.get(MessagingOrganization, conv.organization_id)
    if conv.kind == "private" and org.private_owner_external_id != staff.external_id:
        raise HTTPException(403, "Chat privado no autorizado")
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
    return {
        "id": conv.id, "company_code": org.company_code, "company_name": org.name,
        "kind": conv.kind, "state": conv.state,
        "assigned_staff_external_id": conv.assigned_staff_external_id,
        "updated_at": conv.updated_at.isoformat(),
        "last_message": _serialize_message(db, last) if last else None,
    }


def _serialize_message(db: Session, item: MessagingMessage) -> dict:
    attachments = list(db.scalars(select(MessagingAttachment).where(MessagingAttachment.message_id == item.id)))
    return {
        "id": item.id, "conversation_id": item.conversation_id,
        "author_type": item.author_type, "author_id": item.author_id,
        "author_name": item.author_name, "body": item.body,
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
    storage = MessagingStorage()
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
    item.name, item.role, item.active = payload.name, payload.role, payload.active
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
            MessagingConversation(organization_id=item.id, kind="general"),
            MessagingConversation(organization_id=item.id, kind="private"),
        ])
    item.name = payload.name
    item.active = payload.active
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
    if mail_configured():
        background.add_task(send_invitation, client.email, client.name, url)
    return {
        "invitation_id": invitation.id,
        "url": url, "email_queued": mail_configured(),
        "expires_at": invitation.expires_at.isoformat(),
    }


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
def staff_conversations(staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingConversation).order_by(MessagingConversation.updated_at.desc())).all()
    result = []
    for row in rows:
        if row.kind == "private" and db.get(MessagingOrganization, row.organization_id).private_owner_external_id != staff.external_id:
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
    return [_serialize_message(db, row) for row in rows]


def _resolve_actor(audience: str, request: Request, db: Session):
    if audience == "client":
        return _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
    if audience == "staff":
        require_internal_key(request.headers.get("x-api-key", ""))
        return _staff(
            db, "gest2a3eco", request.headers.get("x-staff-id", ""),
            request.headers.get("x-device-id", ""), request.headers.get("x-device-token", ""),
        )
    raise HTTPException(404)


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
        actor_name=actor.name, body=body, idempotency_key=key, files=files,
    )
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
    return _serialize_message(db, item)


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
        if conv.kind == "private" and org.private_owner_external_id != staff.external_id:
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
                    conv = event_db.get(MessagingConversation, row.conversation_id) if row.conversation_id else None
                    cursor = max(cursor, row.id)
                    if org_id and row.organization_id != org_id:
                        continue
                    if audience == "staff" and conv and conv.kind == "private":
                        org = event_db.get(MessagingOrganization, conv.organization_id)
                        if org.private_owner_external_id != staff_id:
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
