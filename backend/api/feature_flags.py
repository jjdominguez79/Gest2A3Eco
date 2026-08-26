"""Control efectivo de feature flags de la plataforma cliente.

El estado efectivo combina el flag global (variable de entorno) con
el flag por organizacion (columna en msg_organizations).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.config import get_settings
from backend.api.messaging_models import MessagingOrganization


def is_documents_enabled(org: MessagingOrganization) -> bool:
    """Comprueba si el area documental esta activa para la organizacion."""
    settings = get_settings()
    return settings.client_documents_enabled and bool(
        org.client_documents_enabled
    )


def is_invoicing_enabled(org: MessagingOrganization) -> bool:
    """Comprueba si la facturacion online esta activa para la organizacion."""
    settings = get_settings()
    return settings.client_invoicing_enabled and bool(
        org.client_invoicing_enabled
    )


def require_documents_enabled(
    db: Session, org_id: str
) -> MessagingOrganization:
    """Exige que el area documental este habilitada. Lanza 403 si no."""
    org = db.get(MessagingOrganization, org_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")
    if not is_documents_enabled(org):
        raise HTTPException(
            status_code=403,
            detail="Area documental no habilitada para esta organizacion",
        )
    return org


def require_invoicing_enabled(
    db: Session, org_id: str
) -> MessagingOrganization:
    """Exige que la facturacion online este habilitada. Lanza 403 si no."""
    org = db.get(MessagingOrganization, org_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")
    if not is_invoicing_enabled(org):
        raise HTTPException(
            status_code=403,
            detail="Facturacion online no habilitada para esta organizacion",
        )
    return org
