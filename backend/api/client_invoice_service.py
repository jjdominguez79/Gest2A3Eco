"""Servicio de facturacion online: calculos, numeracion y Veri*FACTU."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceCustomer,
    ClientInvoiceEvent,
    ClientInvoiceLine,
    ClientInvoiceProcessingQueue,
    ClientInvoiceSeries,
)
from backend.api.client_validation import (
    calculate_line_total,
    calculate_vat,
    calculate_withholding,
    round_currency,
)
from backend.api.messaging_models import MessagingOrganization
from backend.api.messaging_security import utcnow


def recalculate_invoice(
    invoice: ClientInvoice,
    lines: list[ClientInvoiceLine],
) -> None:
    """Recalcula todos los importes de la factura usando Decimal."""
    subtotal = Decimal("0")
    total_vat = Decimal("0")

    for line in lines:
        line.line_total = calculate_line_total(
            line.quantity, line.unit_price, line.discount_percent,
        )
        line.vat_amount = calculate_vat(line.line_total, line.vat_rate)
        subtotal += line.line_total
        total_vat += line.vat_amount

    invoice.subtotal = round_currency(subtotal)
    invoice.total_vat = round_currency(total_vat)
    invoice.withholding_amount = calculate_withholding(
        invoice.subtotal, invoice.withholding_rate,
    )
    invoice.total = round_currency(
        invoice.subtotal + invoice.total_vat - invoice.withholding_amount,
    )


def assign_invoice_number(
    db: Session,
    organization_id: str,
    fiscal_year: int,
    series_code: str,
) -> int:
    """Asigna el siguiente numero de factura atomicamente.

    Usa SELECT FOR UPDATE para bloquear la fila de la serie durante
    la transaccion, evitando numeros duplicados bajo concurrencia.

    Si la serie no existe, la crea con next_number=1.
    """
    # Obtener o crear serie con bloqueo
    series = db.scalar(
        select(ClientInvoiceSeries)
        .where(
            ClientInvoiceSeries.organization_id == organization_id,
            ClientInvoiceSeries.fiscal_year == fiscal_year,
            ClientInvoiceSeries.series_code == series_code,
        )
        .with_for_update()
    )

    if not series:
        series = ClientInvoiceSeries(
            organization_id=organization_id,
            fiscal_year=fiscal_year,
            series_code=series_code,
            next_number=1,
        )
        db.add(series)
        db.flush()
        # Re-obtener con bloqueo
        series = db.scalar(
            select(ClientInvoiceSeries)
            .where(
                ClientInvoiceSeries.organization_id == organization_id,
                ClientInvoiceSeries.fiscal_year == fiscal_year,
                ClientInvoiceSeries.series_code == series_code,
            )
            .with_for_update()
        )

    number = series.next_number
    series.next_number = number + 1
    series.updated_at = utcnow()
    db.flush()
    return number


def create_issued_snapshot(
    invoice: ClientInvoice,
    lines: list[ClientInvoiceLine],
    customer: ClientInvoiceCustomer,
    org: MessagingOrganization,
) -> str:
    """Crea un snapshot JSON inmutable de la factura emitida."""
    snapshot = {
        "organization": {
            "company_code": org.company_code,
            "name": org.name,
            "legal_name": org.legal_name or org.name,
            "tax_id": org.tax_id,
            "address": org.address,
            "postal_code": org.postal_code,
            "city": org.city,
            "province": org.province,
            "country": org.country,
        },
        "customer": {
            "tax_id": customer.tax_id,
            "legal_name": customer.legal_name,
            "address": customer.address,
            "postal_code": customer.postal_code,
            "city": customer.city,
            "province": customer.province,
            "country": customer.country,
            "email": customer.email,
        },
        "invoice": {
            "id": invoice.id,
            "fiscal_year": invoice.fiscal_year,
            "series_code": invoice.series_code,
            "invoice_number": invoice.invoice_number,
            "invoice_date": (
                invoice.invoice_date.isoformat() if invoice.invoice_date else None
            ),
            "subtotal": str(invoice.subtotal),
            "total_vat": str(invoice.total_vat),
            "withholding_rate": str(invoice.withholding_rate),
            "withholding_amount": str(invoice.withholding_amount),
            "total": str(invoice.total),
            "currency": invoice.currency,
            "payment_method": invoice.payment_method,
            "notes": invoice.notes,
        },
        "lines": [
            {
                "line_number": line.line_number,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "discount_percent": str(line.discount_percent),
                "vat_rate": str(line.vat_rate),
                "line_total": str(line.line_total),
                "vat_amount": str(line.vat_amount),
            }
            for line in sorted(lines, key=lambda l: l.line_number)
        ],
        "issued_at": utcnow().isoformat(),
        "software_id": invoice.software_id,
    }
    return json.dumps(snapshot, ensure_ascii=True, sort_keys=True)


def compute_verifactu_hash(invoice: ClientInvoice, lines: list[ClientInvoiceLine]) -> str:
    """Calcula hash SHA-256 para preparacion Veri*FACTU.

    En V1 solo prepara la estructura; no hay remision real a AEAT.
    """
    data = (
        f"{invoice.organization_id}|{invoice.fiscal_year}|"
        f"{invoice.series_code}|{invoice.invoice_number}|"
        f"{invoice.invoice_date}|{invoice.total}|{invoice.software_id}"
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def chain_verifactu_hash(current_hash: str, previous_hash: str) -> str:
    """Encadena hash actual con el anterior (Veri*FACTU)."""
    combined = f"{previous_hash}|{current_hash}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def create_invoice_event(
    db: Session,
    invoice_id: str,
    event_type: str,
    status_before: str,
    status_after: str,
    *,
    actor_type: str = "",
    actor_id: str = "",
    detail: str = "",
    event_hash: str = "",
    chain_hash: str = "",
) -> ClientInvoiceEvent:
    """Registra un evento inmutable de factura."""
    event = ClientInvoiceEvent(
        invoice_id=invoice_id,
        event_type=event_type,
        status_before=status_before,
        status_after=status_after,
        detail=detail,
        actor_type=actor_type,
        actor_id=actor_id,
        event_hash=event_hash,
        chain_hash=chain_hash,
    )
    db.add(event)
    db.flush()
    return event
