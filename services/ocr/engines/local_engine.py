"""
Motor OCR local: Tesseract via pytesseract + Pillow.

Requisitos:
  - Tesseract OCR instalado en el sistema (tesseract.exe en Windows).
  - Paquetes Python: pytesseract, pillow, pymupdf (para renderizar PDF a imagen).

Si Tesseract no esta disponible, disponible() devuelve False sin error.
Activacion: instalar tesseract y pip install pytesseract.
"""
from __future__ import annotations

import logging
from pathlib import Path

from services.ocr.base import OcrEngineBase
from services.ocr.types import OcrInvoiceResult

logger = logging.getLogger(__name__)

# Idiomas de reconocimiento (requiere paquete spa instalado en Tesseract)
_LANG = "spa+eng"
# Resolucion de renderizado PDF → imagen (DPI)
_PDF_DPI_SCALE = 2.0


class LocalOcrEngine(OcrEngineBase):
    """
    Motor OCR local mediante Tesseract.

    Soporta PDFs (los renderiza a imagen con pymupdf) e imagenes directas
    (PNG, JPG, TIFF).
    """

    def __init__(self, lang: str = _LANG):
        self._lang = lang

    @property
    def nombre(self) -> str:
        return "tesseract"

    def disponible(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extraer(self, path: Path) -> OcrInvoiceResult:
        if not path.exists():
            return self._error_result(f"Fichero no encontrado: {path}")

        if self._es_pdf(path):
            texto = self._pdf_to_text(path)
        elif self._es_imagen(path):
            texto = self._imagen_to_text(path)
        else:
            return self._error_result(f"Tipo de fichero no soportado: {path.suffix}")

        if not texto:
            return self._error_result("Tesseract no extrajo texto del documento.")

        from services.ocr.invoice_interpreter import InvoiceInterpreter
        result = InvoiceInterpreter().interpretar(texto)
        result.motor = self.nombre
        result.confianza = self._calcular_confianza(path)
        return result

    # ── Backends de extraccion ────────────────────────────────────────────────

    def _pdf_to_text(self, path: Path) -> str:
        try:
            import fitz
            import io
            import pytesseract
            from PIL import Image as PilImage

            doc = fitz.open(str(path))
            paginas = []
            mat = fitz.Matrix(_PDF_DPI_SCALE, _PDF_DPI_SCALE)
            for page in doc:
                pix = page.get_pixmap(matrix=mat)
                img = PilImage.open(io.BytesIO(pix.tobytes("png")))
                paginas.append(pytesseract.image_to_string(img, lang=self._lang))
            doc.close()
            return "\n".join(paginas).strip()
        except Exception as exc:
            logger.warning("[tesseract] Error al renderizar PDF: %s", exc)
            return ""

    def _imagen_to_text(self, path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image as PilImage
            img = PilImage.open(str(path))
            return pytesseract.image_to_string(img, lang=self._lang).strip()
        except Exception as exc:
            logger.warning("[tesseract] Error al procesar imagen: %s", exc)
            return ""

    def _calcular_confianza(self, path: Path) -> float:
        """Confianza promedio de Tesseract (solo para imagenes; PDFs = 0.75)."""
        if self._es_pdf(path):
            return 0.75
        try:
            import pytesseract
            from PIL import Image as PilImage
            img = PilImage.open(str(path))
            data = pytesseract.image_to_data(img, lang=self._lang, output_type=pytesseract.Output.DICT)
            confs = [c for c in data.get("conf", []) if c != -1]
            return round(sum(confs) / len(confs) / 100, 3) if confs else 0.0
        except Exception:
            return 0.0
