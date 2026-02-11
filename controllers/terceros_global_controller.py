class TercerosGlobalController:
    def __init__(self, gestor, view):
        self._gestor = gestor
        self._view = view
        self._empresas_cache = []
        self._terceros_cache = []

    def refresh(self):
        self._terceros_cache = self._gestor.listar_terceros()
        self._view.set_terceros(self._terceros_cache)
        self._empresas_cache = self._gestor.listar_empresas()
        self._view.set_empresas(self._empresas_cache)
        self._view.set_empresas_asignadas([])

    def nuevo(self):
        result = self._view.open_tercero_ficha(None)
        if result:
            if not self._nif_valido(result.get("nif")):
                self._view.show_warning("Gest2A3Eco", "NIF/CIF/NIE invalido. Revisa el formato.")
                return
            if self._nif_duplicado(result.get("nif")):
                self._view.show_warning("Gest2A3Eco", "Ya existe un tercero con ese CIF/NIF.")
                return
            tid = self._gestor.upsert_tercero(result)
            self.refresh()
            self._view.select_tercero(str(tid))
            self.load_empresas_asignadas()

    def editar(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            return
        ter = next((t for t in self._gestor.listar_terceros() if str(t.get("id")) == str(tid)), None)
        result = self._view.open_tercero_ficha(ter)
        if result:
            result["id"] = tid
            if not self._nif_valido(result.get("nif")):
                self._view.show_warning("Gest2A3Eco", "NIF/CIF/NIE invalido. Revisa el formato.")
                return
            if self._nif_duplicado(result.get("nif"), exclude_id=tid):
                self._view.show_warning("Gest2A3Eco", "Ya existe un tercero con ese CIF/NIF.")
                return
            self._gestor.upsert_tercero(result)
            self.refresh()
            self._view.select_tercero(str(tid))
            self.load_empresas_asignadas()

    def eliminar(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar el tercero seleccionado?"):
            return
        try:
            self._gestor.eliminar_tercero(tid)
        except Exception as e:
            self._view.show_warning("Gest2A3Eco", str(e))
            return
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
        rel = {
            "tercero_id": tid,
            "codigo_empresa": codigo,
            "ejercicio": 0,
            "subcuenta_cliente": "",
            "subcuenta_proveedor": "",
            "subcuenta_ingreso": "",
            "subcuenta_gasto": "",
        }
        self._gestor.upsert_tercero_empresa(rel)
        self._view.show_info(
            "Gest2A3Eco",
            "Tercero asignado a la empresa (valido para todos los ejercicios).\n"
            "Recomendacion: traspasa los terceros a A3 desde la pantalla de terceros de empresa.",
        )
        self.load_empresas_asignadas()

    def load_empresas_asignadas(self):
        tid = self._view.get_selected_tercero_id()
        if not tid:
            self._view.set_empresas_asignadas([])
            return
        empresas = self._gestor.listar_empresas_de_tercero(tid)
        self._view.set_empresas_asignadas(empresas)

    def _nif_duplicado(self, nif: str | None, exclude_id: str | None = None) -> bool:
        val = self._norm_nif(nif)
        if not val:
            return False
        for t in self._terceros_cache:
            if exclude_id is not None and str(t.get("id")) == str(exclude_id):
                continue
            if self._norm_nif(t.get("nif")) == val:
                return True
        return False

    def _norm_nif(self, value: str | None) -> str:
        return "".join(str(value or "").strip().upper().split())

    def _nif_valido(self, nif: str | None) -> bool:
        from utils.validaciones import validar_nif_cif_nie

        return validar_nif_cif_nie(nif)
