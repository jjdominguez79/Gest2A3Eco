from __future__ import annotations

from types import SimpleNamespace

from controllers.app_controller import AppController
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


def test_empleado_carga_buzon_sin_pedir_listado_administrativo_de_usuarios():
    class GestorEmpleado(GestorStub):
        def listar_usuarios(self):
            raise AssertionError("un empleado no debe consultar todos los usuarios")

    view = object.__new__(UIComunicacionesGlobal)
    view._gestor = GestorEmpleado()
    view._session = SessionStub(admin=False)

    data = UIComunicacionesGlobal._collect_refresh_data(view)

    assert data["mine"] == [{"id": "mine"}]
    assert data["users"] == [{
        "id": 7, "nombre": "", "username": "", "activo": True,
    }]


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


class TreeStub:
    def __init__(self):
        self.rows = {}

    def selection(self):
        return ()

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *items):
        for item in items:
            self.rows.pop(item, None)

    def insert(self, _parent, _position, *, iid, values):
        self.rows[iid] = values

    def exists(self, iid):
        return iid in self.rows

    def selection_set(self, _items):
        pass


def test_apply_refresh_no_oculta_correos_por_configuracion_local():
    view = view_stub(admin=False)
    view._pending_tree = TreeStub()
    view._mine_tree = TreeStub()
    view._company_combo = {}
    view._user_combo = {}
    view._filter_companies = lambda: None

    UIComunicacionesGlobal._apply_refresh_data(view, {
        "companies": [],
        "users": [],
        "pending": [{
            "graph_message_id": "entrada",
            "mailbox": "buzon-central@gestinem.es",
            "payload_json": "{}",
        }],
        "mine": [{
            "id": "asignado",
            "mailbox": "buzon-central@gestinem.es",
            "codigo_empresa": "E00001",
        }],
        "mine_pending": [{
            "graph_message_id": "sin-cliente",
            "mailbox": "buzon-central@gestinem.es",
        }],
    })

    assert set(view._pending_tree.rows) == {"entrada"}
    assert set(view._mine_tree.rows) == {"asignado", "pending::sin-cliente"}


def test_contadores_no_se_filtran_con_buzon_local(monkeypatch):
    calls = []

    class Gestor:
        def obtener_nuevos_avisos_correo(self, usuario_id, mailbox):
            return []

        def resumen_buzon_responsable(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"pendiente": 2, "respondido": 1, "gestionado": 0}

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    controller = object.__new__(AppController)
    controller._mail_poll_scheduled = True
    controller._mail_poll_stopped = False
    controller._mail_poll_running = False
    controller._session = SimpleNamespace(user=SimpleNamespace(id=7))
    controller._gestor = Gestor()
    controller._content = SimpleNamespace(after=lambda _delay, callback, *args: callback(*args))
    controller._shared_mailbox = lambda: "configuracion-local-erronea@gestinem.es"
    controller._finish_mail_poll = lambda *_args: None
    monkeypatch.setattr("controllers.app_controller.threading.Thread", ImmediateThread)

    AppController._start_mail_poll(controller)

    assert calls == [((7,), {})]
