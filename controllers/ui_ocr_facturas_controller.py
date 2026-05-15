from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.validaciones import normalizar_nif_cif
from services.ocr_service import OCRService


class UIOcrFacturasController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._ocr = OCRService()
        self._selected_id = None

    def refresh(self, select_id: str | None = None, auto_select_first: bool = True):
        docs = self._gestor.listar_facturas_recibidas_docs(self._codigo, self._ejercicio)
        self._view.set_documents(docs)
        target = select_id or self._selected_id
        if target:
            self.select_document(target)
        elif docs and auto_select_first:
            self.select_document(str(docs[0].get("id")))
        else:
            self._selected_id = None
            self._view.clear_form()

    def cargar_documentos(self):
        paths = self._view.ask_open_document_paths()
        if not paths:
            return
        created_ids = []
        skipped = []
        for raw_path in paths:
            path = Path(str(raw_path or "").strip())
            if not path.exists() or path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                skipped.append(str(path))
                continue
            doc_id = self._gestor.upsert_factura_recibida_doc(self._build_pending_doc(path))
            created_ids.append(doc_id)
        if created_ids:
            self.refresh(select_id=created_ids[-1])
        else:
            self.refresh()
        msg = f"Documentos cargados: {len(created_ids)}"
        if skipped:
            msg += "\n\nOmitidos por tipo no soportado o ruta invalida:\n- " + "\n- ".join(skipped[:8])
        if created_ids:
            self._view.show_info("Gest2A3Eco", msg)
        else:
            self._view.show_warning("Gest2A3Eco", msg)

    def procesar_seleccionados(self):
        selected_ids = self._view.get_selected_document_ids()
        if not selected_ids:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios documentos.")
            return
        procesados = 0
        con_error = 0
        pendientes = 0
        last_ok_id = None
        errores = []
        for doc_id in selected_ids:
            doc = self._gestor.get_factura_recibida_doc(doc_id)
            if not doc:
                con_error += 1
                errores.append(f"{doc_id}: documento no encontrado")
                continue
            try:
                updated = self._procesar_doc(doc)
                self._gestor.upsert_factura_recibida_doc(updated)
                last_ok_id = doc_id
                if str(updated.get("estado_ocr") or "").strip().lower() == "procesado":
                    procesados += 1
                else:
                    pendientes += 1
            except Exception as exc:
                con_error += 1
                errores.append(f"{Path(str(doc.get('origen_path') or doc_id)).name}: {exc}")
                self._gestor.upsert_factura_recibida_doc(self._mark_doc_error(doc, str(exc)))
        self.refresh(select_id=last_ok_id or self._selected_id)
        msg = (
            f"Procesados: {procesados}\n"
            f"Con error: {con_error}\n"
            f"Pendientes: {pendientes}"
        )
        if errores:
            msg += "\n\nErrores:\n- " + "\n- ".join(errores[:8])
        if con_error:
            self._view.show_warning("Gest2A3Eco", msg)
        else:
            self._view.show_info("Gest2A3Eco", msg)

    def select_document(self, doc_id: str):
        doc = self._gestor.get_factura_recibida_doc(doc_id)
        if not doc:
            return
        self._selected_id = str(doc_id)
        self._view.load_document(doc)

    def guardar_actual(self):
        updates = self._view.get_form_data()
        if not updates:
            self._view.show_warning("Gest2A3Eco", "No hay documento seleccionado.")
            return
        payload = self._gestor.get_factura_recibida_doc(self._selected_id) or {}
        payload.update(updates)
        payload["id"] = self._selected_id
        payload["codigo_empresa"] = self._codigo
        payload["ejercicio"] = self._ejercicio
        payload["proveedor_nif"] = normalizar_nif_cif(payload.get("proveedor_nif"))
        tercero = self._resolve_tercero(payload.get("proveedor_nif"))
        if tercero:
            payload["tercero_id"] = tercero.get("id")
            if not payload.get("proveedor_nombre"):
                payload["proveedor_nombre"] = tercero.get("nombre")
        payload["estado_validacion"] = payload.get("estado_validacion") or "pendiente"
        self._gestor.upsert_factura_recibida_doc(payload)
        self.refresh(select_id=self._selected_id)
        self._view.show_info("Gest2A3Eco", "Documento guardado.")

    def marcar_validada(self):
        doc = self._gestor.get_factura_recibida_doc(self._selected_id)
        if not doc:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        doc["estado_validacion"] = "validada"
        self._gestor.upsert_factura_recibida_doc(doc)
        self.refresh(select_id=self._selected_id)
        self._view.show_info("Gest2A3Eco", "Documento marcado como validado.")

    def eliminar_actual(self):
        if not self._selected_id:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar el documento OCR seleccionado?"):
            return
        self._gestor.eliminar_factura_recibida_doc(self._selected_id)
        self._selected_id = None
        self.refresh()

    def _resolve_tercero(self, nif: str | None):
        normalized = normalizar_nif_cif(nif or "")
        if not normalized:
            return None
        for tercero in self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio):
            if normalizar_nif_cif(tercero.get("nif") or "") == normalized:
                return tercero
        for tercero in self._gestor.listar_terceros():
            if normalizar_nif_cif(tercero.get("nif") or "") == normalized:
                return tercero
        return None

    def _build_pending_doc(self, path: Path) -> dict:
        is_pdf = path.suffix.lower() == ".pdf"
        return {
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": None,
            "origen_path": str(path),
            "pdf_path": str(path) if is_pdf else "",
            "texto_ocr": "",
            "estado_ocr": "pendiente",
            "estado_validacion": "pendiente",
            "estado_contable": "",
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
                "backend": "",
                "avisos": [],
                "nombre_fichero": path.name,
                "extension": path.suffix.lower(),
            },
        }

    def _procesar_doc(self, doc: dict) -> dict:
        source_path = str(doc.get("origen_path") or doc.get("pdf_path") or "").strip()
        if not source_path:
            raise ValueError("El documento no tiene ruta de origen.")
        result = self._ocr.procesar_factura(source_path)
        tercero = self._resolve_tercero(result.get("proveedor_nif"))
        payload = dict(doc)
        payload.update(
            {
                "tercero_id": (tercero or {}).get("id"),
                "origen_path": result.get("origen_path") or source_path,
                "pdf_path": result.get("pdf_path") or payload.get("pdf_path") or "",
                "texto_ocr": result.get("texto_ocr") or "",
                "estado_ocr": result.get("estado_ocr") or "pendiente",
                "estado_validacion": result.get("estado_validacion") or payload.get("estado_validacion") or "pendiente",
                "estado_contable": result.get("estado_contable") or payload.get("estado_contable") or "",
                "proveedor_nif": normalizar_nif_cif(result.get("proveedor_nif")),
                "proveedor_nombre": (tercero or {}).get("nombre") or result.get("proveedor_nombre") or payload.get("proveedor_nombre") or "",
                "numero_factura": result.get("numero_factura") or payload.get("numero_factura") or "",
                "fecha_factura": result.get("fecha_factura") or payload.get("fecha_factura") or "",
                "fecha_operacion": result.get("fecha_operacion") or payload.get("fecha_operacion") or "",
                "fecha_asiento": result.get("fecha_asiento") or payload.get("fecha_asiento") or "",
                "descripcion": result.get("descripcion") or payload.get("descripcion") or "",
                "moneda_codigo": result.get("moneda_codigo") or payload.get("moneda_codigo") or "EUR",
                "base_imponible": result.get("base_imponible") or 0.0,
                "cuota_iva": result.get("cuota_iva") or 0.0,
                "cuota_recargo": result.get("cuota_recargo") or 0.0,
                "cuota_retencion": result.get("cuota_retencion") or 0.0,
                "total": result.get("total") or 0.0,
                "cuenta_gasto": (tercero or {}).get("subcuenta_gasto") or payload.get("cuenta_gasto") or "",
                "cuenta_iva": payload.get("cuenta_iva") or "",
                "cuenta_proveedor": (tercero or {}).get("subcuenta_proveedor") or payload.get("cuenta_proveedor") or "",
                "confianza_ocr": result.get("confianza_ocr") or 0.0,
                "lineas": result.get("lineas") or [],
                "datos_extra": {
                    "backend": result.get("backend"),
                    "avisos": result.get("avisos") or [],
                    "ultimo_procesado_at": datetime.now().isoformat(timespec="seconds"),
                    "nombre_fichero": Path(source_path).name,
                    "extension": Path(source_path).suffix.lower(),
                },
            }
        )
        return payload

    def _mark_doc_error(self, doc: dict, error_message: str) -> dict:
        payload = dict(doc)
        extra = dict(payload.get("datos_extra") or {})
        avisos = list(extra.get("avisos") or [])
        avisos.append(error_message)
        extra["avisos"] = avisos[-20:]
        extra["ultimo_error"] = error_message
        extra["ultimo_procesado_at"] = datetime.now().isoformat(timespec="seconds")
        payload["estado_ocr"] = "error"
        payload["datos_extra"] = extra
        return payload
