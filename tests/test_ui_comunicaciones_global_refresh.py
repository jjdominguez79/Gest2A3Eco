from __future__ import annotations

from types import SimpleNamespace

from views.ui_comunicaciones_global import UIComunicacionesGlobal


class GestorStub:
    def listar_empresas(self):
        return [{"codigo": "E00001"}]

    def listar_usuarios(self):
        return [{"id": 1}]

    def listar_comunicaciones_sin_asignar(self):
        return [{"graph_message_id": "pending"}]

    def listar_buzon_responsable(self, usuario_id):
        assert usuario_id == 7
        return [{"id": "mine"}]

    def listar_pendientes_responsable(self, usuario_id):
        assert usuario_id == 7
        return [{"graph_message_id": "mine-pending"}]

    def listar_comunicaciones_supervision(self):
        return [{"id": "supervision"}]

    def listar_comunicaciones_sin_cliente_asignadas(self):
        return [{"graph_message_id": "without-client"}]

    def listar_comunicaciones_descartadas(self):
        return [{"graph_message_id": "discarded"}]

    def listar_conversaciones_descartadas(self):
        return [{"id": "discarded-conversation"}]


class SessionStub:
    def __init__(self, admin):
        self.user = SimpleNamespace(id=7)
        self._admin = admin

    def is_admin(self):
        return self._admin


def view_stub(admin=True):
    view = object.__new__(UIComunicacionesGlobal)
    view._gestor = GestorStub()
    view._session = SessionStub(admin)
    return view


def test_collect_refresh_data_carga_todas_las_bandejas_para_admin():
    data = UIComunicacionesGlobal._collect_refresh_data(view_stub())

    assert data["pending"][0]["graph_message_id"] == "pending"
    assert data["mine"][0]["id"] == "mine"
    assert data["supervision"][0]["id"] == "supervision"
    assert data["discarded"][0]["graph_message_id"] == "discarded"


def test_collect_refresh_data_no_consulta_supervision_para_empleado():
    data = UIComunicacionesGlobal._collect_refresh_data(view_stub(admin=False))

    assert "supervision" not in data
    assert "discarded" not in data


def test_auto_refresh_descarta_resultado_obsoleto():
    view = view_stub()
    view._auto_refresh_running = True
    view._destroying = False
    view._refresh_generation = 3
    applied = []
    scheduled = []
    view._apply_refresh_data = applied.append
    view._schedule_auto_refresh = lambda: scheduled.append(True)

    UIComunicacionesGlobal._finish_auto_refresh(
        view, {"pending": []}, None, generation=2,
    )

    assert applied == []
    assert scheduled == [True]
    assert view._auto_refresh_running is False
