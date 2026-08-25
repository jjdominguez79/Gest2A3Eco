from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingAttachment,
    MessagingCampaignRecipient,
    MessagingCleanupAudit,
    MessagingClient,
    MessagingConversation,
    MessagingDeletionAudit,
    MessagingDownload,
    MessagingEvent,
    MessagingGroupMember,
    MessagingInvitation,
    MessagingMessage,
    MessagingOrganization,
    MessagingPasswordReset,
    MessagingPresence,
    MessagingRead,
    MessagingSession,
)
from backend.api.messaging_storage import MessagingStorage


CHUNK_SIZE = 500


@dataclass(frozen=True)
class CleanupPlan:
    scope: str
    organization_ids: tuple[str, ...]
    company_codes: tuple[str, ...]
    client_ids: tuple[str, ...]
    conversation_ids: tuple[str, ...]
    message_ids: tuple[str, ...]
    attachment_ids: tuple[str, ...]
    storage_keys: tuple[str, ...]
    event_ids: tuple[int, ...]
    counts: dict[str, int]
    cutoff: datetime | None
    confirmation_code: str

    def public_dict(self) -> dict:
        return {
            "scope": self.scope,
            "organizations": list(self.company_codes),
            "cutoff": self.cutoff.isoformat() if self.cutoff else None,
            "counts": self.counts,
            "confirmation_code": self.confirmation_code,
        }


@dataclass(frozen=True)
class CleanupResult:
    audit_id: str
    counts: dict[str, int]
    failed_storage_keys: tuple[str, ...]


def _chunks(values: tuple[str, ...] | tuple[int, ...]) -> Iterable[tuple]:
    for index in range(0, len(values), CHUNK_SIZE):
        yield values[index:index + CHUNK_SIZE]


def _normalized_cutoff(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _confirmation_payload(plan: CleanupPlan) -> dict:
    return {
        "scope": plan.scope,
        "organizations": plan.organization_ids,
        "clients": plan.client_ids,
        "conversations": plan.conversation_ids,
        "messages": plan.message_ids,
        "attachments": plan.attachment_ids,
        "storage_keys": plan.storage_keys,
        "events": plan.event_ids,
        "cutoff": plan.cutoff.isoformat() if plan.cutoff else None,
    }


def _make_confirmation_code(plan: CleanupPlan) -> str:
    raw = json.dumps(
        _confirmation_payload(plan), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return f"LIMPIAR-{hashlib.sha256(raw).hexdigest()[:12].upper()}"


def build_cleanup_plan(
    db: Session,
    *,
    organization_refs: Iterable[str] = (),
    cutoff: datetime | None = None,
    reset_test: bool = False,
) -> CleanupPlan:
    """Calcula una seleccion inmutable limitada a organizaciones de prueba."""
    cutoff = _normalized_cutoff(cutoff)
    if reset_test == (cutoff is not None):
        raise ValueError("Indica exactamente uno de: reset_test o cutoff.")

    requested = tuple(sorted({value.strip() for value in organization_refs if value.strip()}))
    organizations = list(db.scalars(
        select(MessagingOrganization)
        .where(MessagingOrganization.is_test.is_(True))
        .order_by(MessagingOrganization.company_code)
    ))
    if requested:
        requested_upper = {value.upper() for value in requested}
        organizations = [
            item for item in organizations
            if item.id in requested or item.company_code.upper() in requested_upper
        ]
        found = {item.id for item in organizations} | {
            item.company_code.upper() for item in organizations
        }
        missing = [value for value in requested if value not in found and value.upper() not in found]
        if missing:
            raise ValueError(
                "No existen o no estan marcadas como prueba: " + ", ".join(missing)
            )

    organization_ids = tuple(item.id for item in organizations)
    company_codes = tuple(item.company_code for item in organizations)
    if organization_ids:
        clients = tuple(db.scalars(select(MessagingClient.id).where(
            MessagingClient.organization_id.in_(organization_ids),
        )))
        conversations = tuple(db.scalars(select(MessagingConversation.id).where(
            MessagingConversation.organization_id.in_(organization_ids),
        )))
    else:
        clients, conversations = (), ()

    message_stmt = select(MessagingMessage.id).where(
        MessagingMessage.conversation_id.in_(conversations),
    )
    if cutoff is not None:
        message_stmt = message_stmt.where(MessagingMessage.created_at < cutoff)
    messages = tuple(db.scalars(message_stmt.order_by(MessagingMessage.id))) if conversations else ()

    if messages:
        attachments = tuple(db.scalars(select(MessagingAttachment.id).where(
            MessagingAttachment.message_id.in_(messages),
        ).order_by(MessagingAttachment.id)))
    else:
        attachments = ()
    storage_keys = tuple(db.scalars(select(MessagingAttachment.storage_key).where(
        MessagingAttachment.id.in_(attachments),
        MessagingAttachment.storage_deleted_at.is_(None),
        MessagingAttachment.storage_key != "",
    ).order_by(MessagingAttachment.storage_key))) if attachments else ()

    event_stmt = select(MessagingEvent.id).where(
        MessagingEvent.organization_id.in_(organization_ids),
    )
    if cutoff is not None:
        event_stmt = event_stmt.where(MessagingEvent.created_at < cutoff)
    events = tuple(db.scalars(event_stmt.order_by(MessagingEvent.id))) if organization_ids else ()

    def count_for(model, condition) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(condition)) or 0)

    counts = {
        "organizations_selected": len(organization_ids),
        "organizations_to_delete": len(organization_ids) if reset_test else 0,
        "clients_to_delete": len(clients) if reset_test else 0,
        "conversations_to_delete": len(conversations) if reset_test else 0,
        "messages_to_delete": len(messages),
        "attachments_to_delete": len(attachments),
        "storage_objects_to_delete": len(storage_keys),
        "attachment_bytes_to_delete": int(db.scalar(select(
            func.coalesce(func.sum(MessagingAttachment.size), 0),
        ).where(MessagingAttachment.id.in_(attachments))) or 0) if attachments else 0,
        "events_to_delete": len(events),
        "downloads_to_delete": count_for(
            MessagingDownload, MessagingDownload.attachment_id.in_(attachments),
        ) if attachments else 0,
        "deletion_audits_to_delete": count_for(
            MessagingDeletionAudit,
            MessagingDeletionAudit.conversation_id.in_(conversations),
        ) if reset_test and conversations else (
            count_for(
                MessagingDeletionAudit, MessagingDeletionAudit.message_id.in_(messages),
            ) if messages else 0
        ),
        "campaign_recipients_to_delete": count_for(
            MessagingCampaignRecipient, MessagingCampaignRecipient.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "group_members_to_delete": count_for(
            MessagingGroupMember,
            (MessagingGroupMember.member_type == "client")
            & MessagingGroupMember.member_id.in_(clients),
        ) if reset_test and clients else 0,
        "app_devices_to_delete": count_for(
            MessagingAppDevice,
            (MessagingAppDevice.user_type == "client")
            & MessagingAppDevice.user_id.in_(clients),
        ) if reset_test and clients else 0,
        "sessions_to_delete": count_for(
            MessagingSession, MessagingSession.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "invitations_to_delete": count_for(
            MessagingInvitation, MessagingInvitation.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "password_resets_to_delete": count_for(
            MessagingPasswordReset, MessagingPasswordReset.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "presence_rows_to_delete": count_for(
            MessagingPresence, MessagingPresence.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "read_markers_to_delete": count_for(
            MessagingRead, MessagingRead.conversation_id.in_(conversations),
        ) if reset_test and conversations else 0,
    }
    provisional = CleanupPlan(
        scope="reset_test" if reset_test else "messages_before",
        organization_ids=organization_ids,
        company_codes=company_codes,
        client_ids=clients,
        conversation_ids=conversations,
        message_ids=messages,
        attachment_ids=attachments,
        storage_keys=storage_keys,
        event_ids=events,
        counts=counts,
        cutoff=cutoff,
        confirmation_code="",
    )
    return CleanupPlan(
        **{**provisional.__dict__, "confirmation_code": _make_confirmation_code(provisional)},
    )


def _delete_chunks(db: Session, model, column, values: tuple) -> None:
    for chunk in _chunks(values):
        db.execute(delete(model).where(column.in_(chunk)))


def execute_cleanup_plan(
    db: Session,
    plan: CleanupPlan,
    *,
    confirmation_code: str,
    actor: str,
    reason: str,
    storage: MessagingStorage | None = None,
) -> CleanupResult:
    if confirmation_code.strip().upper() != plan.confirmation_code:
        raise ValueError("El codigo no coincide con el plan actual. Repite la previsualizacion.")
    actor, reason = actor.strip(), reason.strip()
    if not actor or not reason:
        raise ValueError("Actor y motivo son obligatorios para ejecutar la limpieza.")
    if not plan.organization_ids:
        raise ValueError("No hay organizaciones de prueba seleccionadas.")

    audit = MessagingCleanupAudit(
        actor=actor[:160],
        reason=reason[:500],
        scope=plan.scope,
        filters_json=json.dumps({
            "organizations": plan.company_codes,
            "cutoff": plan.cutoff.isoformat() if plan.cutoff else None,
        }, sort_keys=True),
        counts_json=json.dumps(plan.counts, sort_keys=True),
        confirmation_code=plan.confirmation_code,
        storage_keys_json=json.dumps(plan.storage_keys),
    )
    db.add(audit)

    if plan.message_ids:
        for chunk in _chunks(plan.message_ids):
            db.execute(update(MessagingCampaignRecipient).where(
                MessagingCampaignRecipient.message_id.in_(chunk),
            ).values(message_id=None))
            db.execute(update(MessagingMessage).where(
                MessagingMessage.reply_to_message_id.in_(chunk),
            ).values(reply_to_message_id=None))
            db.execute(update(MessagingRead).where(
                MessagingRead.last_message_id.in_(chunk),
            ).values(last_message_id=""))
            db.execute(delete(MessagingDeletionAudit).where(
                MessagingDeletionAudit.message_id.in_(chunk),
            ))
    _delete_chunks(db, MessagingDownload, MessagingDownload.attachment_id, plan.attachment_ids)
    _delete_chunks(db, MessagingAttachment, MessagingAttachment.id, plan.attachment_ids)
    _delete_chunks(db, MessagingMessage, MessagingMessage.id, plan.message_ids)
    _delete_chunks(db, MessagingEvent, MessagingEvent.id, plan.event_ids)

    if plan.scope == "reset_test":
        for chunk in _chunks(plan.client_ids):
            db.execute(delete(MessagingGroupMember).where(
                MessagingGroupMember.member_type == "client",
                MessagingGroupMember.member_id.in_(chunk),
            ))
            db.execute(delete(MessagingAppDevice).where(
                MessagingAppDevice.user_type == "client",
                MessagingAppDevice.user_id.in_(chunk),
            ))
            db.execute(delete(MessagingCampaignRecipient).where(
                MessagingCampaignRecipient.client_id.in_(chunk),
            ))
        _delete_chunks(db, MessagingInvitation, MessagingInvitation.client_id, plan.client_ids)
        _delete_chunks(db, MessagingPasswordReset, MessagingPasswordReset.client_id, plan.client_ids)
        _delete_chunks(db, MessagingSession, MessagingSession.client_id, plan.client_ids)
        _delete_chunks(db, MessagingPresence, MessagingPresence.client_id, plan.client_ids)
        _delete_chunks(db, MessagingRead, MessagingRead.conversation_id, plan.conversation_ids)
        _delete_chunks(
            db, MessagingDeletionAudit, MessagingDeletionAudit.conversation_id,
            plan.conversation_ids,
        )
        _delete_chunks(db, MessagingConversation, MessagingConversation.id, plan.conversation_ids)
        _delete_chunks(db, MessagingClient, MessagingClient.id, plan.client_ids)
        _delete_chunks(db, MessagingOrganization, MessagingOrganization.id, plan.organization_ids)
    else:
        for conversation_id in plan.conversation_ids:
            first_at = db.scalar(select(func.min(MessagingMessage.created_at)).where(
                MessagingMessage.conversation_id == conversation_id,
            ))
            last_at = db.scalar(select(func.max(MessagingMessage.created_at)).where(
                MessagingMessage.conversation_id == conversation_id,
            ))
            conversation_created_at = db.scalar(select(
                MessagingConversation.created_at,
            ).where(MessagingConversation.id == conversation_id))
            db.execute(update(MessagingConversation).where(
                MessagingConversation.id == conversation_id,
            ).values(
                started_at=first_at,
                updated_at=last_at or conversation_created_at,
            ))

    db.commit()
    db.refresh(audit)

    storage = storage or MessagingStorage()
    failed: list[str] = []
    for key in plan.storage_keys:
        try:
            storage.delete(key)
        except Exception:
            failed.append(key)
    if failed:
        audit.failed_storage_keys_json = json.dumps(failed)
        db.commit()
    return CleanupResult(
        audit_id=audit.id,
        counts=plan.counts,
        failed_storage_keys=tuple(failed),
    )
