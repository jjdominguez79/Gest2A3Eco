"""Modelos SQLAlchemy para el area privada del cliente: documentos y facturacion."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.api.database import Base
from backend.api.messaging_models import new_id, utcnow


# ==========================================================================
# DOCUMENTOS DEL CLIENTE
# ==========================================================================

class ClientDocument(Base):
    """Documento permanente publicado en el area del cliente."""
    __tablename__ = "client_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_system", "source_id", "source_version",
            name="uq_client_documents_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )

    # Tipo de documento visible para el cliente (factura, nomina, certificado...)
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    # Sistema origen: desktop_invoice | client_invoice
    source_system: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[str] = mapped_column(String(120), index=True)
    source_version: Mapped[int] = mapped_column(Integer, default=1)

    # Metadatos visibles
    display_name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fiscal_year: Mapped[int] = mapped_column(Integer, default=0, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Archivo en blob storage permanente
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/pdf")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    blob_key: Mapped[str] = mapped_column(String(500), unique=True)

    # Estado: published | replaced | withdrawn
    status: Mapped[str] = mapped_column(String(20), default="published", index=True)
    replaced_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("client_documents.id", ondelete="SET NULL"),
    )
    withdrawal_reason: Mapped[str] = mapped_column(Text, default="")

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class ClientDocumentRead(Base):
    """Registro de lectura de un documento por un usuario cliente."""
    __tablename__ = "client_document_reads"
    __table_args__ = (
        UniqueConstraint("document_id", "client_id", name="uq_client_doc_read"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("client_documents.id", ondelete="CASCADE"), index=True,
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True,
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ==========================================================================
# FACTURACION DEL CLIENTE
# ==========================================================================

class ClientInvoiceSeries(Base):
    """Serie de facturacion online por organizacion."""
    __tablename__ = "client_invoice_series"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "fiscal_year", "series_code",
            name="uq_client_inv_series",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    series_code: Mapped[str] = mapped_column(String(10), default="WEB")
    next_number: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class ClientInvoiceCustomer(Base):
    """Cliente/deudor para facturacion online."""
    __tablename__ = "client_invoice_customers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "tax_id_normalized",
            name="uq_client_inv_customer_nif",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )
    # Datos fiscales
    tax_id: Mapped[str] = mapped_column(String(20))
    tax_id_normalized: Mapped[str] = mapped_column(String(20), index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    postal_code: Mapped[str] = mapped_column(String(10), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    province: Mapped[str] = mapped_column(String(100), default="")
    country: Mapped[str] = mapped_column(String(60), default="ES")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")

    # Defaults para lineas de factura
    default_vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("21.00"),
    )

    # Vinculacion con tercero del escritorio (si existe)
    desktop_tercero_id: Mapped[int | None] = mapped_column(Integer)
    desktop_subcuenta: Mapped[str] = mapped_column(String(20), default="")
    pending_desktop_import: Mapped[bool] = mapped_column(Boolean, default=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class ClientInvoice(Base):
    """Factura online emitida desde Flutter."""
    __tablename__ = "client_invoices"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "fiscal_year", "series_code", "invoice_number",
            name="uq_client_invoice_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("client_invoice_customers.id", ondelete="RESTRICT"), index=True,
    )

    # Numeracion (asignada al emitir)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    series_code: Mapped[str] = mapped_column(String(10), default="WEB")
    invoice_number: Mapped[int | None] = mapped_column(Integer)

    # Fechas
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Estado
    # draft | issued_pending_processing | claimed | imported | rendered |
    # emailed | processing_error | cancelled | replaced
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)

    # Importes (recalculados por el backend al emitir)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_vat: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    withholding_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"),
    )
    withholding_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Forma de pago y observaciones
    payment_method: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    recipient_email: Mapped[str] = mapped_column(String(254), default="")

    # Snapshot inmutable (JSON serializado tras emision)
    issued_snapshot: Mapped[str] = mapped_column(Text, default="")

    # Idempotencia
    idempotency_key: Mapped[str] = mapped_column(String(80), default="", index=True)

    # Emisor (cliente que creo la factura)
    created_by_client_id: Mapped[str] = mapped_column(
        ForeignKey("msg_clients.id", ondelete="SET NULL"), default="",
    )

    # Documento publicado (tras generar PDF)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("client_documents.id", ondelete="SET NULL"),
    )

    # Veri*FACTU: preparacion (sin remision real en V1)
    verifactu_hash: Mapped[str] = mapped_column(String(64), default="")
    verifactu_chain_hash: Mapped[str] = mapped_column(String(64), default="")
    verifactu_qr_data: Mapped[str] = mapped_column(Text, default="")
    verifactu_registration_id: Mapped[str] = mapped_column(String(100), default="")
    software_id: Mapped[str] = mapped_column(String(100), default="Gest2A3Eco")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class ClientInvoiceLine(Base):
    """Linea de factura online."""
    __tablename__ = "client_invoice_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("client_invoices.id", ondelete="CASCADE"), index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"),
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("21.00"),
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))


class ClientInvoiceEvent(Base):
    """Registro inmutable de eventos de factura (Veri*FACTU ready)."""
    __tablename__ = "client_invoice_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("client_invoices.id", ondelete="CASCADE"), index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    # draft_created | issued | claimed | imported | rendered | emailed |
    # processing_error | cancelled | replaced
    status_before: Mapped[str] = mapped_column(String(30), default="")
    status_after: Mapped[str] = mapped_column(String(30), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    actor_type: Mapped[str] = mapped_column(String(16), default="")  # client | worker | system
    actor_id: Mapped[str] = mapped_column(String(64), default="")
    # Hash para encadenamiento Veri*FACTU
    event_hash: Mapped[str] = mapped_column(String(64), default="")
    chain_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True,
    )


class ClientInvoiceProcessingQueue(Base):
    """Cola/outbox de procesamiento de facturas emitidas online."""
    __tablename__ = "client_invoice_processing_queue"
    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_client_inv_queue_invoice"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("client_invoices.id", ondelete="CASCADE"), index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )

    # Estado de procesamiento
    # pending | claimed | imported | rendered | emailed | completed | error
    queue_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)

    # Lease para worker
    claimed_by: Mapped[str] = mapped_column(String(120), default="")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True,
    )

    # Resultado
    pdf_blob_key: Mapped[str] = mapped_column(String(500), default="")
    pdf_sha256: Mapped[str] = mapped_column(String(64), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


# ==========================================================================
# COLA DE PUBLICACION DOCUMENTAL (para el escritorio)
# ==========================================================================

class DesktopPublicationQueue(Base):
    """Cola local de publicaciones pendientes desde el escritorio."""
    __tablename__ = "desktop_publication_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("msg_organizations.id", ondelete="CASCADE"), index=True,
    )

    # Referencia al documento de origen en el escritorio
    source_type: Mapped[str] = mapped_column(String(30))  # factura_emitida
    source_id: Mapped[str] = mapped_column(String(120))
    source_version: Mapped[int] = mapped_column(Integer, default=1)

    # Ruta local del PDF
    local_pdf_path: Mapped[str] = mapped_column(String(500))
    display_name: Mapped[str] = mapped_column(String(300))
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fiscal_year: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))

    # NIF del cliente para identificar la organizacion destino
    customer_tax_id: Mapped[str] = mapped_column(String(20), default="")

    # Estado: pending | published | blocked | error
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    blocked_reason: Mapped[str] = mapped_column(Text, default="")

    # Resultado
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("client_documents.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )
