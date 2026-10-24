"""Servicio de facturacion online: calculos, numeracion y Veri*FACTU."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceCustomer,
    ClientInvoiceEvent,
    ClientInvoiceLine,
    ClientInvoiceProcessingQueue,
    ClientInvoiceSeries,
    ClientVerifactuChainState,
)
from backend.api.client_validation import (
    calculate_line_total,
    calculate_vat,
    calculate_withholding,
    round_currency,
)
from backend.api.messaging_models import MessagingOrganization
from backend.api.messaging_security import utcnow
from services.verifactu.builder import build_registro_alta, build_registro_anulacion
from services.verifactu.models import (
    AltaRegistroInput,
    AnulacionRegistroInput,
    DesgloseIva,
    SistemaInformatico,
)

_MADRID_TZ = ZoneInfo("Europe/Madrid")


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


def _display_num_serie(invoice: ClientInvoice) -> str:
    return f"{invoice.series_code}-{int(invoice.invoice_number or 0):06d}"


def _fecha_expedicion(invoice: ClientInvoice) -> str:
    dt = invoice.invoice_date or invoice.issued_at or utcnow()
    local = dt.astimezone(_MADRID_TZ)
    return local.strftime("%d-%m-%Y")


def _fecha_hora_huso_gen_registro() -> str:
    return datetime.now(_MADRID_TZ).isoformat(timespec="seconds")


def _build_desglose(lines: list[ClientInvoiceLine]) -> list[DesgloseIva]:
    grouped: dict[Decimal, dict[str, Decimal]] = defaultdict(
        lambda: {"base": Decimal("0"), "cuota": Decimal("0")},
    )
    for line in lines:
        bucket = grouped[line.vat_rate]
        bucket["base"] += line.line_total
        bucket["cuota"] += line.vat_amount
    return [
        DesgloseIva(
            tipo_impositivo=rate,
            base_imponible=round_currency(data["base"]),
            cuota_repercutida=round_currency(data["cuota"]),
        )
        for rate, data in sorted(grouped.items())
    ]


def _lock_chain_state(db: Session, organization_id: str) -> ClientVerifactuChainState:
    """Bloquea (o crea) la fila de estado de cadena de la organizacion.

    SELECT ... FOR UPDATE: evita que dos emisiones concurrentes de la misma
    organizacion encadenen contra el mismo hash "anterior" (ADR 0001,
    seccion 9; mismo patron que assign_invoice_number para las series).
    """
    state = db.scalar(
        select(ClientVerifactuChainState)
        .where(ClientVerifactuChainState.organization_id == organization_id)
        .with_for_update()
    )
    if not state:
        state = ClientVerifactuChainState(organization_id=organization_id)
        db.add(state)
        db.flush()
        state = db.scalar(
            select(ClientVerifactuChainState)
            .where(ClientVerifactuChainState.organization_id == organization_id)
            .with_for_update()
        )
    return state


def append_verifactu_alta(
    db: Session,
    invoice: ClientInvoice,
    lines: list[ClientInvoiceLine],
    customer: ClientInvoiceCustomer,
    org: MessagingOrganization,
    *,
    tipo_factura: str = "F1",
) -> tuple[str, str]:
    """Calcula la huella real, construye el XML y encadena el registro.

    Debe llamarse dentro de la misma transaccion que la emision (seccion 9
    del encargo: "crear el registro fiscal inicial" es parte de la
    transaccion de emision, no un paso diferido al worker). Devuelve
    ``(huella, xml)``; tambien dejan actualizados
    ``invoice.verifactu_hash``/``verifactu_chain_hash``/``verifactu_xml`` y
    la fila de ``ClientVerifactuChainState``.
    """
    state = _lock_chain_state(db, org.id)
    previous_hash = state.last_hash
    num_serie = _display_num_serie(invoice)
    fecha_expedicion = _fecha_expedicion(invoice)

    sistema = SistemaInformatico(
        nombre_razon=org.legal_name or org.name, nif=org.tax_id,
    )
    data = AltaRegistroInput(
        id_emisor_factura=org.tax_id,
        num_serie_factura=num_serie,
        fecha_expedicion_factura=fecha_expedicion,
        nombre_razon_emisor=org.legal_name or org.name,
        tipo_factura=tipo_factura,
        descripcion_operacion=invoice.notes or "Prestacion de servicios",
        destinatario_nombre_razon=customer.legal_name,
        destinatario_nif=customer.tax_id,
        desglose=_build_desglose(lines),
        cuota_total=invoice.total_vat,
        importe_total=invoice.total,
        sistema_informatico=sistema,
        fecha_hora_huso_gen_registro=_fecha_hora_huso_gen_registro(),
        huella_registro_anterior=previous_hash,
        id_emisor_factura_anterior=org.tax_id if previous_hash else "",
        num_serie_factura_anterior=state.last_num_serie,
        fecha_expedicion_factura_anterior=state.last_fecha_expedicion,
    )
    huella, xml = build_registro_alta(data)

    invoice.verifactu_hash = huella
    invoice.verifactu_chain_hash = previous_hash
    invoice.verifactu_xml = xml

    state.last_hash = huella
    state.last_invoice_id = invoice.id
    state.last_num_serie = num_serie
    state.last_fecha_expedicion = fecha_expedicion
    state.sequence_number += 1
    state.updated_at = utcnow()

    return huella, xml


def append_verifactu_anulacion(
    db: Session,
    invoice: ClientInvoice,
    org: MessagingOrganization,
) -> tuple[str, str]:
    """Calcula la huella y el XML del registro de anulacion de una factura.

    La anulacion es, en si misma, un nuevo registro de la cadena (se
    encadena contra el ultimo hash conocido, que normalmente sera el de la
    propia factura que se anula si no se ha emitido nada despues).
    """
    state = _lock_chain_state(db, org.id)
    previous_hash = state.last_hash
    num_serie = _display_num_serie(invoice)
    fecha_expedicion = _fecha_expedicion(invoice)

    sistema = SistemaInformatico(
        nombre_razon=org.legal_name or org.name, nif=org.tax_id,
    )
    data = AnulacionRegistroInput(
        id_emisor_factura_anulada=org.tax_id,
        num_serie_factura_anulada=num_serie,
        fecha_expedicion_factura_anulada=fecha_expedicion,
        sistema_informatico=sistema,
        fecha_hora_huso_gen_registro=_fecha_hora_huso_gen_registro(),
        huella_registro_anterior=previous_hash,
        id_emisor_factura_anterior=org.tax_id if previous_hash else "",
        num_serie_factura_anterior=state.last_num_serie,
        fecha_expedicion_factura_anterior=state.last_fecha_expedicion,
    )
    huella, xml = build_registro_anulacion(data)

    state.last_hash = huella
    # El registro de anulacion referencia la factura original, no se crea
    # una factura nueva: el "ultimo registro" de la cadena pasa a ser esta
    # anulacion, identificada por la misma factura.
    state.last_invoice_id = invoice.id
    state.last_num_serie = num_serie
    state.last_fecha_expedicion = fecha_expedicion
    state.sequence_number += 1
    state.updated_at = utcnow()

    return huella, xml


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
