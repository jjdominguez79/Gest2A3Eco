from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from pypdf import PdfReader

from utils.utilidades import load_app_config


class OCRService:
    """
    Servicio OCR desacoplado.

    Prioridad:
    1. Backend HTTP configurado en config.json
    2. Extraccion de texto local para PDFs con capa de texto
    """

    def __init__(self):
        self._cfg = load_app_config()

    def procesar_factura(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise ValueError("El fichero indicado no existe.")

        texto = ""
        backend = "local"
        confianza = 0.0
        avisos = []

        endpoint = str(self._cfg.get("ocr_endpoint") or "").strip()
        if endpoint:
            try:
                texto, confianza = self._extract_via_http(path, endpoint)
                backend = "http"
            except Exception as exc:
                avisos.append(f"No se pudo usar el backend OCR configurado: {exc}")

        if not texto:
            if path.suffix.lower() != ".pdf":
                raise ValueError(
                    "Solo se admiten PDFs en esta version. Configura un backend OCR externo para imagenes o PDFs escaneados."
                )
            texto = self._extract_pdf_text(path)
            backend = "pdf_text"
            if texto.strip():
                confianza = 0.92
            else:
                avisos.append("El PDF no tiene texto embebido. Sera necesaria revision manual o un backend OCR externo.")

        parsed = self._parse_invoice_text(texto)
        parsed.update(
            {
                "backend": backend,
                "texto_ocr": texto,
                "confianza_ocr": confianza,
                "avisos": avisos,
                "pdf_path": str(path),
                "origen_path": str(path),
                "estado_ocr": "procesado" if texto.strip() else "pendiente",
                "estado_validacion": "pendiente",
                "estado_contable": "pendiente",
            }
        )
        return parsed

    def _extract_via_http(self, path: Path, endpoint: str) -> tuple[str, float]:
        payload = json.dumps({"file_path": str(path)}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(str(exc)) from exc
        text = str(raw.get("text") or raw.get("texto") or "")
        confidence = float(raw.get("confidence") or raw.get("confianza") or 0.0)
        return text, confidence

    def _extract_pdf_text(self, path: Path) -> str:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages).strip()

    def _parse_invoice_text(self, text: str) -> dict:
        normalized = text.replace("\r", "\n")
        proveedor_nif = self._search(
            normalized,
            [
                r"\b(?:CIF|NIF|VAT)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{6,16})",
            ],
        )
        numero_factura = self._search(
            normalized,
            [
                r"\b(?:Factura|Invoice)\s*(?:N[ºo]|No\.?|#)?\s*[:#-]?\s*([A-Z0-9\/\.-]{3,40})",
                r"\bN[ºo]\s*factura\s*[:#-]?\s*([A-Z0-9\/\.-]{3,40})",
            ],
        )
        fecha_factura = self._search_date(
            normalized,
            [
                r"\b(?:Fecha factura|Fecha|Invoice date)\s*[:#-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})",
                r"\b([0-9]{4}[\/\-][0-9]{1,2}[\/\-][0-9]{1,2})\b",
            ],
        )
        total = self._search_amount(
            normalized,
            [
                r"\b(?:Total factura|Importe total|Total)\s*[:#]?\s*([0-9\.\,]+)",
            ],
        )
        base = self._search_amount(
            normalized,
            [
                r"\b(?:Base imponible|Base)\s*[:#]?\s*([0-9\.\,]+)",
            ],
        )
        cuota_iva = self._search_amount(
            normalized,
            [
                r"\b(?:Cuota IVA|IVA)\s*[:#]?\s*([0-9\.\,]+)",
            ],
        )
        if total == 0.0 and base and cuota_iva:
            total = round(base + cuota_iva, 2)
        proveedor_nombre = self._guess_supplier_name(normalized)
        descripcion = f"Factura proveedor {proveedor_nombre}".strip()
        return {
            "proveedor_nif": proveedor_nif,
            "proveedor_nombre": proveedor_nombre,
            "numero_factura": numero_factura,
            "fecha_factura": fecha_factura,
            "fecha_operacion": fecha_factura,
            "fecha_asiento": fecha_factura,
            "descripcion": descripcion,
            "moneda_codigo": "EUR",
            "base_imponible": base,
            "cuota_iva": cuota_iva,
            "cuota_recargo": 0.0,
            "cuota_retencion": 0.0,
            "total": total,
            "lineas": [
                {
                    "descripcion": descripcion or "Factura recibida",
                    "base": base,
                    "cuota_iva": cuota_iva,
                    "cuota_re": 0.0,
                    "cuota_irpf": 0.0,
                }
            ],
            "datos_extra": {},
        }

    def _search(self, text: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return str(match.group(1)).strip()
        return ""

    def _search_date(self, text: str, patterns: list[str]) -> str:
        return self._search(text, patterns)

    def _search_amount(self, text: str, patterns: list[str]) -> float:
        raw = self._search(text, patterns)
        if not raw:
            return 0.0
        value = raw.replace(".", "").replace(",", ".")
        try:
            return round(float(value), 2)
        except Exception:
            return 0.0

    def _guess_supplier_name(self, text: str) -> str:
        for line in text.splitlines():
            clean = " ".join(str(line or "").split()).strip()
            if not clean:
                continue
            if len(clean) > 60:
                continue
            upper = clean.upper()
            if any(tag in upper for tag in ("FACTURA", "INVOICE", "CIF", "NIF", "FECHA")):
                continue
            return clean
        return ""
