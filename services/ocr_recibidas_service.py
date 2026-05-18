from __future__ import annotations

from datetime import datetime
from typing import Any

from procesos.facturas_recibidas import generar_recibidas_suenlace


def resolve_recibidas_template(gestor, codigo: str, ejercicio: int) -> dict:
    plantillas = gestor.listar_recibidas(codigo, ejercicio)
    if plantillas:
        return dict(plantillas[0])
    return {
        "nombre": "OCR",
        "cuenta_proveedor_prefijo": "400",
        "cuenta_gasto_por_defecto": "62900000",
        "cuenta_iva_soportado_defecto": "47200000",
        "subtipo_recibidas": "01",
    }


def build_terceros_by_nif(gestor, codigo: str, ejercicio: int) -> dict[str, dict[str, Any]]:
    terceros_by_nif: dict[str, dict[str, Any]] = {}
    for tercero in gestor.listar_terceros():
        nif = _norm_nif(tercero.get("nif"))
        if nif:
            terceros_by_nif[nif] = tercero
    for tercero in gestor.listar_terceros_por_empresa(codigo, ejercicio):
        nif = _norm_nif(tercero.get("nif"))
        if nif:
            terceros_by_nif[nif] = tercero
    return terceros_by_nif


def doc_to_row(doc: dict) -> dict:
    """Convierte un doc en una unica fila (sin lineas fiscales multi-tramo)."""
    return {
        "Fecha Asiento":             doc.get("fecha_asiento") or doc.get("fecha_factura"),
        "Fecha Expedicion":          doc.get("fecha_factura"),
        "Fecha Operacion":           doc.get("fecha_operacion") or doc.get("fecha_factura"),
        "Descripcion Factura":       doc.get("descripcion") or f"Factura {doc.get('numero_factura') or ''}".strip(),
        "Numero Factura":            doc.get("numero_factura"),
        "NIF Cliente Proveedor":     doc.get("proveedor_nif"),
        "Nombre Cliente Proveedor":  doc.get("proveedor_nombre"),
        "Base":                      doc.get("base_imponible") or 0.0,
        "Cuota IVA":                 doc.get("cuota_iva") or 0.0,
        "Cuota Recargo Equivalencia": doc.get("cuota_recargo") or 0.0,
        "Cuota Retencion IRPF":      doc.get("cuota_retencion") or 0.0,
        "Total":                     doc.get("total") or 0.0,
        "_cuenta_tercero_override":  doc.get("cuenta_proveedor") or "",
        "_cuenta_py_gv_override":    doc.get("cuenta_gasto") or "",
        "_cuenta_iva_override":      doc.get("cuenta_iva") or "",
        "_proveedor_tipo_operacion_iva": doc.get("proveedor_tipo_operacion_iva") or "INTERIOR_DEDUCIBLE",
        "_proveedor_iva_deducible": int(doc.get("proveedor_iva_deducible", 1) or 0),
        "_proveedor_porcentaje_deduccion_iva": doc.get("proveedor_porcentaje_deduccion_iva", 100.0),
        "_pdf_ref":                  doc.get("id"),
    }


def doc_to_rows(doc: dict, lineas: list[dict] | None = None) -> list[dict]:
    """Expande un doc en una fila por tramo fiscal (multi-base IVA).

    Si 'lineas' esta vacia o no se proporciona, devuelve [doc_to_row(doc)]
    para mantener compatibilidad con documentos sin lineas fiscales detalladas.

    Los campos comunes (fechas, NIF, descripcion, cuentas override) se replican
    en cada fila; solo los importes y porcentajes vienen de cada linea.
    """
    _lineas = [
        ln for ln in (lineas or [])
        if (ln.get("base_imponible") or ln.get("cuota_iva")
            or ln.get("cuota_recargo") or ln.get("cuota_retencion"))
    ]
    if not _lineas:
        return [doc_to_row(doc)]

    base_row = {
        "Fecha Asiento":             doc.get("fecha_asiento") or doc.get("fecha_factura"),
        "Fecha Expedicion":          doc.get("fecha_factura"),
        "Fecha Operacion":           doc.get("fecha_operacion") or doc.get("fecha_factura"),
        "Descripcion Factura":       doc.get("descripcion") or f"Factura {doc.get('numero_factura') or ''}".strip(),
        "Numero Factura":            doc.get("numero_factura"),
        "NIF Cliente Proveedor":     doc.get("proveedor_nif"),
        "Nombre Cliente Proveedor":  doc.get("proveedor_nombre"),
        "_cuenta_tercero_override":  doc.get("cuenta_proveedor") or "",
        "_cuenta_py_gv_override":    doc.get("cuenta_gasto") or "",
        "_cuenta_iva_override":      doc.get("cuenta_iva") or "",
        "_proveedor_tipo_operacion_iva": doc.get("proveedor_tipo_operacion_iva") or "INTERIOR_DEDUCIBLE",
        "_proveedor_iva_deducible": int(doc.get("proveedor_iva_deducible", 1) or 0),
        "_proveedor_porcentaje_deduccion_iva": doc.get("proveedor_porcentaje_deduccion_iva", 100.0),
        "_pdf_ref":                  doc.get("id"),
    }

    rows = []
    for linea in _lineas:
        row = dict(base_row)
        row["Base"]                        = linea.get("base_imponible") or 0.0
        row["Porcentaje IVA"]              = linea.get("tipo_iva") or 0.0
        row["Cuota IVA"]                   = linea.get("cuota_iva") or 0.0
        row["Porcentaje Recargo Equivalencia"] = linea.get("tipo_recargo") or 0.0
        row["Cuota Recargo Equivalencia"]  = linea.get("cuota_recargo") or 0.0
        row["Porcentaje Retencion IRPF"]   = linea.get("tipo_retencion") or 0.0
        row["Cuota Retencion IRPF"]        = linea.get("cuota_retencion") or 0.0
        # Cuentas contables a nivel de linea (opcionales)
        if linea.get("cuenta_base"):
            row["Cuenta Compras Ventas"] = linea["cuenta_base"]
        if linea.get("cuenta_iva"):
            row["_cuenta_iva_override"] = linea["cuenta_iva"]
        rows.append(row)
    return rows


def generate_suenlace_for_docs(gestor, codigo: str, ejercicio: int, docs: list[dict]) -> list[str]:
    if not docs:
        return []
    plantilla = resolve_recibidas_template(gestor, codigo, ejercicio)
    empresa = gestor.get_empresa(codigo, ejercicio) or {}
    ndig = int(empresa.get("digitos_plan") or 8)
    terceros_by_nif = build_terceros_by_nif(gestor, codigo, ejercicio)

    rows: list[dict] = []
    for doc in docs:
        # Cargar lineas fiscales desde DB si el doc no las trae ya en memoria
        lineas = doc.get("lineas") or []
        if not lineas:
            doc_id = doc.get("id")
            if doc_id:
                lineas = gestor.listar_ocr_lineas_doc(str(doc_id)) or []
        rows.extend(doc_to_rows(doc, lineas))

    return generar_recibidas_suenlace(
        rows,
        plantilla,
        str(codigo),
        ndig,
        ejercicio=ejercicio,
        terceros_by_nif=terceros_by_nif,
    )


def mark_docs_as_generated(gestor, docs: list[dict], *, estado_contable: str = "contabilizada", fecha_generacion: str | None = None) -> None:
    timestamp = fecha_generacion or datetime.now().strftime("%Y-%m-%d %H:%M")
    for doc in docs:
        payload = dict(doc)
        payload["generada"] = True
        payload["fecha_generacion"] = timestamp
        payload["estado_contable"] = estado_contable
        gestor.upsert_factura_recibida_doc(payload)
        asiento = gestor.get_asiento_contable_por_documento(payload.get("id"))
        if asiento:
            asiento["estado"] = "exportado"
            asiento["numero_asiento"] = payload.get("numero_asiento")
            asiento["fecha_asiento"] = payload.get("fecha_asiento")
            gestor.upsert_asiento_contable(asiento)


def _norm_nif(value: Any) -> str:
    return str(value or "").strip().upper()
