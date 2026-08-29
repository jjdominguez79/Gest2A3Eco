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
    MessagingCleanupPolicy,
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
    MessagingStaffThread,
    MessagingStaffThreadMessage,
    MessagingStaffThreadRead,
)
from backend.api.config import get_settings
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
    internal_thread_ids: tuple[str, ...]
    internal_message_ids: tuple[str, ...]
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
            "includes_internal_messages": bool(self.internal_thread_ids),
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


def _values_for_chunks(db: Session, selected_column, match_column, values: tuple) -> tuple:
    result = []
    for chunk in _chunks(values):
        result.extend(db.scalars(select(selected_column).where(match_column.in_(chunk))))
    return tuple(result)


def _count_for_chunks(db: Session, model, match_column, values: tuple) -> int:
    total = 0
    for chunk in _chunks(values):
        total += int(db.scalar(select(func.count()).select_from(model).where(
            match_column.in_(chunk),
        )) or 0)
    return total


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
        "internal_threads": plan.internal_thread_ids,
        "internal_messages": plan.internal_message_ids,
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
    pre_release: bool = False,
) -> CleanupPlan:
    """Calcula una seleccion inmutable de prueba o global de prepublicacion."""
    cutoff = _normalized_cutoff(cutoff)
    requested = tuple(sorted({value.strip() for value in organization_refs if value.strip()}))
    if pre_release:
        if reset_test or cutoff is None or requested:
            raise ValueError(
                "La purga de prepublicacion exige cutoff y no admite organizaciones."
            )
    elif reset_test == (cutoff is not None):
        raise ValueError("Indica exactamente uno de: reset_test o cutoff.")

    organization_stmt = select(MessagingOrganization).order_by(
        MessagingOrganization.company_code,
    )
    if not pre_release:
        organization_stmt = organization_stmt.where(MessagingOrganization.is_test.is_(True))
    organizations = list(db.scalars(organization_stmt))
    if requested and not pre_release:
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

    internal_threads = tuple(db.scalars(select(MessagingStaffThread.id).order_by(
        MessagingStaffThread.id,
    ))) if pre_release else ()
    internal_messages = tuple(db.scalars(select(MessagingStaffThreadMessage.id).where(
        MessagingStaffThreadMessage.created_at < cutoff,
    ).order_by(MessagingStaffThreadMessage.id))) if pre_release else ()

    attachment_values = list(_values_for_chunks(
        db, MessagingAttachment.id, MessagingAttachment.message_id, messages,
    ))
    attachment_values.extend(_values_for_chunks(
        db, MessagingAttachment.id, MessagingAttachment.internal_message_id,
        internal_messages,
    ))
    attachments = tuple(sorted(set(attachment_values)))
    storage_key_values = []
    for chunk in _chunks(attachments):
        storage_key_values.extend(db.scalars(select(MessagingAttachment.storage_key).where(
            MessagingAttachment.id.in_(chunk),
            MessagingAttachment.storage_deleted_at.is_(None),
            MessagingAttachment.storage_key != "",
        )))
    storage_keys = tuple(sorted(storage_key_values))

    event_stmt = select(MessagingEvent.id)
    if not pre_release:
        event_stmt = event_stmt.where(MessagingEvent.organization_id.in_(organization_ids))
    if cutoff is not None:
        event_stmt = event_stmt.where(MessagingEvent.created_at < cutoff)
    events = tuple(db.scalars(event_stmt.order_by(MessagingEvent.id))) if (
        organization_ids or pre_release
    ) else ()

    def count_for(model, condition) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(condition)) or 0)

    counts = {
        "organizations_selected": len(organization_ids),
        "organizations_to_delete": len(organization_ids) if reset_test else 0,
        "clients_to_delete": len(clients) if reset_test else 0,
        "conversations_to_delete": len(conversations) if reset_test else 0,
        "messages_to_delete": len(messages),
        "internal_messages_to_delete": len(internal_messages),
        "internal_threads_selected": len(internal_threads),
        "attachments_to_delete": len(attachments),
        "storage_objects_to_delete": len(storage_keys),
        "attachment_bytes_to_delete": sum(
            int(db.scalar(select(func.coalesce(func.sum(MessagingAttachment.size), 0)).where(
                MessagingAttachment.id.in_(chunk),
            )) or 0) for chunk in _chunks(attachments)
        ),
        "events_to_delete": len(events),
        "downloads_to_delete": _count_for_chunks(
            db, MessagingDownload, MessagingDownload.attachment_id, attachments,
        ),
        "deletion_audits_to_delete": count_for(
            MessagingDeletionAudit,
            MessagingDeletionAudit.conversation_id.in_(conversations),
        ) if reset_test and conversations else (
            _count_for_chunks(
                db, MessagingDeletionAudit, MessagingDeletionAudit.message_id,
                messages + internal_messages,
            )
        ),
        "campaign_recipients_to_delete": count_for(
            MessagingCampaignRecipient, MessagingCampaignRecipient.client_id.in_(clients),
        ) if reset_test and clients else 0,
        "campaign_recipients_to_unlink": _count_for_chunks(
            db, MessagingCampaignRecipient, MessagingCampaignRecipient.message_id,
            messages,
        ) if pre_release else 0,
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
        scope=(
            "pre_release_global" if pre_release
            else ("reset_test" if reset_test else "messages_before")
        ),
        organization_ids=organization_ids,
        company_codes=company_codes,
        client_ids=clients,
        conversation_ids=conversations,
        message_ids=messages,
        internal_thread_ids=internal_threads,
        internal_message_ids=internal_messages,
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


POLICY_ID = "pre_release"
CLOSE_CONFIRMATION = "CERRAR-PREPUBLICACION-DEFINITIVAMENTE"
RECOVER_CONFIRMATION = "RECUPERAR-MANTENIMIENTO-MENSAJERIA"


def _cleanup_policy(db: Session, *, lock: bool = False) -> MessagingCleanupPolicy:
    if lock:
        policy = db.scalar(select(MessagingCleanupPolicy).where(
            MessagingCleanupPolicy.id == POLICY_ID,
        ).with_for_update())
    else:
        policy = db.get(MessagingCleanupPolicy, POLICY_ID)
    if policy is None:
        policy = MessagingCleanupPolicy(id=POLICY_ID)
        db.add(policy)
        db.flush()
    return policy


def _require_pre_release_enabled(
    db: Session, *, lock: bool = False,
) -> MessagingCleanupPolicy:
    if not get_settings().messaging_pre_release_cleanup_enabled:
        raise ValueError(
            "MESSAGING_PRE_RELEASE_CLEANUP_ENABLED no esta activado."
        )
    policy = _cleanup_policy(db, lock=lock)
    if policy.publication_locked_at:
        raise ValueError(
            "La purga global fue cerrada definitivamente al publicar la aplicacion."
        )
    return policy


def close_pre_release_cleanup(
    db: Session, *, confirmation: str, actor: str, reason: str,
) -> str:
    actor, reason = actor.strip(), reason.strip()
    if confirmation.strip().upper() != CLOSE_CONFIRMATION:
        raise ValueError(f"La confirmacion requerida es {CLOSE_CONFIRMATION}.")
    if not actor or not reason:
        raise ValueError("Actor y motivo son obligatorios.")
    policy = _require_pre_release_enabled(db, lock=True)
    if policy.maintenance_started_at:
        raise ValueError("No se puede cerrar mientras hay una limpieza en mantenimiento.")
    policy.publication_locked_at = datetime.now(timezone.utc)
    policy.publication_locked_by = actor[:160]
    audit = MessagingCleanupAudit(
        actor=actor[:160], reason=reason[:500], scope="close_pre_release",
        filters_json="{}", counts_json="{}",
        confirmation_code=CLOSE_CONFIRMATION,
    )
    db.add(audit)
    db.commit()
    return audit.id


def recover_cleanup_maintenance(
    db: Session, *, confirmation: str, actor: str, reason: str,
) -> str:
    actor, reason = actor.strip(), reason.strip()
    if confirmation.strip().upper() != RECOVER_CONFIRMATION:
        raise ValueError(f"La confirmacion requerida es {RECOVER_CONFIRMATION}.")
    if not actor or not reason:
        raise ValueError("Actor y motivo son obligatorios.")
    policy = _cleanup_policy(db, lock=True)
    if not policy.maintenance_started_at:
        raise ValueError("La mensajeria no esta bloqueada por una limpieza.")
    policy.maintenance_started_at = None
    policy.maintenance_actor = ""
    audit = MessagingCleanupAudit(
        actor=actor[:160], reason=reason[:500], scope="recover_maintenance",
        filters_json="{}", counts_json="{}",
        confirmation_code=RECOVER_CONFIRMATION,
    )
    db.add(audit)
    db.commit()
    return audit.id


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
    is_pre_release = plan.scope == "pre_release_global"
    if not is_pre_release and not plan.organization_ids:
        raise ValueError("No hay organizaciones de prueba seleccionadas.")

    maintenance_active = False
    if is_pre_release:
        policy = _require_pre_release_enabled(db, lock=True)
        if policy.maintenance_started_at:
            raise ValueError(
                "Ya existe una limpieza en mantenimiento. Recuperala antes de continuar."
            )
        policy.maintenance_started_at = datetime.now(timezone.utc)
        policy.maintenance_actor = actor[:160]
        db.commit()
        maintenance_active = True

    try:
        if is_pre_release:
            # El mantenimiento ya bloquea nuevas escrituras. Recalculamos el plan
            # para cerrar la pequena ventana entre la CLI y el bloqueo del backend.
            current_plan = build_cleanup_plan(
                db, cutoff=plan.cutoff, pre_release=True,
            )
            if current_plan.confirmation_code != confirmation_code.strip().upper():
                raise ValueError(
                    "El contenido cambio antes de activar mantenimiento. "
                    "Repite la previsualizacion."
                )
            plan = current_plan
        audit = MessagingCleanupAudit(
            actor=actor[:160],
            reason=reason[:500],
            scope=plan.scope,
            filters_json=json.dumps({
                "organizations": plan.company_codes,
                "cutoff": plan.cutoff.isoformat() if plan.cutoff else None,
                "includes_internal_messages": is_pre_release,
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
        if plan.internal_message_ids:
            for chunk in _chunks(plan.internal_message_ids):
                db.execute(update(MessagingStaffThreadMessage).where(
                    MessagingStaffThreadMessage.reply_to_message_id.in_(chunk),
                ).values(reply_to_message_id=None))
                db.execute(update(MessagingStaffThreadRead).where(
                    MessagingStaffThreadRead.last_message_id.in_(chunk),
                ).values(last_message_id=""))
        for chunk in _chunks(plan.message_ids + plan.internal_message_ids):
            db.execute(delete(MessagingDeletionAudit).where(
                MessagingDeletionAudit.message_id.in_(chunk),
            ))
        _delete_chunks(db, MessagingDownload, MessagingDownload.attachment_id, plan.attachment_ids)
        _delete_chunks(db, MessagingAttachment, MessagingAttachment.id, plan.attachment_ids)
        _delete_chunks(db, MessagingMessage, MessagingMessage.id, plan.message_ids)
        _delete_chunks(
            db, MessagingStaffThreadMessage, MessagingStaffThreadMessage.id,
            plan.internal_message_ids,
        )
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
            for thread_id in plan.internal_thread_ids:
                last_at = db.scalar(select(func.max(
                    MessagingStaffThreadMessage.created_at,
                )).where(MessagingStaffThreadMessage.thread_id == thread_id))
                thread_created_at = db.scalar(select(
                    MessagingStaffThread.created_at,
                ).where(MessagingStaffThread.id == thread_id))
                db.execute(update(MessagingStaffThread).where(
                    MessagingStaffThread.id == thread_id,
                ).values(updated_at=last_at or thread_created_at))

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
    finally:
        if maintenance_active:
            db.rollback()
            policy = _cleanup_policy(db)
            policy.maintenance_started_at = None
            policy.maintenance_actor = ""
            db.commit()
