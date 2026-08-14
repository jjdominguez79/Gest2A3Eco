"""
Servicio OCR del backend: proxy hacia Azure Document Intelligence.

Las credenciales Azure residen exclusivamente en las variables de entorno
del servidor; el escritorio nunca accede a ellas directamente.

Exporta:
  analyze_invoice(content, filename, model_id_override) -> dict
  ocr_available() -> bool
"""
from __future__ import annotations

import re

from backend.api.config import get_settings


# ── Helpers de mapeo Azure → dict ────────────────────────────────────────────

def _azure_str(field) -> str:
    if field is None:
        return ""
    content = getattr(field, "content", None) or _azure_value(field) or getattr(field, "value_string", None)
    return str(content or "").strip()


def _campo(fields: dict, *nombres: str) -> str:
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


def _parse_importe(raw) -> float:
    """
    Convierte un string de importe en float, soportando formatos ES y EN.

    Ejemplos soportados:
      "340,00€"    → 340.0
      "280,98€"    → 280.98
      "1.234,56 €" → 1234.56
      "1,234.56"   → 1234.56
      "1234.56"    → 1234.56
      "1234,56"    → 1234.56
      "€340,00"    → 340.0
      ""           → 0.0
      None         → 0.0

    Logica: si hay tanto '.' como ',' el que aparece mas a la derecha es el
    separador decimal. Si solo hay ',' es separador decimal estilo espanol.
    """
    if not raw:
        return 0.0
    s = str(raw).strip()
    s = re.sub(r'[€$£\s]', '', s)
    s = s.replace('%', '')
    if not s:
        return 0.0
    try:
        pos_punto = s.rfind('.')
        pos_coma  = s.rfind(',')
        if pos_punto != -1 and pos_coma != -1:
            if pos_punto > pos_coma:
                # Formato EN: 1,234.56
                s = s.replace(',', '')
            else:
                # Formato ES: 1.234,56
                s = s.replace('.', '').replace(',', '.')
        elif pos_coma != -1:
            # Solo coma: separador decimal espanol
            s = s.replace(',', '.')
        return float(s)
    except Exception:
        return 0.0


def _parse_fecha(raw) -> str:
    """
    Normaliza una fecha a formato ISO YYYY-MM-DD.

    Formatos soportados:
      "22/07/2026" → "2026-07-22"
      "22-07-2026" → "2026-07-22"
      "2026-07-22" → "2026-07-22"
      None/""      → ""
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    return s


def _azure_float(field) -> float:
    if field is None:
        return 0.0
    # Prioridad 1: valueCurrency (objeto con .amount)
    val = _azure_value(field) or getattr(field, "value_number", None)
    if val is not None:
        try:
            if hasattr(val, "amount"):
                return float(val.amount or 0.0)
            if isinstance(val, str):
                return _parse_importe(val)
            return float(val)
        except Exception:
            pass
    # Prioridad 2: valueString como fallback
    vs = getattr(field, "value_string", None)
    if vs:
        result = _parse_importe(vs)
        if result:
            return result
    # Prioridad 3: content como ultimo recurso
    content = getattr(field, "content", None)
    if content:
        return _parse_importe(str(content))
    return 0.0


def _azure_fecha(field) -> str:
    if field is None:
        return ""
    val = _azure_value(field) or getattr(field, "value_date", None)
    if val is not None:
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if isinstance(val, str):
            return _parse_fecha(val)
        return str(val)
    # Fallback: valueString
    vs = getattr(field, "value_string", None)
    if vs:
        return _parse_fecha(str(vs))
    # Fallback: content
    content = getattr(field, "content", None)
    if content:
        return _parse_fecha(str(content))
    return ""


def _azure_value(field):
    if field is None:
        return None
    value = getattr(field, "value", None)
    if value is not None:
        return value
    return getattr(field, "value_array", None) or getattr(field, "value_object", None)


def _parece_razon_social(value: str) -> bool:
    return bool(re.search(r"\b(?:S\.?L\.?U?|S\.?A\.?|S\.?C\.?|COOP\.?|SLNE)\b", value or "", re.IGNORECASE))


def _mapear_documento(doc, model_id: str, texto: str = "") -> dict:
    """
    Mapea un DocumentAnalysisResult de Azure al formato OcrInvoiceResult.to_dict().
    No importa nada del modulo desktop services/.
    """
    f = doc.fields or {}

    # Proveedor
    proveedor_modelo = _campo(f, "VendorName", "ProveedorNombre", "nombre_proveedor")
    proveedor_destinatario = _campo(f, "VendorAddressRecipient")
    proveedor_nombre = (
        proveedor_destinatario
        if _parece_razon_social(proveedor_destinatario)
        else proveedor_modelo or proveedor_destinatario
    )
    proveedor_nif = _campo(f, "VendorTaxId", "ProveedorNif", "NifProveedor", "nif_proveedor")

    # Numero y fechas
    numero_factura = _campo(f, "InvoiceId", "NumeroFactura", "numero_factura")
    fecha_factura = _campo_fecha(f, "InvoiceDate", "FechaFactura", "fecha_factura")
    fecha_vencimiento = _campo_fecha(f, "DueDate", "FechaVencimiento", "fecha_vencimiento")

    # Importes globales
    total = _campo_float(f, "InvoiceTotal", "TotalFactura", "total_factura")
    base_total = _campo_float(f, "SubTotal", "BaseTotal", "base_total")
    iva_total = _campo_float(f, "TotalTax", "IvaTotal", "iva_total")
    retencion_total = 0.0

    # Lineas de IVA desde TaxDetails
    bases_iva = []
    tax_details = _azure_value(f.get("TaxDetails")) or []
    items_val = tax_details if isinstance(tax_details, list) else []
    for item in items_val:
        item_f = _azure_value(item) or {}
        if not isinstance(item_f, dict):
            continue
        bases_iva.append({
            "tipo_iva": _azure_float(item_f.get("Rate")) or 0.0,
            "base": base_total,
            "cuota_iva": _azure_float(item_f.get("Amount")) or 0.0,
            "tipo_recargo": 0.0,
            "cuota_recargo": 0.0,
            "deducible": True,
            "porcentaje_deduccion": 100.0,
            "cuenta_gasto": "",
            "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
        })

    # Tabla LineasIva de modelo personalizado
    if not bases_iva:
        for item in _azure_value(f.get("LineasIva")) or []:
            item_f = _azure_value(item) or {}
            if not isinstance(item_f, dict):
                continue
            bases_iva.append({
                "tipo_iva": _campo_float(item_f, "TipoIva", "tipo_iva"),
                "base": _campo_float(item_f, "Base", "base"),
                "cuota_iva": _campo_float(item_f, "CuotaIva", "cuota_iva"),
                "tipo_recargo": 0.0,
                "cuota_recargo": 0.0,
                "deducible": True,
                "porcentaje_deduccion": 100.0,
                "cuenta_gasto": "",
                "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
            })

    # Fallback: una linea desde totales
    if not bases_iva and base_total:
        tipo = round(iva_total / base_total * 100, 1) if base_total else 0.0
        bases_iva.append({
            "tipo_iva": tipo,
            "base": base_total,
            "cuota_iva": iva_total,
            "tipo_recargo": 0.0,
            "cuota_recargo": 0.0,
            "deducible": True,
            "porcentaje_deduccion": 100.0,
            "cuenta_gasto": "",
            "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
        })

    # Confianza: media de campos clave
    campos_clave = [f.get(k) for k in ("VendorName", "InvoiceId", "InvoiceDate", "InvoiceTotal")]
    confs = [c.confidence for c in campos_clave if c and hasattr(c, "confidence")]
    confianza = round(sum(confs) / len(confs), 3) if confs else 0.85

    raw_json = {
        "model_id": model_id,
        "azure_fields": {k: str(v) for k, v in f.items()},
        "texto_disponible": bool(texto),
    }

    # Errores basicos de coherencia
    errores = []
    if not proveedor_nif:
        errores.append("NIF del proveedor no detectado.")
    if not numero_factura:
        errores.append("Numero de factura no detectado.")
    if not fecha_factura:
        errores.append("Fecha de factura no detectada.")

    return {
        "proveedor_nombre": proveedor_nombre,
        "proveedor_nif": proveedor_nif,
        "numero_factura": numero_factura,
        "fecha_factura": fecha_factura,
        "fecha_vencimiento": fecha_vencimiento,
        "total": total,
        "base_total": base_total,
        "iva_total": iva_total,
        "retencion_total": retencion_total,
        "bases_iva": bases_iva,
        "retenciones": [],
        "texto": texto,
        "raw_json": raw_json,
        "confianza": confianza,
        "motor": "azure_backend",
        "errores": errores,
    }


# ── API publica del modulo ────────────────────────────────────────────────────

def ocr_available() -> bool:
    """True si las credenciales Azure estan configuradas en el backend."""
    return bool(get_settings().azure_doc_intelligence_key)


def analyze_invoice(content: bytes, filename: str, model_id_override: str = "") -> dict:
    """
    Analiza una factura con Azure Document Intelligence.

    Parametros:
      content          — bytes del fichero PDF o imagen
      filename         — nombre original del fichero (solo informativo)
      model_id_override — si no esta vacio, sustituye al model_id de configuracion

    Devuelve un dict con la misma estructura que OcrInvoiceResult.to_dict()
    mas el campo motor="azure_backend".

    Lanza RuntimeError si las credenciales no estan configuradas.
    Lanza cualquier excepcion del SDK de Azure si el servicio falla.
    """
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    settings = get_settings()
    if not settings.azure_doc_intelligence_key:
        raise RuntimeError("Azure OCR no configurado")

    model_id = (
        model_id_override
        or settings.azure_doc_intelligence_model_id
        or "prebuilt-invoice"
    )

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intelligence_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intelligence_key),
    )

    poller = client.begin_analyze_document(
        model_id,
        body=content,
        content_type="application/octet-stream",
    )
    result = poller.result()

    if not result.documents:
        return {
            "proveedor_nombre": "",
            "proveedor_nif": "",
            "numero_factura": "",
            "fecha_factura": "",
            "fecha_vencimiento": "",
            "total": 0.0,
            "base_total": 0.0,
            "iva_total": 0.0,
            "retencion_total": 0.0,
            "bases_iva": [],
            "retenciones": [],
            "texto": str(getattr(result, "content", "") or ""),
            "raw_json": {"model_id": model_id},
            "confianza": 0.0,
            "motor": "azure_backend",
            "errores": ["Azure no devolvio documentos analizados."],
        }

    doc = result.documents[0]
    texto = str(getattr(result, "content", "") or "")
    return _mapear_documento(doc, model_id=model_id, texto=texto)
