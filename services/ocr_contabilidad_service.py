"""Proyeccion del OCR tipado al flujo contable de recibidas."""
from __future__ import annotations

import logging
from pathlib import Path

from utils.validaciones import normalizar_nif_cif

logger = logging.getLogger(__name__)


class OcrContabilidadService:
    """Convierte documentos OCR revisados en documentos contables."""

    def __init__(self, gestor, codigo_empresa: str, ejercicio: int):
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio

    def proyectar_factura_validada(self, documento: dict, factura: dict) -> dict:
        """Crea o actualiza la fila usada por Contabilidad para SUENLACE."""
        payload = self._build_payload(documento, factura)
        self._gestor.upsert_factura_recibida_doc(payload)
        return payload

    def _build_payload(self, documento: dict, factura: dict) -> dict:
        doc_id = str(documento.get("id") or "")
        lineas = self._lineas_iva(str(factura.get("id") or ""), factura)
        proveedor_id, relacion = self._resolver_relacion_proveedor(factura)
        ruta = str(documento.get("ruta_original") or "")
        tipo_operacion = factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE"
        fecha_contable = factura.get("fecha_contable") or factura.get("fecha_factura") or ""
        suplidos = float(factura.get("suplidos") or 0.0)
        cuenta_suplidos = str(factura.get("cuenta_suplidos") or "").strip()

        return {
            "id": doc_id,
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "origen_path": ruta,
            "pdf_path": ruta if Path(ruta).suffix.lower() == ".pdf" else "",
            "estado_ocr": "procesado",
            "estado_validacion": "validada",
            "estado_contable": "pendiente_contabilizar",
            "tipo_documento": "factura_recibida",
            "tercero_id": proveedor_id,
            "cuenta_proveedor": (
                factura.get("cuenta_proveedor")
                or relacion.get("subcuenta_proveedor")
                or ""
            ),
            "cuenta_gasto": (
                factura.get("cuenta_gasto")
                or relacion.get("subcuenta_gasto")
                or ""
            ),
            "cuenta_iva": factura.get("cuenta_iva") or "",
            "proveedor_nif": factura.get("nif_proveedor") or "",
            "proveedor_nombre": factura.get("nombre_proveedor") or "",
            "proveedor_tipo_operacion_iva": tipo_operacion,
            "numero_factura": factura.get("numero_factura") or "",
            "fecha_factura": factura.get("fecha_factura") or "",
            "fecha_operacion": (
                factura.get("fecha_operacion")
                or factura.get("fecha_factura")
                or ""
            ),
            "fecha_asiento": fecha_contable,
            "fecha_vencimiento": factura.get("fecha_vencimiento") or "",
            "descripcion": f"Factura {factura.get('numero_factura') or ''}".strip(),
            "moneda_codigo": "EUR",
            "base_imponible": factura.get("base_total") or 0.0,
            "cuota_iva": factura.get("iva_total") or 0.0,
            "cuota_retencion": factura.get("retencion_total") or 0.0,
            "pagada": 1 if factura.get("pagada") else 0,
            "suplidos": suplidos,
            "cuenta_suplidos": cuenta_suplidos,
            "total": factura.get("total_factura") or 0.0,
            "lineas": lineas,
            "datos_extra": {
                "documento_ocr_id": doc_id,
                "tipo_operacion_iva": tipo_operacion,
                "fecha_contable": fecha_contable,
                "pagada": bool(factura.get("pagada")),
                "suplidos": suplidos,
                "cuenta_suplidos": cuenta_suplidos,
            },
        }

    def _lineas_iva(self, factura_id: str, factura: dict) -> list[dict]:
        lineas = []
        try:
            for item in self._gestor.listar_lineas_iva_ocr(factura_id):
                lineas.append({
                    "base_imponible": item.get("base") or 0.0,
                    "tipo_iva": item.get("tipo_iva") or 0.0,
                    "cuota_iva": item.get("cuota_iva") or 0.0,
                    "tipo_recargo": item.get("tipo_recargo") or 0.0,
                    "cuota_recargo": item.get("cuota_recargo") or 0.0,
                    "cuenta_base": item.get("cuenta_gasto") or "",
                    "tipo_operacion_iva": (
                        item.get("tipo_operacion_iva")
                        or factura.get("tipo_operacion_iva")
                    ),
                })
        except Exception as exc:
            logger.warning("[OCR] No se pudieron obtener las lineas IVA: %s", exc)
        return lineas

    def _resolver_relacion_proveedor(self, factura: dict) -> tuple[str, dict]:
        proveedor_id = str(factura.get("proveedor_id") or "").strip()
        if not proveedor_id:
            proveedor_id = self._buscar_proveedor_por_nif(factura)
            if proveedor_id:
                factura["proveedor_id"] = proveedor_id

        if not proveedor_id:
            return "", {}

        try:
            relacion = self._gestor.get_tercero_empresa(
                self._codigo, proveedor_id, self._ejercicio
            ) or {}
        except Exception as exc:
            logger.warning("[OCR] No se pudo cargar la relacion contable del proveedor: %s", exc)
            relacion = {}
        return proveedor_id, relacion

    def _buscar_proveedor_por_nif(self, factura: dict) -> str:
        nif_norm = _normalizar_nif(factura.get("nif_proveedor"))
        if not nif_norm:
            return ""

        try:
            terceros = self._gestor.listar_terceros_por_empresa(
                self._codigo, self._ejercicio
            ) or []
        except Exception:
            return ""

        for tercero in terceros:
            tercero_nif = _normalizar_nif(tercero.get("nif"))
            if tercero_nif and tercero_nif == nif_norm:
                return str(tercero.get("id") or tercero.get("tercero_id") or "")
        return ""


def _normalizar_nif(value) -> str:
    try:
        return normalizar_nif_cif(value)
    except Exception:
        return str(value or "").upper().replace("-", "").replace(" ", "")
