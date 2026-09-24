from unittest.mock import MagicMock

import views.ui_panel_general as modulo
from views.ui_panel_general import UIPanelGeneral


def _ui(callback):
    ui = object.__new__(UIPanelGeneral)
    ui._on_set_company_active = callback
    ui.get_selected_companies = lambda: [
        {"codigo": "E00001"}, {"codigo": "E00006"},
    ]
    ui.winfo_toplevel = lambda: None
    ui.refresh = MagicMock()
    return ui


def test_desactivar_pregunta_y_retira_servicios_si_se_confirma(monkeypatch):
    callback = MagicMock(return_value=2)
    ui = _ui(callback)
    monkeypatch.setattr(modulo.messagebox, "askyesnocancel", lambda *a, **k: True)
    monkeypatch.setattr(modulo.messagebox, "showinfo", MagicMock())

    ui._change_selected_status(False)

    callback.assert_called_once_with(["E00001", "E00006"], False, True)
    assert "buzones dados de baja" in modulo.messagebox.showinfo.call_args.args[1].lower()
    ui.refresh.assert_called_once_with()


def test_desactivar_sin_retirar_servicios_si_se_responde_no(monkeypatch):
    callback = MagicMock(return_value=1)
    ui = _ui(callback)
    monkeypatch.setattr(modulo.messagebox, "askyesnocancel", lambda *a, **k: False)
    monkeypatch.setattr(modulo.messagebox, "showinfo", MagicMock())

    ui._change_selected_status(False)

    callback.assert_called_once_with(["E00001", "E00006"], False, False)
    assert "buzones dados de baja" in modulo.messagebox.showinfo.call_args.args[1].lower()


def test_desactivar_no_hace_cambios_si_se_cancela(monkeypatch):
    callback = MagicMock()
    ui = _ui(callback)
    monkeypatch.setattr(modulo.messagebox, "askyesnocancel", lambda *a, **k: None)

    ui._change_selected_status(False)

    callback.assert_not_called()
