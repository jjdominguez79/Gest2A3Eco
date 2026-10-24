"""Renderizado del PDF de factura.

Etapa 5: placeholder minimo (sin Chromium) para poder probar de extremo a
extremo el bucle de claim/lease/subida/publicacion/entrega sin depender
todavia de Playwright. La Etapa 6 sustituye ``render_invoice_pdf`` por el
renderer real (plantilla HTML/CSS + Playwright + QR fiscal), manteniendo la
misma firma para no tocar el resto del pipeline.
"""

from __future__ import annotations

import hashlib

_PLACEHOLDER_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"%%EOF\n"
)


def render_invoice_pdf(payload: dict) -> bytes:
    """Genera los bytes del PDF para el payload de una factura.

    ``payload`` es el dict devuelto por ``GET /worker/invoice/{id}/payload``
    (factura, lineas, cliente, organizacion, snapshot emitido). El
    placeholder actual no usa ese contenido todavia; la Etapa 6 lo
    sustituye por el renderer real.
    """
    invoice = payload.get("invoice") or {}
    marker = f"{invoice.get('id', '')}|{invoice.get('invoice_number', '')}".encode("utf-8")
    # Contenido determinista por factura para poder verificar en pruebas que
    # no se reutiliza el PDF de otra factura.
    return _PLACEHOLDER_PDF + b"% " + hashlib.sha256(marker).hexdigest().encode("ascii") + b"\n"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
