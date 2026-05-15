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
    return {
        "Fecha Asiento": doc.get("fecha_asiento") or doc.get("fecha_factura"),
        "Fecha Expedicion": doc.get("fecha_factura"),
        "Fecha Operacion": doc.get("fecha_operacion") or doc.get("fecha_factura"),
        "Descripcion Factura": doc.get("descripcion") or f"Factura {doc.get('numero_factura') or ''}".strip(),
        "Numero Factura": doc.get("numero_factura"),
        "NIF Cliente Proveedor": doc.get("proveedor_nif"),
        "Nombre Cliente Proveedor": doc.get("proveedor_nombre"),
        "Base": doc.get("base_imponible") or 0.0,
        "Cuota IVA": doc.get("cuota_iva") or 0.0,
        "Cuota Recargo Equivalencia": doc.get("cuota_recargo") or 0.0,
        "Cuota Retencion IRPF": doc.get("cuota_retencion") or 0.0,
        "Total": doc.get("total") or 0.0,
        "_cuenta_tercero_override": doc.get("cuenta_proveedor") or "",
        "_cuenta_py_gv_override": doc.get("cuenta_gasto") or "",
        "_cuenta_iva_override": doc.get("cuenta_iva") or "",
        "_pdf_ref": doc.get("id"),
    }


def generate_suenlace_for_docs(gestor, codigo: str, ejercicio: int, docs: list[dict]) -> list[str]:
    if not docs:
        return []
    plantilla = resolve_recibidas_template(gestor, codigo, ejercicio)
    empresa = gestor.get_empresa(codigo, ejercicio) or {}
    ndig = int(empresa.get("digitos_plan") or 8)
    terceros_by_nif = build_terceros_by_nif(gestor, codigo, ejercicio)
    rows = [doc_to_row(doc) for doc in docs]
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
