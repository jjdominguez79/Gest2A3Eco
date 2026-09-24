from unittest.mock import MagicMock

import pytest

from models.gestor_base import GestorBase
from services.empresa_service import EmpresaService


class _Gestor:
    def __init__(self):
        self.calls = []

    def actualizar_estado_empresas(self, codigos, activo):
        self.calls.append((codigos, activo))
        return len(codigos)


def test_empresa_service_actualiza_estado_masivo():
    gestor = _Gestor()
    service = EmpresaService(gestor)

    result = service.actualizar_estado_empresas(["E00001", "E00006"], True)

    assert result == 2
    assert gestor.calls == [(["E00001", "E00006"], True)]


def test_empresa_service_desactiva_buzones_aunque_conserve_certificado(monkeypatch):
    class _GestorBaja(_Gestor):
        def __init__(self):
            super().__init__()
            self.buzones_guardados = []

        def listar_notif_certificados(self, _codigo):
            raise AssertionError("No debe eliminar certificados")

        def listar_notif_buzones(self, codigo):
            return [{"id": "dehu-1", "codigo_empresa": codigo, "activo": 1}]

        def upsert_notif_buzon(self, buzon):
            self.buzones_guardados.append(buzon)

    backend = MagicMock()
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )
    gestor = _GestorBaja()

    result = EmpresaService(gestor).actualizar_estado_empresas(
        ["E00001"], False, retirar_servicios=False,
    )

    assert result == 1
    backend.delete_dehu_mailbox_config.assert_called_once_with(company_code="E00001")
    backend.delete_dev_mailbox_config.assert_called_once_with(company_code="E00001")
    backend.delete_client_certificate.assert_not_called()
    assert gestor.buzones_guardados[0]["activo"] == 0
    assert gestor.calls == [(["E00001"], False)]


def test_empresa_service_retira_certificado_y_desactiva_buzones(monkeypatch):
    class _GestorRetirada(_Gestor):
        def __init__(self):
            super().__init__()
            self.certificados_eliminados = []
            self.buzones_guardados = []

        def listar_notif_certificados(self, codigo):
            return [{"id": "cert-1", "codigo_empresa": codigo}]

        def eliminar_notif_certificado(self, codigo, cert_id):
            self.certificados_eliminados.append((codigo, cert_id))

        def listar_notif_buzones(self, codigo):
            return [
                {"id": "dehu-1", "codigo_empresa": codigo, "activo": 1},
                {"id": "dev-1", "codigo_empresa": codigo, "activo": 0},
            ]

        def upsert_notif_buzon(self, buzon):
            self.buzones_guardados.append(buzon)

    backend = MagicMock()
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )
    gestor = _GestorRetirada()

    result = EmpresaService(gestor).actualizar_estado_empresas(
        [" e00001 "], False, retirar_servicios=True,
    )

    assert result == 1
    backend.delete_client_certificate.assert_called_once_with(company_code="E00001")
    backend.delete_dehu_mailbox_config.assert_called_once_with(company_code="E00001")
    backend.delete_dev_mailbox_config.assert_called_once_with(company_code="E00001")
    assert gestor.certificados_eliminados == [("E00001", "cert-1")]
    assert [(b["id"], b["activo"]) for b in gestor.buzones_guardados] == [
        ("dehu-1", 0),
    ]
    assert gestor.calls == [([" e00001 "], False)]


def test_empresa_service_no_desactiva_si_azure_no_confirma_la_retirada(monkeypatch):
    gestor = _Gestor()
    backend = MagicMock()
    backend.delete_dehu_mailbox_config.side_effect = RuntimeError("Azure no disponible")
    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        lambda: backend,
    )

    with pytest.raises(RuntimeError, match="Azure no disponible"):
        EmpresaService(gestor).actualizar_estado_empresas(
            ["E00001"], False, retirar_servicios=True,
        )

    assert gestor.calls == []


class _Cursor:
    rowcount = 3


class _Connection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return _Cursor()

    def commit(self):
        self.commits += 1


def test_gestor_actualiza_todos_los_ejercicios_una_vez_por_empresa():
    connection = _Connection()
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = connection

    result = gestor.actualizar_estado_empresas(
        ["e00001", "E00001", " E00006 "],
        False,
    )

    assert result == 2
    assert connection.executed == [
        ("UPDATE empresas SET activo=? WHERE codigo=?", (0, "E00001")),
        ("UPDATE empresas SET activo=? WHERE codigo=?", (0, "E00006")),
    ]
    assert connection.commits == 1


class _CursorEmpresas:
    description = [("codigo",), ("nombre",), ("cif",), ("ejercicio",)]

    def fetchall(self):
        return []


class _ConnectionEmpresas:
    def __init__(self):
        self.sql = ""

    def execute(self, sql):
        self.sql = sql
        return _CursorEmpresas()


def test_listar_empresas_resumen_puede_filtrar_solo_activas():
    connection = _ConnectionEmpresas()
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = connection

    assert gestor.listar_empresas_resumen(solo_activas=True) == []

    assert "COALESCE(e.activo, 1) <> 0" in connection.sql


def test_gestor_aplica_solicitud_y_logo_a_todos_los_ejercicios():
    connection = _Connection()
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = connection

    result = gestor.aplicar_cambios_empresa_solicitados(
        " e00006 ",
        {
            "legal_name": " Empresa Demo SL ",
            "tax_id": " b-123 45678 ",
            "bank_accounts": [" ES12 1234 ", "", "ES98 7654"],
        },
        r"\\servidor\documentos\E00006\logotipo_empresa.png",
    )

    assert result == 1
    sql, params = connection.executed[0]
    assert sql == (
        "UPDATE empresas SET nombre=?, cif=?, cuentas_bancarias=?, logo_path=? "
        "WHERE codigo=?"
    )
    assert params == (
        "Empresa Demo SL",
        "B12345678",
        "ES12 1234\nES98 7654",
        r"\\servidor\documentos\E00006\logotipo_empresa.png",
        "E00006",
    )
    assert connection.commits == 1
