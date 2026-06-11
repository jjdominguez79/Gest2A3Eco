"""
OcrService — orquestador OCR con gestion de base de datos.

Flujo principal:
  1. Recibir archivo y empresa_id.
  2. Calcular hash SHA-256.
  3. Comprobar duplicados (por hash + empresa).
  4. Intentar extraccion de texto (PDF nativo → local → extensible).
  5. Si hay texto suficiente, interpretar factura.
  6. Guardar documento y factura propuesta en BD.
  7. Marcar estado: pendiente_revision | error | duplicado.

Compatible con el contrato OcrInvoiceResult de services/ocr/types.py.
No reemplaza services/ocr_service.py (que sigue activo para el flujo
existente de facturas_recibidas_docs).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from services.ocr.types import OcrInvoiceResult, OcrDocumentState

logger = logging.getLogger(__name__)

# Umbral de caracteres para considerar texto suficiente
_MIN_TEXT_CHARS = 50


class OcrService:
    """
    Orquestador OCR con persistencia en las tablas documentos_ocr y
    facturas_recibidas_ocr.

    Parametros:
      gestor     — instancia de GestorSQLite
      empresa_id — codigo de empresa (ej: 'E00001')
      ejercicio  — ejercicio fiscal (ej: 2024)
      usuario    — nombre de usuario (para auditoría)
    """

    def __init__(self, gestor, empresa_id: str, ejercicio: int, usuario: str = ""):
        self._gestor    = gestor
        self._empresa   = empresa_id
        self._ejercicio = ejercicio
        self._usuario   = usuario
        self._motores   = self._construir_cadena_motores()

    # ── Punto de entrada publico ──────────────────────────────────────────────

    def procesar_archivo(self, file_path: str) -> dict:
        """
        Procesa un fichero PDF o imagen.

        Devuelve dict con:
          documento_id    — ID del registro en documentos_ocr
          factura_id      — ID del registro en facturas_recibidas_ocr (None si error)
          estado          — OcrDocumentState (str)
          resultado       — OcrInvoiceResult serializado como dict
          errores         — lista de errores
        """
        path = Path(file_path)
        if not path.exists():
            return self._respuesta_error(None, f"Fichero no encontrado: {file_path}")

        # 1. Hash para detectar duplicados
        hash_archivo = _sha256(path)

        # 2. Comprobar duplicado
        doc_dup = self._gestor.buscar_documento_ocr_por_hash(self._empresa, hash_archivo)
        if doc_dup:
            logger.info("[OcrService] Duplicado detectado: %s", path.name)
            return {
                "documento_id": doc_dup["id"],
                "factura_id":   None,
                "estado":       OcrDocumentState.DUPLICADO.value,
                "resultado":    {},
                "errores":      [f"Documento duplicado (ya existe: {doc_dup.get('nombre_archivo')})"],
            }

        # 3. Crear registro inicial en documentos_ocr
        doc_id = str(uuid.uuid4())
        doc_payload = {
            "id":              doc_id,
            "empresa_id":      self._empresa,
            "ruta_original":   str(path),
            "nombre_archivo":  path.name,
            "hash_archivo":    hash_archivo,
            "tipo_documento":  "factura_recibida",
            "estado":          OcrDocumentState.PROCESANDO.value,
            "fecha_alta":      _now(),
            "fecha_procesado": None,
            "motor_ocr":       "",
            "confianza_global": 0.0,
            "error_ocr":       "",
            "texto_extraido":  "",
            "json_ocr":        "",
        }
        self._gestor.upsert_documento_ocr(doc_payload)

        # 4. Intentar extraccion con cadena de motores
        result = self._ejecutar_motores(path)

        # 5. Actualizar documento con resultado
        doc_payload.update({
            "estado":          result.estado_sugerido.value,
            "fecha_procesado": _now(),
            "motor_ocr":       result.motor,
            "confianza_global": result.confianza,
            "error_ocr":       "; ".join(result.errores) if not result.proveedor_nif else "",
            "texto_extraido":  result.texto,
            "json_ocr":        result.to_json(),
        })
        self._gestor.upsert_documento_ocr(doc_payload)

        # 6. Guardar factura propuesta si hay datos minimos
        factura_id = None
        if result.proveedor_nif or result.numero_factura:
            factura_id = self._guardar_factura(doc_id, result)

        estado_final = result.estado_sugerido.value

        logger.info(
            "[OcrService] %s → motor=%s confianza=%.0f%% estado=%s",
            path.name, result.motor, result.confianza * 100, estado_final,
        )

        return {
            "documento_id": doc_id,
            "factura_id":   factura_id,
            "estado":       estado_final,
            "resultado":    result.to_dict(),
            "errores":      result.errores,
        }

    # ── Cadena de motores ─────────────────────────────────────────────────────

    def _construir_cadena_motores(self):
        """Construye la lista ordenada de motores disponibles."""
        motores = []

        # 1. PDF texto nativo (siempre primero si disponible)
        try:
            from services.ocr.engines.pdf_text_engine import PdfTextEngine
            e = PdfTextEngine()
            if e.disponible():
                motores.append(e)
        except Exception:
            pass

        # 2. Azure (si configurado)
        try:
            cfg = self._leer_config_ocr()
            if cfg.get("motor_activo") == "azure":
                from services.ocr.engines.azure_invoice_engine import AzureInvoiceEngine
                e = AzureInvoiceEngine(
                    endpoint=cfg.get("azure_endpoint", ""),
                    api_key=cfg.get("azure_key", ""),
                )
                if e.disponible():
                    motores.append(e)
        except Exception:
            pass

        # 3. Tesseract local (si disponible)
        try:
            from services.ocr.engines.local_engine import LocalOcrEngine
            e = LocalOcrEngine()
            if e.disponible():
                motores.append(e)
        except Exception:
            pass

        return motores

    def _ejecutar_motores(self, path: Path) -> OcrInvoiceResult:
        """
        Ejecuta la cadena de motores en orden.
        Devuelve el primer resultado con texto suficiente o el ultimo error.
        """
        ultimo_resultado = OcrInvoiceResult(
            motor="none",
            errores=["No hay motores OCR disponibles para procesar este documento."],
        )

        for motor in self._motores:
            try:
                resultado = motor.extraer(path)
            except Exception as exc:
                logger.warning("[OcrService] Motor %s lanzo excepcion: %s", motor.nombre, exc)
                continue

            if resultado.texto and len(resultado.texto.strip()) >= _MIN_TEXT_CHARS:
                return resultado

            # Motor no extrajo texto util: guardar como fallback y continuar
            ultimo_resultado = resultado

        # Ningun motor extrajo texto suficiente
        if not self._motores:
            ext = path.suffix.lower()
            if ext == ".pdf":
                ultimo_resultado.errores = [
                    "El PDF no tiene texto embebido. Configura Tesseract o Azure para PDFs escaneados."
                ]
            else:
                ultimo_resultado.errores = [
                    "La imagen requiere un motor OCR local (Tesseract) o externo (Azure)."
                ]

        return ultimo_resultado

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _guardar_factura(self, doc_id: str, result: OcrInvoiceResult) -> str:
        """Guarda la factura propuesta en facturas_recibidas_ocr. Devuelve el ID."""
        factura_id = str(uuid.uuid4())
        payload = {
            "id":              factura_id,
            "documento_id":    doc_id,
            "empresa_id":      self._empresa,
            "proveedor_id":    None,
            "nif_proveedor":   result.proveedor_nif,
            "nombre_proveedor": result.proveedor_nombre,
            "numero_factura":  result.numero_factura,
            "fecha_factura":   result.fecha_factura,
            "fecha_operacion": result.fecha_factura,
            "fecha_vencimiento": result.fecha_vencimiento,
            "total_factura":   result.total,
            "base_total":      result.base_total,
            "iva_total":       result.iva_total,
            "retencion_total": result.retencion_total,
            "estado_validacion": "pendiente",
            "observaciones":   "; ".join(result.errores) if result.errores else "",
        }
        self._gestor.upsert_factura_recibida_ocr(payload)

        # Lineas de IVA
        for i, linea in enumerate(result.bases_iva):
            self._gestor.upsert_linea_iva_ocr({
                "factura_id":           factura_id,
                "tipo_iva":             linea.tipo_iva,
                "base":                 linea.base,
                "cuota_iva":            linea.cuota_iva,
                "tipo_recargo":         linea.tipo_recargo,
                "cuota_recargo":        linea.cuota_recargo,
                "deducible":            1 if linea.deducible else 0,
                "porcentaje_deduccion": linea.porcentaje_deduccion,
                "cuenta_gasto":         linea.cuenta_gasto,
                "tipo_operacion_iva":   linea.tipo_operacion_iva,
            })

        # Retenciones
        for ret in result.retenciones:
            self._gestor.upsert_retencion_ocr({
                "factura_id":        factura_id,
                "base_retencion":    ret.base_retencion,
                "tipo_retencion":    ret.tipo_retencion,
                "importe_retencion": ret.importe_retencion,
                "clase_retencion":   ret.clase_retencion,
            })

        return factura_id

    # ── Correcciones manuales ─────────────────────────────────────────────────

    def registrar_correccion(self, factura_id: str, campo: str, valor_ocr: str, valor_corregido: str):
        """Registra una correccion manual del usuario para auditoría."""
        self._gestor.upsert_correccion_ocr({
            "factura_id":      factura_id,
            "campo":           campo,
            "valor_ocr":       valor_ocr,
            "valor_corregido": valor_corregido,
            "fecha_correccion": _now(),
            "usuario":         self._usuario,
        })

    # ── Configuracion ─────────────────────────────────────────────────────────

    def _leer_config_ocr(self) -> dict:
        """Lee configuracion OCR desde BD o config.json."""
        try:
            from utils.utilidades import load_app_config
            cfg = load_app_config()
            return {
                "motor_activo":    cfg.get("ocr_motor_activo") or cfg.get("ocr_provider") or "",
                "azure_endpoint":  cfg.get("azure_doc_intelligence_endpoint") or "",
                "azure_key":       cfg.get("azure_doc_intelligence_key") or "",
            }
        except Exception:
            return {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _respuesta_error(self, doc_id: Optional[str], mensaje: str) -> dict:
        return {
            "documento_id": doc_id,
            "factura_id":   None,
            "estado":       OcrDocumentState.ERROR.value,
            "resultado":    {},
            "errores":      [mensaje],
        }


# ── Utilidades ────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
