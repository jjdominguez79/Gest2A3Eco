from __future__ import annotations

from procesos.facturas_recibidas import generar_asiento_recibida
from services.ocr_recibidas_service import (
    doc_to_row,
    generate_suenlace_for_docs,
    mark_docs_as_generated,
    resolve_recibidas_template,
)
from services.documentos_recibidos_a3_service import preparar_documentos_para_suenlace
from services.estado_facturas_recibidas import CONTABILIZADA, EXPORTADA_A3
from services.import_a3_empresa import leer_numero_asiento_desde_a3


class UIContabilidadController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._selected_id = None

    def refresh(self, select_id: str | None = None):
        refresh_async = getattr(self._view, "refresh_async", None)
        if callable(refresh_async):
            refresh_async(select_id=select_id)
            return
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
        asiento = self._gestor.get_asiento_contable_por_documento(doc_id)
        self.load_document_data(doc_id, doc, asiento)

    def load_document_data(self, doc_id: str, doc: dict | None, asiento: dict | None):
        """Aplica en la vista los datos ya obtenidos por la carga asincrona."""
        if not doc:
            return
        self._selected_id = str(doc_id)
        self._view.load_document(doc, asiento)

    def generar_asiento(self):
        seleccionados = self._selected_received_ids()
        if not seleccionados:
            self._view.show_warning("Gest2A3Eco", "Selecciona al menos un documento.")
            return
        plantilla = self._resolve_plantilla()
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        generados, errores = [], []
        for documento_id in seleccionados:
            doc = self._gestor.get_factura_recibida_doc(documento_id)
            if not doc:
                continue
            try:
                self._generar_asiento_documento(doc, plantilla, empresa)
                generados.append(str(doc.get("numero_factura") or documento_id))
            except Exception as exc:
                errores.append(f"{doc.get('numero_factura') or documento_id}: {exc}")
        self.refresh(select_id=self._selected_id)
        if errores:
            self._view.show_warning(
                "Gest2A3Eco",
                f"{len(generados)} asiento(s) generado(s).\n"
                f"Errores ({len(errores)}):\n" + "\n".join(errores),
            )
        else:
            self._view.show_info(
                "Gest2A3Eco",
                f"{len(generados)} asiento(s) generado(s) y guardado(s).",
            )

    def _generar_asiento_documento(
        self, doc: dict, plantilla: dict, empresa: dict,
    ) -> None:
        self._completar_cuentas_desde_tercero(doc)
        lineas = generar_asiento_recibida(
            doc_to_row(doc), self._configuracion_asiento(doc, plantilla, empresa),
        )
        payload_lineas = [
            {
                "fecha": linea.fecha,
                "subcuenta": linea.subcuenta,
                "dh": linea.dh,
                "importe": float(linea.importe),
                "concepto": linea.concepto,
            }
            for linea in lineas
        ]
        numero_asiento = str(doc.get("numero_asiento") or "").strip()
        fecha_asiento = doc.get("fecha_asiento") or doc.get("fecha_factura")
        self._gestor.upsert_asiento_contable({
            "documento_id": doc.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "fecha_asiento": fecha_asiento,
            "numero_asiento": numero_asiento,
            "descripcion": doc.get("descripcion")
            or f"Factura {doc.get('numero_factura') or ''}".strip(),
            "estado": "borrador",
            "total_debe": self._total_por_naturaleza(payload_lineas, "D"),
            "total_haber": self._total_por_naturaleza(payload_lineas, "H"),
            "lineas": payload_lineas,
        })
        # Generar el borrador no equivale a contabilizar la factura.
        doc["numero_asiento"] = numero_asiento
        doc["fecha_asiento"] = fecha_asiento
        self._gestor.upsert_factura_recibida_doc(doc)

    def _completar_cuentas_desde_tercero(self, doc: dict) -> None:
        """Recupera subcuentas maestras ausentes en proyecciones OCR antiguas."""
        tercero_id = str(doc.get("tercero_id") or "").strip()
        if not tercero_id:
            return
        relacion = self._gestor.get_tercero_empresa(
            self._codigo, tercero_id, self._ejercicio,
        ) or {}
        cambiado = False
        for campo, campo_relacion in (
            ("cuenta_proveedor", "subcuenta_proveedor"),
            ("cuenta_gasto", "subcuenta_gasto"),
        ):
            valor = str(relacion.get(campo_relacion) or "").strip()
            if not str(doc.get(campo) or "").strip() and valor:
                doc[campo] = valor
                cambiado = True
        if cambiado:
            self._gestor.upsert_factura_recibida_doc(doc)

    @staticmethod
    def _configuracion_asiento(doc: dict, plantilla: dict, empresa: dict) -> dict:
        return {
            "digitos_plan": int(empresa.get("digitos_plan") or 8),
            "cuenta_proveedor_prefijo": (
                plantilla.get("cuenta_proveedor_prefijo") or "400"
            ),
            "cuenta_gasto_por_defecto": (
                doc.get("cuenta_gasto")
                or plantilla.get("cuenta_gasto_por_defecto")
                or "62900000"
            ),
            "cuenta_iva_soportado_defecto": (
                doc.get("cuenta_iva")
                or plantilla.get("cuenta_iva_soportado_defecto")
                or "47200000"
            ),
            "cuenta_proveedor_por_defecto": doc.get("cuenta_proveedor") or "",
            "cuenta_suplidos": doc.get("cuenta_suplidos") or "55509999",
        }

    @staticmethod
    def _total_por_naturaleza(lineas: list[dict], naturaleza: str) -> float:
        return round(
            sum(linea["importe"] for linea in lineas if linea["dh"] == naturaleza),
            2,
        )

    def editar_asiento(self):
        doc = self._current_doc()
        if not doc:
            self._view.show_warning("Gest2A3Eco", "Selecciona un documento.")
            return
        asiento = self._gestor.get_asiento_contable_por_documento(doc.get("id"))
        if not asiento:
            self._view.show_warning(
                "Gest2A3Eco", "Genera primero el asiento para poder editarlo.",
            )
            return
        catalogo = self._gestor.listar_maestro_subcuentas_empresa(
            self._codigo, activo=None,
        ) or []
        self._view.edit_document_asiento(doc, asiento, catalogo)

    def guardar_asiento_editado(self, doc: dict, asiento: dict, lineas: list[dict]):
        total_debe = self._total_por_naturaleza(lineas, "D")
        total_haber = self._total_por_naturaleza(lineas, "H")
        self._gestor.upsert_asiento_contable({
            "documento_id": doc.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "fecha_asiento": asiento.get("fecha_asiento") or doc.get("fecha_asiento"),
            "numero_asiento": asiento.get("numero_asiento") or doc.get("numero_asiento"),
            "descripcion": asiento.get("descripcion") or doc.get("descripcion"),
            "estado": asiento.get("estado") or "borrador",
            "total_debe": total_debe,
            "total_haber": total_haber,
            "lineas": lineas,
        })
        # Mantener las cuentas propuestas en el documento coherentes con la
        # edicion para las siguientes regeneraciones del asiento.
        for linea in lineas:
            cuenta = str(linea.get("subcuenta") or "")
            if linea.get("dh") == "H" and cuenta.startswith(("400", "410")):
                doc["cuenta_proveedor"] = cuenta
            elif linea.get("dh") == "D" and cuenta.startswith("472"):
                doc["cuenta_iva"] = cuenta
            elif linea.get("dh") == "D":
                doc["cuenta_gasto"] = cuenta
        self._gestor.upsert_factura_recibida_doc(doc)
        self.refresh(select_id=self._selected_id)
        self._view.show_info("Gest2A3Eco", "Asiento actualizado.")

    def exportar_suenlace(self):
        seleccionados = self._view.get_selected_received_ids()
        if not seleccionados:
            self._view.show_warning("Gest2A3Eco", "Selecciona al menos un documento.")
            return
        docs_a_exportar = []
        ya_contabilizadas = []
        for documento_id in seleccionados:
            doc = self._gestor.get_factura_recibida_doc(documento_id)
            if not doc:
                continue
            estado = str(doc.get("estado_contable") or "").strip().lower()
            if bool(doc.get("generada")) or estado in {EXPORTADA_A3, CONTABILIZADA}:
                ya_contabilizadas.append(str(doc.get("numero_factura") or documento_id))
            else:
                docs_a_exportar.append(doc)
        if ya_contabilizadas:
            nombres = ", ".join(ya_contabilizadas[:5])
            if len(ya_contabilizadas) > 5:
                nombres += f" y {len(ya_contabilizadas) - 5} mas"
            self._view.show_warning(
                "Gest2A3Eco",
                f"Las siguientes facturas ya tienen suenlace generado y se omitiran:\n{nombres}\n\n"
                "Captura primero el numero de asiento desde A3 para verificar si ya estan contabilizadas.",
            )
        if not docs_a_exportar:
            return
        try:
            docs_preparados = preparar_documentos_para_suenlace(
                self._gestor, self._codigo, self._ejercicio, docs_a_exportar,
            )
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", f"No se pudo preparar el PDF para A3ECO:\n{exc}")
            return
        regs = generate_suenlace_for_docs(self._gestor, self._codigo, self._ejercicio, docs_preparados)
        if not regs:
            self._view.show_warning("Gest2A3Eco", "No se generaron registros para los documentos seleccionados.")
            return
        save_path = self._view.ask_save_path(f"{self._codigo}.dat")
        if not save_path:
            return
        # SUENLACE es un fichero binario de registros fijos. Escribirlo como
        # texto puede alterar saltos de linea o longitudes y A3 lo interpreta
        # entonces como registros desplazados ("tipo incorrecto").
        try:
            # Algunas versiones de A3ECO no admiten el registro 6 de
            # trazabilidad en el enlace de recibidas (lo reportan como
            # "tipo de registro incorrecto" y muestran R00000001/cuenta 0).
            # La trazabilidad queda guardada en la BD y no es necesaria para
            # importar el asiento, por lo que se excluye del fichero enviado.
            registros_a3 = [reg for reg in regs if str(reg)[14:15] != "6"]
            if not registros_a3:
                self._view.show_error("Gest2A3Eco", "No hay registros compatibles para importar en A3ECO.")
                return
            bloques = [str(reg).encode("latin-1") for reg in registros_a3]
        except UnicodeEncodeError as exc:
            self._view.show_error("Gest2A3Eco", f"El asiento contiene caracteres no validos para A3ECO:\n{exc}")
            return
        longitudes = {len(bloque) for bloque in bloques}
        if not longitudes.issubset({256, 512}):
            self._view.show_error(
                "Gest2A3Eco",
                "El suenlace generado contiene registros con longitud invalida "
                f"({sorted(longitudes)} bytes; deben ser 256 o 512).",
            )
            return
        with open(save_path, "wb") as f:
            f.write(b"".join(bloques))
        for doc in docs_preparados:
            doc["numero_asiento"] = doc.get("numero_asiento") or ""
            doc["fecha_asiento"] = doc.get("fecha_asiento") or doc.get("fecha_factura") or ""
            self._gestor.upsert_factura_recibida_doc(doc)
        mark_docs_as_generated(
            self._gestor, docs_preparados, estado_contable=EXPORTADA_A3,
        )
        self._selected_id = None
        self.refresh(select_id="__clear_selection__")
        self._view.clear_preview()
        self._view.show_info(
            "Gest2A3Eco",
            f"{len(docs_preparados)} factura(s) exportadas.\nFichero generado:\n{save_path}",
        )

    def devolver_a_ocr(self):
        """Retira de Contabilidad y devuelve a Errores OCR para corregir."""
        seleccionados = self._view.get_selected_received_ids()
        if not seleccionados:
            self._view.show_warning(
                "Gest2A3Eco", "Selecciona al menos una factura para devolver.",
            )
            return
        permitidas, bloqueadas, enlazadas = [], [], []
        for documento_id in seleccionados:
            doc = self._gestor.get_factura_recibida_doc(documento_id) or {}
            if str(doc.get("numero_asiento") or "").strip():
                bloqueadas.append(documento_id)
                continue
            permitidas.append(documento_id)
            if doc.get("generada") or doc.get("estado_contable") in {
                EXPORTADA_A3, CONTABILIZADA,
            }:
                enlazadas.append(documento_id)
        if bloqueadas:
            self._view.show_warning(
                "Gest2A3Eco",
                f"{len(bloqueadas)} factura(s) tienen asiento confirmado y no pueden devolverse.",
            )
        if not permitidas:
            return
        if enlazadas and not self._view.ask_yes_no(
            "Anular suenlace y devolver",
            f"{len(enlazadas)} factura(s) ya tienen suenlace generado.\n"
            "Se anulara esa marca y volveran a Errores OCR.\n\n¿Continuar?",
        ):
            return
        motivo = self._view.ask_return_reason(
            "Motivo de devolucion",
            "Indica el motivo. Se mostrara al revisar de nuevo la factura en OCR.",
        )
        if motivo is None:
            return
        resultado = self._gestor.devolver_facturas_recibidas_a_ocr(
            self._codigo, permitidas,
            motivo.strip() or "Devuelta desde Contabilidad para corregirla.",
        )
        self._selected_id = None
        self.refresh(select_id="__clear_selection__")
        self._view.clear_preview()
        self._view.show_info(
            "Gest2A3Eco",
            f"{resultado.get('ocr', 0)} factura(s) devueltas a Errores OCR.",
        )

    def capturar_numero_asiento_desde_a3(self):
        seleccionados = self._view.get_selected_received_ids()
        if not seleccionados:
            self._view.show_warning(
                "Gest2A3Eco", "Selecciona al menos una factura exportada a A3."
            )
            return
        actualizadas, sin_asiento = [], []
        codigo_a3 = self._codigo_empresa_a3()
        for documento_id in seleccionados:
            doc = self._gestor.get_factura_recibida_doc(documento_id)
            if not doc or doc.get("estado_contable") not in {
                EXPORTADA_A3, CONTABILIZADA,
            }:
                sin_asiento.append(
                    str((doc or {}).get("numero_factura") or documento_id)
                )
                continue
            numero = str(doc.get("numero_factura") or "").strip()[:10]
            descripcion = str(
                doc.get("descripcion") or f"Su Fra Nº. {numero}"
            ).strip()
            mes = self._month_from_date(
                doc.get("fecha_asiento") or doc.get("fecha_factura")
            )
            asiento = leer_numero_asiento_desde_a3(
                codigo_a3, int(self._ejercicio), numero, descripcion, mes=mes,
            )
            if asiento and self._gestor.actualizar_numero_asiento_factura_recibida(
                self._codigo, documento_id, asiento,
            ):
                actualizadas.append(f"{numero} -> asiento {asiento}")
            else:
                sin_asiento.append(numero or documento_id)
        self.refresh(select_id=seleccionados[0] if actualizadas else None)
        partes = []
        if actualizadas:
            partes.append("Asientos capturados:\n" + "\n".join(actualizadas))
        if sin_asiento:
            partes.append(
                "No encontradas en A3ECO (importa primero el suenlace):\n"
                + "\n".join(sin_asiento)
            )
        self._view.show_info("Gest2A3Eco", "\n\n".join(partes) or "Sin cambios.")

    def _codigo_empresa_a3(self) -> str:
        digits = "".join(ch for ch in str(self._codigo or "") if ch.isdigit())
        return f"E{(digits.zfill(5) if digits else '00000')[:5]}"

    @staticmethod
    def _month_from_date(value) -> int | None:
        from datetime import datetime
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).month
            except ValueError:
                continue
        return None

    def _current_doc(self):
        if not self._selected_id:
            return None
        return self._gestor.get_factura_recibida_doc(self._selected_id)

    def _resolve_plantilla(self):
        return resolve_recibidas_template(self._gestor, self._codigo, self._ejercicio)

    def _selected_received_ids(self) -> list[str]:
        getter = getattr(self._view, "get_selected_received_ids", None)
        if callable(getter):
            return getter()
        return [self._selected_id] if self._selected_id else []
