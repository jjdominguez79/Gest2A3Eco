class PlantillasController:
    def __init__(self, gestor, empresa, view):
        self._gestor = gestor
        self._empresa = empresa
        self._view = view
        self._tabs = {}

    def register_tabs(self, tab_bancos, tab_emitidas, tab_recibidas):
        self._tabs = {
            "bancos": tab_bancos,
            "emitidas": tab_emitidas,
            "recibidas": tab_recibidas,
        }

    def refresh_all(self):
        if not self._tabs:
            return
        self._refresh_bancos()
        self._refresh_emitidas()
        self._refresh_recibidas()

    def nuevo(self, title):
        tipo = self._tipo_from_title(title)
        result, pl = self._view.open_config_dialog(tipo, {})
        if result:
            self._upsert(tipo, pl)
            self.refresh_all()
            self._view.show_info("Gest2A3Eco", "Plantilla guardada.")

    def config(self, tv, title):
        tipo = self._tipo_from_title(title)
        key = self._sel_key(tv)
        if not key:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        pl = self._get_plantilla(tipo, key)
        result, pl = self._view.open_config_dialog(tipo, pl)
        if result:
            self._upsert(tipo, pl)
            self.refresh_all()
            self._view.show_info("Gest2A3Eco", "Cambios guardados.")

    def eliminar(self, tv, title):
        tipo = self._tipo_from_title(title)
        key = self._sel_key(tv)
        if not key:
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar la plantilla seleccionada?"):
            return
        self._delete(tipo, key)
        self.refresh_all()

    def _refresh_bancos(self):
        tv = self._tabs["bancos"]["tv"]
        tv.delete(*tv.get_children())
        for p in self._gestor.listar_bancos(self._empresa.get("codigo"), self._empresa.get("ejercicio")):
            tv.insert("", "end", values=(p.get("banco"), p.get("subcuenta_banco"), p.get("subcuenta_por_defecto")))

    def _refresh_emitidas(self):
        tv = self._tabs["emitidas"]["tv"]
        tv.delete(*tv.get_children())
        for p in self._gestor.listar_emitidas(self._empresa.get("codigo"), self._empresa.get("ejercicio")):
            tv.insert("", "end", values=(p.get("nombre"), p.get("cuenta_cliente_prefijo","430"), p.get("cuenta_iva_repercutido_defecto","47700000")))

    def _refresh_recibidas(self):
        tv = self._tabs["recibidas"]["tv"]
        tv.delete(*tv.get_children())
        for p in self._gestor.listar_recibidas(self._empresa.get("codigo"), self._empresa.get("ejercicio")):
            tv.insert("", "end", values=(p.get("nombre"), p.get("cuenta_proveedor_prefijo","400"), p.get("cuenta_iva_soportado_defecto","47200000")))

    def _sel_key(self, tv):
        sel = tv.selection()
        if not sel:
            return None
        v = tv.item(sel[0], "values")
        return v[0] if v else None

    def _tipo_from_title(self, title):
        t = (title or "").lower()
        if "bancos" in t:
            return "bancos"
        if "emitidas" in t:
            return "emitidas"
        return "recibidas"

    def _get_plantilla(self, tipo, key):
        codigo = self._empresa.get("codigo")
        ejercicio = self._empresa.get("ejercicio")
        if tipo == "bancos":
            return next((x for x in self._gestor.listar_bancos(codigo, ejercicio) if x.get("banco") == key), None)
        if tipo == "emitidas":
            return next((x for x in self._gestor.listar_emitidas(codigo, ejercicio) if x.get("nombre") == key), None)
        return next((x for x in self._gestor.listar_recibidas(codigo, ejercicio) if x.get("nombre") == key), None)

    def _upsert(self, tipo, pl):
        if tipo == "bancos":
            self._gestor.upsert_banco(pl)
        elif tipo == "emitidas":
            self._gestor.upsert_emitida(pl)
        else:
            self._gestor.upsert_recibida(pl)

    def _delete(self, tipo, key):
        codigo = self._empresa.get("codigo")
        ejercicio = self._empresa.get("ejercicio")
        if tipo == "bancos":
            self._gestor.eliminar_banco(codigo, key, ejercicio)
        elif tipo == "emitidas":
            self._gestor.eliminar_emitida(codigo, key, ejercicio)
        else:
            self._gestor.eliminar_recibida(codigo, key, ejercicio)
