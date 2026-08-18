"""Proyeccion del OCR tipado al flujo contable de emitidas."""
from __future__ import annotations

import logging
from pathlib import Path

from utils.validaciones import normalizar_nif_cif

logger = logging.getLogger(__name__)


class OcrEmitContabilidadService:
    """Convierte documentos OCR de emitidas revisados en documentos contables."""

    def __init__(self, gestor, codigo_empresa: str, ejercicio: int):
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio

    def proyectar_factura_validada(self, documento: dict, factura: dict) -> dict:
        """Crea o actualiza la fila usada por Contabilidad para SUENLACE."""
        payload = self._build_payload(documento, factura)
        self._gestor.upsert_factura_emitida(payload)
        self._gestor.enviar_facturas_emitidas_a_contabilidad(
            self._codigo, self._ejercicio, [payload["id"]],
        )
        payload["estado_contable"] = "pendiente"
        return payload

    def _build_payload(self, documento: dict, factura: dict) -> dict:
        doc_id = str(documento.get("id") or "")
        lineas = self._lineas_iva(str(factura.get("id") or ""), factura)
        cliente_id, relacion = self._resolver_relacion_cliente(factura)
        ruta = str(documento.get("ruta_original") or "")
        tipo_operacion = factura.get("tipo_operacion") or "01"
        fecha_contable = factura.get("fecha_contable") or factura.get("fecha_factura") or ""
        cobrada = 1 if factura.get("cobrada") else 0
        base_retencion = float(factura.get("base_total") or 0.0)
        importe_retencion = float(factura.get("retencion_total") or 0.0)
        porcentaje_retencion = (
            round(abs(importe_retencion) * 100.0 / abs(base_retencion), 2)
            if base_retencion else 0.0
        )

        return {
            "id": doc_id,
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "origen_factura": "ocr",
            "ocr_documento_id": doc_id,
            "serie": "",
            "numero": factura.get("numero_factura") or "",
            "numero_largo_sii": factura.get("numero_factura") or "",
            "numero_asiento": "",
            "fecha_expedicion": factura.get("fecha_factura") or "",
            "fecha_operacion": factura.get("fecha_operacion") or factura.get("fecha_factura") or "",
            "fecha_asiento": fecha_contable,
            "tipo_operacion": tipo_operacion,
            "modelo_fiscal": "",
            "nif": factura.get("nif_cliente") or "",
            "nombre": factura.get("nombre_cliente") or "",
            "descripcion": f"Factura {factura.get('numero_factura') or ''}".strip(),
            "observaciones": "Documento externo incorporado mediante OCR.",
            "tercero_id": cliente_id,
            "subcuenta_cliente": factura.get("subcuenta_cliente") or relacion.get("subcuenta_cliente") or "",
            "subcuenta_ingreso": factura.get("cuenta_ingreso") or relacion.get("subcuenta_ingreso") or "",
            "subcuenta_iva": factura.get("cuenta_iva") or "",
            "forma_pago": "Cobrada" if cobrada else "",
            "retencion_aplica": bool(importe_retencion),
            "retencion_pct": porcentaje_retencion,
            "retencion_base": base_retencion if importe_retencion else 0.0,
            "retencion_importe": importe_retencion,
            "moneda_codigo": "EUR",
            "moneda_simbolo": "€",
            "pdf_path": ruta if Path(ruta).suffix.lower() == ".pdf" else "",
            "pdf_ref": doc_id,
            "generada": False,
            "enviado": False,
            "borrador": False,
            "lineas": lineas,
        }

    def _lineas_iva(self, factura_id: str, factura: dict) -> list[dict]:
        lineas = []
        try:
            for item in self._gestor.listar_lineas_iva_emitida_ocr(factura_id):
                lineas.append({
                    "tipo": "linea",
                    "concepto": f"Factura {factura.get('numero_factura') or ''}".strip(),
                    "base": item.get("base") or 0.0,
                    "pct_iva": item.get("tipo_iva") or 0.0,
                    "cuota_iva": item.get("cuota_iva") or 0.0,
                    "pct_re": item.get("tipo_recargo") or 0.0,
                    "cuota_re": item.get("cuota_recargo") or 0.0,
                    "cuenta_ingreso": item.get("cuenta_ingreso") or "",
                })
        except Exception as exc:
            logger.warning("[OCR Emitidas] No se pudieron obtener lineas IVA: %s", exc)
        return lineas

    def _resolver_relacion_cliente(self, factura: dict) -> tuple[str, dict]:
        cliente_id = str(factura.get("cliente_id") or "").strip()
        if not cliente_id:
            cliente_id = self._buscar_cliente_por_nif(factura)
            if cliente_id:
                factura["cliente_id"] = cliente_id

        if not cliente_id:
            return "", {}

        try:
            relacion = self._gestor.get_tercero_empresa(
                self._codigo, cliente_id, self._ejercicio
            ) or {}
        except Exception as exc:
            logger.warning("[OCR Emitidas] No se pudo cargar relacion contable del cliente: %s", exc)
            relacion = {}
        return cliente_id, relacion

    def _buscar_cliente_por_nif(self, factura: dict) -> str:
        nif_norm = _normalizar_nif(factura.get("nif_cliente"))
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
