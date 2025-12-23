class TercerosGlobalController:
    def __init__(self, gestor, view):
        self._gestor = gestor
        self._view = view
        self._empresas_cache = []

    def refresh(self):
        self._view.set_terceros(self._gestor.listar_terceros())
        self._empresas_cache = self._gestor.listar_empresas()
        self._view.set_empresas(self._empresas_cache)

    def nuevo(self):
        result = self._view.open_tercero_ficha(None)
        if result:
            tid = self._gestor.upsert_tercero(result)
            self.refresh()
            self._view.select_tercero(str(tid))

    def editar(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            return
        ter = next((t for t in self._gestor.listar_terceros() if str(t.get("id")) == str(tid)), None)
        result = self._view.open_tercero_ficha(ter)
        if result:
            result["id"] = tid
            self._gestor.upsert_tercero(result)
            self.refresh()

    def eliminar(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar el tercero seleccionado?"):
            return
        self._gestor.eliminar_tercero(tid)
        self.refresh()

    def asignar_a_empresa(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            self._view.show_info("Gest2A3Eco", "Selecciona un tercero.")
            return
        codigo, ejercicios = self._view.get_selected_empresa()
        if not codigo:
            self._view.show_info("Gest2A3Eco", "Selecciona una empresa.")
            return
        if not ejercicios:
            self._view.show_info("Gest2A3Eco", "Selecciona uno o varios ejercicios.")
            return
        for ejercicio in ejercicios:
            rel = {
                "tercero_id": tid,
                "codigo_empresa": codigo,
                "ejercicio": ejercicio,
                "subcuenta_cliente": "",
                "subcuenta_proveedor": "",
                "subcuenta_ingreso": "",
                "subcuenta_gasto": "",
            }
            self._gestor.upsert_tercero_empresa(rel)
        self._view.show_info("Gest2A3Eco", "Tercero asignado a los ejercicios seleccionados.")
