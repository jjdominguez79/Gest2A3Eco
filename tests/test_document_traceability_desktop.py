from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from controllers.app_controller import AppController
from models.auth import CompanyPermission, UserRecord, UserRole, UserSession
from services.auth_service import AuthorizationService
from services.secured_gestor import SecuredGestor


class _BaseAdjuntos:
    def __init__(self):
        self.rows = [
            {
                "id": "a-1", "codigo_empresa": "E00001",
                "revisado": False, "aviso_mostrado": False,
            },
            {
                "id": "a-2", "codigo_empresa": "E00002",
                "revisado": False, "aviso_mostrado": False,
            },
        ]

    def listar_adjuntos_mensajeria(self, filtro=None):
        rows = list(self.rows)
        filtro = filtro or {}
        if filtro.get("codigo_empresa"):
            rows = [
                row for row in rows
                if row["codigo_empresa"] == filtro["codigo_empresa"]
            ]
        if filtro.get("solo_pendientes"):
            rows = [row for row in rows if not row["revisado"]]
        return rows

    def get_adjunto_mensajeria(self, adjunto_id):
        return next((row for row in self.rows if row["id"] == adjunto_id), None)

    def marcar_aviso_adjunto_mensajeria(self, adjunto_id):
        self.get_adjunto_mensajeria(adjunto_id)["aviso_mostrado"] = True

    def marcar_adjunto_mensajeria_revisado(self, *args):
        return args


def _session(permission=CompanyPermission.READ):
    return UserSession(
        user=UserRecord(7, "empleado", "Analía", UserRole.EMPLEADO, True),
        company_permissions={"E00001": permission},
    )


def test_bandeja_global_filtra_empresas_sin_permiso():
    gestor = SecuredGestor(_BaseAdjuntos(), AuthorizationService(_session()))

    rows = gestor.listar_adjuntos_mensajeria({"solo_pendientes": True})

    assert [row["id"] for row in rows] == ["a-1"]
    assert gestor.contar_adjuntos_mensajeria_pendientes() == 1


def test_revision_exige_permiso_de_escritura():
    gestor = SecuredGestor(_BaseAdjuntos(), AuthorizationService(_session()))

    with pytest.raises(PermissionError):
        gestor.marcar_adjunto_mensajeria_revisado("a-1", "Analía")


def test_ir_a_gestion_documental_abre_ultimo_ejercicio():
    controller = object.__new__(AppController)
    controller._empresa_service = SimpleNamespace(
        listar_empresas_panel=lambda **_kwargs: [
            {"codigo": "E00001", "ultimo_ejercicio": 2026},
        ],
    )
    controller._open_module_in_shell = MagicMock()

    controller._open_messaging_document_management("E00001")

    controller._open_module_in_shell.assert_called_once_with(
        "E00001", 2026, "gestion_documental", open_messaging_incoming=True,
    )


def test_fin_poll_actualiza_contador_y_muestra_nuevos():
    controller = object.__new__(AppController)
    controller._attachment_poll_running = True
    controller._attachment_poll_stopped = False
    counts = []
    shown = []
    controller._attachment_status_callback = counts.append
    controller._show_attachment_toast = lambda rows: shown.extend(rows)
    controller._schedule_attachment_poll = lambda: None
    rows = [{"id": "a-1"}, {"id": "a-2"}]

    controller._finish_attachment_poll(rows, [rows[1]], None)

    assert counts == [2]
    assert shown == [rows[1]]
    assert controller._attachment_poll_running is False
