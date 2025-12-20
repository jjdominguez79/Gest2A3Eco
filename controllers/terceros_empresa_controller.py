from utils.utilidades import validar_subcuenta_longitud


class TercerosEmpresaController:
    def __init__(self, gestor, codigo, ejercicio, ndig, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._ndig = ndig
        self._view = view

    def refresh(self):
        self._view.set_terceros(self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio))
        self._view.clear_subcuentas()

    def load_subcuentas(self):
        tid = self._view.get_selected_id()
        if not tid:
            self._view.set_subcuentas("", "")
            return
        rel = self._gestor.get_tercero_empresa(self._codigo, tid, self._ejercicio) or {}
        self._view.set_subcuentas(rel.get("subcuenta_cliente", ""), rel.get("subcuenta_proveedor", ""))

    def guardar_subcuentas(self):
        tid = self._view.get_selected_id()
        if not tid:
            self._view.show_info("Gest2A3Eco", "Selecciona un tercero.")
            return
        sc = self._view.get_subcuenta_cliente().strip()
        sp = self._view.get_subcuenta_proveedor().strip()
        if sc:
            validar_subcuenta_longitud(sc, self._ndig, "subcuenta cliente")
        if sp:
            validar_subcuenta_longitud(sp, self._ndig, "subcuenta proveedor")
        rel = {
            "tercero_id": tid,
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "subcuenta_cliente": sc,
            "subcuenta_proveedor": sp,
        }
        self._gestor.upsert_tercero_empresa(rel)
        self._view.show_info("Gest2A3Eco", "Subcuentas guardadas.")
