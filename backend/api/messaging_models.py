from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.api.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class MessagingOrganization(Base):
    __tablename__ = "msg_organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    private_owner_external_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Perfil empresarial (sincronizado desde el escritorio)
    tax_id: Mapped[str] = mapped_column(String(20), default="")
    legal_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    postal_code: Mapped[str] = mapped_column(String(10), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    province: Mapped[str] = mapped_column(String(100), default="")
    country: Mapped[str] = mapped_column(String(60), default="ES")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    profile_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_invoicing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    client_documents_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MessagingStaff(Base):
    __tablename__ = "msg_staff"
    external_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), default="", index=True)
    entra_oid: Mapped[str] = mapped_column(String(64), default="", index=True)
    chat_alias: Mapped[str] = mapped_column(String(160), default="")
    avatar_storage_key: Mapped[str] = mapped_column(String(500), default="")
    avatar_content_type: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(32), default="empleado")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MessagingStaffChannel(Base):
    __tablename__ = "msg_staff_channels"
    __table_args__ = (UniqueConstraint("staff_external_id", "channel"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    staff_external_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True,
    )
    channel: Mapped[str] = mapped_column(String(20), index=True)  # laboral | fiscal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingStaffSession(Base):
    __tablename__ = "msg_staff_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    staff_external_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingStaffAuthFlow(Base):
    __tablename__ = "msg_staff_auth_flows"
    state: Mapped[str] = mapped_column(String(160), primary_key=True)
    flow_json: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class MessagingStaffThread(Base):
    __tablename__ = "msg_staff_threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # group | direct
    channel: Mapped[str] = mapped_column(String(20), default="", index=True)
    admin_staff_external_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    member_staff_external_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)


class MessagingStaffThreadMessage(Base):
    __tablename__ = "msg_staff_thread_messages"
    __table_args__ = (UniqueConstraint("thread_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff_threads.id", ondelete="CASCADE"), index=True,
    )
    author_staff_external_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True,
    )
    author_name: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    reply_to_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("msg_staff_thread_messages.id", ondelete="SET NULL"), index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str] = mapped_column(String(64), default="")
    deleted_by_type: Mapped[str] = mapped_column(String(16), default="")
    delete_reason: Mapped[str] = mapped_column(String(500), default="")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MessagingStaffThreadRead(Base):
    __tablename__ = "msg_staff_thread_reads"
    __table_args__ = (UniqueConstraint("thread_id", "staff_external_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff_threads.id", ondelete="CASCADE"), index=True,
    )
    staff_external_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True,
    )
    last_message_id: Mapped[str] = mapped_column(String(36), default="")
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingDevice(Base):
    __tablename__ = "msg_devices"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessagingClient(Base):
    __tablename__ = "msg_clients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)




class MessagingInvitation(Base):
    __tablename__ = "msg_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingPasswordReset(Base):
    __tablename__ = "msg_password_resets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingSession(Base):
    __tablename__ = "msg_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingPresence(Base):
    __tablename__ = "msg_presence"
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), primary_key=True)
    connected_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MessagingConversation(Base):
    __tablename__ = "msg_conversations"
    __table_args__ = (UniqueConstraint("organization_id", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # laboral | fiscal | private
    state: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    assigned_staff_external_id: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)


class MessagingMessage(Base):
    __tablename__ = "msg_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("msg_conversations.id", ondelete="CASCADE"), index=True)
    author_type: Mapped[str] = mapped_column(String(16))  # client | staff | system
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    reply_to_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("msg_messages.id", ondelete="SET NULL"), index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str] = mapped_column(String(64), default="")
    deleted_by_type: Mapped[str] = mapped_column(String(16), default="")
    delete_reason: Mapped[str] = mapped_column(String(500), default="")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MessagingAttachment(Base):
    __tablename__ = "msg_attachments"
    __table_args__ = (
        CheckConstraint(
            "(message_id IS NOT NULL AND internal_message_id IS NULL) OR "
            "(message_id IS NULL AND internal_message_id IS NOT NULL)",
            name="ck_msg_attachments_single_parent",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("msg_messages.id", ondelete="CASCADE"), index=True,
    )
    internal_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("msg_staff_thread_messages.id", ondelete="CASCADE"), index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    direction: Mapped[str] = mapped_column(String(16))  # incoming | outgoing
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by: Mapped[str] = mapped_column(String(120), default="")
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Retirada de documento (sustituye al borrado para mensajes con adjuntos salientes)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[str] = mapped_column(String(64), default="")
    withdrawal_reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingRead(Base):
    __tablename__ = "msg_reads"
    __table_args__ = (UniqueConstraint("conversation_id", "actor_type", "actor_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("msg_conversations.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str] = mapped_column(String(64))
    last_message_id: Mapped[str] = mapped_column(String(36), default="")
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingDownload(Base):
    __tablename__ = "msg_downloads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attachment_id: Mapped[str] = mapped_column(ForeignKey("msg_attachments.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Confirmacion de guardado completo por Flutter (distingue iniciada de completada)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessagingEvent(Base):
    __tablename__ = "msg_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MessagingGroup(Base):
    __tablename__ = "msg_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    group_type: Mapped[str] = mapped_column(String(20), index=True)  # staff_chat | client_list
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MessagingGroupMember(Base):
    __tablename__ = "msg_group_members"
    __table_args__ = (UniqueConstraint("group_id", "member_type", "member_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(ForeignKey("msg_groups.id", ondelete="CASCADE"), index=True)
    member_type: Mapped[str] = mapped_column(String(16), index=True)  # staff | client
    member_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingCampaign(Base):
    __tablename__ = "msg_campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="fiscal")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessagingCampaignRecipient(Base):
    __tablename__ = "msg_campaign_recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "client_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("msg_campaigns.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("msg_messages.id", ondelete="SET NULL"), index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessagingAppDevice(Base):
    __tablename__ = "msg_app_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_type: Mapped[str] = mapped_column(String(16), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    push_token: Mapped[str] = mapped_column(Text, unique=True)
    device_name: Mapped[str] = mapped_column(String(160), default="")
    app_version: Mapped[str] = mapped_column(String(40), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    active_conversation_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    active_target_type: Mapped[str] = mapped_column(String(24), default="", index=True)
    active_target_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingDeletionAudit(Base):
    __tablename__ = "msg_deletion_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # soft_delete | hard_delete
    reason: Mapped[str] = mapped_column(String(500), default="")
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingStaffAppCode(Base):
    __tablename__ = "msg_staff_app_codes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    staff_external_id: Mapped[str] = mapped_column(ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="mobile")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingWebSocketTicket(Base):
    __tablename__ = "msg_websocket_tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_type: Mapped[str] = mapped_column(String(16), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    staff_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("msg_staff_sessions.id", ondelete="CASCADE"), index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessagingCleanupAudit(Base):
    __tablename__ = "msg_cleanup_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(String(500))
    scope: Mapped[str] = mapped_column(String(32))
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    counts_json: Mapped[str] = mapped_column(Text, default="{}")
    confirmation_code: Mapped[str] = mapped_column(String(32), index=True)
    storage_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    failed_storage_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MessagingCleanupPolicy(Base):
    __tablename__ = "msg_cleanup_policy"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="pre_release")
    publication_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_locked_by: Mapped[str] = mapped_column(String(160), default="")
    maintenance_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_actor: Mapped[str] = mapped_column(String(160), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class MessagingStaffPresenceConnection(Base):
    __tablename__ = "msg_staff_presence_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    staff_external_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff.external_id", ondelete="CASCADE"), index=True,
    )
    staff_session_id: Mapped[str] = mapped_column(
        ForeignKey("msg_staff_sessions.id", ondelete="CASCADE"), index=True,
    )
    connected_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )
