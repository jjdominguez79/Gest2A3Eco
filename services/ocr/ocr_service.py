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
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from services.ocr.types import OcrInvoiceResult, OcrDocumentState
from utils.utilidades import get_default_received_documents_dir

logger = logging.getLogger(__name__)

# Umbral de caracteres para considerar texto suficiente
_MIN_TEXT_CHARS = 50


class OcrService:
    """
    Orquestador OCR con persistencia en las tablas documentos_ocr y
    facturas_recibidas_ocr o facturas_emitidas_ocr.

    Parametros:
      gestor     — instancia del gestor principal de datos
      empresa_id — codigo de empresa (ej: 'E00001')
      ejercicio  — ejercicio fiscal (ej: 2024)
      usuario    — nombre de usuario (para auditoría)
    """

    def __init__(
        self,
        gestor,
        empresa_id: str,
        ejercicio: int,
        usuario: str = "",
        tipo_documento: str = "factura_recibida",
        fecha_contable: str | None = None,
    ):
        self._gestor    = gestor
        self._empresa   = empresa_id
        self._ejercicio = ejercicio
        self._usuario   = usuario
        if tipo_documento not in {"factura_recibida", "factura_emitida"}:
            raise ValueError(f"Tipo de documento OCR no admitido: {tipo_documento}")
        self._tipo_documento = tipo_documento
        self._fecha_contable = str(fecha_contable or "").strip()
        self._motores   = self._construir_cadena_motores()

    # ── Punto de entrada publico ──────────────────────────────────────────────

    def procesar_archivo(self, file_path: str, progress_callback=None) -> dict:
        """
        Procesa un fichero PDF o imagen.

        Devuelve dict con:
          documento_id    — ID del registro en documentos_ocr
          factura_id      — ID del registro en facturas_recibidas_ocr (None si error)
          estado          — OcrDocumentState (str)
          resultado       — OcrInvoiceResult serializado como dict
          errores         — lista de errores
        """
        source_path = Path(file_path)
        if not source_path.exists():
            return self._respuesta_error(None, f"Fichero no encontrado: {file_path}")

        # 1. Hash para detectar duplicados
        hash_archivo = _sha256(source_path)

        # 2. Comprobar duplicado
        doc_dup = self._gestor.buscar_documento_ocr_por_hash(self._empresa, hash_archivo)
        if doc_dup:
            tipo_anterior = str(doc_dup.get("tipo_documento") or "factura_recibida")
            if tipo_anterior != self._tipo_documento:
                estado_anterior = str(doc_dup.get("estado") or "")
                if estado_anterior not in {
                    OcrDocumentState.ERROR.value,
                    OcrDocumentState.PENDIENTE_REVISION.value,
                    OcrDocumentState.DUPLICADO.value,
                }:
                    return self._respuesta_error(
                        str(doc_dup.get("id") or ""),
                        "El documento ya existe con otra clasificacion y esta "
                        f"en estado '{estado_anterior}'. No se ha cambiado automaticamente.",
                    )
                # Una importacion de prueba clasificada al reves puede corregirse
                # mientras aun no haya entrado en Contabilidad.
                for tabla in ("facturas_recibidas_ocr", "facturas_emitidas_ocr"):
                    self._gestor.conn.execute(
                        f"DELETE FROM {tabla} WHERE documento_id=?",
                        (str(doc_dup["id"]),),
                    )
                self._gestor.conn.commit()
                payload_dup = dict(doc_dup)
                payload_dup["tipo_documento"] = self._tipo_documento
                payload_dup["estado"] = OcrDocumentState.PROCESANDO.value
                payload_dup["error_ocr"] = ""
                self._gestor.upsert_documento_ocr(payload_dup)
                self._notificar_progreso(progress_callback, payload_dup)
                return self.reprocesar_documento(
                    str(doc_dup["id"]), progress_callback=progress_callback,
                )
            # Recupera documentos antiguos que apuntaban al Escritorio de un
            # puesto: la nueva seleccion pasa a ser la copia compartida.
            ruta_existente = Path(str(doc_dup.get("ruta_original") or ""))
            if not ruta_existente.is_file():
                try:
                    payload_dup = dict(doc_dup)
                    payload_dup["ruta_original"] = str(
                        self._archivar_en_repositorio_compartido(source_path)
                    )
                    self._gestor.upsert_documento_ocr(payload_dup)
                except Exception as exc:
                    logger.warning("[OcrService] No se pudo recuperar la copia compartida: %s", exc)
            logger.info("[OcrService] Duplicado detectado: %s", source_path.name)
            return {
                "documento_id": doc_dup["id"],
                "factura_id":   None,
                "estado":       OcrDocumentState.DUPLICADO.value,
                "resultado":    {},
                "errores":      [f"Documento duplicado (ya existe: {doc_dup.get('nombre_archivo')})"],
            }

        # 3. Copiar antes de OCR al repositorio comun. El procesamiento y la
        # ruta persistida no deben depender del ordenador que importo el PDF.
        try:
            path = self._archivar_en_repositorio_compartido(source_path)
        except Exception as exc:
            return self._respuesta_error(
                None, f"No se pudo archivar el documento en la ruta compartida: {exc}"
            )

        # 4. Crear registro inicial en documentos_ocr
        doc_id = str(uuid.uuid4())
        doc_payload = {
            "id":              doc_id,
            "empresa_id":      self._empresa,
            "ruta_original":   str(path),
            "nombre_archivo":  path.name,
            "hash_archivo":    hash_archivo,
            "tipo_documento":  self._tipo_documento,
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
        self._notificar_progreso(progress_callback, doc_payload)

        # 5. Intentar extraccion con cadena de motores
        result = self._ejecutar_motores(path)

        # 6. Actualizar documento con resultado
        doc_payload.update({
            "estado":          result.estado_sugerido.value,
            "fecha_procesado": _now(),
            "motor_ocr":       result.motor,
            "confianza_global": result.confianza,
            "error_ocr":       "; ".join(result.errores),
            "texto_extraido":  result.texto,
            "json_ocr":        result.to_json(),
        })
        self._gestor.upsert_documento_ocr(doc_payload)

        # 7. Guardar factura propuesta si hay datos minimos
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

    def reprocesar_documento(self, documento_id: str, progress_callback=None) -> dict:
        """Vuelve a analizar un documento existente sin tratarlo como duplicado."""
        doc = self._gestor.get_documento_ocr(documento_id)
        if not doc:
            return self._respuesta_error(documento_id, "Documento OCR no encontrado.")
        path = Path(str(doc.get("ruta_original") or ""))
        if not path.exists():
            return self._respuesta_error(documento_id, f"Fichero original no encontrado: {path}")

        doc_payload = dict(doc)
        doc_payload.update({"estado": OcrDocumentState.PROCESANDO.value, "error_ocr": ""})
        self._gestor.upsert_documento_ocr(doc_payload)
        self._notificar_progreso(progress_callback, doc_payload)
        result = self._ejecutar_motores(path)
        doc_payload.update({
            "estado": result.estado_sugerido.value,
            "fecha_procesado": _now(),
            "motor_ocr": result.motor,
            "confianza_global": result.confianza,
            "error_ocr": "; ".join(result.errores),
            "texto_extraido": result.texto,
            "json_ocr": result.to_json(),
        })
        self._gestor.upsert_documento_ocr(doc_payload)

        # La propuesta anterior y sus lineas se eliminan por cascada antes de
        # guardar la nueva. Asi nunca se acumulan IVAs de intentos previos.
        tipo = doc.get("tipo_documento") or "factura_recibida"
        tabla_ocr = (
            "facturas_emitidas_ocr"
            if tipo == "factura_emitida"
            else "facturas_recibidas_ocr"
        )
        self._gestor.conn.execute(
            f"DELETE FROM {tabla_ocr} WHERE documento_id=?", (str(documento_id),)
        )
        self._gestor.conn.commit()
        self._tipo_documento = tipo
        factura_id = self._guardar_factura(str(documento_id), result) if (
            result.proveedor_nif or result.numero_factura
        ) else None
        return {
            "documento_id": str(documento_id),
            "factura_id": factura_id,
            "estado": result.estado_sugerido.value,
            "resultado": result.to_dict(),
            "errores": result.errores,
        }

    @staticmethod
    def _notificar_progreso(callback, documento: dict) -> None:
        if not callback:
            return
        try:
            callback(dict(documento))
        except Exception as exc:
            logger.warning("[OcrService] No se pudo notificar el progreso: %s", exc)

    def _archivar_en_repositorio_compartido(self, source: Path) -> Path:
        """Devuelve la copia definitiva del OCR en el repositorio compartido."""
        root = get_default_received_documents_dir()
        try:
            # Un documento que ya procede del archivo compartido no se copia
            # otra vez (por ejemplo, los adjuntos de correo o Gestion Documental).
            source.relative_to(root)
            return source
        except ValueError:
            pass

        digits = "".join(ch for ch in str(self._empresa) if ch.isdigit())
        empresa = f"E{digits.zfill(5)[:5]}"
        subdir = (
            "Facturas_emitidas"
            if getattr(self, "_tipo_documento", "factura_recibida") == "factura_emitida"
            else "Facturas_recibidas"
        )
        destination_dir = root / empresa / str(self._ejercicio) / subdir
        destination_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source.name).strip(". ") or "Documento"
        destination = destination_dir / safe_name
        index = 2
        while destination.exists() and _sha256(destination) != _sha256(source):
            destination = destination_dir / f"{Path(safe_name).stem}_{index}{Path(safe_name).suffix}"
            index += 1
        if not destination.exists():
            shutil.copy2(source, destination)
        return destination

    # ── Cadena de motores ─────────────────────────────────────────────────────

    def _construir_cadena_motores(self):
        """Construye la lista ordenada de motores disponibles."""
        motores = []

        # El OCR estructurado se ejecuta exclusivamente en el backend. El
        # escritorio solo conoce su URL y el WorkstationToken; endpoint, clave
        # y modelo de Azure son configuracion privada del servidor.
        try:
            cfg = self._leer_config_ocr()
            api_url = cfg.get("integrations_api_url", "")
            api_key = cfg.get("backend_api_key", "")
            if api_url:
                from services.ocr.engines.backend_ocr_engine import BackendOcrEngine
                engine = BackendOcrEngine(base_url=api_url, api_key=api_key)
                if engine.disponible():
                    motores.append(engine)
        except Exception:
            pass

        # 1. PDF texto nativo (siempre disponible si el motor esta instalado)
        try:
            from services.ocr.engines.pdf_text_engine import PdfTextEngine
            e = PdfTextEngine()
            if e.disponible():
                motores.append(e)
        except Exception:
            pass

        # 2. Tesseract local (si disponible)
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

        diagnosticos = []
        azure_prioritario = any(motor.nombre == "azure_backend" for motor in self._motores)
        for motor in self._motores:
            try:
                resultado = motor.extraer(path)
            except Exception as exc:
                logger.warning("[OcrService] Motor %s lanzo excepcion: %s", motor.nombre, exc)
                diagnosticos.append(f"{motor.nombre}: {exc}")
                continue

            if resultado.errores:
                diagnosticos.extend(f"{motor.nombre}: {error}" for error in resultado.errores)

            # No ocultar un fallo del backend usando silenciosamente texto
            # local: la configuracion debe corregirse en el servidor.
            if motor.nombre == "azure_backend" and azure_prioritario:
                resultado.raw_json = dict(resultado.raw_json or {})
                resultado.raw_json["diagnostico_motores"] = {
                    "cadena": [m.nombre for m in self._motores],
                    "motor_elegido": "azure_backend",
                    "diagnosticos_previos": diagnosticos,
                }
                return resultado

            if (
                (resultado.texto and len(resultado.texto.strip()) >= _MIN_TEXT_CHARS)
                or (resultado.proveedor_nif and resultado.numero_factura)
            ):
                # Si el backend fallo y se uso la lectura local como respaldo, no
                # ocultar el motivo: el usuario necesita poder corregir la
                # configuracion en vez de confiar en datos heurísticos.
                if diagnosticos and motor.nombre != "azure_backend":
                    resultado.errores = list(dict.fromkeys(diagnosticos + resultado.errores))
                resultado.raw_json = dict(resultado.raw_json or {})
                resultado.raw_json["diagnostico_motores"] = {
                    "cadena": [m.nombre for m in self._motores],
                    "motor_elegido": motor.nombre,
                    "diagnosticos_previos": diagnosticos,
                }
                return resultado

            # Motor no extrajo texto util: guardar como fallback y continuar
            ultimo_resultado = resultado

        # Ningun motor extrajo texto suficiente
        if not self._motores:
            ext = path.suffix.lower()
            if ext == ".pdf":
                ultimo_resultado.errores = [
                    "El PDF no tiene texto embebido. Comprueba el acceso al backend OCR "
                    "o configura Tesseract para PDFs escaneados."
                ]
            else:
                ultimo_resultado.errores = [
                    "La imagen requiere un motor OCR local (Tesseract) o externo (Azure)."
                ]

        if diagnosticos:
            ultimo_resultado.errores = list(dict.fromkeys(diagnosticos + ultimo_resultado.errores))
        return ultimo_resultado

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _guardar_factura(self, doc_id: str, result: OcrInvoiceResult) -> str:
        """Guarda la factura propuesta en la tabla OCR correspondiente. Devuelve el ID."""
        factura_id = str(uuid.uuid4())
        if self._tipo_documento == "factura_emitida":
            payload = {
                "id":              factura_id,
                "documento_id":    doc_id,
                "empresa_id":      self._empresa,
                "cliente_id":      None,
                "nif_cliente":     result.cliente_nif,
                "nombre_cliente":  result.cliente_nombre,
                "numero_factura":  result.numero_factura,
                "fecha_factura":   result.fecha_factura,
                "fecha_operacion": result.fecha_factura,
                "fecha_vencimiento": result.fecha_vencimiento,
                "fecha_contable": self._fecha_contable or result.fecha_factura,
                "total_factura":   result.total,
                "base_total":      result.base_total,
                "iva_total":       result.iva_total,
                "retencion_total": result.retencion_total,
                "estado_validacion": "pendiente",
                "observaciones":   "; ".join(
                    result.errores
                    + ([] if result.cliente_nif else ["NIF del cliente no detectado."])
                ),
            }
            self._gestor.upsert_factura_emitida_ocr(payload)
            for linea in result.bases_iva:
                self._gestor.upsert_linea_iva_emitida_ocr({
                    "factura_id":   factura_id,
                    "tipo_iva":     linea.tipo_iva,
                    "base":         linea.base,
                    "cuota_iva":    linea.cuota_iva,
                    "tipo_recargo": linea.tipo_recargo,
                    "cuota_recargo": linea.cuota_recargo,
                    "cuenta_ingreso": "",
                    "es_suplido":   0,
                    "tipo_operacion": "01",
                })
            for ret in result.retenciones:
                self._gestor.upsert_retencion_emitida_ocr({
                    "factura_id":        factura_id,
                    "base_retencion":    ret.base_retencion,
                    "tipo_retencion":    ret.tipo_retencion,
                    "importe_retencion": ret.importe_retencion,
                    "clase_retencion":   ret.clase_retencion,
                })
        else:
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
                "fecha_contable": self._fecha_contable or result.fecha_factura,
                "total_factura":   result.total,
                "base_total":      result.base_total,
                "iva_total":       result.iva_total,
                "retencion_total": result.retencion_total,
                "estado_validacion": "pendiente",
                "observaciones":   "; ".join(result.errores) if result.errores else "",
            }
            self._gestor.upsert_factura_recibida_ocr(payload)
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
        """Lee la URL y credencial necesarias para acceder al backend OCR.

        La autenticacion del escritorio frente al backend usa EXCLUSIVAMENTE
        WorkstationToken. Las claves legacy (integrations_api_key, dgt_api_key)
        ya no se aceptan.
        """
        try:
            import os
            from utils.utilidades import load_app_config
            from utils.credential_store import get_workstation_token
            cfg = load_app_config()
            api_url = cfg.get("integrations_api_url") or ""
            return {
                "integrations_api_url": api_url,
                "backend_api_key": (
                    get_workstation_token()
                    or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
                ),
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
