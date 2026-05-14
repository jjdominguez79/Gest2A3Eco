from __future__ import annotations

from datetime import datetime

from procesos.facturas_recibidas import generar_asiento_recibida, generar_recibidas_suenlace


class UIContabilidadController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
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
            self._view.clear_preview()

    def select_document(self, doc_id: str):
        doc = self._gestor.get_factura_recibida_doc(doc_id)
        if not doc:
            return
        self._selected_id = str(doc_id)
        asiento = self._gestor.get_asiento_contable_por_documento(doc_id)
        self._view.load_document(doc, asiento)

    def generar_asiento(self):
        doc = self._current_doc()
        if not doc:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        plantilla = self._resolve_plantilla()
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        row = self._doc_to_row(doc)
        conf = {
            "digitos_plan": int(empresa.get("digitos_plan") or 8),
            "cuenta_proveedor_prefijo": plantilla.get("cuenta_proveedor_prefijo") or "400",
            "cuenta_gasto_por_defecto": doc.get("cuenta_gasto") or plantilla.get("cuenta_gasto_por_defecto") or "62900000",
            "cuenta_iva_soportado_defecto": doc.get("cuenta_iva") or plantilla.get("cuenta_iva_soportado_defecto") or "47200000",
            "cuenta_proveedor_por_defecto": doc.get("cuenta_proveedor") or "",
        }
        lineas = generar_asiento_recibida(row, conf)
        payload_lineas = [
            {
                "fecha": ln.fecha,
                "subcuenta": ln.subcuenta,
                "dh": ln.dh,
                "importe": float(ln.importe),
                "concepto": ln.concepto,
            }
            for ln in lineas
        ]
        total_debe = round(sum(x["importe"] for x in payload_lineas if x["dh"] == "D"), 2)
        total_haber = round(sum(x["importe"] for x in payload_lineas if x["dh"] == "H"), 2)
        numero_asiento = str(doc.get("numero_asiento") or self._view.get_numero_asiento() or "").strip()
        fecha_asiento = self._view.get_fecha_asiento() or doc.get("fecha_asiento")
        self._gestor.upsert_asiento_contable(
            {
                "documento_id": doc.get("id"),
                "codigo_empresa": self._codigo,
                "ejercicio": self._ejercicio,
                "fecha_asiento": fecha_asiento,
                "numero_asiento": numero_asiento,
                "descripcion": doc.get("descripcion") or f"Factura {doc.get('numero_factura') or ''}".strip(),
                "estado": "borrador",
                "total_debe": total_debe,
                "total_haber": total_haber,
                "lineas": payload_lineas,
            }
        )
        doc["estado_contable"] = "contabilizada"
        doc["numero_asiento"] = numero_asiento
        doc["fecha_asiento"] = fecha_asiento
        self._gestor.upsert_factura_recibida_doc(doc)
        self.refresh(select_id=self._selected_id)
        self._view.show_info("Gest2A3Eco", "Asiento generado y guardado.")

    def exportar_suenlace(self):
        doc = self._current_doc()
        if not doc:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        plantilla = self._resolve_plantilla()
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)
        terceros_empresa = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        terceros_by_nif = {}
        for tercero in terceros_empresa:
            nif = str(tercero.get("nif") or "").strip().upper()
            if nif:
                terceros_by_nif[nif] = tercero
        row = self._doc_to_row(doc)
        rows = [row]
        regs = generar_recibidas_suenlace(
            rows,
            plantilla,
            str(self._codigo),
            ndig,
            ejercicio=self._ejercicio,
            terceros_by_nif=terceros_by_nif,
        )
        if not regs:
            self._view.show_warning("Gest2A3Eco", "No se generaron registros para el documento seleccionado.")
            return
        save_path = self._view.ask_save_path(f"{self._codigo}.dat")
        if not save_path:
            return
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(regs)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        doc["generada"] = True
        doc["fecha_generacion"] = now
        doc["estado_contable"] = "enlazada"
        doc["numero_asiento"] = self._view.get_numero_asiento() or doc.get("numero_asiento")
        doc["fecha_asiento"] = self._view.get_fecha_asiento() or doc.get("fecha_asiento")
        self._gestor.upsert_factura_recibida_doc(doc)
        asiento = self._gestor.get_asiento_contable_por_documento(doc.get("id"))
        if asiento:
            asiento["estado"] = "exportado"
            asiento["numero_asiento"] = doc.get("numero_asiento")
            asiento["fecha_asiento"] = doc.get("fecha_asiento")
            self._gestor.upsert_asiento_contable(asiento)
        self.refresh(select_id=self._selected_id)
        self._view.show_info("Gest2A3Eco", f"Fichero generado:\n{save_path}")

    def _current_doc(self):
        if not self._selected_id:
            return None
        return self._gestor.get_factura_recibida_doc(self._selected_id)

    def _resolve_plantilla(self):
        plantillas = self._gestor.listar_recibidas(self._codigo, self._ejercicio)
        if plantillas:
            return dict(plantillas[0])
        return {
            "nombre": "OCR",
            "cuenta_proveedor_prefijo": "400",
            "cuenta_gasto_por_defecto": "62900000",
            "cuenta_iva_soportado_defecto": "47200000",
            "subtipo_recibidas": "01",
        }

    def _doc_to_row(self, doc: dict):
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
