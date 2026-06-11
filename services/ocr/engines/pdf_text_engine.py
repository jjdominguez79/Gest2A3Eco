"""
Motor OCR: extraccion de texto nativo de PDFs (sin OCR de imagen).

Usa pymupdf (fitz) como primera opcion y pypdf como fallback.
Solo funciona con PDFs que tienen capa de texto embebida (PDFs digitales).
Para PDFs escaneados sin texto, la cadena de motores debe continuar con
un motor de imagen (Tesseract, Azure, etc.).
"""
from __future__ import annotations

import logging
from pathlib import Path

from services.ocr.base import OcrEngineBase
from services.ocr.types import OcrInvoiceResult

logger = logging.getLogger(__name__)

# Umbral minimo de caracteres para considerar que hay texto util
_MIN_CHARS = 50


class PdfTextEngine(OcrEngineBase):
    """
    Extrae el texto nativo de PDFs digitales.

    Orden de intentos:
      1. pymupdf (fitz) — mas fiel al layout, maneja tablas mejor.
      2. pypdf          — fallback si pymupdf no esta disponible.

    Si el PDF no tiene texto o tiene menos de _MIN_CHARS caracteres,
    devuelve OcrInvoiceResult vacio (sin errores criticos) para que
    la cadena de motores continue con un motor de imagen.
    """

    @property
    def nombre(self) -> str:
        return "pdf_text"

    def disponible(self) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            try:
                import pypdf  # noqa: F401
                return True
            except ImportError:
                return False

    def extraer(self, path: Path) -> OcrInvoiceResult:
        if not self._es_pdf(path):
            return self._error_result("PdfTextEngine solo procesa ficheros PDF.")
        if not path.exists():
            return self._error_result(f"Fichero no encontrado: {path}")

        texto = self._extraer_pymupdf(path) or self._extraer_pypdf(path)

        if not texto or len(texto.strip()) < _MIN_CHARS:
            # PDF sin texto suficiente — no es error, continuar cadena
            return OcrInvoiceResult(
                motor=self.nombre,
                texto="",
                confianza=0.0,
                errores=["PDF sin capa de texto suficiente. Se requiere motor OCR de imagen."],
            )

        # Texto extraido: interpretar campos
        from services.ocr.invoice_interpreter import InvoiceInterpreter
        result = InvoiceInterpreter().interpretar(texto)
        result.motor = self.nombre
        result.confianza = 0.92
        return result

    # ── Backends de extraccion ────────────────────────────────────────────────

    def _extraer_pymupdf(self, path: Path) -> str:
        try:
            import fitz
            doc = fitz.open(str(path))
            paginas = []
            for page in doc:
                paginas.append(page.get_text("text") or "")
            doc.close()
            texto = "\n".join(paginas).strip()
            if texto:
                logger.debug("[pdf_text] pymupdf: %d chars extraidos de %s", len(texto), path.name)
            return texto
        except Exception as exc:
            logger.debug("[pdf_text] pymupdf fallo: %s", exc)
            return ""

    def _extraer_pypdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            paginas = []
            for page in reader.pages:
                try:
                    paginas.append(page.extract_text() or "")
                except Exception:
                    paginas.append("")
            texto = "\n".join(paginas).strip()
            if texto:
                logger.debug("[pdf_text] pypdf: %d chars extraidos de %s", len(texto), path.name)
            return texto
        except Exception as exc:
            logger.debug("[pdf_text] pypdf fallo: %s", exc)
            return ""
