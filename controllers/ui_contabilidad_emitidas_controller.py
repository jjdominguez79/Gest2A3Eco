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
        self._empresa_conf = None
        self._adapter = _ViewAdapter(self, view)
        self._fac_ctrl = None

    def _facturas_controller(self):
        """Crea el controlador solo cuando se usa una accion de emitidas.

        Consultar la empresa al abrir Contabilidad hacia que el hilo grafico se
        quedase esperando la base de datos compartida antes de pintar la vista.
        """
        if self._fac_ctrl is None:
            self._empresa_conf = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
            self._fac_ctrl = FacturasEmitidasController(
                self._gestor, self._codigo, self._ejercicio, self._empresa_conf,
                self._adapter, allow_all_years=False, incluir_origen_ocr=True,
            )
        return self._fac_ctrl

    def refresh(self):
        docs = self._gestor.listar_facturas_emitidas_en_contabilidad(self._codigo, self._ejercicio)
        self._view.set_emitidas(docs)

    def generar_suenlace(self):
        self._facturas_controller().generar_suenlace()

    def quitar_de_contabilidad(self):
        """Devuelve cada factura a Facturacion o a Errores OCR segun su origen."""
        sel = self._view.get_selected_emitida_ids()
        if not sel:
            self._view.show_warning(
                "Gest2A3Eco",
                "Selecciona al menos una factura para quitar del modulo de contabilidad.",
            )
            return
        docs_map = {str(d.get("id")): d for d in (self._view._emitidas_docs or [])}
        con_asiento = [
            fid for fid in sel
            if str((docs_map.get(fid) or {}).get("numero_asiento") or "").strip()
        ]
        permitidas = [fid for fid in sel if fid not in con_asiento]
        if con_asiento:
            self._view.show_warning(
                "Gest2A3Eco",
                f"{len(con_asiento)} factura(s) tienen asiento confirmado y no pueden devolverse.",
            )
        if not permitidas:
            return
        enlazadas = [
            fid for fid in permitidas
            if (docs_map.get(fid) or {}).get("estado_contable") in {
                "generado", "contabilizada",
            }
            or bool((docs_map.get(fid) or {}).get("generada"))
        ]
        if enlazadas and not self._view.ask_yes_no(
            "Anular suenlace y devolver",
            f"{len(enlazadas)} factura(s) ya tienen suenlace generado.\n"
            "Se anulara esa marca y se devolveran a su modulo de origen.\n\n¿Continuar?",
        ):
            return
        motivo = self._view.ask_return_reason(
            "Motivo de devolucion",
            "Indica por que se devuelve la factura. El motivo sera visible en OCR.",
        )
        if motivo is None:
            return
        resultado = self._gestor.devolver_facturas_emitidas_desde_contabilidad(
            self._codigo, self._ejercicio, permitidas,
            motivo.strip() or "Devuelta desde Contabilidad para corregirla.",
        )
        self.refresh()
        partes = []
        if resultado.get("facturacion"):
            partes.append(
                f"{resultado['facturacion']} devuelta(s) al modulo de Facturacion."
            )
        if resultado.get("ocr"):
            partes.append(f"{resultado['ocr']} devuelta(s) a Errores OCR.")
        if resultado.get("bloqueadas"):
            partes.append(f"{len(resultado['bloqueadas'])} bloqueada(s) por tener asiento.")
        self._view.show_info(
            "Gest2A3Eco",
            "\n".join(partes) or "Sin cambios.",
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
        self._facturas_controller().capturar_numero_asiento_desde_a3()

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
        generadas = [
            fid for fid in sel
            if (docs_map.get(fid) or {}).get("estado_contable") in {
                "generado", "contabilizada",
            }
        ]
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
        result = self.preparar_asiento_seleccionada(fac_id)
        if result:
            self._view.set_asiento_emitida(*result)

    def preparar_asiento_seleccionada(self, fac_id: str):
        """Calcula el asiento sin tocar Tkinter, apto para carga en segundo plano."""
        from views.ui_asiento_emitida_dialog import calcular_asiento_emitida

        fac = next(
            (d for d in (self._view._emitidas_docs or []) if str(d.get("id")) == fac_id),
            None,
        )
        if not fac:
            return None

        self._facturas_controller()
        ndig = int((self._empresa_conf or {}).get("digitos_plan") or 8)
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
        return lineas, label

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

        self._facturas_controller()
        ndig = int((self._empresa_conf or {}).get("digitos_plan") or 8)
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
            return self._facturas_controller()._plantilla_emitidas_for_factura(fac, {}, set())
        except Exception:
            return {}

    def _get_catalogo_subcuentas(self) -> list[dict]:
        try:
            return self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None) or []
        except Exception:
            return []
