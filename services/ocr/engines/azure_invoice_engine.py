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
import re
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

    def __init__(self, endpoint: str = "", api_key: str = "", model_id: str = ""):
        self._endpoint = (endpoint or "").strip().rstrip("/")
        self._api_key  = (api_key or "").strip()
        # Vacio conserva el comportamiento actual. Con un id de modelo se
        # invoca un modelo personalizado entrenado en Document Intelligence.
        self._model_id = (model_id or "").strip() or "prebuilt-invoice"

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
                self._model_id,
                    body=f,
                    content_type="application/octet-stream",
                )
            result = poller.result()

            if not result.documents:
                return self._error_result("Azure no devolvio documentos analizados.")

            doc = result.documents[0]
            return self._mapear_documento(
                doc, path, texto=str(getattr(result, "content", "") or ""),
            )

        except Exception as exc:
            return self._error_result(f"Error Azure Document Intelligence: {exc}")

    # ── Mapeo de campos Azure → OcrInvoiceResult ──────────────────────────────

    def _mapear_documento(self, doc, path: Path, texto: str = "") -> OcrInvoiceResult:
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

        result = OcrInvoiceResult(motor=self.nombre, texto=texto)

        # Proveedor
        proveedor_modelo = _campo(f, "VendorName", "ProveedorNombre", "nombre_proveedor")
        proveedor_destinatario = _campo(f, "VendorAddressRecipient")
        # En algunos disenos Azure toma el logotipo como VendorName (por
        # ejemplo, "Frozen Food elmar") y deja la razon social completa en el
        # destinatario de la direccion del proveedor.
        result.proveedor_nombre = (
            proveedor_destinatario
            if _parece_razon_social(proveedor_destinatario)
            else proveedor_modelo or proveedor_destinatario
        )
        result.proveedor_nif    = _campo(f, "VendorTaxId", "ProveedorNif", "NifProveedor", "nif_proveedor")

        # Numero y fechas
        result.numero_factura    = _campo(f, "InvoiceId", "NumeroFactura", "numero_factura")
        result.fecha_factura     = _campo_fecha(f, "InvoiceDate", "FechaFactura", "fecha_factura")
        result.fecha_vencimiento = _campo_fecha(f, "DueDate", "FechaVencimiento", "fecha_vencimiento")

        # Importes globales
        result.total       = _campo_float(f, "InvoiceTotal", "TotalFactura", "total_factura")
        result.base_total  = _campo_float(f, "SubTotal", "BaseTotal", "base_total")
        result.iva_total   = _campo_float(f, "TotalTax", "IvaTotal", "iva_total")

        # Algunos formatos españoles no rellenan todos los campos normalizados
        # del modelo prebuilt-invoice. Azure sí aporta el texto completo: se
        # interpreta como respaldo sin sustituir los valores estructurados.
        if texto:
            from services.ocr.invoice_interpreter import InvoiceInterpreter
            fallback = InvoiceInterpreter().interpretar(texto)
            # Algunos tickets colocan primero los datos del emisor y despues
            # el bloque del cliente. En esos casos Azure puede etiquetar el
            # segundo NIF como VendorTaxId; el primer NIF etiquetado del texto
            # es una correccion mas fiable para una factura recibida.
            if fallback.proveedor_nif and fallback.proveedor_nif != result.proveedor_nif:
                result.proveedor_nif = fallback.proveedor_nif
                if fallback.proveedor_nombre:
                    result.proveedor_nombre = fallback.proveedor_nombre
            for campo in (
                "proveedor_nombre", "proveedor_nif", "numero_factura",
                "fecha_factura", "fecha_vencimiento",
            ):
                if not getattr(result, campo):
                    setattr(result, campo, getattr(fallback, campo))
            for campo in ("total", "base_total", "iva_total", "retencion_total"):
                if not getattr(result, campo):
                    setattr(result, campo, getattr(fallback, campo))
            if not result.bases_iva and fallback.bases_iva:
                result.bases_iva = fallback.bases_iva
            if not result.retenciones and fallback.retenciones:
                result.retenciones = fallback.retenciones

        # Lineas de IVA desde TaxDetails (si disponible)
        tax_details = _azure_value(f.get("TaxDetails")) or []
        items_val = tax_details if isinstance(tax_details, list) else []
        for item in items_val:
            item_f = _azure_value(item) or {}
            if not isinstance(item_f, dict):
                continue
            linea = OcrVatLine(
                tipo_iva  = _azure_float(item_f.get("Rate")) or 0.0,
                base      = result.base_total,  # Azure no siempre desglosa base por tipo
                cuota_iva = _azure_float(item_f.get("Amount")) or 0.0,
            )
            result.bases_iva.append(linea)

        # Tabla etiquetada en un modelo personalizado. Los nombres son los
        # indicados en la guia de configuracion y permiten varios tipos de IVA.
        if not result.bases_iva:
            for item in _azure_value(f.get("LineasIva")) or []:
                item_f = _azure_value(item) or {}
                if not isinstance(item_f, dict):
                    continue
                result.bases_iva.append(OcrVatLine(
                    tipo_iva=_campo_float(item_f, "TipoIva", "tipo_iva"),
                    base=_campo_float(item_f, "Base", "base"),
                    cuota_iva=_campo_float(item_f, "CuotaIva", "cuota_iva"),
                ))

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
        result.raw_json = {
            "model_id": self._model_id,
            "azure_fields": {k: str(v) for k, v in f.items()},
            "texto_disponible": bool(texto),
        }

        # Validar coherencia
        from services.ocr.invoice_interpreter import InvoiceInterpreter
        result.errores = InvoiceInterpreter().generar_errores(result)

        return result


# ── Utilidades de mapeo ───────────────────────────────────────────────────────

def _azure_str(field) -> str:
    if field is None:
        return ""
    content = getattr(field, "content", None) or _azure_value(field) or getattr(field, "value_string", None)
    return str(content or "").strip()


def _campo(fields: dict, *nombres: str) -> str:
    """Lee un campo prebuilt o su equivalente etiquetado por el despacho."""
    for nombre in nombres:
        value = _azure_str(fields.get(nombre))
        if value:
            return value
    return ""


def _campo_float(fields: dict, *nombres: str) -> float:
    for nombre in nombres:
        value = _azure_float(fields.get(nombre))
        if value:
            return value
    return 0.0


def _campo_fecha(fields: dict, *nombres: str) -> str:
    for nombre in nombres:
        value = _azure_fecha(fields.get(nombre))
        if value:
            return value
    return ""


def _azure_float(field) -> float:
    if field is None:
        return 0.0
    val = _azure_value(field) or getattr(field, "value_number", None)
    if val is None:
        return 0.0
    try:
        # Azure devuelve CurrencyValue con amount y currency_symbol
        if hasattr(val, "amount"):
            return float(val.amount or 0.0)
        if isinstance(val, str):
            raw = val.strip().replace("%", "")
            if "," in raw and "." in raw:
                raw = raw.replace(".", "").replace(",", ".")
            elif "," in raw:
                raw = raw.replace(",", ".")
            return float(raw)
        return float(val)
    except Exception:
        return 0.0


def _azure_fecha(field) -> str:
    if field is None:
        return ""
    val = _azure_value(field) or getattr(field, "value_date", None)
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _azure_value(field):
    """Compatibilidad con DocumentField de las versiones actuales del SDK."""
    if field is None:
        return None
    value = getattr(field, "value", None)
    if value is not None:
        return value
    # Las versiones antiguas exponian valueArray/valueObject directamente.
    return getattr(field, "value_array", None) or getattr(field, "value_object", None)


def _parece_razon_social(value: str) -> bool:
    return bool(re.search(r"\b(?:S\.?L\.?U?|S\.?A\.?|S\.?C\.?|COOP\.?|SLNE)\b", value or "", re.IGNORECASE))
