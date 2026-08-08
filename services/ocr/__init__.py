"""
Paquete services/ocr — capa de abstraccion tipada para el modulo OCR.

Jerarquia:
  services/ocr/types.py            — contratos de datos (OcrInvoiceResult, etc.)
  services/ocr/base.py             — interfaz abstracta de motor OCR
  services/ocr/invoice_interpreter.py — extraccion de campos desde texto libre
  services/ocr/ocr_service.py      — orquestador con gestion de BD
  services/ocr/engines/            — implementaciones concretas de motores

Este paquete es el unico nucleo OCR activo.  La proyeccion hacia
facturas_recibidas_docs vive fuera, en services/ocr_contabilidad_service.py.
"""
from services.ocr.types import (
    OcrInvoiceResult,
    OcrVatLine,
    OcrRetentionLine,
    OcrField,
    OcrDocumentState,
)
from services.ocr.base import OcrEngineBase
from services.ocr.ocr_service import OcrService
from services.ocr.aprendizaje_service import AprendizajeOcrService

__all__ = [
    "OcrInvoiceResult",
    "OcrVatLine",
    "OcrRetentionLine",
    "OcrField",
    "OcrDocumentState",
    "OcrEngineBase",
    "OcrService",
    "AprendizajeOcrService",
]
