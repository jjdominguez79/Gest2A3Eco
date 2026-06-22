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

    def refresh_facturas(self):
        self._outer_ctrl.refresh()


class UIContabilidadEmitidasController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        empresa_conf = gestor.get_empresa(codigo, ejercicio) or {}
        adapter = _ViewAdapter(self, view)
        self._fac_ctrl = FacturasEmitidasController(
            gestor, codigo, ejercicio, empresa_conf, adapter, allow_all_years=False
        )

    def refresh(self):
        docs = self._gestor.listar_facturas_emitidas_en_contabilidad(self._codigo, self._ejercicio)
        self._view.set_emitidas(docs)

    def generar_suenlace(self):
        self._fac_ctrl.generar_suenlace()
