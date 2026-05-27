from utils.validaciones import (
    inferir_pais_desde_identificacion,
    normalizar_codigo_pais,
    normalizar_nif_cif,
    validar_nif_o_nif_iva_intracomunitario,
)


class TercerosGlobalController:
    def __init__(self, gestor, view):
        self._gestor = gestor
        self._view = view
        self._empresas_cache = []
        self._terceros_cache = []

    def refresh(self):
        self._terceros_cache = self._gestor.listar_terceros()
        self._view.set_terceros(self._terceros_cache)
        self._empresas_cache = self._listar_empresas_unicas()
        self._view.set_empresas(self._empresas_cache)
        self._view.set_empresas_asignadas([])

    def nuevo(self):
        if not self._can_manage_global_third_parties():
            self._view.show_error("Gest2A3Eco", "Solo administradores y empleados pueden gestionar terceros globales.")
            return
        result = self._view.open_tercero_ficha(None)
        if result:
            nif_extranjero = bool(result.pop("_nif_extranjero", False))
            if not nif_extranjero:
                result["nif"] = self._norm_nif(result.get("nif"))
                if not self._nif_valido(result.get("nif")):
                    self._view.show_warning("Gest2A3Eco", "NIF/CIF/NIE invalido. Revisa el formato.")
                    return
            result["pais"] = normalizar_codigo_pais(result.get("pais")) or inferir_pais_desde_identificacion(result.get("nif"))
            result["tipo_identificacion"] = {
                "vat": "vat",
                "foreign": "foreign",
                "nacional": "nif",
            }.get(result.get("_tipo_identificacion_selector"))
            if self._nif_duplicado(result.get("nif")):
                self._view.show_warning("Gest2A3Eco", "Ya existe un tercero con ese CIF/NIF.")
                return
            tid = self._gestor.upsert_tercero(result)
            self.refresh()
            self._view.select_tercero(str(tid))
            self.load_empresas_asignadas()

    def editar(self):
        if not self._can_manage_global_third_parties():
            self._view.show_error("Gest2A3Eco", "Solo administradores y empleados pueden gestionar terceros globales.")
            return
        tid = self._view.get_selected_tercero_id()
        if not tid:
            return
        ter = next((t for t in self._gestor.listar_terceros() if str(t.get("id")) == str(tid)), None)
        result = self._view.open_tercero_ficha(ter)
        if result:
            result["id"] = tid
            nif_extranjero = bool(result.pop("_nif_extranjero", False))
            if not nif_extranjero:
                result["nif"] = self._norm_nif(result.get("nif"))
                if not self._nif_valido(result.get("nif")):
                    self._view.show_warning("Gest2A3Eco", "NIF/CIF/NIE invalido. Revisa el formato.")
                    return
            result["pais"] = normalizar_codigo_pais(result.get("pais")) or inferir_pais_desde_identificacion(result.get("nif"))
            result["tipo_identificacion"] = {
                "vat": "vat",
                "foreign": "foreign",
                "nacional": "nif",
            }.get(result.get("_tipo_identificacion_selector"))
            if self._nif_duplicado(result.get("nif"), exclude_id=tid):
                self._view.show_warning("Gest2A3Eco", "Ya existe un tercero con ese CIF/NIF.")
                return
            self._gestor.upsert_tercero(result)
            self.refresh()
            self._view.select_tercero(str(tid))
            self.load_empresas_asignadas()

    def eliminar(self):
        if not self._can_manage_global_third_parties():
            self._view.show_error("Gest2A3Eco", "Solo administradores y empleados pueden gestionar terceros globales.")
            return
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
        if not self._can_manage_global_third_parties():
            self._view.show_error("Gest2A3Eco", "Solo administradores y empleados pueden gestionar terceros globales.")
            return
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
        return normalizar_nif_cif(value)

    def _nif_valido(self, nif: str | None) -> bool:
        return validar_nif_o_nif_iva_intracomunitario(nif)

    def _can_manage_global_third_parties(self) -> bool:
        security = getattr(self._gestor, "security", None)
        return True if not security else security.can_manage_global_third_parties()

    def _listar_empresas_unicas(self) -> list[dict]:
        rows = self._gestor.listar_empresas()
        by_code = {}
        for row in rows:
            codigo = str(row.get("codigo") or "").strip()
            if not codigo:
                continue
            current = by_code.get(codigo)
            if current is None:
                by_code[codigo] = {
                    "codigo": codigo,
                    "nombre": row.get("nombre", ""),
                }
                continue
            if not current.get("nombre") and row.get("nombre"):
                current["nombre"] = row.get("nombre")
        return sorted(by_code.values(), key=lambda item: (item["codigo"], str(item.get("nombre") or "")))
