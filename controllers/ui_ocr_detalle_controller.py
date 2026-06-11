"""Controlador de la pantalla de detalle/revision de documentos OCR."""
from __future__ import annotations

from datetime import datetime

from services.terceros_empresa_fiscal_service import (
    ocr_tipo_to_proveedor,
    proveedor_tipo_to_ocr,
)
from utils.validaciones import normalizar_nif_cif
from services.terceros_ocr_service import TercerosOcrService

_TIPOS_TERCERO = {"proveedor", "acreedor", "cliente"}


class UIOcrDetalleController:

    def __init__(self, gestor, codigo: str, ejercicio: int, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._terceros_svc = TercerosOcrService()
        self._current_doc: dict | None = None

    # ── Carga ─────────────────────────────────────────────────────────────────

    def load_doc(self, doc_id: str):
        doc = self._gestor.get_factura_recibida_doc(doc_id)
        if not doc:
            self._view.show_error(
                "Gest2A3Eco", f"Documento no encontrado: {doc_id}"
            )
            return

        lineas_db = self._gestor.listar_ocr_lineas_doc(doc_id)
        if lineas_db:
            doc["lineas"] = lineas_db

        self._current_doc = doc
        self._view.populate(doc)

        path = str(doc.get("origen_path") or doc.get("pdf_path") or "").strip()
        if path:
            self._view.load_document(path)

        # Auto-buscar tercero si hay NIF y aun no esta vinculado
        if not doc.get("tercero_id"):
            nif = normalizar_nif_cif(doc.get("proveedor_nif") or "")
            if nif:
                tercero = self._terceros_svc.resolver_tercero(
                    self._gestor, nif,
                    doc.get("proveedor_nombre") or "",
                    self._codigo, self._ejercicio,
                )
                if tercero:
                    self._current_doc["tercero_id"] = tercero.get("id")
                    sub = (
                        tercero.get("subcuenta_proveedor")
                        or tercero.get("subcuenta_cliente")
                        or ""
                    )
                    self._view.set_tercero_info(
                        f"Tercero localizado: {tercero.get('nombre')} — subcuenta {sub}"
                    )
                    self._aplicar_configuracion_proveedor(tercero, force_missing_only=True)

    # ── Guardado ──────────────────────────────────────────────────────────────

    def guardar(self):
        if self._current_doc is None:
            return
        if not self._apply_form_safe():
            return
        self._persist()
        self._view.show_info("Gest2A3Eco", "Cambios guardados.")

    def guardar_silencioso(self):
        """Persiste sin dialogo (al navegar prev/next o al cerrar)."""
        if self._current_doc is None:
            return
        if not self._apply_form_safe():
            return
        self._persist()

    def _apply_form(self):
        form = self._view.get_form_data()
        for k, v in form.items():
            if k != "lineas":
                self._current_doc[k] = v
        self._current_doc["lineas"] = form["lineas"]
        self._current_doc["proveedor_tipo_operacion_iva"] = (
            self._current_doc.get("proveedor_tipo_operacion_iva")
            or ocr_tipo_to_proveedor(self._current_doc.get("tipo_operacion"))
        )

    def _apply_form_safe(self) -> bool:
        try:
            self._apply_form()
            return True
        except ValueError as exc:
            self._view.show_warning("Gest2A3Eco", str(exc))
            return False

    def _persist(self):
        lineas = self._current_doc.pop("lineas", [])
        self._gestor.upsert_factura_recibida_doc(self._current_doc)
        self._gestor.reemplazar_ocr_lineas_doc(self._current_doc["id"], lineas)
        self._current_doc["lineas"] = lineas

    # ── Acciones de estado ────────────────────────────────────────────────────

    def validar(self):
        if self._current_doc is None:
            return
        if not self._apply_form_safe():
            return
        errors = self._validate_para_contabilizar(self._current_doc)
        if errors:
            self._view.show_warning(
                "Gest2A3Eco",
                "Faltan datos obligatorios:\n- " + "\n- ".join(errors),
            )
            return

        nif = normalizar_nif_cif(self._current_doc.get("proveedor_nif") or "")
        tercero = self._terceros_svc.resolver_tercero(
            self._gestor,
            nif,
            self._current_doc.get("proveedor_nombre") or "",
            self._codigo,
            self._ejercicio,
        )
        self._current_doc["proveedor_nif"] = nif
        if tercero:
            self._current_doc["tercero_id"] = tercero.get("id")
            if not self._current_doc.get("proveedor_nombre"):
                self._current_doc["proveedor_nombre"] = tercero.get("nombre")
            self._aplicar_configuracion_proveedor(tercero, force_missing_only=True)

        self._current_doc["estado_ocr"] = (
            self._current_doc.get("estado_ocr") or "procesado"
        )
        self._current_doc["estado_validacion"] = "validada"
        self._current_doc["estado_contable"]   = "pendiente_contabilizar"
        self._current_doc["fecha_validacion"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._persist()
        self._view.populate(self._current_doc)
        self._view.show_info(
            "Gest2A3Eco", "Documento validado. Pasa a 'Pte. contabilizar'."
        )

    def enviar_a_error(self):
        if self._current_doc is None:
            return
        if not self._apply_form_safe():
            return
        self._current_doc["estado_ocr"]    = "error"
        self._current_doc["error_mensaje"] = "Enviado manualmente a errores."
        self._persist()
        self._view.populate(self._current_doc)
        self._view.show_info("Gest2A3Eco", "Documento enviado a Errores.")

    def enviar_pendiente_contabilizar(self):
        if self._current_doc is None:
            return
        if not self._apply_form_safe():
            return
        errors = self._validate_para_contabilizar(self._current_doc)
        if errors:
            self._view.show_warning(
                "Gest2A3Eco",
                "Faltan datos obligatorios:\n- " + "\n- ".join(errors),
            )
            return
        self._current_doc["estado_validacion"] = "validada"
        self._current_doc["estado_contable"]   = "pendiente_contabilizar"
        self._persist()
        self._view.populate(self._current_doc)
        self._view.show_info("Gest2A3Eco", "Documento enviado a 'Pte. contabilizar'.")

    # ── Terceros ──────────────────────────────────────────────────────────────

    def buscar_tercero(self):
        if self._current_doc is None:
            return
        form   = self._view.get_form_data()
        nif    = normalizar_nif_cif(form.get("proveedor_nif") or "")
        nombre = form.get("proveedor_nombre") or ""
        tercero = self._terceros_svc.resolver_tercero(
            self._gestor, nif, nombre, self._codigo, self._ejercicio
        )
        if not tercero:
            self._view.show_info(
                "Gest2A3Eco", "No se encontro ningun tercero con ese NIF/nombre."
            )
            return
        self._current_doc["tercero_id"] = tercero.get("id")
        # Rellenar nombre si el formulario esta vacio
        nombre_encontrado = tercero.get("nombre_legal") or tercero.get("nombre") or ""
        if nombre_encontrado and not form.get("proveedor_nombre"):
            self._current_doc["proveedor_nombre"] = nombre_encontrado
        sub = (
            tercero.get("subcuenta_proveedor")
            or tercero.get("subcuenta_cliente")
            or ""
        )
        self._view.set_tercero_info(
            f"Encontrado: {nombre_encontrado or nombre} — subcuenta {sub or '(sin asignar)'}"
        )
        self._aplicar_configuracion_proveedor(tercero, force_missing_only=True)

    def crear_tercero(self):
        if self._current_doc is None:
            return
        form   = self._view.get_form_data()
        nif    = normalizar_nif_cif(form.get("proveedor_nif") or "")
        nombre = form.get("proveedor_nombre") or ""

        if not nif:
            self._view.show_warning("Gest2A3Eco", "Introduce el NIF antes de crear el tercero.")
            return
        if not nombre:
            self._view.show_warning("Gest2A3Eco", "Introduce el nombre antes de crear el tercero.")
            return
        if self._terceros_svc.nif_ya_existe(self._gestor, nif):
            self._view.show_warning(
                "Gest2A3Eco",
                f"Ya existe un tercero con NIF {nif}.\n"
                "Usa 'Buscar tercero' para vincularlo.",
            )
            return

        # Proponer subcuenta antes de abrir el dialog (tipo proveedor por defecto)
        subcuenta_propuesta = self._terceros_svc.proponer_subcuenta(
            self._gestor, "proveedor", self._codigo, self._ejercicio
        )
        dlg_result = self._view.open_crear_tercero_dialog(
            nif=nif, nombre=nombre
        )
        if not dlg_result:
            return
        tipo = dlg_result.get("tipo") or "proveedor"
        subcuenta = dlg_result.get("subcuenta") or ""

        # Si el usuario no modifico la subcuenta propuesta, recalcular para el tipo elegido
        if not subcuenta or subcuenta == subcuenta_propuesta:
            subcuenta = self._terceros_svc.proponer_subcuenta(
                self._gestor, tipo, self._codigo, self._ejercicio
            )

        tercero = self._terceros_svc.crear_tercero(
            self._gestor,
            {"nif": nif, "nombre": nombre},
            subcuenta,
            tipo,
            self._codigo,
            self._ejercicio,
        )
        self._current_doc["tercero_id"] = tercero.get("id")
        self._view.set_tercero_info(f"Creado: {nombre} — subcuenta {subcuenta}")
        self._aplicar_configuracion_proveedor(tercero, force_missing_only=False)
        self._view.show_info(
            "Gest2A3Eco", f"Tercero '{nombre}' ({tipo}) creado con subcuenta {subcuenta}."
        )

    # ── Validacion ────────────────────────────────────────────────────────────

    def _validate_para_contabilizar(self, doc: dict) -> list[str]:
        errors = []
        if not str(doc.get("proveedor_nif") or "").strip():
            errors.append("NIF del proveedor no detectado.")
        if not str(doc.get("numero_factura") or "").strip():
            errors.append("Numero de factura no detectado.")
        if not str(doc.get("fecha_factura") or "").strip():
            errors.append("Fecha de factura no detectada.")
        if (doc.get("total") or 0.0) == 0.0:
            errors.append("Total 0,00: revisa los importes.")
        return errors

    def _aplicar_configuracion_proveedor(self, tercero: dict, *, force_missing_only: bool):
        cuenta_proveedor = str(
            tercero.get("subcuenta_proveedor")
            or tercero.get("subcuenta_cliente")
            or tercero.get("subcuenta")
            or ""
        ).strip()
        cuenta_gasto = str(
            tercero.get("subcuenta_gasto")
            or tercero.get("cuenta_gasto_predeterminada_id")
            or ""
        ).strip()
        has_config = self._tercero_tiene_configuracion_proveedor(tercero)
        warning = (
            ""
            if has_config
            else "La subcuenta seleccionada no tiene configuracion fiscal/contable completa. Puede continuar, pero algunos campos deberan revisarse manualmente."
        )
        self._view.set_subcuenta_warning(warning)
        if force_missing_only:
            if cuenta_proveedor and not self._current_doc.get("cuenta_proveedor"):
                self._current_doc["cuenta_proveedor"] = cuenta_proveedor
                self._view.set_cuenta_proveedor(cuenta_proveedor)
            if has_config and cuenta_gasto and not self._current_doc.get("cuenta_gasto"):
                self._current_doc["cuenta_gasto"] = cuenta_gasto
                self._view.set_cuenta_gasto(cuenta_gasto)
            if has_config and not self._current_doc.get("proveedor_tipo_operacion_iva"):
                tipo_iva = str(tercero.get("proveedor_tipo_operacion_iva") or "").strip()
                iva_deducible = int(bool(tercero.get("proveedor_iva_deducible")))
                pct_deduccion = float(tercero.get("proveedor_porcentaje_deduccion_iva") or 0.0)
                self._current_doc["proveedor_tipo_operacion_iva"] = tipo_iva
                self._view.set_proveedor_fiscal_config(
                    tipo_iva,
                    iva_deducible,
                    pct_deduccion,
                    proveedor_tipo_to_ocr(tipo_iva),
                )
            return
        if cuenta_proveedor:
            self._current_doc["cuenta_proveedor"] = cuenta_proveedor
            self._view.set_cuenta_proveedor(cuenta_proveedor)
        if cuenta_gasto:
            self._current_doc["cuenta_gasto"] = cuenta_gasto
            self._view.set_cuenta_gasto(cuenta_gasto)
        if not has_config:
            return
        tipo_iva = str(tercero.get("proveedor_tipo_operacion_iva") or "").strip()
        iva_deducible = int(bool(tercero.get("proveedor_iva_deducible")))
        pct_deduccion = float(tercero.get("proveedor_porcentaje_deduccion_iva") or 0.0)
        self._current_doc["proveedor_tipo_operacion_iva"] = tipo_iva
        self._current_doc["proveedor_iva_deducible"] = iva_deducible
        self._current_doc["proveedor_porcentaje_deduccion_iva"] = pct_deduccion
        self._current_doc["tipo_operacion"] = proveedor_tipo_to_ocr(tipo_iva)
        self._view.set_proveedor_fiscal_config(
            tipo_iva,
            iva_deducible,
            pct_deduccion,
            self._current_doc["tipo_operacion"],
        )

    def _tercero_tiene_configuracion_proveedor(self, tercero: dict) -> bool:
        keys = (
            "subcuenta_gasto",
            "cuenta_gasto_predeterminada_id",
            "proveedor_tipo_operacion_iva",
            "proveedor_intracomunitaria_clase",
            "proveedor_iva_deducible",
            "proveedor_porcentaje_deduccion_iva",
        )
        return any(tercero.get(k) not in (None, "") for k in keys)
