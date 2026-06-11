"""
Interfaz abstracta de motor OCR.

Todos los motores (PDF nativo, local Tesseract, Azure, HTTP, etc.)
deben implementar esta clase.

Contrato:
  - extraer() nunca lanza excepcion: los errores van en OcrInvoiceResult.errores.
  - disponible() devuelve False si el motor no puede ejecutarse (libreria
    no instalada, credenciales ausentes, etc.) sin lanzar excepcion.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from services.ocr.types import OcrInvoiceResult

logger = logging.getLogger(__name__)


class OcrEngineBase(ABC):
    """Motor OCR: recibe un fichero y devuelve OcrInvoiceResult."""

    # ── Interfaz obligatoria ──────────────────────────────────────────────────

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador unico del motor (usado en logs y en el campo 'motor')."""

    @abstractmethod
    def disponible(self) -> bool:
        """True si el motor puede ejecutarse en el entorno actual."""

    @abstractmethod
    def extraer(self, path: Path) -> OcrInvoiceResult:
        """
        Extrae e interpreta la factura desde el fichero indicado.

        Parametros:
          path — ruta al fichero PDF o imagen.

        Devuelve:
          OcrInvoiceResult con los campos extraidos y, si hay errores,
          la lista errores rellena.  Nunca lanza excepcion.
        """

    # ── Utilidades para subclases ─────────────────────────────────────────────

    def _error_result(self, mensaje: str) -> OcrInvoiceResult:
        """Crea un OcrInvoiceResult de error con el motor identificado."""
        logger.warning("[%s] %s", self.nombre, mensaje)
        return OcrInvoiceResult(motor=self.nombre, errores=[mensaje])

    @staticmethod
    def _es_pdf(path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @staticmethod
    def _es_imagen(path: Path) -> bool:
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
