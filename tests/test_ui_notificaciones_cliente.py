from types import SimpleNamespace
from unittest.mock import Mock

import views.ui_notificaciones_cliente as modulo


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def _vista(gestor):
    gestor.get_notif_config_global = Mock(return_value={
        "periodicidad_sync": "SEMANAL", "avisar_cliente_email": True,
        "email_resumen_interno": "avisos@gestinem.es",
    })
    gestor.get_empresa = Mock(return_value={"email": "ficha@cliente.test"})
    vista = object.__new__(modulo.UINotificacionesCliente)
    vista._gestor = gestor
    vista._codigo = "E00006"
    vista._organismos = [{"id": 7, "nombre": "DEHu"}]
    vista._org_marca = {7: True}
    vista._var_modo = _Var("Consultar metadatos")
    vista._var_periodicidad = _Var("DIARIA")
    vista._var_email = _Var("avisos@gestinem.es")
    vista._var_responsable = _Var("")
    vista._var_envio = _Var(False)
    vista._modo_labels = ["Consultar metadatos"]
    vista.refresh = Mock()
    vista.winfo_toplevel = Mock(return_value=None)
    return vista


def test_guardar_programa_en_backend_antes_de_actualizar_local(monkeypatch):
    gestor = SimpleNamespace(
        listar_notif_certificados=Mock(return_value=[{"id": "cert-1", "nif_titular": "72044071K"}]),
        listar_notif_buzones=Mock(return_value=[{
            "id": "buzon-1",
            "organismo_id": 7,
            "nombre": "DEHu",
            "activo": 1,
        }]),
        upsert_notif_buzon=Mock(),
    )
    backend = Mock()
    monkeypatch.setattr(modulo, "BackendClientService", Mock(return_value=backend))
    monkeypatch.setattr(modulo.messagebox, "showinfo", Mock())
    monkeypatch.setattr(modulo.messagebox, "showerror", Mock())

    vista = _vista(gestor)
    vista._on_guardar()

    backend.save_dehu_mailbox_config.assert_called_once_with(
        company_code="E00006",
        mailbox_id="buzon-1",
        mailbox_name="DEHu",
        active=True,
        periodicity="SEMANAL",
        notification_email="avisos@gestinem.es",
    )
    guardado = gestor.upsert_notif_buzon.call_args.args[0]
    assert guardado["modo_descarga"] == "SOLO_DETECTAR"
    assert guardado["envio_automatico_cliente"] == 0
    assert guardado["email_aviso"] == "ficha@cliente.test"


def test_no_actualiza_local_si_falla_la_programacion_central(monkeypatch):
    gestor = SimpleNamespace(
        listar_notif_certificados=Mock(return_value=[{"id": "cert-1", "nif_titular": "72044071K"}]),
        listar_notif_buzones=Mock(return_value=[{
            "id": "buzon-1",
            "organismo_id": 7,
            "nombre": "DEHu",
            "activo": 1,
        }]),
        upsert_notif_buzon=Mock(),
    )
    backend = Mock()
    backend.save_dehu_mailbox_config.side_effect = RuntimeError("Azure no disponible")
    monkeypatch.setattr(modulo, "BackendClientService", Mock(return_value=backend))
    monkeypatch.setattr(modulo.messagebox, "showinfo", Mock())
    error = Mock()
    monkeypatch.setattr(modulo.messagebox, "showerror", error)

    vista = _vista(gestor)
    vista._on_guardar()

    gestor.upsert_notif_buzon.assert_not_called()
    error.assert_called_once()
