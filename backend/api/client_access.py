"""Operaciones compartidas sobre el acceso de clientes a Flutter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingClient,
    MessagingInvitation,
    MessagingSession,
)
from backend.api.messaging_security import utcnow


def revoke_organization_client_access(db: Session, organization_id: str) -> int:
    """Desactiva todas las credenciales de una organizacion sin borrar datos."""
    client_ids = list(db.scalars(select(MessagingClient.id).where(
        MessagingClient.organization_id == organization_id,
    )))
    if not client_ids:
        return 0

    now = utcnow()
    db.query(MessagingClient).filter(
        MessagingClient.id.in_(client_ids),
    ).update({MessagingClient.active: False}, synchronize_session=False)
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
    return len(client_ids)
