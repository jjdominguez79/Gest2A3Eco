from __future__ import annotations

from unittest.mock import MagicMock

import views.ui_certificados as modulo
from views.ui_certificados import UICertificados


class _ThreadInmediato:
    def __init__(self, *, target, daemon):
        self._target = target

    def start(self):
        self._target()


def _ui(gestor):
    ui = object.__new__(UICertificados)
    ui._codigo = "E00001"
    ui._gestor = gestor
    ui._cert = None
    ui._estado_central_seq = 0
    ui._vals = {"central": MagicMock()}
    ui._btn_set = MagicMock()
    ui._btn_del = MagicMock()
    ui._btn_cloud = MagicMock()
    ui.after = lambda _delay, callback: callback()
    ui.winfo_toplevel = lambda: None
    ui.winfo_exists = lambda: True
    ui.refresh = MagicMock()
    return ui


def test_reemplazo_sube_automaticamente_a_azure(monkeypatch):
    gestor = MagicMock()
    ui = _ui(gestor)
    backend = MagicMock()
    backend.upload_client_certificate.return_value = {
        "configured": True,
        "status": "valid",
        "version": 2,
        "tax_id_warning": False,
    }
    monkeypatch.setattr(modulo.threading, "Thread", _ThreadInmediato)
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )
    monkeypatch.setattr(modulo.messagebox, "showinfo", MagicMock())

    ui._iniciar_subida_central(
        cert={
            "id": "cert-1",
            "nombre": "Cliente Uno",
            "nif_titular": "B12345678",
            "ruta_archivo": "C:/certificados/nuevo.pfx",
            "fecha_caducidad": "2099-12-31",
        },
        password="clave-nueva",
        automatico=True,
    )

    backend.upload_client_certificate.assert_called_once_with(
        company_code="E00001",
        pfx_path="C:/certificados/nuevo.pfx",
        password="clave-nueva",
    )
    guardado = gestor.upsert_notif_certificado.call_args.args[0]
    assert guardado["ruta_archivo"] is None
    assert guardado["password_cifrada"] is None
    modulo.messagebox.showinfo.assert_called_once()
    assert "version 2" in modulo.messagebox.showinfo.call_args.args[1]


def test_reemplazo_no_conserva_material_local_si_azure_falla(monkeypatch):
    gestor = MagicMock()
    ui = _ui(gestor)
    ui._cert = {"id": "cert-1", "codigo_empresa": "E00001", "nombre": "Anterior"}
    backend = MagicMock()
    backend.upload_client_certificate.side_effect = RuntimeError("Azure no disponible")
    monkeypatch.setattr(modulo.threading, "Thread", _ThreadInmediato)
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )
    monkeypatch.setattr(modulo.messagebox, "showerror", MagicMock())

    ui._iniciar_subida_central(
        cert={"id": "cert-1", "ruta_archivo": "nuevo.pfx"},
        password="clave",
        automatico=True,
    )

    gestor.upsert_notif_certificado.assert_not_called()
    assert "ninguna copia nueva" in modulo.messagebox.showerror.call_args.args[1]


def test_estado_azure_confirmado_elimina_ruta_y_clave_locales():
    gestor = MagicMock()
    ui = _ui(gestor)
    ui._cert = {
        "id": "cert-1",
        "codigo_empresa": "E00001",
        "ruta_archivo": "C:/temporal/cliente.pfx",
        "password_cifrada": "cifrada",
    }

    ui._estado_central_fin(
        0,
        {"configured": True, "status": "valid", "version": 3},
        None,
    )

    limpio = gestor.upsert_notif_certificado.call_args.args[0]
    assert limpio["ruta_archivo"] is None
    assert limpio["password_cifrada"] is None


def test_comprobacion_manual_confirma_la_custodia_al_usuario(monkeypatch):
    gestor = MagicMock()
    ui = _ui(gestor)
    ui._cert = {
        "id": "cert-1",
        "codigo_empresa": "E00001",
        "ruta_archivo": None,
        "password_cifrada": None,
    }
    backend = MagicMock()
    backend.get_client_certificate_status.return_value = {
        "configured": True,
        "status": "valid",
        "version": 4,
    }
    monkeypatch.setattr(modulo.threading, "Thread", _ThreadInmediato)
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )
    monkeypatch.setattr(modulo.messagebox, "showinfo", MagicMock())

    ui._consultar_estado_central(avisar=True)

    modulo.messagebox.showinfo.assert_called_once()
    assert "version 4" in modulo.messagebox.showinfo.call_args.args[1]


def test_eliminacion_confirmada_borra_el_registro_local(monkeypatch):
    gestor = MagicMock()
    ui = _ui(gestor)
    monkeypatch.setattr(modulo.messagebox, "showinfo", MagicMock())

    ui._eliminacion_fin({"id": "cert-1"}, None)

    gestor.eliminar_notif_certificado.assert_called_once_with("E00001", "cert-1")
    ui.refresh.assert_called_once_with()
    modulo.messagebox.showinfo.assert_called_once()
