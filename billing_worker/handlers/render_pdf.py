"""Renderizado del PDF de factura: plantilla HTML/CSS + Chromium (Playwright).

Etapa 6: sustituye el placeholder de la Etapa 5. Compatible con Linux/
Railway (mismo patron ya probado en ``deploy/aapp-worker``: Chromium headless
instalado en el propio contenedor del worker). No usa Word ni Word COM.

El contenido y el QR siguen el contrato fijado en
``docs/adr/0001-facturacion-autonoma-cliente.md`` seccion 9/14: el texto y la
URL de validacion VERI*FACTU reales solo se imprimen cuando
``verifactu_submission_enabled`` es true en el payload (Etapa 7). Mientras
tanto se usa una referencia interna neutral.
"""

from __future__ import annotations

import base64
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape

from billing_worker.handlers.fiscal_qr import (
    PENDING_LEGAL_PHRASE,
    VERIFACTU_LEGAL_PHRASE,
    build_aeat_validation_url,
    build_pending_reference_payload,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _qr_data_uri(content: str) -> str:
    qr = segno.make(content, error="m")
    buffer = qr.png_data_uri(scale=6, border=2)
    return buffer


def _build_iva_breakdown(lines: list[dict]) -> list[dict]:
    totals: dict[str, dict[str, Decimal]] = {}
    for line in lines:
        rate = str(line.get("vat_rate", "0"))
        bucket = totals.setdefault(rate, {"base": Decimal("0"), "amount": Decimal("0")})
        bucket["base"] += _dec(line.get("line_total"))
        bucket["amount"] += _dec(line.get("vat_amount"))
    return [
        {"rate": rate, "base": f"{data['base']:.2f}", "amount": f"{data['amount']:.2f}"}
        for rate, data in sorted(totals.items(), key=lambda item: item[0])
    ]


def _format_date(value: str | None) -> str:
    if not value:
        return ""
    # ISO 8601 (YYYY-MM-DDTHH:MM:SS...) -> DD-MM-YYYY para mostrar y para el QR.
    date_part = value[:10]
    parts = date_part.split("-")
    if len(parts) != 3:
        return date_part
    year, month, day = parts
    return f"{day}-{month}-{year}"


def build_template_context(payload: dict) -> dict:
    invoice = payload.get("invoice") or {}
    customer = payload.get("customer") or {}
    organization = payload.get("organization") or {}
    lines = payload.get("lines") or []

    series_code = invoice.get("series_code") or ""
    invoice_number = int(invoice.get("invoice_number") or 0)
    display_number = f"{series_code}-{invoice_number:06d}"
    invoice_date_display = _format_date(invoice.get("invoice_date"))

    verifactu_enabled = bool(payload.get("verifactu_submission_enabled", False))
    if verifactu_enabled:
        qr_content = build_aeat_validation_url(
            nif=organization.get("tax_id", ""),
            numserie=display_number,
            fecha=invoice_date_display,
            importe=_dec(invoice.get("total")),
        )
        legal_phrase = VERIFACTU_LEGAL_PHRASE
        qr_caption = "Validar en la sede electronica de la AEAT"
    else:
        qr_content = build_pending_reference_payload(
            organization_code=organization.get("company_code", ""),
            series_code=series_code,
            invoice_number=invoice_number,
        )
        legal_phrase = PENDING_LEGAL_PHRASE
        qr_caption = "Referencia interna (sin remision AEAT)"

    return {
        "emisor": organization,
        "cliente": customer,
        "factura": {
            **invoice,
            "display_number": display_number,
            "invoice_date_display": invoice_date_display,
        },
        "lineas": lines,
        "iva_breakdown": _build_iva_breakdown(lines),
        "qr_data_uri": _qr_data_uri(qr_content),
        "legal_phrase": legal_phrase,
        "qr_caption": qr_caption,
    }


def render_invoice_html(payload: dict) -> str:
    template = _env.get_template("invoice.html")
    return template.render(**build_template_context(payload))


def render_invoice_pdf(payload: dict) -> bytes:
    """Genera los bytes del PDF a partir del payload de
    ``GET /worker/invoice/{id}/payload``.

    Lanza Chromium headless una vez por factura (coste aceptable para el
    volumen de este pipeline); no se mantiene un navegador persistente para
    evitar fugas de estado entre facturas de distintas organizaciones.
    """
    from playwright.sync_api import sync_playwright

    html = render_invoice_html(payload)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            pdf_bytes = page.pdf(format="A4", print_background=True)
        finally:
            browser.close()
    return pdf_bytes


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
