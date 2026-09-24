import tkinter as tk
import gc
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from views.ui_bandeja_global import UIBandejaGlobal
from views.ui_buzones_global import UIBuzonesGlobal
from views.ui_config_notificaciones_global import UIConfigNotificacionesGlobal
from views.ui_buzones import _BuzonDialog


@pytest.fixture
def root():
    try:
        ventana = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk no disponible")
    ventana.withdraw()
    yield ventana
    ventana.destroy()
    gc.collect()


def test_bandeja_seleccion_multiple_y_acciones_individuales(root, tmp_path):
    pdf = tmp_path / "notificacion.pdf"
    pdf.write_bytes(b"%PDF-1.7\nprueba")
    items = [
        {"id": str(i), "codigo_empresa": f"E0000{i}", "estado": "PENDIENTE", "asunto": f"Aviso {i}", "pdf_path": str(pdf)}
        for i in (1, 2)
    ]
    gestor = SimpleNamespace(
        get_notif_config_global=Mock(return_value={"avisar_cliente_email": True}),
        listar_notif_bandeja_global=Mock(return_value=items),
    )
    vista = UIBandejaGlobal(root, gestor)
    assert str(vista._tv.cget("selectmode")) == "extended"
    vista._tv.selection_set(vista._tv.get_children())
    vista._on_select()
    assert len(vista._filas_seleccionadas()) == 2
    assert str(vista._btn_enviar.cget("state")) == "normal"
    assert "(2)" in vista._btn_enviar.cget("text")
    assert str(vista._btn_archivar.cget("state")) == "disabled"
    assert str(vista._btn_descargar.cget("state")) == "disabled"
    items[0].update(enviada_cliente=1, email_cliente_estado="ERROR")
    assert vista._es_publicable(items[0]) is True
    items[0]["email_cliente_estado"] = "ENVIADO"
    assert vista._es_publicable(items[0]) is False


def test_configuracion_global_edita_plantilla_independiente(root):
    gestor = SimpleNamespace(get_notif_config_global=Mock(return_value={
        "periodicidad_sync": "SEMANAL", "avisar_cliente_email": True,
        "email_resumen_interno": "despacho@gestinem.es",
        "email_asunto": "Notificaciones de {nombre_cliente}",
        "email_html": "<p>{nombre_cliente}</p>{notificaciones}",
    }))
    vista = UIConfigNotificacionesGlobal(root, gestor)
    datos = vista._datos()
    assert datos["periodicidad_sync"] == "SEMANAL"
    assert datos["email_resumen_interno"] == "despacho@gestinem.es"
    assert datos["avisar_cliente_email"] is True
    vista._validar(datos)


def test_configuracion_diaria_exige_hora_valida():
    vista = object.__new__(UIConfigNotificacionesGlobal)
    datos = {
        "periodicidad_sync": "DIARIA", "hora_sync_diaria": "",
        "email_resumen_interno": "", "email_asunto": "Aviso",
        "email_html": "<p>{nombre_cliente}</p>{notificaciones}",
    }
    with pytest.raises(ValueError, match="hora diaria"):
        vista._validar(datos)
    datos["hora_sync_diaria"] = "25:00"
    with pytest.raises(ValueError, match="HH:MM"):
        vista._validar(datos)
    datos["hora_sync_diaria"] = "08:45"
    vista._validar(datos)


def test_configuracion_buzones_solicita_solo_clientes_activos():
    gestor = SimpleNamespace(
        listar_notif_buzones_global=Mock(return_value=[]),
        listar_empresas_resumen=Mock(return_value=[]),
        listar_notif_organismos=Mock(return_value=[]),
    )
    vista = object.__new__(UIBuzonesGlobal)
    vista._gestor = gestor
    vista._cache = []
    vista._cb_cliente = Mock()
    vista._cb_cliente.get.return_value = "Todos"
    vista._cb_org = Mock()
    vista._cb_org.get.return_value = "Todos"
    vista._render = Mock()
    vista._cargar_estados_dev = Mock()

    vista.refresh()

    gestor.listar_empresas_resumen.assert_called_once_with(solo_activas=True)
    assert vista._cache == []


def test_configuracion_buzones_mantiene_visible_buzon_de_empresa_inactiva():
    buzon = {
        "id": "buzon-rivas", "codigo_empresa": "E00099",
        "empresa_nombre": "Rivas Sierra CB", "organismo_codigo": "DEHU",
        "organismo_nombre": "DEHu", "activo": 1,
    }
    gestor = SimpleNamespace(
        listar_notif_buzones_global=Mock(return_value=[buzon]),
        listar_empresas_resumen=Mock(return_value=[]),
        listar_notif_organismos=Mock(return_value=[]),
    )
    vista = object.__new__(UIBuzonesGlobal)
    vista._gestor = gestor
    vista._cache = []
    vista._cb_cliente = Mock()
    vista._cb_cliente.get.return_value = "Todos"
    vista._cb_org = Mock()
    vista._cb_org.get.return_value = "Todos"
    vista._render = Mock()
    vista._cargar_estados_dev = Mock()

    vista.refresh()

    assert vista._cache[0]["id"] == "buzon-rivas"
    assert vista._cache[0]["_empresa_inactiva"] is True


def test_buzon_global_no_se_activa_sin_certificado(monkeypatch):
    backend = Mock()
    monkeypatch.setattr(
        "views.ui_buzones_global.BackendClientService", lambda: backend,
    )
    vista = object.__new__(UIBuzonesGlobal)
    vista._gestor = SimpleNamespace(
        get_notif_config_global=Mock(return_value={}),
        get_empresa=Mock(return_value={"activo": 1, "cif": "E12345678"}),
        listar_notif_certificados=Mock(return_value=[]),
        upsert_notif_buzon=Mock(),
    )

    with pytest.raises(ValueError, match="certificado digital activo"):
        vista._guardar_estado_buzon({
            "id": "buzon-1", "codigo_empresa": "E00001",
            "organismo_codigo": "DEHU", "organismo_id": 1,
        }, True)

    backend.save_dehu_mailbox_config.assert_not_called()
    vista._gestor.upsert_notif_buzon.assert_not_called()


def test_dialogo_legacy_no_puede_guardar_periodicidad_ni_email_particulares():
    vista = object.__new__(_BuzonDialog)
    vista._gestor = SimpleNamespace(
        get_notif_config_global=Mock(return_value={"periodicidad_sync": "SEMANAL"}),
        get_empresa=Mock(return_value={"email": "ficha@cliente.test"}),
    )
    vista._empresa = "E00001"
    vista._buzon = {}
    vista._cert = {"id": "cert-1", "nif_titular": "B12345678"}
    vista._org_nombres = ["", "DEHU - DEHu"]
    vista._org_ids = [None, 1]
    vista._modo_labels = ["Solo detectar"]
    vista._modo_values = ["SOLO_DETECTAR"]
    for nombre, valor in {
        "nombre": "DEHu", "org": "DEHU - DEHu", "modo": "Solo detectar",
        "periodicidad": "DIARIA", "email": "otro@incorrecto.test",
        "responsable": "", "activo": True,
    }.items():
        setattr(vista, "_var_" + nombre, SimpleNamespace(get=lambda value=valor: value))
    vista.destroy = Mock()
    vista._on_ok()
    assert vista.result["periodicidad_sync"] == "SEMANAL"
    assert vista.result["email_aviso"] == "ficha@cliente.test"
