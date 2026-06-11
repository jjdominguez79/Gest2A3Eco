"""
Motor OCR: Azure Document Intelligence (Document Analysis — prebuilt-invoice).

Estado: ESQUELETO — no activo por defecto.

Para activar:
  1. Configura en la BD (tabla ocr_configuracion) o en config.json:
       "azure_doc_intelligence_endpoint": "https://<tu-recurso>.cognitiveservices.azure.com/"
       "azure_doc_intelligence_key":      "<tu_api_key>"
       "ocr_motor_activo":                "azure"
  2. Instala el SDK: pip install azure-ai-documentintelligence
  3. Reinicia la aplicacion.

Ver docs/ocr_azure.md para instrucciones completas de configuracion y
el mapeo de campos Azure → OcrInvoiceResult.
"""
from __future__ import annotations

import logging
from pathlib import Path

from services.ocr.base import OcrEngineBase
from services.ocr.types import OcrInvoiceResult, OcrVatLine, OcrRetentionLine

logger = logging.getLogger(__name__)


class AzureInvoiceEngine(OcrEngineBase):
    """
    Extraccion estructurada de facturas mediante Azure Document Intelligence.

    El modelo 'prebuilt-invoice' de Azure devuelve directamente los campos
    clave sin necesidad de regex.  Esta clase mapea los campos de Azure
    al contrato OcrInvoiceResult.

    Configuracion necesaria:
      endpoint  — URL del recurso Azure (sin slash final)
      api_key   — clave de autenticacion

    Ambos parametros se leen desde la tabla ocr_configuracion o desde
    config.json (claves: azure_doc_intelligence_endpoint / _key).
    """

    def __init__(self, endpoint: str = "", api_key: str = ""):
        self._endpoint = (endpoint or "").strip().rstrip("/")
        self._api_key  = (api_key or "").strip()

    @property
    def nombre(self) -> str:
        return "azure"

    def disponible(self) -> bool:
        if not self._endpoint or not self._api_key:
            return False
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient  # noqa: F401
            return True
        except ImportError:
            logger.debug(
                "[azure] SDK no instalado. Ejecuta: pip install azure-ai-documentintelligence"
            )
            return False

    def extraer(self, path: Path) -> OcrInvoiceResult:
        """
        Envia el fichero a Azure y mapea la respuesta a OcrInvoiceResult.

        Flujo:
          1. Abrir fichero y enviar al endpoint con begin_analyze_document().
          2. Esperar resultado (polling automatico del SDK).
          3. Mapear campos del modelo 'prebuilt-invoice' a OcrInvoiceResult.
          4. Interpretar texto libre si hay campos sin mapeo directo.
        """
        if not path.exists():
            return self._error_result(f"Fichero no encontrado: {path}")

        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential

            client = DocumentIntelligenceClient(
                endpoint=self._endpoint,
                credential=AzureKeyCredential(self._api_key),
            )

            with open(str(path), "rb") as f:
                poller = client.begin_analyze_document(
                    "prebuilt-invoice",
                    body=f,
                    content_type="application/octet-stream",
                )
            result = poller.result()

            if not result.documents:
                return self._error_result("Azure no devolvio documentos analizados.")

            doc = result.documents[0]
            return self._mapear_documento(doc, path)

        except Exception as exc:
            return self._error_result(f"Error Azure Document Intelligence: {exc}")

    # ── Mapeo de campos Azure → OcrInvoiceResult ──────────────────────────────

    def _mapear_documento(self, doc, path: Path) -> OcrInvoiceResult:
        """
        Mapeo de campos del modelo prebuilt-invoice de Azure.

        Referencia de campos Azure:
          VendorName              → proveedor_nombre
          VendorTaxId             → proveedor_nif
          InvoiceId               → numero_factura
          InvoiceDate             → fecha_factura
          DueDate                 → fecha_vencimiento
          InvoiceTotal            → total
          SubTotal                → base_total
          TotalTax                → iva_total
          Items[]                 → bases_iva (desglose por linea)
          TaxDetails[]            → detalle de impuestos
        """
        f = doc.fields or {}

        result = OcrInvoiceResult(motor=self.nombre)

        # Proveedor
        result.proveedor_nombre = _azure_str(f.get("VendorName"))
        result.proveedor_nif    = _azure_str(f.get("VendorTaxId"))

        # Numero y fechas
        result.numero_factura    = _azure_str(f.get("InvoiceId"))
        result.fecha_factura     = _azure_fecha(f.get("InvoiceDate"))
        result.fecha_vencimiento = _azure_fecha(f.get("DueDate"))

        # Importes globales
        result.total       = _azure_float(f.get("InvoiceTotal"))
        result.base_total  = _azure_float(f.get("SubTotal"))
        result.iva_total   = _azure_float(f.get("TotalTax"))

        # Lineas de IVA desde TaxDetails (si disponible)
        tax_details = f.get("TaxDetails") or {}
        items_val   = tax_details.get("valueArray") or []
        for item in items_val:
            item_f = item.get("valueObject") or {}
            linea = OcrVatLine(
                tipo_iva  = _azure_float(item_f.get("Amount")) or 0.0,
                base      = result.base_total,  # Azure no siempre desglosa base por tipo
                cuota_iva = _azure_float(item_f.get("Amount")) or 0.0,
            )
            result.bases_iva.append(linea)

        # Fallback: si no hay lineas de IVA, crear una desde totales
        if not result.bases_iva and result.base_total:
            tipo = round(result.iva_total / result.base_total * 100, 1) if result.base_total else 0.0
            result.bases_iva.append(OcrVatLine(
                tipo_iva  = tipo,
                base      = result.base_total,
                cuota_iva = result.iva_total,
            ))

        # Confianza: media de las confianzas de campos clave
        campos_clave = [f.get(k) for k in ("VendorName", "InvoiceId", "InvoiceDate", "InvoiceTotal")]
        confs = [c.confidence for c in campos_clave if c and hasattr(c, "confidence")]
        result.confianza = round(sum(confs) / len(confs), 3) if confs else 0.85

        # Guardar JSON bruto para auditoría
        result.raw_json = {"azure_fields": {k: str(v) for k, v in f.items()}}

        # Validar coherencia
        from services.ocr.invoice_interpreter import InvoiceInterpreter
        result.errores = InvoiceInterpreter().generar_errores(result)

        return result


# ── Utilidades de mapeo ───────────────────────────────────────────────────────

def _azure_str(field) -> str:
    if field is None:
        return ""
    content = getattr(field, "content", None) or getattr(field, "value_string", None)
    return str(content or "").strip()


def _azure_float(field) -> float:
    if field is None:
        return 0.0
    val = getattr(field, "value", None) or getattr(field, "value_number", None)
    if val is None:
        return 0.0
    try:
        # Azure devuelve CurrencyValue con amount y currency_symbol
        if hasattr(val, "amount"):
            return float(val.amount or 0.0)
        return float(val)
    except Exception:
        return 0.0


def _azure_fecha(field) -> str:
    if field is None:
        return ""
    val = getattr(field, "value", None) or getattr(field, "value_date", None)
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)
