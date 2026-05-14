from __future__ import annotations

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

    def refresh(self, select_id: str | None = None):
        docs = self._gestor.listar_facturas_recibidas_docs(self._codigo, self._ejercicio)
        self._view.set_documents(docs)
        target = select_id or self._selected_id
        if target:
            self.select_document(target)
        elif docs:
            self.select_document(str(docs[0].get("id")))
        else:
            self._selected_id = None
            self._view.clear_form()

    def cargar_documento(self):
        path = self._view.ask_open_document_path()
        if not path:
            return
        result = self._ocr.procesar_factura(path)
        tercero = self._resolve_tercero(result.get("proveedor_nif"))
        doc = {
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": (tercero or {}).get("id"),
            "origen_path": result.get("origen_path"),
            "pdf_path": result.get("pdf_path"),
            "texto_ocr": result.get("texto_ocr"),
            "estado_ocr": result.get("estado_ocr"),
            "estado_validacion": result.get("estado_validacion"),
            "estado_contable": result.get("estado_contable"),
            "proveedor_nif": normalizar_nif_cif(result.get("proveedor_nif")),
            "proveedor_nombre": (tercero or {}).get("nombre") or result.get("proveedor_nombre"),
            "numero_factura": result.get("numero_factura"),
            "fecha_factura": result.get("fecha_factura"),
            "fecha_operacion": result.get("fecha_operacion"),
            "fecha_asiento": result.get("fecha_asiento"),
            "descripcion": result.get("descripcion"),
            "moneda_codigo": result.get("moneda_codigo") or "EUR",
            "base_imponible": result.get("base_imponible") or 0.0,
            "cuota_iva": result.get("cuota_iva") or 0.0,
            "cuota_recargo": result.get("cuota_recargo") or 0.0,
            "cuota_retencion": result.get("cuota_retencion") or 0.0,
            "total": result.get("total") or 0.0,
            "cuenta_gasto": (tercero or {}).get("subcuenta_gasto") or "",
            "cuenta_iva": "",
            "cuenta_proveedor": (tercero or {}).get("subcuenta_proveedor") or "",
            "confianza_ocr": result.get("confianza_ocr") or 0.0,
            "lineas": result.get("lineas") or [],
            "datos_extra": {"backend": result.get("backend"), "avisos": result.get("avisos") or []},
        }
        doc_id = self._gestor.upsert_factura_recibida_doc(doc)
        avisos = result.get("avisos") or []
        self.refresh(select_id=doc_id)
        if avisos:
            self._view.show_warning("Gest2A3Eco", "Documento importado con avisos:\n- " + "\n- ".join(avisos[:8]))
        else:
            self._view.show_info("Gest2A3Eco", "Documento OCR importado.")

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
