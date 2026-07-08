from __future__ import annotations

from controllers.ui_facturas_emitidas_controller import FacturasEmitidasController


class _ViewAdapter:
    """Adapts UIContabilidad's emitidas tab to FacturasEmitidasController's view API."""

    def __init__(self, outer_ctrl: "UIContabilidadEmitidasController", view):
        self._outer_ctrl = outer_ctrl
        self._view = view

    def get_marked_ids(self):
        return self._view.get_selected_emitida_ids()

    def get_selected_ids(self):
        return self._view.get_selected_emitida_ids()

    def show_warning(self, title, msg):
        self._view.show_warning(title, msg)

    def ask_yes_no(self, title, msg):
        return self._view.ask_yes_no(title, msg)

    def ask_save_dat_path(self, filename):
        return self._view.ask_save_dat_path(filename)

    def clear_marked_ids(self, ids):
        pass

    def show_info(self, title, msg):
        self._view.show_info(title, msg)

    def show_error(self, title, msg):
        self._view.show_error(title, msg)

    def refresh_facturas(self):
        self._outer_ctrl.refresh()

    def winfo_toplevel(self):
        try:
            return self._view.winfo_toplevel()
        except Exception:
            return None

    # Metodos de vista que FacturasEmitidasController.refresh_facturas necesita
    def set_facturas_series(self, series):
        pass

    def clear_facturas(self):
        pass

    def insert_factura_row(self, fac, total):
        pass

    def auto_sort_facturas(self):
        # Despues de que el controller interno refresca su cache, actualizar
        # el listado del modulo de contabilidad.
        self._outer_ctrl.refresh()

    def set_detalle_lineas(self, lineas):
        pass

    def get_facturas_year_filter(self):
        return None

    def get_facturas_serie_filter(self):
        return None

    def get_facturas_cliente_filter(self):
        return ""

    def get_facturas_estado_filter(self):
        return None


class UIContabilidadEmitidasController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        empresa_conf = gestor.get_empresa(codigo, ejercicio) or {}
        self._empresa_conf = empresa_conf
        adapter = _ViewAdapter(self, view)
        self._fac_ctrl = FacturasEmitidasController(
            gestor, codigo, ejercicio, empresa_conf, adapter, allow_all_years=False
        )

    def refresh(self):
        docs = self._gestor.listar_facturas_emitidas_en_contabilidad(self._codigo, self._ejercicio)
        self._view.set_emitidas(docs)

    def generar_suenlace(self):
        self._fac_ctrl.generar_suenlace()

    def quitar_de_contabilidad(self):
        """Quita las facturas seleccionadas del modulo de contabilidad.
        Solo permite quitar las que aun no tienen el suenlace generado."""
        sel = self._view.get_selected_emitida_ids()
        if not sel:
            self._view.show_warning(
                "Gest2A3Eco",
                "Selecciona al menos una factura para quitar del modulo de contabilidad.",
            )
            return
        # Separar pendientes y generadas
        docs_map = {str(d.get("id")): d for d in (self._view._emitidas_docs or [])}
        ya_generadas = [fid for fid in sel if (docs_map.get(fid) or {}).get("estado_contable") == "generado"]
        pendientes = [fid for fid in sel if fid not in ya_generadas]

        if ya_generadas and not pendientes:
            self._view.show_warning(
                "Gest2A3Eco",
                "Las facturas seleccionadas ya tienen el suenlace generado y no pueden quitarse.\n"
                "Solo se pueden quitar facturas en estado 'Pendiente'.",
            )
            return
        if ya_generadas:
            n = len(ya_generadas)
            self._view.show_warning(
                "Gest2A3Eco",
                f"{n} factura(s) ya tienen el suenlace generado y no se quitaran.\n"
                f"Se quitaran solo las {len(pendientes)} factura(s) en estado pendiente.",
            )
        if not pendientes:
            return
        removidas = self._gestor.quitar_facturas_emitidas_de_contabilidad(
            self._codigo, self._ejercicio, pendientes
        )
        self.refresh()
        self._view.show_info(
            "Gest2A3Eco",
            f"{removidas} factura(s) quitadas del modulo de contabilidad.\n"
            "Vuelven a aparecer como pendientes en el modulo de facturacion.",
        )

    def marcar_con_asiento_como_generadas(self):
        """Marca como 'generado' todas las facturas pendientes que ya tienen numero de asiento."""
        if not self._view.ask_yes_no(
            "Marcar como generadas",
            "Se van a marcar como 'Generado' todas las facturas pendientes\n"
            "que ya tienen numero de asiento registrado.\n\n"
            "¿Continuar?",
        ):
            return
        n = self._gestor.marcar_generadas_con_asiento(self._codigo, self._ejercicio)
        self.refresh()
        self._view.show_info(
            "Gest2A3Eco",
            f"{n} factura(s) marcadas como 'Generado'.",
        )

    def capturar_numero_asiento_desde_a3(self):
        """Delega en el controlador interno de facturas emitidas."""
        self._fac_ctrl.capturar_numero_asiento_desde_a3()

    def resetear_generadas(self):
        """Revierte el estado 'generado' a NULL de las facturas seleccionadas para poder regenerar el suenlace."""
        sel = self._view.get_selected_emitida_ids()
        if not sel:
            self._view.show_warning(
                "Gest2A3Eco",
                "Selecciona al menos una factura para resetear.",
            )
            return
        docs_map = {str(d.get("id")): d for d in (self._view._emitidas_docs or [])}
        generadas = [fid for fid in sel if (docs_map.get(fid) or {}).get("estado_contable") == "generado"]
        if not generadas:
            self._view.show_warning(
                "Gest2A3Eco",
                "Ninguna de las facturas seleccionadas tiene estado 'Generado'.",
            )
            return
        if not self._view.ask_yes_no(
            "Resetear estado",
            f"Se van a resetear {len(generadas)} factura(s) a 'No generado'.\n"
            "Esto permite volver a incluirlas en el modulo de contabilidad y regenerar el suenlace.\n\n"
            "¿Continuar?",
        ):
            return
        reseteadas = self._gestor.resetear_facturas_emitidas_generadas(
            self._codigo, self._ejercicio, generadas
        )
        self.refresh()
        self._view.show_info(
            "Gest2A3Eco",
            f"{reseteadas} factura(s) reseteadas a 'No generado'.",
        )

    def on_seleccionar(self, fac_id: str):
        """Calcula y muestra el asiento de la factura seleccionada en el panel derecho."""
        from views.ui_asiento_emitida_dialog import calcular_asiento_emitida

        fac = next(
            (d for d in (self._view._emitidas_docs or []) if str(d.get("id")) == fac_id),
            None,
        )
        if not fac:
            return

        ndig = int(self._empresa_conf.get("digitos_plan") or 8)
        plantilla = self._get_plantilla_para_factura(fac)
        lineas = calcular_asiento_emitida(fac, plantilla, ndig)

        # Enriquecer lineas con descripcion del maestro
        catalogo = self._get_catalogo_subcuentas()
        nombres = {str(r.get("subcuenta") or ""): str(r.get("nombre_subcuenta") or "") for r in catalogo}
        for ln in lineas:
            ln["descripcion"] = nombres.get(str(ln.get("subcuenta") or ""), "")

        serie = str(fac.get("serie") or "").strip()
        num = str(fac.get("numero") or "").strip()
        nombre = str(fac.get("nombre") or "").strip()
        fecha = str(fac.get("fecha_asiento") or fac.get("fecha_expedicion") or "").strip()
        label = f"Fra. {serie}{num}  {fecha}  —  {nombre}"
        self._view.set_asiento_emitida(lineas, label)

    def editar_asiento_seleccionada(self):
        """Abre el dialogo de edicion completa del asiento para la factura seleccionada."""
        from views.ui_asiento_emitida_dialog import AsientoEmitidaDialog

        sel = self._view.get_selected_emitida_ids()
        if not sel:
            self._view.show_warning("Gest2A3Eco", "Selecciona una factura.")
            return
        fac_id = sel[0]
        fac = next(
            (d for d in (self._view._emitidas_docs or []) if str(d.get("id")) == fac_id),
            None,
        )
        if not fac:
            return

        ndig = int(self._empresa_conf.get("digitos_plan") or 8)
        plantilla = self._get_plantilla_para_factura(fac)

        parent_win = None
        try:
            parent_win = self._view.winfo_toplevel()
        except Exception:
            pass

        def _on_save(fac_mod):
            # Actualizar doc en cache y refrescar asiento
            for i, d in enumerate(self._view._emitidas_docs or []):
                if str(d.get("id")) == fac_id:
                    self._view._emitidas_docs[i] = fac_mod
                    break
            self.on_seleccionar(fac_id)

        AsientoEmitidaDialog(
            parent_win,
            fac=fac,
            plantilla=plantilla,
            gestor=self._gestor,
            codigo_empresa=self._codigo,
            ndig=ndig,
            on_save=_on_save,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _get_plantilla_para_factura(self, fac: dict) -> dict:
        try:
            return self._fac_ctrl._plantilla_emitidas_for_factura(fac, {}, set())
        except Exception:
            return {}

    def _get_catalogo_subcuentas(self) -> list[dict]:
        try:
            return self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None) or []
        except Exception:
            return []
