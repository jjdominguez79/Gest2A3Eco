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
        source_path = Path(file_path)
        if not source_path.exists():
            return self._respuesta_error(None, f"Fichero no encontrado: {file_path}")

        # 1. Hash para detectar duplicados
        hash_archivo = _sha256(source_path)

        # 2. Comprobar duplicado
        doc_dup = self._gestor.buscar_documento_ocr_por_hash(self._empresa, hash_archivo)
        if doc_dup:
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

    def reprocesar_documento(self, documento_id: str) -> dict:
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
        self._gestor.conn.execute(
            "DELETE FROM facturas_recibidas_ocr WHERE documento_id=?", (str(documento_id),)
        )
        self._gestor.conn.commit()
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
        destination_dir = root / empresa / str(self._ejercicio) / "Facturas_recibidas"
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

        # Azure se ejecuta primero cuando se configura expresamente: su modelo
        # prebuilt-invoice entrega campos estructurados y evita depender de
        # expresiones regulares sobre el texto local.
        try:
            cfg = self._leer_config_ocr()
            if cfg.get("motor_activo") == "azure":
                from services.ocr.engines.azure_invoice_engine import AzureInvoiceEngine
                engine = AzureInvoiceEngine(
                    endpoint=cfg.get("azure_endpoint", ""),
                    api_key=cfg.get("azure_key", ""),
                    model_id=cfg.get("azure_model_id", ""),
                )
                if engine.disponible():
                    motores.append(engine)
        except Exception:
            pass

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
            if cfg.get("motor_activo") == "azure" and not any(m.nombre == "azure" for m in motores):
                from services.ocr.engines.azure_invoice_engine import AzureInvoiceEngine
                e = AzureInvoiceEngine(
                    endpoint=cfg.get("azure_endpoint", ""),
                    api_key=cfg.get("azure_key", ""),
                    model_id=cfg.get("azure_model_id", ""),
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

        diagnosticos = []
        azure_prioritario = any(motor.nombre == "azure" for motor in self._motores)
        for motor in self._motores:
            try:
                resultado = motor.extraer(path)
            except Exception as exc:
                logger.warning("[OcrService] Motor %s lanzo excepcion: %s", motor.nombre, exc)
                diagnosticos.append(f"{motor.nombre}: {exc}")
                continue

            if resultado.errores:
                diagnosticos.extend(f"{motor.nombre}: {error}" for error in resultado.errores)

            # Si el usuario ha seleccionado Azure, no ocultar un fallo del
            # modelo personalizado usando silenciosamente PDF/texto. La
            # aplicacion debe mostrar el error para que se pueda corregir el
            # endpoint, la clave o el ID del modelo.
            if motor.nombre == "azure" and azure_prioritario:
                resultado.raw_json = dict(resultado.raw_json or {})
                resultado.raw_json["diagnostico_motores"] = {
                    "cadena": [m.nombre for m in self._motores],
                    "motor_elegido": "azure",
                    "diagnosticos_previos": diagnosticos,
                }
                return resultado

            if (
                (resultado.texto and len(resultado.texto.strip()) >= _MIN_TEXT_CHARS)
                or (resultado.proveedor_nif and resultado.numero_factura)
            ):
                # Si Azure fallo y se uso la lectura local como respaldo, no
                # ocultar el motivo: el usuario necesita poder corregir la
                # configuracion en vez de confiar en datos heurísticos.
                if diagnosticos and motor.nombre != "azure":
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
                    "El PDF no tiene texto embebido. Configura Tesseract o Azure para PDFs escaneados."
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
                "motor_activo":    cfg.get("ocr_motor_activo") or "",
                "azure_endpoint":  cfg.get("azure_doc_intelligence_endpoint") or "",
                "azure_key":       cfg.get("azure_doc_intelligence_key") or "",
                "azure_model_id":  cfg.get("azure_doc_intelligence_model_id") or "",
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
