from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path

from utils.validaciones import normalizar_nif_cif
from services.ocr_recibidas_service import generate_suenlace_for_docs, mark_docs_as_generated
from services.ocr_service import OCRService
from services.terceros_ocr_service import TercerosOcrService


class UIOcrFacturasController:
    def __init__(self, gestor, codigo: str, ejercicio: int, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._ocr = OCRService()
        self._terceros_svc = TercerosOcrService()
        self._ocr_queue: queue.Queue = queue.Queue()
        self._ocr_thread: threading.Thread | None = None

    # ── Refresco de bandejas ──────────────────────────────────────────────────

    def refresh_all(self):
        for estado, _ in [
            ("procesando",              None),
            ("error",                   None),
            ("pendiente_revision",      None),
            ("pendiente_contabilizar",  None),
            ("contabilizada",           None),
        ]:
            self.refresh_bandeja(estado)

    def refresh_bandeja(self, estado: str):
        docs = self._gestor.listar_facturas_recibidas_docs_filtrado(
            self._codigo, self._ejercicio, estado
        )
        self._view.set_bandeja_docs(estado, docs)

    # ── Carga y procesamiento OCR ─────────────────────────────────────────────

    def cargar_documentos(self):
        paths = self._view.ask_open_document_paths()
        if not paths:
            return

        pending_docs: list[dict] = []
        skipped: list[str] = []
        for raw in paths:
            path = Path(str(raw or "").strip())
            if not path.exists() or path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                skipped.append(path.name)
                continue
            doc = self._build_pending_doc(path)
            doc_id = self._gestor.upsert_factura_recibida_doc(doc)
            doc["id"] = doc_id
            pending_docs.append(doc)

        if skipped:
            self._view.show_warning(
                "Gest2A3Eco",
                f"Omitidos ({len(skipped)} ficheros no soportados):\n- " + "\n- ".join(skipped[:8]),
            )
        if not pending_docs:
            return

        self.refresh_bandeja("procesando")
        self._view.switch_to_bandeja("procesando")
        self._start_ocr_thread(pending_docs)

    def reintentar_seleccionados(self, estado: str):
        ids = self._view.get_selected_ids(estado)
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios documentos.")
            return
        docs = []
        for doc_id in ids:
            doc = self._gestor.get_factura_recibida_doc(doc_id)
            if not doc:
                continue
            doc["estado_ocr"] = "procesando"
            doc["error_mensaje"] = ""
            self._gestor.upsert_factura_recibida_doc(doc)
            docs.append(doc)
        if docs:
            self.refresh_all()
            self._view.switch_to_bandeja("procesando")
            self._start_ocr_thread(docs)

    # ── Acciones sobre documentos ─────────────────────────────────────────────

    def marcar_validada_seleccionado(self, estado: str):
        ids = self._view.get_selected_ids(estado)
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        if len(ids) > 1:
            self._view.show_warning("Gest2A3Eco", "Selecciona solo un documento para validar.")
            return
        doc = self._gestor.get_factura_recibida_doc(ids[0])
        if not doc:
            return
        errors = self._validate_para_contabilizar(doc)
        if errors:
            self._view.show_warning(
                "Gest2A3Eco",
                "No se puede validar. Faltan datos obligatorios:\n- " + "\n- ".join(errors)
                + "\n\nAbre el documento para completar los datos.",
            )
            return
        nif = normalizar_nif_cif(doc.get("proveedor_nif"))
        tercero = self._resolve_tercero(nif, doc.get("proveedor_nombre") or "")
        doc["proveedor_nif"] = nif
        if tercero:
            doc["tercero_id"] = tercero.get("id")
            if not doc.get("proveedor_nombre"):
                doc["proveedor_nombre"] = tercero.get("nombre")
        doc["estado_ocr"] = doc.get("estado_ocr") or "procesado"
        doc["estado_validacion"] = "validada"
        doc["estado_contable"] = "pendiente_contabilizar"
        doc["fecha_validacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._gestor.upsert_factura_recibida_doc(doc)
        self.refresh_all()
        self._view.show_info("Gest2A3Eco", "Documento validado. Pasa a 'Pendiente de contabilizar'.")

    def enviar_a_error_seleccionado(self, estado: str):
        ids = self._view.get_selected_ids(estado)
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios documentos.")
            return
        for doc_id in ids:
            doc = self._gestor.get_factura_recibida_doc(doc_id)
            if not doc:
                continue
            doc["estado_ocr"] = "error"
            doc["error_mensaje"] = "Enviado manualmente a errores."
            self._gestor.upsert_factura_recibida_doc(doc)
        self.refresh_all()

    def eliminar_seleccionado(self, estado: str):
        ids = self._view.get_selected_ids(estado)
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios documentos.")
            return
        n = len(ids)
        if not self._view.ask_yes_no(
            "Gest2A3Eco", f"Eliminar {n} documento{'s' if n > 1 else ''}? Esta accion no se puede deshacer."
        ):
            return
        for doc_id in ids:
            self._gestor.eliminar_factura_recibida_doc(doc_id)
        self.refresh_all()

    def abrir_documento_seleccionado(self, estado: str):
        ids = self._view.get_selected_ids(estado)
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return

        # Obtener todos los IDs de la bandeja para navegacion prev/next
        all_docs = self._gestor.listar_facturas_recibidas_docs_filtrado(
            self._codigo, self._ejercicio, estado
        )
        all_ids = [str(d["id"]) for d in all_docs]

        from views.ui_ocr_detalle import UIOcrDetalle
        UIOcrDetalle(
            master=self._view,
            gestor=self._gestor,
            codigo_empresa=self._codigo,
            ejercicio=self._ejercicio,
            doc_ids=all_ids,
            current_id=str(ids[0]),
            on_close=self.refresh_all,
        )

    # ── Generacion suenlace ───────────────────────────────────────────────────

    def generar_suenlace_seleccionadas(self):
        ids = self._view.get_selected_ids("pendiente_contabilizar")
        if not ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios documentos.")
            return

        docs_ok: list[dict] = []
        omitidos: list[str] = []
        for doc_id in ids:
            doc = self._gestor.get_factura_recibida_doc(doc_id)
            if not doc:
                omitidos.append(f"{doc_id}: no encontrado")
                continue
            errors = self._validate_para_contabilizar(doc)
            if errors:
                label = doc.get("numero_factura") or doc_id
                omitidos.append(f"{label}: " + "; ".join(errors))
                continue
            docs_ok.append(doc)

        if not docs_ok:
            self._view.show_warning(
                "Gest2A3Eco",
                "Ninguno de los documentos seleccionados es valido para generar suenlace."
                + (("\n\nOmitidos:\n- " + "\n- ".join(omitidos[:8])) if omitidos else ""),
            )
            return

        regs = generate_suenlace_for_docs(self._gestor, self._codigo, self._ejercicio, docs_ok)
        if not regs:
            self._view.show_warning("Gest2A3Eco", "No se generaron registros para los documentos seleccionados.")
            return

        save_path = self._view.ask_save_path(f"{self._codigo}.dat")
        if not save_path:
            return

        lote = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(regs)

        for doc in docs_ok:
            doc["lote_generacion"] = lote
        mark_docs_as_generated(self._gestor, docs_ok, estado_contable="contabilizada")
        self.refresh_all()

        msg = f"Fichero generado:\n{save_path}\n\nContabilizados: {len(docs_ok)}"
        if omitidos:
            msg += "\n\nOmitidos:\n- " + "\n- ".join(omitidos[:8])
            self._view.show_warning("Gest2A3Eco", msg)
        else:
            self._view.show_info("Gest2A3Eco", msg)

    # ── OCR en segundo plano ──────────────────────────────────────────────────

    def _start_ocr_thread(self, docs: list[dict]):
        n = len(docs)
        self._view.set_ocr_running(True, f"Procesando OCR — {n} documento{'s' if n > 1 else ''}...")
        self._ocr_thread = threading.Thread(
            target=self._ocr_worker,
            args=(list(docs),),
            daemon=True,
        )
        self._ocr_thread.start()
        self._view.after(250, self._poll_ocr_queue)

    def _ocr_worker(self, docs: list[dict]):
        for doc in docs:
            source = str(doc.get("origen_path") or doc.get("pdf_path") or "").strip()
            if not source:
                error_doc = dict(doc)
                error_doc["estado_ocr"] = "error"
                error_doc["error_mensaje"] = "Sin ruta de origen."
                self._ocr_queue.put(error_doc)
                continue
            try:
                result = self._ocr.procesar_factura(source)
                updated = self._merge_ocr_result(doc, result)
                self._ocr_queue.put(updated)
            except Exception as exc:
                error_doc = dict(doc)
                error_doc["estado_ocr"] = "error"
                error_doc["error_mensaje"] = str(exc)[:240]
                self._ocr_queue.put(error_doc)

    def _poll_ocr_queue(self):
        changed = False
        try:
            while True:
                updated_doc = self._ocr_queue.get_nowait()
                self._gestor.upsert_factura_recibida_doc(updated_doc)
                changed = True
        except queue.Empty:
            pass

        if changed:
            self.refresh_all()

        if self._ocr_thread and self._ocr_thread.is_alive():
            self._view.after(300, self._poll_ocr_queue)
        else:
            # Vaciamos restos que llegaron justo al terminar
            try:
                while True:
                    updated_doc = self._ocr_queue.get_nowait()
                    self._gestor.upsert_factura_recibida_doc(updated_doc)
                    changed = True
            except queue.Empty:
                pass
            if changed:
                self.refresh_all()
            self._view.set_ocr_running(False)
            self._ocr_thread = None

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _build_pending_doc(self, path: Path) -> dict:
        is_pdf = path.suffix.lower() == ".pdf"
        return {
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": None,
            "origen_path": str(path),
            "pdf_path": str(path) if is_pdf else "",
            "texto_ocr": "",
            "estado_ocr": "procesando",
            "estado_validacion": "pendiente",
            "estado_contable": "",
            "tipo_documento": "factura_recibida",
            "tipo_operacion": "interior",
            "proveedor_nif": "",
            "proveedor_nombre": "",
            "numero_factura": "",
            "fecha_factura": "",
            "fecha_operacion": "",
            "fecha_asiento": "",
            "descripcion": path.stem,
            "moneda_codigo": "EUR",
            "base_imponible": 0.0,
            "cuota_iva": 0.0,
            "cuota_recargo": 0.0,
            "cuota_retencion": 0.0,
            "total": 0.0,
            "cuenta_gasto": "",
            "cuenta_iva": "",
            "cuenta_proveedor": "",
            "confianza_ocr": 0.0,
            "lineas": [],
            "datos_extra": {
                "nombre_fichero": path.name,
                "extension": path.suffix.lower(),
            },
        }

    def _merge_ocr_result(self, doc: dict, result: dict) -> dict:
        """Combina el doc original con el resultado OCR. Solo escribe desde hilo OCR — sin SQLite."""
        updated = dict(doc)
        texto = result.get("texto_ocr") or ""
        # El parser devuelve 'bandeja': "error" si faltan datos criticos,
        # "pendiente_revision" si el texto es valido y completo.
        bandeja = result.get("bandeja") or ("pendiente_revision" if texto.strip() else "error")

        if bandeja == "error":
            updated["estado_ocr"] = "error"
            updated["error_mensaje"] = (
                result.get("error_mensaje")
                or (result.get("avisos") or ["Error en el procesamiento OCR."])[0]
            )
        else:
            updated["estado_ocr"] = "procesado"
            updated["estado_validacion"] = "pendiente"
            updated["error_mensaje"] = ""

        updated["texto_ocr"]       = texto
        updated["confianza_ocr"]   = result.get("confianza_ocr") or 0.0
        updated["fecha_ocr"]       = datetime.now().strftime("%Y-%m-%d %H:%M")
        updated["proveedor_nif"]   = normalizar_nif_cif(result.get("proveedor_nif")) or doc.get("proveedor_nif") or ""
        updated["proveedor_nombre"]= result.get("proveedor_nombre") or doc.get("proveedor_nombre") or ""
        updated["numero_factura"]  = result.get("numero_factura") or doc.get("numero_factura") or ""
        updated["fecha_factura"]   = result.get("fecha_factura") or doc.get("fecha_factura") or ""
        updated["fecha_operacion"] = result.get("fecha_operacion") or doc.get("fecha_operacion") or ""
        updated["fecha_asiento"]   = result.get("fecha_asiento") or doc.get("fecha_asiento") or ""
        updated["descripcion"]     = result.get("descripcion") or doc.get("descripcion") or ""
        updated["base_imponible"]  = result.get("base_imponible") or 0.0
        updated["cuota_iva"]       = result.get("cuota_iva") or 0.0
        updated["cuota_recargo"]   = result.get("cuota_recargo") or 0.0
        updated["cuota_retencion"] = result.get("cuota_retencion") or 0.0
        updated["total"]           = result.get("total") or 0.0
        # Lineas fiscales multi-tramo devueltas por el parser (Fase 4)
        lineas_parser = result.get("lineas") or []
        updated["lineas"] = lineas_parser if lineas_parser else doc.get("lineas") or []
        updated["datos_extra"] = {
            "backend":         result.get("backend"),
            "source_type":     result.get("source_type"),
            "avisos":          result.get("avisos") or [],
            "nombre_fichero":  Path(str(doc.get("origen_path") or "")).name,
            "extension":       Path(str(doc.get("origen_path") or "")).suffix.lower(),
        }
        return updated

    def _resolve_tercero(self, nif: str | None, nombre: str = "") -> dict | None:
        return self._terceros_svc.resolver_tercero(
            self._gestor, nif or "", nombre, self._codigo, self._ejercicio
        )

    def _validate_para_contabilizar(self, doc: dict) -> list[str]:
        errors = []
        if not str(doc.get("proveedor_nif") or "").strip():
            errors.append("NIF del proveedor/cliente no detectado.")
        if not str(doc.get("numero_factura") or "").strip():
            errors.append("Numero de factura no detectado.")
        if not str(doc.get("fecha_factura") or "").strip():
            errors.append("Fecha de factura no detectada.")
        total = doc.get("total") or 0.0
        if total == 0.0:
            errors.append("Total 0,00: revisa los importes.")
        return errors
