"""Servicio de cola de publicacion documental desde el escritorio.

Gestiona la publicacion asincrona de documentos (facturas) en el area del
cliente cuando se envian por email desde el escritorio.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.client_models import ClientDocument, DesktopPublicationQueue
from backend.api.client_storage import ClientDocumentStorage
from backend.api.client_validation import normalize_tax_id
from backend.api.messaging_models import MessagingOrganization
from backend.api.messaging_security import utcnow

logger = logging.getLogger(__name__)


def enqueue_publication(
    db: Session,
    *,
    organization_id: str,
    source_type: str,
    source_id: str,
    source_version: int = 1,
    local_pdf_path: str,
    display_name: str,
    document_date: datetime | None = None,
    fiscal_year: int = 0,
    amount: Decimal | None = None,
    customer_tax_id: str = "",
) -> DesktopPublicationQueue:
    """Encola una publicacion pendiente. Idempotente por source."""
    existing = db.scalar(
        select(DesktopPublicationQueue).where(
            DesktopPublicationQueue.organization_id == organization_id,
            DesktopPublicationQueue.source_type == source_type,
            DesktopPublicationQueue.source_id == source_id,
            DesktopPublicationQueue.source_version == source_version,
        )
    )
    if existing:
        return existing

    item = DesktopPublicationQueue(
        organization_id=organization_id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        local_pdf_path=local_pdf_path,
        display_name=display_name,
        document_date=document_date,
        fiscal_year=fiscal_year,
        amount=amount,
        customer_tax_id=customer_tax_id,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def find_organization_by_tax_id(
    db: Session, tax_id: str,
) -> MessagingOrganization | None:
    """Busca organizacion por NIF. Devuelve None si es ambiguo (>1 resultado)."""
    normalized = normalize_tax_id(tax_id)
    if not normalized:
        return None

    orgs = db.scalars(
        select(MessagingOrganization).where(
            MessagingOrganization.tax_id == normalized,
            MessagingOrganization.active.is_(True),
        )
    ).all()

    if len(orgs) == 1:
        return orgs[0]
    return None


def process_pending_publications(
    db: Session,
    storage: ClientDocumentStorage,
) -> list[str]:
    """Procesa publicaciones pendientes. Devuelve IDs procesados."""
    pending = db.scalars(
        select(DesktopPublicationQueue).where(
            DesktopPublicationQueue.status == "pending",
        ).order_by(DesktopPublicationQueue.created_at)
        .limit(20)
    ).all()

    processed = []
    for item in pending:
        try:
            _process_one(db, storage, item)
            processed.append(item.id)
        except Exception:
            logger.exception(
                "Error procesando publicacion %s", item.id,
            )
            item.status = "error"
            item.error_message = "Error interno al publicar"
            item.updated_at = utcnow()
            db.commit()

    return processed


def _process_one(
    db: Session,
    storage: ClientDocumentStorage,
    item: DesktopPublicationQueue,
) -> None:
    """Procesa un elemento de la cola."""
    # Verificar que el PDF existe localmente
    pdf_path = Path(item.local_pdf_path)
    if not pdf_path.is_file():
        item.status = "error"
        item.error_message = f"PDF no encontrado: {item.local_pdf_path}"
        item.updated_at = utcnow()
        db.commit()
        return

    # Leer PDF
    content = pdf_path.read_bytes()
    sha256 = storage.compute_sha256(content)

    # Verificar idempotencia del documento final
    existing_doc = db.scalar(
        select(ClientDocument).where(
            ClientDocument.organization_id == item.organization_id,
            ClientDocument.source_system == "desktop_invoice",
            ClientDocument.source_id == item.source_id,
            ClientDocument.source_version == item.source_version,
        )
    )
    if existing_doc:
        item.status = "published"
        item.document_id = existing_doc.id
        item.updated_at = utcnow()
        db.commit()
        return

    # Subir al blob permanente
    blob_key = storage.put(
        content, pdf_path.name,
        organization_id=item.organization_id,
    )

    # Crear documento
    doc = ClientDocument(
        organization_id=item.organization_id,
        document_type="factura",
        source_system="desktop_invoice",
        source_id=item.source_id,
        source_version=item.source_version,
        display_name=item.display_name,
        document_date=item.document_date,
        fiscal_year=item.fiscal_year,
        amount=item.amount,
        currency="EUR",
        file_name=pdf_path.name,
        content_type="application/pdf",
        file_size=len(content),
        sha256=sha256,
        blob_key=blob_key,
        status="published",
        published_at=utcnow(),
    )
    db.add(doc)
    db.flush()

    item.status = "published"
    item.document_id = doc.id
    item.updated_at = utcnow()
    db.commit()


def retry_errored(db: Session, storage: ClientDocumentStorage) -> list[str]:
    """Reintenta publicaciones con error."""
    errored = db.scalars(
        select(DesktopPublicationQueue).where(
            DesktopPublicationQueue.status == "error",
        ).limit(10)
    ).all()

    retried = []
    for item in errored:
        item.status = "pending"
        item.error_message = ""
        item.updated_at = utcnow()
        db.commit()
        try:
            _process_one(db, storage, item)
            retried.append(item.id)
        except Exception:
            logger.exception("Error reintentando publicacion %s", item.id)

    return retried
