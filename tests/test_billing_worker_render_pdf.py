"""Tests de contenido del PDF real (Etapa 6): plantilla + Chromium headless.

Se saltan si Chromium no esta instalado en el entorno de pruebas
(``playwright install chromium``), igual que los tests gated por
TEST_POSTGRES_URL se saltan sin una base de datos real disponible.
"""

from __future__ import annotations

import pytest

pypdf = pytest.importorskip("pypdf")


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _chromium_available(),
    reason="Chromium no disponible (ejecutar: playwright install chromium)",
)


def _sample_payload(**overrides) -> dict:
    payload = {
        "invoice": {
            "id": "inv-1", "series_code": "APP", "invoice_number": 7,
            "invoice_date": "2026-05-20T10:00:00+00:00",
            "subtotal": "200.00", "total_vat": "42.00", "withholding_rate": "15.00",
            "withholding_amount": "30.00", "total": "212.00", "currency": "EUR",
            "payment_method": "Transferencia bancaria", "notes": "Pedido 99",
            "software_id": "Gest2A3Eco",
        },
        "lines": [
            {
                "description": "Consultoria fiscal", "quantity": "4",
                "unit_price": "50.00", "discount_percent": "0", "vat_rate": "21.00",
                "line_total": "200.00", "vat_amount": "42.00",
            },
        ],
        "customer": {
            "legal_name": "Cliente Pruebas SL", "tax_id": "B11112222",
            "address": "Calle Prueba 9", "postal_code": "08001", "city": "Barcelona",
            "province": "Barcelona", "country": "ES", "email": "cliente@test.es",
        },
        "organization": {
            "company_code": "GEST01", "name": "Gestinem",
            "legal_name": "Gestinem Asesores SL", "tax_id": "B99998888",
            "address": "Gran Via 1", "postal_code": "28013", "city": "Madrid",
            "province": "Madrid", "country": "ES", "phone": "", "email": "",
        },
        "verifactu_submission_enabled": False,
    }
    payload.update(overrides)
    return payload


_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def _extract_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(__import__("io").BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for ligature, plain in _LIGATURES.items():
        text = text.replace(ligature, plain)
    return text


def test_rendered_pdf_is_a_valid_pdf_document():
    from billing_worker.handlers.render_pdf import render_invoice_pdf

    pdf_bytes = render_invoice_pdf(_sample_payload())
    assert pdf_bytes.startswith(b"%PDF-")


def test_rendered_pdf_contains_required_fiscal_content():
    from billing_worker.handlers.render_pdf import render_invoice_pdf

    text = _extract_text(render_invoice_pdf(_sample_payload()))

    # Emisor y destinatario
    assert "Gestinem Asesores SL" in text
    assert "B99998888" in text
    assert "Cliente Pruebas SL" in text
    assert "B11112222" in text
    # Serie y numero
    assert "APP-000007" in text
    # Fecha (DD-MM-YYYY)
    assert "20-05-2026" in text
    # Lineas: cantidad, precio, descripcion
    assert "Consultoria fiscal" in text
    assert "50.00" in text
    # Base/IVA/retencion/total
    assert "200.00" in text
    assert "42.00" in text
    assert "15.00" in text  # tipo de retencion
    assert "30.00" in text  # importe retenido
    assert "212.00" in text  # total
    # Forma de pago
    assert "Transferencia bancaria" in text
    # Identificador de software
    assert "Gest2A3Eco" in text


def test_pending_invoice_never_claims_verifactu_compliance():
    from billing_worker.handlers.render_pdf import render_invoice_pdf

    text = _extract_text(render_invoice_pdf(_sample_payload(verifactu_submission_enabled=False)))

    assert "no acogido todavia a VERI*FACTU" in text
    assert "agenciatributaria" not in text.lower()


def test_verifactu_enabled_invoice_prints_legal_phrase_and_aeat_qr_caption():
    from billing_worker.handlers.render_pdf import render_invoice_pdf

    text = _extract_text(render_invoice_pdf(_sample_payload(verifactu_submission_enabled=True)))

    assert "Factura verificable en la sede electronica de la AEAT" in text
    normalized = " ".join(text.split())
    assert "Validar en la sede electronica de la AEAT" in normalized


def test_different_invoices_produce_different_pdfs():
    from billing_worker.handlers.render_pdf import render_invoice_pdf, sha256_hex

    pdf_a = render_invoice_pdf(_sample_payload())
    payload_b = _sample_payload()
    payload_b["invoice"]["invoice_number"] = 8
    pdf_b = render_invoice_pdf(payload_b)

    assert sha256_hex(pdf_a) != sha256_hex(pdf_b)
