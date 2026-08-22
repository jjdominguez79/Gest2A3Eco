from __future__ import annotations

import asyncio
import hashlib
import io
import json
import mimetypes
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urlencode, urlparse

import msal
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.config import get_settings
from backend.api.database import SessionLocal
from backend.api.messaging_models import (
    MessagingAttachment, MessagingClient, MessagingConversation, MessagingDevice, MessagingDownload,
    MessagingAppDevice, MessagingCampaign, MessagingCampaignRecipient,
    MessagingDeletionAudit, MessagingEvent, MessagingGroup, MessagingGroupMember,
    MessagingInvitation, MessagingMessage, MessagingOrganization,
    MessagingPasswordReset, MessagingPresence, MessagingRead, MessagingSession, MessagingStaff,
    MessagingStaffAuthFlow, MessagingStaffChannel, MessagingStaffSession,
    MessagingStaffAppCode, MessagingStaffThread, MessagingStaffThreadMessage,
    MessagingStaffThreadRead, MessagingWebSocketTicket,
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
from backend.api.messaging_firebase import configured as fcm_configured, send_fcm
from backend.api.messaging_realtime import hub
from backend.api.security import require_internal_key, require_workstation_or_internal


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
    role: Literal["admin", "empleado"] = "empleado"
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
    role: Literal["admin", "empleado"] | None = None
    chat_alias: str | None = Field(default=None, max_length=160)


class StaffCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    role: Literal["admin", "empleado"] = "empleado"
    chat_alias: str = Field(default="", max_length=160)
    active: bool = True
    channels: list[str] = Field(default_factory=list)


class StaffAppCodeIn(BaseModel):
    code: str = Field(min_length=20, max_length=300)


class AppDeviceIn(BaseModel):
    platform: Literal["android", "ios", "windows", "macos", "web"]
    push_token: str = Field(min_length=20, max_length=5000)
    device_name: str = Field(default="", max_length=160)
    app_version: str = Field(default="", max_length=40)


class StaffSelfPatchIn(BaseModel):
    chat_alias: str | None = Field(default=None, max_length=160)


class ClientAccessIn(BaseModel):
    active: bool


class MessageDeleteIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    group_type: Literal["staff_chat", "client_list"]
    active: bool = True


class GroupMemberIn(BaseModel):
    member_type: Literal["staff", "client"]
    member_id: str = Field(min_length=1, max_length=64)
    role: Literal["owner", "member"] = "member"


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=20000)
    channel: str = "fiscal"
    all_clients: bool = False
    group_ids: list[str] = Field(default_factory=list)
    client_ids: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None


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


def _primary_admin(db: Session) -> MessagingStaff | None:
    admins = db.scalars(select(MessagingStaff).where(
        MessagingStaff.role == "admin",
        MessagingStaff.active.is_(True),
    ).order_by(MessagingStaff.name)).all()
    configured = [
        value.strip().lower()
        for value in get_settings().messaging_staff_admin_emails.replace(";", ",").split(",")
        if value.strip()
    ]
    by_email = {admin.email.strip().lower(): admin for admin in admins}
    return next((by_email[email] for email in configured if email in by_email), None) or (
        admins[0] if admins else None
    )


def _get_or_create_staff_direct_thread(
    db: Session, admin: MessagingStaff, member: MessagingStaff,
) -> MessagingStaffThread:
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
    return thread


def _ensure_employee_admin_direct_thread(
    db: Session, staff: MessagingStaff,
) -> MessagingStaffThread | None:
    if staff.role == "admin":
        return None
    admin = _primary_admin(db)
    if not admin:
        return None
    return _get_or_create_staff_direct_thread(db, admin, staff)


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
    # Web Push/VAPID retirado: ya no hay suscripciones que desactivar aqui.


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
        if thread.key.startswith("dynamic-group:"):
            group_id = thread.key.split(":", 1)[1]
            return staff.role == "admin" or bool(db.scalar(select(MessagingGroupMember.id).where(
                MessagingGroupMember.group_id == group_id,
                MessagingGroupMember.member_type == "staff",
                MessagingGroupMember.member_id == staff.external_id,
            )))
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
    if not org:
        return False
    if org.company_code.strip().upper() in TEST_COMPANY_CODES:
        return bool(org.private_owner_external_id == staff.external_id)
    if conv.kind == "private":
        # Si no hay propietario asignado, el admin puede acceder (cliente antiguo sin owner)
        if org.private_owner_external_id is None:
            return staff.role == "admin"
        return bool(org.private_owner_external_id == staff.external_id)
    if staff.role == "admin":
        return True
    if not org.active:
        return False
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
    organization = db.get(MessagingOrganization, client.organization_id)
    if not organization or not organization.active:
        raise HTTPException(403, "Cuenta inactiva")
    return client


def _organization(db: Session, code: str) -> MessagingOrganization:
    item = db.scalar(select(MessagingOrganization).where(MessagingOrganization.company_code == code))
    if not item:
        raise HTTPException(404, "Empresa no encontrada")
    return item


def _organization_access_state(db: Session, org: MessagingOrganization) -> dict:
    clients = db.scalars(select(MessagingClient).where(
        MessagingClient.organization_id == org.id,
    )).all()
    active_clients = [client for client in clients if client.active]
    accepted = [client for client in active_clients if client.password_hash]
    pending = False
    if active_clients:
        invitations = db.scalars(select(MessagingInvitation).where(
            MessagingInvitation.client_id.in_([client.id for client in active_clients]),
            MessagingInvitation.used_at.is_(None),
            MessagingInvitation.revoked_at.is_(None),
        )).all()
        pending = any(not is_expired(invitation.expires_at) for invitation in invitations)
    if not org.active or (clients and not active_clients):
        status = "disabled"
    elif accepted:
        status = "active"
    elif pending:
        status = "pending"
    elif clients:
        status = "invitation_expired"
    else:
        status = "not_invited"
    return {
        "status": status,
        "active": bool(org.active and accepted),
        "client_count": len(clients),
    }


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


def _serialize_conversation(
    db: Session, conv: MessagingConversation, audience: str = "staff",
    access: dict | None = None,
) -> dict:
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
    access = access or _organization_access_state(db, org)
    channel_label = {"laboral": "LA", "fiscal": "CF"}.get(conv.kind, "")
    channel_avatar_url = ""
    if conv.kind == "private":
        owner_id = org.private_owner_external_id or conv.assigned_staff_external_id
        owner = db.get(MessagingStaff, owner_id) if owner_id else None
        owner_name = (owner.chat_alias.strip() or owner.name.strip()) if owner else ""
        words = [word for word in owner_name.split() if word]
        if len(words) >= 2:
            channel_label = "".join(word[0] for word in words[:2]).upper()
        elif words:
            channel_label = words[0][:2].upper()
        else:
            channel_label = "DP"
        if owner and owner.avatar_storage_key:
            channel_avatar_url = (
                f"/api/v1/messaging/{audience}/avatars/{owner.external_id}"
            )
    return {
        "id": conv.id, "company_code": org.company_code, "company_name": org.name,
        "kind": conv.kind, "channel_label": channel_label,
        "channel_avatar_url": channel_avatar_url, "state": conv.state,
        "active_client_count": active_client_count,
        "client_access_status": access["status"],
        "client_access_active": access["active"],
        "organization_active": org.active,
        "assigned_staff_external_id": conv.assigned_staff_external_id,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "updated_at": conv.updated_at.isoformat(),
        "last_message": _serialize_message(db, last) if last else None,
    }


def _attachment_download_summary(db: Session, attachment_id: str) -> dict:
    """Resumen de descargas completadas para personal (adjuntos salientes)."""
    rows = db.scalars(
        select(MessagingDownload).where(
            MessagingDownload.attachment_id == attachment_id,
            MessagingDownload.success.is_(True),
            MessagingDownload.completed_at.is_not(None),
        ).order_by(MessagingDownload.completed_at)
    ).all()
    if not rows:
        return {"completed_download_count": 0, "first_downloaded_at": None,
                "last_downloaded_at": None, "last_client_name": None}
    last = rows[-1]
    last_client = db.get(MessagingClient, last.client_id)
    return {
        "completed_download_count": len(rows),
        "first_downloaded_at": rows[0].completed_at.isoformat(),
        "last_downloaded_at": last.completed_at.isoformat(),
        "last_client_name": last_client.name if last_client else None,
    }


def _serialize_attachment(db: Session, a: MessagingAttachment, audience: str) -> dict:
    withdrawn = bool(a.withdrawn_at)
    expired = bool(a.expires_at and is_expired(a.expires_at))

    if a.direction == "incoming":
        if a.local_confirmed_at:
            status = "guardado_por_asesoria"
        else:
            status = "recibido_por_gestinem"
    else:
        if withdrawn:
            status = "retirado"
        elif expired or a.storage_deleted_at:
            status = "caducado"
        else:
            status = "disponible"

    base = {
        "id": a.id, "name": a.name, "content_type": a.content_type,
        "size": a.size, "direction": a.direction,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "local_confirmed": bool(a.local_confirmed_at),
        "status": status,
        "withdrawn_at": a.withdrawn_at.isoformat() if a.withdrawn_at else None,
    }
    if audience == "staff":
        base["withdrawn_by"] = a.withdrawn_by
        base["withdrawal_reason"] = a.withdrawal_reason
        base["sha256"] = a.sha256
        if a.direction == "outgoing":
            base.update(_attachment_download_summary(db, a.id))
    elif audience == "client":
        if a.direction == "incoming":
            # El cliente subio el archivo: puede ver su propio sha256
            base["sha256"] = a.sha256
        base["available"] = (
            a.direction == "outgoing"
            and not withdrawn
            and not expired
            and not a.storage_deleted_at
        )
    return base


def _serialize_message(db: Session, item: MessagingMessage, audience: str = "") -> dict:
    attachments = [] if item.deleted_at else list(db.scalars(select(MessagingAttachment).where(MessagingAttachment.message_id == item.id)))
    author_name = item.author_name
    author_avatar_url = ""
    if item.author_type == "staff":
        author = db.get(MessagingStaff, item.author_id)
        if author:
            author_name = author.chat_alias.strip() or item.author_name
            if author.avatar_storage_key and audience in {"client", "staff"}:
                author_avatar_url = f"/api/v1/messaging/{audience}/avatars/{author.external_id}"
    reply = db.get(MessagingMessage, item.reply_to_message_id) if item.reply_to_message_id else None
    reply_data = None
    if reply:
        reply_data = {
            "id": reply.id,
            "author_name": reply.author_name,
            "body_fragment": "Mensaje eliminado" if reply.deleted_at else reply.body[:180],
            "deleted": bool(reply.deleted_at),
        }
    has_attachments = bool(db.scalar(
        select(func.count(MessagingAttachment.id)).where(MessagingAttachment.message_id == item.id)
    ))
    return {
        "id": item.id, "conversation_id": item.conversation_id,
        "author_type": item.author_type, "author_id": item.author_id,
        "author_name": author_name, "author_avatar_url": author_avatar_url,
        "body": "" if item.deleted_at else item.body,
        "deleted": bool(item.deleted_at),
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
        "delete_reason": item.delete_reason if item.deleted_at and audience == "staff" else "",
        "has_attachments": has_attachments,
        "reply_to": reply_data,
        "created_at": item.created_at.isoformat(),
        "attachments": [_serialize_attachment(db, a, audience) for a in attachments],
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
    """Web Push (VAPID) retirado. Las notificaciones al despacho van solo por FCM."""


def _queue_client_pushes(
    db: Session, background: BackgroundTasks, conv: MessagingConversation,
) -> None:
    """Web Push (VAPID) retirado. Las notificaciones al cliente van solo por FCM."""


def _queue_app_pushes(
    db: Session, background: BackgroundTasks, conv: MessagingConversation,
    recipient_type: str,
) -> None:
    if not fcm_configured():
        return
    now = utcnow()
    if recipient_type == "client":
        user_ids = set(db.scalars(select(MessagingClient.id).where(
            MessagingClient.organization_id == conv.organization_id,
            MessagingClient.active.is_(True),
        )))
    else:
        org = db.get(MessagingOrganization, conv.organization_id)
        if conv.kind == "private" or org.company_code.strip().upper() in TEST_COMPANY_CODES:
            user_ids = {org.private_owner_external_id} if org.private_owner_external_id else set()
        else:
            user_ids = set(db.scalars(select(MessagingStaffChannel.staff_external_id).where(
                MessagingStaffChannel.channel == conv.kind,
            )))
    if not user_ids:
        return
    devices = db.scalars(select(MessagingAppDevice).where(
        MessagingAppDevice.user_type == recipient_type,
        MessagingAppDevice.user_id.in_(user_ids),
        MessagingAppDevice.active.is_(True),
    )).all()
    payload = {
        "title": "Nuevo mensaje de Gestinem",
        "body": "Tienes un nuevo mensaje",
        "event": "message.created",
        "conversation_id": conv.id,
    }
    for device in devices:
        viewing = (
            device.active_conversation_id == conv.id
            and (now - device.last_seen_at).total_seconds() < 75
        )
        if not viewing:
            background.add_task(send_fcm, device.push_token, payload)


def _publish_conversation_event(db: Session, conv: MessagingConversation, event_type: str, **extra) -> None:
    payload = {"type": event_type, "conversation_id": conv.id, **extra}
    org = db.get(MessagingOrganization, conv.organization_id)
    staff_ids = None
    if conv.kind == "private" or (org and org.company_code.strip().upper() in TEST_COMPANY_CODES):
        staff_ids = {org.private_owner_external_id} if org and org.private_owner_external_id else set()
    hub.publish(payload, organization_id=conv.organization_id, channel=conv.kind, staff_ids=staff_ids)


def _create_message(
    db: Session, conv: MessagingConversation, *, actor_type: str, actor_id: str,
    actor_name: str, body: str, idempotency_key: str, files: list[UploadFile],
    reply_to_message_id: str | None = None,
) -> MessagingMessage:
    existing = db.scalar(select(MessagingMessage).where(
        MessagingMessage.conversation_id == conv.id,
        MessagingMessage.idempotency_key == idempotency_key,
    ))
    if existing:
        return existing
    reply_to = None
    if reply_to_message_id:
        reply_to = db.get(MessagingMessage, reply_to_message_id)
        if not reply_to or reply_to.conversation_id != conv.id:
            raise HTTPException(422, "El mensaje respondido no pertenece a la conversacion")
    message = MessagingMessage(
        conversation_id=conv.id, author_type=actor_type, author_id=actor_id,
        author_name=actor_name, body=body.strip(), idempotency_key=idempotency_key,
        reply_to_message_id=reply_to.id if reply_to else None,
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
    conv.started_at = conv.started_at or utcnow()
    conv.updated_at = utcnow()
    _event(db, conv, "message_created")
    db.commit()
    db.refresh(message)
    _publish_conversation_event(
        db, conv, "message.created",
        message_id=message.id,
        author_type=actor_type,
        author_id=actor_id,
        author_name=actor_name,
        preview=message.body[:160],
    )
    return message


@router.put("/internal/staff/{external_id}", dependencies=[Depends(require_workstation_or_internal)])
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


@router.post("/internal/devices/{device_id}", dependencies=[Depends(require_workstation_or_internal)])
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
    org.active = True
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
    app_url = _app_deep_link("invite", token)
    url = _public_app_link("invite", token)
    email_queued = payload.send_email and mail_configured()
    if email_queued:
        background.add_task(send_invitation, client.email, client.name, url)
    return {
        "invitation_id": invitation.id,
        "url": url,
        "app_url": app_url,
        "email_queued": email_queued,
        "expires_at": invitation.expires_at.isoformat(),
    }


def _app_deep_link(action: str, token: str) -> str:
    configured = get_settings().messaging_app_redirect_uri.strip()
    parsed = urlparse(configured)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("MESSAGING_APP_REDIRECT_URI no es una URI valida")
    query = urlencode({"token": token})
    return f"{parsed.scheme}://{parsed.netloc}/{action}?{query}"


def _public_app_link(action: str, token: str) -> str:
    base_url = get_settings().messaging_public_base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("MESSAGING_PUBLIC_BASE_URL no es una URL publica valida")
    query = urlencode({"token": token})
    return f"{base_url}/api/v1/messaging/public/app-link/{action}?{query}"


@router.get("/public/app-link/{action}")
def public_app_link(action: Literal["invite", "reset"], token: str = Query(min_length=1)):
    """Enlace HTTPS apto para correo que entrega el token a la app Flutter."""
    return RedirectResponse(_app_deep_link(action, token), status_code=307)


@router.get("/public/auth-done")
def public_auth_done(code: str = Query(min_length=1)):
    """Página de cierre del flujo OAuth móvil. Abre el deep link y muestra mensaje al usuario."""
    configured = get_settings().messaging_app_redirect_uri.strip()
    parsed = urlparse(configured)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(500, "MESSAGING_APP_REDIRECT_URI no configurada")
    deep_link = f"{parsed.scheme}://{parsed.netloc}/auth?{urlencode({'code': code})}"
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceso completado · Gestinem</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f0f4ff;display:flex;align-items:center;justify-content:center;
         min-height:100vh;padding:24px}}
    .card{{background:#fff;border-radius:16px;padding:40px 32px;max-width:380px;
           width:100%;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
    .icon{{font-size:56px;margin-bottom:20px}}
    h1{{font-size:22px;color:#1a1a2e;margin-bottom:12px}}
    p{{font-size:15px;color:#555;line-height:1.6;margin-bottom:24px}}
    a.btn{{display:inline-block;background:#1a56e8;color:#fff;text-decoration:none;
           padding:14px 32px;border-radius:10px;font-size:16px;font-weight:600}}
    .note{{font-size:13px;color:#888;margin-top:20px}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Acceso completado</h1>
    <p>Ya puedes cerrar esta pestaña y volver a la aplicación Gestinem.</p>
    <a class="btn" href="{deep_link}">Volver a Gestinem</a>
    <p class="note">Si la aplicación no se abre automáticamente, pulsa el botón.</p>
  </div>
  <script>
    // Intentar abrir la app automáticamente al cargar la página
    setTimeout(function() {{ window.location.href = "{deep_link}"; }}, 400);
  </script>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


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


def _web_redirect_scheme_allowed(url: str) -> bool:
    """HTTPS siempre permitido; HTTP solo para localhost/127.0.0.1."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme == "https":
        return True
    if scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return True
    return False


@router.get("/staff-auth/login")
def staff_auth_login(
    app: bool = Query(default=False), web_redirect: str = Query(default=""),
    db: Session = Depends(get_db),
):
    allowed_web_redirect = get_settings().messaging_app_web_redirect_uri.strip()
    if web_redirect and (
        not app or not allowed_web_redirect
        or not secrets.compare_digest(web_redirect, allowed_web_redirect)
        or not _web_redirect_scheme_allowed(web_redirect)
    ):
        raise HTTPException(422, "Retorno web de Gestinem no autorizado")
    flow = _staff_msal_app().initiate_auth_code_flow(
        # MSAL agrega automaticamente openid/profile/offline_access.
        scopes=["email"],
        redirect_uri=_staff_redirect_uri(),
        prompt="select_account",
    )
    state = str(flow.get("state") or "")
    if not state or not flow.get("auth_uri"):
        raise HTTPException(502, "Microsoft no pudo iniciar el acceso")
    db.add(MessagingStaffAuthFlow(
        state=state,
        flow_json=json.dumps({"msal": flow, "mobile": app, "web_redirect": web_redirect}),
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
        stored_flow = json.loads(stored.flow_json)
        mobile = bool(stored_flow.get("mobile")) if "msal" in stored_flow else False
        web_redirect = str(stored_flow.get("web_redirect") or "") if "msal" in stored_flow else ""
        msal_flow = stored_flow.get("msal", stored_flow)
        result = _staff_msal_app().acquire_token_by_auth_code_flow(msal_flow, dict(request.query_params))
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
    if mobile:
        code = new_token()
        db.add(MessagingStaffAppCode(
            staff_external_id=staff.external_id, code_hash=hash_token(code),
            expires_at=utcnow() + timedelta(minutes=2),
        ))
        db.commit()
        if web_redirect:
            # Flujo web: redirigir directamente al destino web configurado
            separator = "&" if "?" in web_redirect else "?"
            return RedirectResponse(
                f"{web_redirect}{separator}{urlencode({'code': code})}", status_code=302,
            )
        # Flujo móvil: mostrar página de cierre que abre el deep link y muestra
        # un mensaje claro al usuario antes de volver a la app.
        base_url = get_settings().messaging_public_base_url.strip().rstrip("/")
        done_url = f"{base_url}/api/v1/messaging/public/auth-done?{urlencode({'code': code})}"
        return RedirectResponse(done_url, status_code=302)
    # El acceso web al despacho (/equipo/mensajes) ha sido retirado.
    # El flujo OAuth sin app=true ya no tiene destino valido.
    # Para iniciar sesion en la mensajeria, usa la aplicacion Flutter con app=true.
    db.commit()
    raise HTTPException(
        410,
        "La interfaz web de mensajeria del despacho ha sido retirada. "
        "Usa la aplicacion Gestinem (app=true en el parametro de inicio de sesion).",
    )


@router.post("/staff-auth/mobile/exchange")
def staff_app_exchange(payload: StaffAppCodeIn, db: Session = Depends(get_db)):
    item = db.scalar(select(MessagingStaffAppCode).where(
        MessagingStaffAppCode.code_hash == hash_token(payload.code),
    ))
    if not item or item.used_at or is_expired(item.expires_at):
        raise HTTPException(400, "Codigo de acceso no valido o caducado")
    staff = db.get(MessagingStaff, item.staff_external_id)
    if not staff or not staff.active:
        raise HTTPException(403, "Usuario del despacho no autorizado")
    item.used_at = utcnow()
    token = new_token()
    db.add(MessagingStaffSession(
        staff_external_id=staff.external_id, token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=30),
    ))
    db.commit()
    return {
        "token": token,
        "staff": {
            "id": staff.external_id,
            "name": staff.chat_alias.strip() or staff.name,
            "email": staff.email,
            "role": staff.role,
            "avatar_url": (
                f"/api/v1/messaging/staff/avatars/{staff.external_id}"
                if staff.avatar_storage_key else ""
            ),
            "channels": sorted(_channels_for_staff(db, staff)),
        },
    }


@router.post("/staff-auth/logout")
def staff_auth_logout(
    response: Response, request: Request, db: Session = Depends(get_db),
):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    token = token or request.cookies.get("msg_staff_session", "")
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
        "id": staff.external_id,
        "name": staff.chat_alias.strip() or staff.name,
        "email": staff.email,
        "role": staff.role, "chat_alias": staff.chat_alias,
        "avatar_configured": bool(staff.avatar_storage_key),
        "avatar_url": f"/api/v1/messaging/staff/avatars/{staff.external_id}" if staff.avatar_storage_key else "",
        "channels": sorted(_channels_for_staff(db, staff)),
    }


@router.patch("/staff/me")
def patch_staff_me(
    payload: StaffSelfPatchIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Actualiza el perfil propio del staff (alias de chat)."""
    staff = _staff_from_request(db, request)
    if payload.chat_alias is not None:
        staff.chat_alias = payload.chat_alias.strip()
    db.commit()
    return {"ok": True}


@router.put("/staff/me/avatar", status_code=200)
def upload_own_avatar(
    avatar: UploadFile = File(...),
    request: Request = ...,
    db: Session = Depends(get_db),
):
    """Sube o reemplaza el avatar propio del staff autenticado."""
    staff = _staff_from_request(db, request)
    content = _normalized_avatar(avatar)
    storage = MessagingStorage()
    old_key = staff.avatar_storage_key
    staff.avatar_storage_key = storage.put(content, f"avatar-{staff.external_id}.webp")
    staff.avatar_content_type = "image/webp"
    if old_key:
        try:
            storage.delete(old_key)
        except Exception:
            pass
    db.commit()
    return {"ok": True, "avatar_url": f"/api/v1/messaging/staff/avatars/{staff.external_id}"}


# Web Push/VAPID retirado. Los endpoints /staff/push/* y /client/push/* han sido eliminados.
# Las notificaciones van exclusivamente por Firebase Cloud Messaging (FCM) a traves de
# los endpoints /{audience}/app-devices existentes.


def _serialize_staff_thread_message(db: Session, item: MessagingStaffThreadMessage) -> dict:
    author = db.get(MessagingStaff, item.author_staff_external_id)
    reply = db.get(MessagingStaffThreadMessage, item.reply_to_message_id) if item.reply_to_message_id else None
    return {
        "id": item.id, "thread_id": item.thread_id,
        "author_id": item.author_staff_external_id,
        "author_name": (author.chat_alias.strip() or author.name) if author else item.author_name,
        "author_avatar_url": (
            f"/api/v1/messaging/staff/avatars/{author.external_id}"
            if author and author.avatar_storage_key else ""
        ),
        "body": "" if item.deleted_at else item.body,
        "deleted": bool(item.deleted_at),
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
        "reply_to": ({
            "id": reply.id, "author_name": reply.author_name,
            "body_fragment": "Mensaje eliminado" if reply.deleted_at else reply.body[:180],
            "deleted": bool(reply.deleted_at),
        } if reply else None),
        "created_at": item.created_at.isoformat(),
    }


def _staff_thread_title(db: Session, thread: MessagingStaffThread, staff: MessagingStaff) -> str:
    if thread.kind == "group":
        if thread.key.startswith("dynamic-group:"):
            group = db.get(MessagingGroup, thread.key.split(":", 1)[1])
            return group.name if group else "Grupo interno"
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
    _ensure_employee_admin_direct_thread(db, staff)
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
    thread = _get_or_create_staff_direct_thread(db, admin, member)
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


def _staff_thread_recipient_ids(
    db: Session, thread: MessagingStaffThread,
) -> set[str]:
    if thread.kind == "direct":
        candidates = {
            thread.admin_staff_external_id, thread.member_staff_external_id,
        }
    elif thread.key.startswith("dynamic-group:"):
        group_id = thread.key.split(":", 1)[1]
        candidates = set(db.scalars(select(MessagingGroupMember.member_id).where(
            MessagingGroupMember.group_id == group_id,
            MessagingGroupMember.member_type == "staff",
        )))
    else:
        candidates = set(db.scalars(select(MessagingStaffChannel.staff_external_id).where(
            MessagingStaffChannel.channel == thread.channel,
        )))
        candidates.update(db.scalars(select(MessagingStaff.external_id).where(
            MessagingStaff.role == "admin",
            MessagingStaff.active.is_(True),
        )))
    if not candidates:
        return set()
    return set(db.scalars(select(MessagingStaff.external_id).where(
        MessagingStaff.external_id.in_(candidates),
        MessagingStaff.active.is_(True),
    )))


def _queue_internal_pushes(
    db: Session, background: BackgroundTasks, thread: MessagingStaffThread,
    sender: MessagingStaff,
) -> None:
    """Envia FCM solo a los miembros autorizados del chat interno."""
    if not fcm_configured():
        return
    recipients = _staff_thread_recipient_ids(db, thread) - {sender.external_id}
    if not recipients:
        return
    devices = db.scalars(select(MessagingAppDevice).where(
        MessagingAppDevice.user_type == "staff",
        MessagingAppDevice.user_id.in_(recipients),
        MessagingAppDevice.active.is_(True),
    )).all()
    payload = {
        "title": f"Nuevo mensaje de {sender.chat_alias.strip() or sender.name}",
        "body": "Tienes un nuevo mensaje interno",
        "event": "internal_message",
        "conversation_id": "",
        "thread_id": thread.id,
    }
    for device in devices:
        background.add_task(send_fcm, device.push_token, payload)


@router.post("/staff/internal/threads/{thread_id}/messages")
def post_staff_thread_message(
    thread_id: str, background: BackgroundTasks,
    body: str = Form(...), idempotency_key: str = Form(default=""),
    reply_to_message_id: str = Form(default=""),
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
    reply = None
    if reply_to_message_id:
        reply = db.get(MessagingStaffThreadMessage, reply_to_message_id)
        if not reply or reply.thread_id != thread.id:
            raise HTTPException(422, "El mensaje respondido no pertenece al chat")
    item = MessagingStaffThreadMessage(
        thread_id=thread.id, author_staff_external_id=staff.external_id,
        author_name=staff.chat_alias.strip() or staff.name,
        body=text_body, idempotency_key=key,
        reply_to_message_id=reply.id if reply else None,
    )
    thread.updated_at = utcnow()
    db.add(item)
    db.add(MessagingEvent(
        organization_id="", conversation_id=thread.id, event_type="internal_message",
    ))
    db.commit()
    db.refresh(item)
    _queue_internal_pushes(db, background, thread, staff)
    recipients = _staff_thread_recipient_ids(db, thread)
    hub.publish(
        {
            "type": "message.created",
            "thread_id": thread.id,
            "message_id": item.id,
            "author_type": "staff",
            "author_id": staff.external_id,
            "author_name": staff.chat_alias.strip() or staff.name,
            "preview": item.body[:160],
        },
        staff_ids=recipients,
    )
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
    result = []
    for row in rows:
        if (
            row.company_code.strip().upper() in TEST_COMPANY_CODES
            and row.private_owner_external_id != admin.external_id
        ):
            continue
        access = _organization_access_state(db, row)
        result.append({
            "company_code": row.company_code, "name": row.name,
            "active": row.active,
            "private_owner_external_id": row.private_owner_external_id,
            "client_access_status": access["status"],
            "client_access_active": access["active"],
        })
    return result


@router.patch("/staff/admin/organizations/{company_code}/client-access")
def set_client_access(
    company_code: str, payload: ClientAccessIn,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    org = _organization(db, company_code)
    if (
        org.company_code.strip().upper() in TEST_COMPANY_CODES
        and org.private_owner_external_id != admin.external_id
    ):
        raise HTTPException(403, "Cliente de pruebas privado")
    clients = db.scalars(select(MessagingClient).where(
        MessagingClient.organization_id == org.id,
    )).all()
    if payload.active and not clients:
        raise HTTPException(409, "El cliente todavia no ha sido invitado")
    org.active = payload.active
    for client in clients:
        client.active = payload.active
    if not payload.active and clients:
        client_ids = [client.id for client in clients]
        now = utcnow()
        db.query(MessagingSession).filter(
            MessagingSession.client_id.in_(client_ids),
            MessagingSession.revoked_at.is_(None),
        ).update({MessagingSession.revoked_at: now}, synchronize_session=False)
        db.query(MessagingAppDevice).filter(
            MessagingAppDevice.user_type == "client",
            MessagingAppDevice.user_id.in_(client_ids),
        ).update({MessagingAppDevice.active: False}, synchronize_session=False)
        db.query(MessagingInvitation).filter(
            MessagingInvitation.client_id.in_(client_ids),
            MessagingInvitation.used_at.is_(None),
            MessagingInvitation.revoked_at.is_(None),
        ).update({MessagingInvitation.revoked_at: now}, synchronize_session=False)
    db.commit()
    return _organization_access_state(db, org)


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
    # Auto-asignar el admin como propietario del canal Directo si aún no está asignado
    if org.private_owner_external_id is None:
        org.private_owner_external_id = admin.external_id
        db.commit()
    return create_invitation(payload, background, db)


@router.get("/public/app-version")
def public_app_version(platform: str = ""):
    """Version publicada que los clientes Flutter pueden comparar con la instalada."""
    settings = get_settings()
    return {
        "platform": platform.strip().lower(),
        "latest_version": settings.messaging_latest_app_version,
        "latest_build": settings.messaging_latest_app_build,
        "minimum_build": settings.messaging_minimum_app_build,
    }


@router.post("/auth/accept-invite")
def accept_invite(payload: AcceptInviteIn, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(MessagingInvitation).where(
        MessagingInvitation.token_hash == hash_token(payload.token),
    ))
    if not invitation or invitation.used_at or invitation.revoked_at or is_expired(invitation.expires_at):
        raise HTTPException(400, "Invitacion no valida o caducada")
    client = db.get(MessagingClient, invitation.client_id)
    organization = db.get(MessagingOrganization, client.organization_id) if client else None
    if not client or not client.active or not organization or not organization.active:
        raise HTTPException(403, "Cuenta inactiva")
    client.password_hash = hash_password(payload.password)
    invitation.used_at = utcnow()
    token = _new_session(db, client)
    db.commit()
    _set_cookie(response, token)
    return {"token": token, "client": {"id": client.id, "name": client.name, "email": client.email}}


@router.post("/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    client = db.scalar(select(MessagingClient).where(MessagingClient.email == payload.email.strip().lower()))
    organization = db.get(MessagingOrganization, client.organization_id) if client else None
    if (
        not client or not client.active or not organization or not organization.active
        or not verify_password(payload.password, client.password_hash)
    ):
        raise HTTPException(401, "Credenciales no validas")
    token = _new_session(db, client); db.commit(); _set_cookie(response, token)
    return {"token": token, "client": {"id": client.id, "name": client.name, "email": client.email}}


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(
    payload: ForgotPasswordIn,
    background: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Solicita un enlace de recuperacion de contrasena.

    Responde siempre de forma neutra para evitar enumeracion de usuarios.
    Rate limiting: max 5 intentos por email o por IP en ventana de 15 minutos.
    """
    from sqlalchemy import text as _text

    email_key = f"pwd_reset:{payload.email.strip().lower()}"
    ip = (
        request.headers.get("x-forwarded-for", "")
        .split(",")[0]
        .strip()
        or (request.client.host if request.client else "unknown")
    )
    ip_key = f"pwd_reset_ip:{ip}"
    now = utcnow()
    window_15m = now.replace(
        minute=(now.minute // 15) * 15, second=0, microsecond=0
    )

    # Verificar y registrar intentos para email e IP.
    # La tabla msg_rate_limits solo existe en PostgreSQL (creada en 003_ux_iteration.sql).
    # En entornos SQLite (tests) el rate limiting se omite silenciosamente.
    try:
        for rate_key in (email_key, ip_key):
            existing = db.execute(
                _text(
                    "SELECT count FROM msg_rate_limits WHERE key = :k AND window_start = :w"
                ),
                {"k": rate_key, "w": window_15m},
            ).first()
            count = existing[0] if existing else 0
            if count >= 5:
                # Misma respuesta para no revelar el rate limiting exacto
                return {"ok": True, "email_queued": mail_configured()}
            db.execute(
                _text(
                    "INSERT INTO msg_rate_limits (key, window_start, count) VALUES (:k, :w, 1) "
                    "ON CONFLICT (key, window_start) DO UPDATE SET count = msg_rate_limits.count + 1"
                ),
                {"k": rate_key, "w": window_15m},
            )
    except Exception:
        # Rate limiting no disponible en este entorno (ej. SQLite en tests).
        # Se registra silenciosamente y se continua con el flujo normal.
        db.rollback()

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
            reset_url = _app_deep_link("reset", token)
            background.add_task(send_password_reset, client.email, client.name, reset_url)
    else:
        db.commit()  # persist rate limit counts

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
        item = _serialize_conversation(db, row, "client")
        item["unread_count"] = _unread_count(db, row, "client", client.id)
        result.append(item)
    return result


@router.get("/client/unified-conversation")
def client_unified_conversation(
    request: Request,
    db: Session = Depends(get_db),
):
    """Vista unificada de todas las conversaciones del cliente."""
    client = _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
    org = db.get(MessagingOrganization, client.organization_id)
    convs = db.scalars(
        select(MessagingConversation).where(
            MessagingConversation.organization_id == client.organization_id
        ).order_by(MessagingConversation.updated_at.desc())
    ).all()

    total_unread = 0
    last_message = None
    last_updated = None
    channel_ids: dict = {}

    for conv in convs:
        unread = _unread_count(db, conv, "client", client.id)
        total_unread += unread
        channel_ids[conv.kind] = conv.id
        if last_updated is None or conv.updated_at > last_updated:
            last_updated = conv.updated_at
            last_msg_row = db.scalar(
                select(MessagingMessage).where(
                    MessagingMessage.conversation_id == conv.id
                ).order_by(MessagingMessage.created_at.desc()).limit(1)
            )
            if last_msg_row:
                last_message = _serialize_message(db, last_msg_row, "client")

    return {
        "organization_name": org.name if org else "",
        "company_code": org.company_code if org else "",
        "channel_ids": channel_ids,
        "unread_count": total_unread,
        "last_message": last_message,
        "updated_at": last_updated.isoformat() if last_updated else None,
    }


@router.get("/client/unified-messages")
def client_unified_messages(
    request: Request,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """Todos los mensajes del cliente de todos los canales, ordenados cronologicamente."""
    client = _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
    convs = db.scalars(
        select(MessagingConversation).where(
            MessagingConversation.organization_id == client.organization_id
        )
    ).all()
    conv_ids = [c.id for c in convs]
    if not conv_ids:
        return []

    rows = db.scalars(
        select(MessagingMessage).where(
            MessagingMessage.conversation_id.in_(conv_ids)
        ).order_by(MessagingMessage.created_at.asc()).limit(limit)
    ).all()

    return [_serialize_message(db, row, "client") for row in rows]


@router.post("/client/unified-messages", status_code=201)
def client_send_unified(
    request: Request,
    background: BackgroundTasks,
    body: str = Form(default=""),
    idempotency_key: str = Form(default=""),
    reply_to_message_id: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """Envia un mensaje al canal del ultimo mensaje recibido del staff, o fiscal como fallback."""
    client = _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
    convs = db.scalars(
        select(MessagingConversation).where(
            MessagingConversation.organization_id == client.organization_id
        ).order_by(MessagingConversation.updated_at.desc())
    ).all()

    # Elegir conversacion: la que tenga el ultimo mensaje de staff
    target_conv = None
    latest_staff_msg_at = None

    for conv in convs:
        last_staff_msg = db.scalar(
            select(MessagingMessage).where(
                MessagingMessage.conversation_id == conv.id,
                MessagingMessage.author_type == "staff",
                MessagingMessage.deleted_at.is_(None),
            ).order_by(MessagingMessage.created_at.desc()).limit(1)
        )
        if last_staff_msg and (latest_staff_msg_at is None or last_staff_msg.created_at > latest_staff_msg_at):
            latest_staff_msg_at = last_staff_msg.created_at
            target_conv = conv

    # Fallback: preferir canal fiscal, luego laboral, luego cualquiera
    if target_conv is None:
        for kind in ("fiscal", "laboral"):
            target_conv = next((c for c in convs if c.kind == kind), None)
            if target_conv:
                break
        if target_conv is None and convs:
            target_conv = convs[0]

    if target_conv is None:
        raise HTTPException(404, "No hay conversaciones disponibles")

    key = idempotency_key.strip() or str(uuid.uuid4())

    # Comprobar idempotencia
    existing = db.scalar(
        select(MessagingMessage).where(
            MessagingMessage.conversation_id == target_conv.id,
            MessagingMessage.idempotency_key == key,
        )
    )
    if existing:
        return _serialize_message(db, existing, "client")

    if not body.strip() and not files:
        raise HTTPException(422, "El mensaje esta vacio")

    # Validar reply_to dentro de las conversaciones del cliente
    conv_ids = [c.id for c in convs]
    reply_id = reply_to_message_id or None
    if reply_id:
        reply_msg = db.get(MessagingMessage, reply_id)
        if not reply_msg or reply_msg.conversation_id not in conv_ids:
            reply_id = None

    item = _create_message(
        db, target_conv,
        actor_type="client",
        actor_id=client.id,
        actor_name=client.name,
        body=body,
        idempotency_key=key,
        files=files,
        reply_to_message_id=reply_id,
    )
    _queue_staff_pushes(db, background, target_conv)
    _queue_app_pushes(db, background, target_conv, "staff")

    if mail_configured():
        pass  # notificacion de email manejada en post_message

    return _serialize_message(db, item, "client")


@router.get("/staff/conversations")
def staff_conversations(
    active_only: bool = True,
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    stmt = select(MessagingConversation)
    if active_only:
        stmt = stmt.where(
            MessagingConversation.started_at.is_not(None) |
            select(MessagingMessage.id).where(
                MessagingMessage.conversation_id == MessagingConversation.id,
            ).exists(),
        )
    rows = db.scalars(stmt.order_by(MessagingConversation.updated_at.desc())).all()
    result = []
    access_by_organization: dict[str, dict] = {}
    for row in rows:
        if not _can_access_conversation(db, row, staff):
            continue
        access = access_by_organization.get(row.organization_id)
        if access is None:
            organization = db.get(MessagingOrganization, row.organization_id)
            access = _organization_access_state(db, organization)
            access_by_organization[row.organization_id] = access
        if active_only and access["status"] not in {"active", "pending"}:
            continue
        item = _serialize_conversation(db, row, access=access)
        item["unread_count"] = _unread_count(db, row, "staff", staff.external_id)
        result.append(item)
    return result


@router.get("/staff/conversation-targets")
def staff_conversation_targets(
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    """Canales de clientes invitados y accesibles para iniciar un chat."""
    rows = db.scalars(
        select(MessagingConversation).order_by(MessagingConversation.updated_at.desc())
    ).all()
    result = []
    access_by_organization: dict[str, dict] = {}
    for row in rows:
        if not _can_access_conversation(db, row, staff):
            continue
        access = access_by_organization.get(row.organization_id)
        if access is None:
            organization = db.get(MessagingOrganization, row.organization_id)
            access = _organization_access_state(db, organization)
            access_by_organization[row.organization_id] = access
        if access["status"] not in {"active", "pending"}:
            continue
        item = _serialize_conversation(db, row, access=access)
        item["unread_count"] = _unread_count(db, row, "staff", staff.external_id)
        result.append(item)
    return result


@router.post("/staff/conversations/{conversation_id}/start")
def staff_start_conversation(
    conversation_id: str,
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    """Marca un canal disponible como conversación iniciada por el personal."""
    conv = _conversation_for_staff(db, conversation_id, staff)
    organization = db.get(MessagingOrganization, conv.organization_id)
    access = _organization_access_state(db, organization)
    if access["status"] not in {"active", "pending"}:
        raise HTTPException(409, "El cliente no esta invitado o tiene el acceso inactivo")
    now = utcnow()
    conv.started_at = conv.started_at or now
    conv.updated_at = now
    _event(db, conv, "conversation_started")
    db.commit()
    item = _serialize_conversation(db, conv, access=access)
    item["unread_count"] = _unread_count(db, conv, "staff", staff.external_id)
    return item


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
        organization = db.get(MessagingOrganization, actor.organization_id)
        owns_private_channel = bool(
            organization
            and organization.private_owner_external_id == external_id
        )
        if not authored and not owns_private_channel:
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
    read.read_at = utcnow(); db.add(read); _event(db, conv, "read_updated")
    if audience == "client":
        recipients = db.scalars(select(MessagingCampaignRecipient).where(
            MessagingCampaignRecipient.client_id == actor.id,
            MessagingCampaignRecipient.status == "sent",
        )).all()
        for recipient in recipients:
            message = db.get(MessagingMessage, recipient.message_id) if recipient.message_id else None
            if message and message.conversation_id == conv.id and message.created_at <= read.read_at:
                recipient.status = "read"
                recipient.read_at = read.read_at
    db.commit()
    _publish_conversation_event(db, conv, "message.read", actor_type=audience, actor_id=actor_id)
    return {"ok": True, "changed": True}


@router.delete("/{audience}/conversations/{conversation_id}/read", status_code=204)
def mark_unread(
    audience: str,
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Marca la conversacion como no leida eliminando el registro de lectura."""
    if audience == "client":
        client = _client(db, request.headers.get("authorization", ""), request.cookies.get("msg_session", ""))
        conv = _conversation_for_client(db, conversation_id, client)
        db.query(MessagingRead).filter(
            MessagingRead.conversation_id == conv.id,
            MessagingRead.actor_type == "client",
            MessagingRead.actor_id == client.id,
        ).delete()
    elif audience == "staff":
        staff = _staff_from_request(db, request)
        db.query(MessagingRead).filter(
            MessagingRead.conversation_id == conversation_id,
            MessagingRead.actor_type == "staff",
            MessagingRead.actor_id == staff.external_id,
        ).delete()
    else:
        raise HTTPException(400, "audience invalido")
    db.commit()


@router.post("/{audience}/conversations/{conversation_id}/messages")
def post_message(
    audience: str, conversation_id: str, request: Request,
    background: BackgroundTasks,
    body: str = Form(default=""), idempotency_key: str = Form(default=""),
    reply_to_message_id: str = Form(default=""),
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
        reply_to_message_id=reply_to_message_id or None,
    )
    if audience == "client":
        _queue_staff_pushes(db, background, conv)
        _queue_app_pushes(db, background, conv, "staff")
    if audience == "staff":
        _queue_client_pushes(db, background, conv)
        _queue_app_pushes(db, background, conv, "client")
    if audience == "staff" and mail_configured():
        clients = db.scalars(select(MessagingClient).where(
            MessagingClient.organization_id == conv.organization_id,
            MessagingClient.active.is_(True),
        )).all()
        for recipient in clients:
            presence = db.get(MessagingPresence, recipient.id)
            if not presence or is_expired(presence.connected_until):
                # TODO(flutter-notice): sustituir por deep link Flutter cuando este implementado.
                # Se envia aviso informativo sin enlace (la PWA ha sido retirada).
                background.add_task(
                    send_message_notice, recipient.email, recipient.name, "",
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
    _publish_conversation_event(db, conv, "conversation.updated")
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
        if not message or message.deleted_at:
            continue
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
    if not item or item.direction != "outgoing":
        raise HTTPException(404, "Adjunto no disponible")
    if item.withdrawn_at:
        raise HTTPException(410, "Documento retirado por el despacho")
    if item.storage_deleted_at or is_expired(item.expires_at):
        raise HTTPException(410, "Adjunto caducado")
    message = db.get(MessagingMessage, item.message_id)
    if not message or message.deleted_at:
        raise HTTPException(404, "Adjunto no disponible")
    _conversation_for_client(db, message.conversation_id, client)
    content = MessagingStorage().get(item.storage_key)
    valid = hmac_compare(hashlib.sha256(content).hexdigest(), item.sha256)
    dl = MessagingDownload(
        attachment_id=item.id, client_id=client.id,
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:500], sha256=item.sha256, success=valid,
    )
    db.add(dl)
    db.flush()
    download_id = dl.id
    db.commit()
    if not valid:
        raise HTTPException(500, "La integridad del adjunto no es valida")
    response = Response(content, media_type=item.content_type, headers={
        "Content-Disposition": f'attachment; filename="{safe_name(item.name)}"',
        "X-Download-Id": download_id,
    })
    return response


@router.post("/client/attachments/{attachment_id}/confirm-download")
def client_confirm_download(
    attachment_id: str,
    download_id: str = Form(...),
    request: Request = None,
    client: MessagingClient = Depends(_client),
    db: Session = Depends(get_db),
):
    """El cliente confirma que Flutter guardo el archivo correctamente."""
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.direction != "outgoing":
        raise HTTPException(404, "Adjunto no disponible")
    message = db.get(MessagingMessage, item.message_id)
    if not message:
        raise HTTPException(404, "Adjunto no disponible")
    conv = _conversation_for_client(db, message.conversation_id, client)
    dl = db.get(MessagingDownload, download_id)
    if not dl or dl.attachment_id != attachment_id or dl.client_id != client.id:
        raise HTTPException(404, "Registro de descarga no encontrado")
    if dl.completed_at:
        return {"ok": True, "already_confirmed": True, "completed_at": dl.completed_at.isoformat()}
    dl.completed_at = utcnow()
    db.commit()
    _publish_conversation_event(
        db, conv, "attachment.download_completed",
        attachment_id=attachment_id,
        client_id=client.id,
        client_name=client.name,
        completed_at=dl.completed_at.isoformat(),
    )
    return {"ok": True, "already_confirmed": False, "completed_at": dl.completed_at.isoformat()}


@router.get("/staff/attachments/{attachment_id}/downloads")
def download_audit(attachment_id: str, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    item = db.get(MessagingAttachment, attachment_id)
    if not item:
        raise HTTPException(404)
    message = db.get(MessagingMessage, item.message_id)
    if not message or message.deleted_at:
        raise HTTPException(404, "Adjunto no disponible")
    _conversation_for_staff(db, message.conversation_id, staff)
    rows = db.scalars(select(MessagingDownload).where(MessagingDownload.attachment_id == item.id).order_by(MessagingDownload.downloaded_at)).all()
    return [{
        "id": row.id,
        "client_id": row.client_id,
        "client_name": (db.get(MessagingClient, row.client_id).name if db.get(MessagingClient, row.client_id) else ""),
        "downloaded_at": row.downloaded_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "ip": row.ip,
        "user_agent": row.user_agent, "sha256": row.sha256, "success": row.success,
    } for row in rows]


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("/staff/admin/attachments/{attachment_id}/withdraw")
def withdraw_attachment(
    attachment_id: str,
    payload: WithdrawIn,
    admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Retira un adjunto saliente: el mensaje permanece pero el cliente ya no puede descargarlo."""
    item = db.get(MessagingAttachment, attachment_id)
    if not item:
        raise HTTPException(404, "Adjunto no encontrado")
    if item.direction != "outgoing":
        raise HTTPException(409, "Solo se pueden retirar adjuntos salientes")
    message = db.get(MessagingMessage, item.message_id)
    if not message:
        raise HTTPException(404, "Mensaje no encontrado")
    conv = _conversation_for_staff(db, message.conversation_id, admin)
    if item.withdrawn_at:
        return {"ok": True, "already_withdrawn": True, "withdrawn_at": item.withdrawn_at.isoformat()}
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(422, "Debes indicar el motivo de la retirada")
    item.withdrawn_at = utcnow()
    item.withdrawn_by = admin.external_id
    item.withdrawal_reason = reason
    db.commit()
    _publish_conversation_event(
        db, conv, "attachment.withdrawn",
        attachment_id=attachment_id,
        withdrawn_by=admin.external_id,
    )
    return {"ok": True, "already_withdrawn": False, "withdrawn_at": item.withdrawn_at.isoformat()}


@router.get("/staff/attachments/{attachment_id}/download")
def staff_download_attachment(
    attachment_id: str, staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    item = db.get(MessagingAttachment, attachment_id)
    if not item or item.storage_deleted_at or not item.storage_key:
        raise HTTPException(404, "Adjunto no disponible")
    message = db.get(MessagingMessage, item.message_id)
    if not message or message.deleted_at:
        raise HTTPException(404, "Adjunto no disponible")
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
    now = utcnow()
    stale_threshold = timedelta(hours=1)
    result = []
    for item in rows:
        message = db.get(MessagingMessage, item.message_id)
        if not message or message.deleted_at:
            continue
        conv = db.get(MessagingConversation, message.conversation_id)
        org = db.get(MessagingOrganization, conv.organization_id)
        created = item.created_at
        if created.tzinfo is None:
            from datetime import timezone as _tz
            created = created.replace(tzinfo=_tz.utc)
        age = now - created
        result.append({
            "id": item.id, "message_id": message.id, "conversation_id": conv.id,
            "channel": conv.kind, "company_code": org.company_code,
            "company_name": org.name, "name": item.name, "size": item.size,
            "sha256": item.sha256, "content_type": item.content_type,
            "author_name": message.author_name, "created_at": item.created_at.isoformat(),
            "stale": age > stale_threshold,
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


@router.delete("/{audience}/messages/{message_id}")
def soft_delete_message(
    audience: str, message_id: str, request: Request,
    payload: MessageDeleteIn | None = None, db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    item = db.get(MessagingMessage, message_id)
    if not item:
        raise HTTPException(404, "Mensaje no encontrado")
    conv = (
        _conversation_for_client(db, item.conversation_id, actor)
        if audience == "client" else _conversation_for_staff(db, item.conversation_id, actor)
    )
    actor_id = actor.id if audience == "client" else actor.external_id
    is_admin = audience == "staff" and actor.role == "admin"
    if not is_admin and not (item.author_type == audience and item.author_id == actor_id):
        raise HTTPException(403, "No puedes eliminar este mensaje")
    if item.deleted_at:
        return _serialize_message(db, item, audience)
    attachment_count = int(db.scalar(select(func.count(MessagingAttachment.id)).where(
        MessagingAttachment.message_id == item.id,
    )) or 0)
    if attachment_count:
        raise HTTPException(
            409,
            "Los mensajes con adjuntos no se pueden eliminar. "
            "Usa 'Retirar documento' para adjuntos salientes.",
        )
    reason = (payload.reason if payload else "").strip()
    item.deleted_at = utcnow()
    item.deleted_by = actor_id
    item.deleted_by_type = audience
    item.delete_reason = reason
    db.add(MessagingDeletionAudit(
        message_id=item.id, conversation_id=conv.id, actor_id=actor_id,
        action="soft_delete", reason=reason,
        attachment_count=int(db.scalar(select(func.count(MessagingAttachment.id)).where(
            MessagingAttachment.message_id == item.id,
        )) or 0),
    ))
    _event(db, conv, "message_deleted")
    db.commit()
    _publish_conversation_event(db, conv, "message.deleted", message_id=item.id)
    return _serialize_message(db, item, audience)


@router.delete("/staff/internal/messages/{message_id}")
def soft_delete_internal_message(
    message_id: str, payload: MessageDeleteIn | None = None,
    staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db),
):
    item = db.get(MessagingStaffThreadMessage, message_id)
    if not item:
        raise HTTPException(404, "Mensaje interno no encontrado")
    thread = _staff_thread(db, item.thread_id, staff)
    if staff.role != "admin" and item.author_staff_external_id != staff.external_id:
        raise HTTPException(403, "No puedes eliminar este mensaje")
    if not item.deleted_at:
        reason = (payload.reason if payload else "").strip()
        item.deleted_at, item.deleted_by = utcnow(), staff.external_id
        item.deleted_by_type, item.delete_reason = "staff", reason
        db.add(MessagingDeletionAudit(
            message_id=item.id, conversation_id=thread.id,
            actor_id=staff.external_id, action="soft_delete", reason=reason,
        ))
        db.add(MessagingEvent(
            organization_id="", conversation_id=thread.id,
            event_type="internal_message",
        ))
        db.commit()
        hub.publish(
            {"type": "message.deleted", "thread_id": thread.id, "message_id": item.id},
            staff_ids=set(db.scalars(select(MessagingStaff.external_id).where(
                MessagingStaff.active.is_(True),
            ))),
        )
    return _serialize_staff_thread_message(db, item)


@router.delete("/staff/admin/internal/messages/{message_id}/hard", status_code=204)
def hard_delete_internal_message(
    message_id: str, payload: MessageDeleteIn | None = None,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    item = db.get(MessagingStaffThreadMessage, message_id)
    if not item:
        raise HTTPException(404, "Mensaje interno no encontrado")
    thread = _staff_thread(db, item.thread_id, admin)
    db.add(MessagingDeletionAudit(
        message_id=item.id, conversation_id=thread.id, actor_id=admin.external_id,
        action="hard_delete", reason=(payload.reason if payload else "").strip(),
    ))
    db.delete(item)
    thread.updated_at = utcnow()
    db.commit()
    hub.publish(
        {"type": "message.deleted", "thread_id": thread.id, "message_id": message_id, "hard": True},
        staff_ids=set(db.scalars(select(MessagingStaff.external_id).where(
            MessagingStaff.active.is_(True),
        ))),
    )
    return Response(status_code=204)


@router.delete("/staff/admin/messages/{message_id}/hard", status_code=204)
def hard_delete_message(
    message_id: str, payload: MessageDeleteIn | None = None,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    item = db.get(MessagingMessage, message_id)
    if not item:
        raise HTTPException(404, "Mensaje no encontrado")
    conv = _conversation_for_staff(db, item.conversation_id, admin)
    attachments = list(db.scalars(select(MessagingAttachment).where(
        MessagingAttachment.message_id == item.id,
    )))
    if attachments:
        raise HTTPException(
            409,
            "Los mensajes con adjuntos no admiten borrado definitivo ordinario. "
            "Usa 'Retirar documento' para adjuntos salientes.",
        )
    storage = MessagingStorage()
    reason = (payload.reason if payload else "").strip()
    db.add(MessagingDeletionAudit(
        message_id=item.id, conversation_id=conv.id, actor_id=admin.external_id,
        action="hard_delete", reason=reason, attachment_count=0,
    ))
    db.delete(item)
    conv.updated_at = utcnow()
    _event(db, conv, "message_deleted")
    db.commit()
    _publish_conversation_event(db, conv, "message.deleted", message_id=message_id, hard=True)
    return Response(status_code=204)


def _serialize_group(db: Session, group: MessagingGroup) -> dict:
    members = db.scalars(select(MessagingGroupMember).where(
        MessagingGroupMember.group_id == group.id,
    ).order_by(MessagingGroupMember.created_at)).all()
    return {
        "id": group.id, "name": group.name, "description": group.description,
        "group_type": group.group_type, "created_by": group.created_by,
        "active": group.active, "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
        "members": [{
            "id": row.id, "member_type": row.member_type,
            "member_id": row.member_id, "role": row.role,
        } for row in members],
    }


@router.get("/staff/groups")
def list_groups(staff: MessagingStaff = Depends(_staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingGroup).where(MessagingGroup.active.is_(True)).order_by(
        MessagingGroup.name,
    )).all()
    if staff.role != "admin":
        allowed = set(db.scalars(select(MessagingGroupMember.group_id).where(
            MessagingGroupMember.member_type == "staff",
            MessagingGroupMember.member_id == staff.external_id,
        )))
        rows = [row for row in rows if row.group_type == "staff_chat" and row.id in allowed]
    return [_serialize_group(db, row) for row in rows]


@router.post("/staff/admin/groups", status_code=201)
def create_group(
    payload: GroupIn, admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    if payload.group_type not in {"staff_chat", "client_list"}:
        raise HTTPException(422, "Tipo de grupo no valido")
    group = MessagingGroup(
        name=payload.name.strip(), description=payload.description.strip(),
        group_type=payload.group_type, created_by=admin.external_id,
        active=payload.active,
    )
    db.add(group)
    db.flush()
    if group.group_type == "staff_chat":
        db.add(MessagingGroupMember(
            group_id=group.id, member_type="staff",
            member_id=admin.external_id, role="owner",
        ))
        db.add(MessagingStaffThread(
            key=f"dynamic-group:{group.id}", kind="group", channel="",
        ))
    db.commit()
    db.refresh(group)
    hub.publish({"type": "group.updated", "group_id": group.id}, staff_ids={admin.external_id})
    return _serialize_group(db, group)


@router.patch("/staff/admin/groups/{group_id}")
def update_group(
    group_id: str, payload: GroupIn, admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(MessagingGroup, group_id)
    if not group:
        raise HTTPException(404, "Grupo no encontrado")
    if payload.group_type != group.group_type:
        raise HTTPException(409, "No se puede cambiar el tipo de un grupo existente")
    group.name, group.description, group.active = (
        payload.name.strip(), payload.description.strip(), payload.active,
    )
    group.updated_at = utcnow()
    db.commit()
    hub.publish({"type": "group.updated", "group_id": group.id}, staff_ids={admin.external_id})
    return _serialize_group(db, group)


@router.post("/staff/admin/groups/{group_id}/members", status_code=201)
def add_group_member(
    group_id: str, payload: GroupMemberIn,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    group = db.get(MessagingGroup, group_id)
    if not group:
        raise HTTPException(404, "Grupo no encontrado")
    expected = "staff" if group.group_type == "staff_chat" else "client"
    if payload.member_type != expected:
        raise HTTPException(422, "Tipo de miembro incompatible con el grupo")
    target = db.get(MessagingStaff if expected == "staff" else MessagingClient, payload.member_id)
    if not target:
        raise HTTPException(404, "Miembro no encontrado")
    item = db.scalar(select(MessagingGroupMember).where(
        MessagingGroupMember.group_id == group.id,
        MessagingGroupMember.member_type == expected,
        MessagingGroupMember.member_id == payload.member_id,
    ))
    if not item:
        item = MessagingGroupMember(
            group_id=group.id, member_type=expected,
            member_id=payload.member_id, role=payload.role,
        )
        db.add(item)
    else:
        item.role = payload.role
    group.updated_at = utcnow()
    db.commit()
    hub.publish({"type": "group.updated", "group_id": group.id}, staff_ids={payload.member_id, admin.external_id})
    return _serialize_group(db, group)


@router.delete("/staff/admin/groups/{group_id}/members/{member_id}", status_code=204)
def remove_group_member(
    group_id: str, member_id: str, _admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(MessagingGroupMember).where(
        MessagingGroupMember.group_id == group_id,
        MessagingGroupMember.member_id == member_id,
    ))
    if not item:
        raise HTTPException(404, "Miembro no encontrado")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def _serialize_campaign(db: Session, campaign: MessagingCampaign) -> dict:
    recipients = db.scalars(select(MessagingCampaignRecipient).where(
        MessagingCampaignRecipient.campaign_id == campaign.id,
    )).all()
    counts = {status: 0 for status in ("pending", "sent", "read", "error")}
    for recipient in recipients:
        counts[recipient.status] = counts.get(recipient.status, 0) + 1
    return {
        "id": campaign.id, "name": campaign.name, "body": campaign.body,
        "channel": campaign.channel, "status": campaign.status,
        "created_by": campaign.created_by,
        "created_at": campaign.created_at.isoformat(),
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
        "recipient_counts": counts, "recipient_count": len(recipients),
    }


def process_campaign(campaign_id: str) -> None:
    """Procesa destinatarios pendientes; cada mensaje tiene clave idempotente estable."""
    with SessionLocal() as db:
        campaign = db.get(MessagingCampaign, campaign_id)
        if not campaign or campaign.status == "sent":
            return
        campaign.status = "sending"
        db.commit()
        recipients = db.scalars(select(MessagingCampaignRecipient).where(
            MessagingCampaignRecipient.campaign_id == campaign.id,
            MessagingCampaignRecipient.status.in_(["pending", "error"]),
        )).all()
        for recipient in recipients:
            try:
                client = db.get(MessagingClient, recipient.client_id)
                if not client or not client.active:
                    raise ValueError("Cliente inactivo o inexistente")
                conv = db.scalar(select(MessagingConversation).where(
                    MessagingConversation.organization_id == client.organization_id,
                    MessagingConversation.kind == campaign.channel,
                ))
                if not conv:
                    raise ValueError("La organizacion no dispone del canal solicitado")
                message = _create_message(
                    db, conv, actor_type="staff", actor_id=campaign.created_by,
                    actor_name="Gestinem", body=campaign.body,
                    idempotency_key=f"campaign:{campaign.id}:client:{client.id}", files=[],
                )
                recipient.message_id = message.id
                recipient.status = "sent"
                recipient.sent_at = utcnow()
                recipient.error = ""
                db.commit()
            except Exception as exc:
                db.rollback()
                recipient = db.scalar(select(MessagingCampaignRecipient).where(
                    MessagingCampaignRecipient.campaign_id == campaign_id,
                    MessagingCampaignRecipient.client_id == recipient.client_id,
                ))
                if recipient:
                    recipient.status = "error"
                    recipient.error = str(exc)[:2000]
                    db.commit()
        campaign = db.get(MessagingCampaign, campaign_id)
        statuses = set(db.scalars(select(MessagingCampaignRecipient.status).where(
            MessagingCampaignRecipient.campaign_id == campaign_id,
        )))
        if statuses <= {"sent", "read"}:
            campaign.status = "sent"
            campaign.sent_at = utcnow()
        elif statuses & {"sent", "read"}:
            campaign.status = "partial"
        else:
            campaign.status = "failed"
        db.commit()


@router.get("/staff/admin/campaigns")
def list_campaigns(_admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(MessagingCampaign).order_by(MessagingCampaign.created_at.desc())).all()
    return [_serialize_campaign(db, row) for row in rows]


@router.get("/staff/admin/campaign-targets/clients")
def campaign_client_targets(
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    rows = db.execute(
        select(MessagingClient, MessagingOrganization)
        .outerjoin(
            MessagingOrganization,
            MessagingOrganization.id == MessagingClient.organization_id,
        )
        .where(MessagingClient.active.is_(True))
        .order_by(MessagingClient.name, MessagingClient.email)
    ).all()
    return [{
        "id": client.id, "name": client.name, "email": client.email,
        "organization_id": client.organization_id,
        "company_code": organization.company_code if organization else "",
        "company_name": organization.name if organization else "",
    } for client, organization in rows]


@router.post("/staff/admin/campaigns", status_code=201)
def create_campaign(
    payload: CampaignIn, background: BackgroundTasks,
    admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    if payload.channel not in STAFF_CHANNELS:
        raise HTTPException(422, "Canal de campana no valido")
    if payload.scheduled_at is not None:
        if payload.scheduled_at.tzinfo is None:
            raise HTTPException(422, "scheduled_at debe incluir zona horaria")
        if payload.scheduled_at > utcnow():
            raise HTTPException(
                422,
                "La programacion de campanas todavia no esta disponible; "
                "el envio debe ser inmediato",
            )
    client_ids = set(payload.client_ids)
    if payload.all_clients:
        client_ids.update(db.scalars(select(MessagingClient.id).where(MessagingClient.active.is_(True))))
    if payload.group_ids:
        valid_groups = set(db.scalars(select(MessagingGroup.id).where(
            MessagingGroup.id.in_(payload.group_ids),
            MessagingGroup.group_type == "client_list",
            MessagingGroup.active.is_(True),
        )))
        if valid_groups != set(payload.group_ids):
            raise HTTPException(422, "Alguna lista de clientes no es valida")
        client_ids.update(db.scalars(select(MessagingGroupMember.member_id).where(
            MessagingGroupMember.group_id.in_(valid_groups),
            MessagingGroupMember.member_type == "client",
        )))
    existing_clients = set(db.scalars(select(MessagingClient.id).where(
        MessagingClient.id.in_(client_ids), MessagingClient.active.is_(True),
    ))) if client_ids else set()
    if existing_clients != client_ids or not client_ids:
        raise HTTPException(422, "La campana necesita destinatarios validos")
    campaign = MessagingCampaign(
        name=payload.name.strip(), body=payload.body.strip(), channel=payload.channel,
        created_by=admin.external_id, status="pending",
        scheduled_at=payload.scheduled_at,
    )
    db.add(campaign)
    db.flush()
    db.add_all([
        MessagingCampaignRecipient(campaign_id=campaign.id, client_id=client_id)
        for client_id in sorted(client_ids)
    ])
    db.commit()
    db.refresh(campaign)
    background.add_task(process_campaign, campaign.id)
    return _serialize_campaign(db, campaign)


@router.post("/staff/admin/campaigns/{campaign_id}/retry", status_code=202)
def retry_campaign(
    campaign_id: str, background: BackgroundTasks,
    _admin: MessagingStaff = Depends(_require_admin), db: Session = Depends(get_db),
):
    campaign = db.get(MessagingCampaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campana no encontrada")
    if campaign.status == "sent":
        return {"ok": True, "already_sent": True}
    campaign.status = "pending"
    db.commit()
    background.add_task(process_campaign, campaign.id)
    return {"ok": True, "already_sent": False}


@router.get("/staff/admin/campaigns/{campaign_id}/recipients")
def campaign_recipients(
    campaign_id: str, _admin: MessagingStaff = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(MessagingCampaign, campaign_id):
        raise HTTPException(404, "Campana no encontrada")
    rows = db.scalars(select(MessagingCampaignRecipient).where(
        MessagingCampaignRecipient.campaign_id == campaign_id,
    )).all()
    return [{
        "id": row.id, "client_id": row.client_id, "status": row.status,
        "message_id": row.message_id, "error": row.error,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
    } for row in rows]


@router.put("/{audience}/app-devices")
def register_app_device(
    audience: str, payload: AppDeviceIn, request: Request, db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    if payload.platform not in {"android", "ios", "windows", "macos", "web"}:
        raise HTTPException(422, "Plataforma no valida")
    actor_id = actor.id if audience == "client" else actor.external_id
    item = db.scalar(select(MessagingAppDevice).where(
        MessagingAppDevice.push_token == payload.push_token,
    ))
    if not item:
        item = MessagingAppDevice(
            user_type=audience, user_id=actor_id, platform=payload.platform,
            push_token=payload.push_token,
        )
    item.user_type, item.user_id = audience, actor_id
    item.platform, item.device_name = payload.platform, payload.device_name.strip()
    item.app_version, item.active = payload.app_version.strip(), True
    item.last_seen_at = utcnow()
    db.add(item)
    db.commit()
    return {"id": item.id, "active": item.active, "fcm_configured": fcm_configured()}


@router.patch("/{audience}/app-devices/{device_id}/presence")
def app_device_presence(
    audience: str, device_id: str, request: Request,
    conversation_id: str = Form(default=""), db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    actor_id = actor.id if audience == "client" else actor.external_id
    item = db.get(MessagingAppDevice, device_id)
    if not item or item.user_type != audience or item.user_id != actor_id:
        raise HTTPException(404, "Dispositivo no encontrado")
    if conversation_id:
        if audience == "client":
            _conversation_for_client(db, conversation_id, actor)
        else:
            _conversation_for_staff(db, conversation_id, actor)
    item.active_conversation_id = conversation_id
    item.last_seen_at = utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/{audience}/app-devices/{device_id}", status_code=204)
def unregister_app_device(
    audience: str, device_id: str, request: Request, db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    actor_id = actor.id if audience == "client" else actor.external_id
    item = db.get(MessagingAppDevice, device_id)
    if not item or item.user_type != audience or item.user_id != actor_id:
        raise HTTPException(404, "Dispositivo no encontrado")
    item.active = False
    item.active_conversation_id = ""
    db.commit()
    return Response(status_code=204)


@router.post("/{audience}/ws-ticket")
def create_websocket_ticket(
    audience: str, request: Request, db: Session = Depends(get_db),
):
    actor = _resolve_actor(audience, request, db)
    actor_id = actor.id if audience == "client" else actor.external_id
    token = new_token()
    db.add(MessagingWebSocketTicket(
        user_type=audience, user_id=actor_id, token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(seconds=60),
    ))
    db.commit()
    return {"ticket": token, "expires_in": 60}


@router.websocket("/ws/{audience}")
async def messaging_websocket(websocket: WebSocket, audience: str, ticket: str = Query(default="")):
    if audience not in {"client", "staff"} or not ticket:
        await websocket.close(code=4401)
        return
    with SessionLocal() as db:
        ws_ticket = db.scalar(select(MessagingWebSocketTicket).where(
            MessagingWebSocketTicket.token_hash == hash_token(ticket),
            MessagingWebSocketTicket.user_type == audience,
        ))
        if not ws_ticket or ws_ticket.used_at or is_expired(ws_ticket.expires_at):
            await websocket.close(code=4401)
            return
        ws_ticket.used_at = utcnow()
        if audience == "client":
            actor = db.get(MessagingClient, ws_ticket.user_id)
            if not actor or not actor.active:
                await websocket.close(code=4401)
                return
            subscription = hub.subscribe(
                audience="client", actor_id=actor.id, organization_id=actor.organization_id,
            )
        else:
            actor = db.get(MessagingStaff, ws_ticket.user_id)
            if not actor or not actor.active:
                await websocket.close(code=4401)
                return
            subscription = hub.subscribe(
                audience="staff", actor_id=actor.external_id,
                channels=_channels_for_staff(db, actor),
            )
        db.commit()
    await websocket.accept()
    try:
        await websocket.send_json({"type": "connected"})
        while True:
            try:
                event = await asyncio.wait_for(subscription.queue.get(), timeout=25)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(subscription)


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
