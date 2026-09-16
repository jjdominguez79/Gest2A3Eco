from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models.gestor_postgres import FilaPostgres, GestorPostgres
from services.aapp.configuracion_notificaciones import aplicar_programacion_global


def test_config_global_no_depende_de_empresa_ni_ejercicio():
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = FilaPostgres({
        "id": 1, "periodicidad_sync": "DIARIA", "avisar_cliente_email": 1,
        "email_html": "<p>Hola {nombre_cliente}</p>",
    })
    gestor = object.__new__(GestorPostgres)
    gestor.conn = conn
    assert gestor.get_notif_config_global()["periodicidad_sync"] == "DIARIA"
    assert conn.execute.call_args.args == ("SELECT * FROM notif_config_global WHERE id=1",)


def test_guardar_config_global_valida_periodicidad():
    gestor = object.__new__(GestorPostgres)
    gestor.conn = Mock()
    with pytest.raises(ValueError):
        gestor.upsert_notif_config_global({"periodicidad_sync": "CADA_RATO"})
    gestor.conn.execute.assert_not_called()


def test_migracion_global_conserva_programacion_y_resumen_legacy():
    def ejecutar(sql, params=None):
        result = Mock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        if "to_regclass" in sql:
            result.fetchone.return_value = FilaPostgres({"tabla": None})
        elif "information_schema.columns" in sql:
            result.fetchall.return_value = [FilaPostgres({"column_name": "email_resumen_interno"})]
        elif "DISTINCT email_aviso" in sql:
            result.fetchall.return_value = [FilaPostgres({"email_aviso": "despacho@gestinem.es"})]
        elif "DISTINCT periodicidad_sync" in sql:
            result.fetchall.return_value = [FilaPostgres({"periodicidad_sync": "DIARIA"})]
        return result

    gestor = object.__new__(GestorPostgres)
    gestor.conn = Mock()
    gestor.conn.execute.side_effect = ejecutar
    gestor._utc_now = Mock(return_value="2026-09-16T10:00:00")
    gestor._asegurar_esquema_notificaciones_global()
    inserts = [call for call in gestor.conn.execute.call_args_list if "INSERT INTO notif_config_global" in call.args[0]]
    assert inserts[0].args[1] == ("DIARIA", "despacho@gestinem.es", "2026-09-16T10:00:00")
    assert "ON CONFLICT(id) DO NOTHING" in inserts[0].args[0]


def test_programacion_comun_separa_resumen_interno_de_email_cliente():
    gestor = SimpleNamespace(
        listar_notif_buzones_global=Mock(return_value=[
            {"id": "b1", "codigo_empresa": "E00001", "activo": 1, "periodicidad_sync": "DIARIA"},
            {"id": "b2", "codigo_empresa": "E00002", "activo": 1, "periodicidad_sync": "MENSUAL"},
            {"id": "b3", "codigo_empresa": "E00003", "activo": 0},
        ]),
        get_empresa=Mock(side_effect=lambda codigo: {"email": f"{codigo}@cliente.test"}),
        upsert_notif_buzon=Mock(),
    )
    backend = Mock()
    count, errores = aplicar_programacion_global(gestor, {
        "periodicidad_sync": "SEMANAL", "avisar_cliente_email": True,
        "email_resumen_interno": "despacho@gestinem.es",
    }, backend)
    assert count == 2
    assert errores == []
    for llamada in backend.save_dehu_mailbox_config.call_args_list:
        assert llamada.kwargs["periodicity"] == "SEMANAL"
        assert llamada.kwargs["notification_email"] == "despacho@gestinem.es"
    backend.delete_dehu_mailbox_config.assert_called_once_with(company_code="E00003")
    assert gestor.upsert_notif_buzon.call_args_list[0].args[0]["email_aviso"] == "E00001@cliente.test"
