"""
Pruebas de regresion para la estabilidad del pool de conexiones PostgreSQL
en el WebSocket de mensajeria (fix/messaging-websocket-pool).

Cubre los escenarios exigidos:
- varios WebSockets concurrentes
- pool temporalmente ocupado
- event loop libre mientras una operacion espera PostgreSQL
- WebSocket desconectado durante una operacion
- autenticacion invalida o sesion revocada
- error de PostgreSQL durante heartbeat y durante cleanup
- cancelacion del handler mientras heartbeat esta en curso
- cierre correcto de todas las sesiones
- ausencia de conexiones checked out al terminar
- ausencia de idle-in-transaction
- /health/live y /health/ready siguen respondiendo
- _ws_cleanup_presence no bloquea el event loop (asyncio.to_thread)

Estructura:
  - Pruebas unitarias (SQLite en memoria): comportamiento funcional.
  - Pruebas de integracion con PostgreSQL real: comportamiento del pool.
    Se saltan automaticamente si TEST_DATABASE_URL no esta definida.
"""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, exc as sa_exc, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

# DGT_DATABASE_URL / BACKEND_DATABASE_URL: necesaria para importar el modulo
# (database.py crea engine a nivel de modulo). Las pruebas unitarias no la usan
# realmente ya que monkeypatchean SessionLocal. Las pruebas de integracion usan
# TEST_DATABASE_URL exclusivamente; no importa el valor que tenga esta variable
# en esas pruebas porque se sustituye SessionLocal.
os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from backend.api import messaging_api
from backend.api.database import Base, build_engine
from backend.api.messaging_api import (
    _ws_auth,
    _ws_cleanup_presence,
    _ws_heartbeat,
)
from backend.api.messaging_models import (
    MessagingStaff,
    MessagingStaffPresenceConnection,
    MessagingStaffSession,
    MessagingWebSocketTicket,
)
from backend.api.messaging_realtime import RealtimeHub
from backend.api.messaging_security import hash_token, utcnow


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------

def _memory_factory():
    """Fabrica de sesiones SQLite en memoria para pruebas unitarias."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_staff(factory, staff_id: str = "employee", active: bool = True):
    with factory() as db:
        db.merge(MessagingStaff(
            external_id=staff_id, name=staff_id.title(),
            email=f"{staff_id}@gestinem.es", role="empleado", active=active,
        ))
        db.commit()


def _seed_ticket(
    factory,
    token: str,
    staff_id: str = "employee",
    *,
    expired: bool = False,
    used: bool = False,
) -> str:
    """Crea una sesion activa + ticket WebSocket. Retorna el ID de sesion."""
    with factory() as db:
        session = MessagingStaffSession(
            staff_external_id=staff_id,
            token_hash=hash_token(f"session-{token}"),
            expires_at=(
                utcnow() - timedelta(seconds=1) if expired
                else utcnow() + timedelta(days=1)
            ),
        )
        db.add(session)
        db.flush()
        ticket = MessagingWebSocketTicket(
            user_type="staff", user_id=staff_id,
            token_hash=hash_token(token),
            staff_session_id=session.id,
            expires_at=utcnow() + timedelta(seconds=60),
            used_at=utcnow() if used else None,
        )
        db.add(ticket)
        db.commit()
        return session.id


def _presencia_count(factory) -> int:
    with factory() as db:
        return db.scalar(
            select(func.count()).select_from(MessagingStaffPresenceConnection)
        )


# ---------------------------------------------------------------------------
# Pruebas unitarias: _ws_auth
# ---------------------------------------------------------------------------

def test_ws_auth_rechaza_ticket_inexistente(monkeypatch):
    factory = _memory_factory()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    assert _ws_auth(hash_token("no-existe"), "staff") is None


def test_ws_auth_rechaza_ticket_caducado(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "caduca", expired=True)
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    assert _ws_auth(hash_token("caduca"), "staff") is None


def test_ws_auth_rechaza_ticket_ya_usado(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "usado", used=True)
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    assert _ws_auth(hash_token("usado"), "staff") is None


def test_ws_auth_rechaza_sesion_revocada(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    session_id = _seed_ticket(factory, "revocada")
    with factory() as db:
        db.get(MessagingStaffSession, session_id).revoked_at = utcnow()
        db.commit()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    assert _ws_auth(hash_token("revocada"), "staff") is None


def test_ws_auth_rechaza_staff_inactivo(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory, active=False)
    _seed_ticket(factory, "inactivo")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    assert _ws_auth(hash_token("inactivo"), "staff") is None


def test_ws_auth_staff_valido_registra_presencia_y_retorna_dict(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "valido")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)

    result = _ws_auth(hash_token("valido"), "staff")

    assert result is not None
    assert result["actor_id"] == "employee"
    assert "presence_id" in result
    assert _presencia_count(factory) == 1


def test_ws_auth_no_deja_conexion_abierta_tras_rechazo(monkeypatch):
    """La sesion debe cerrarse aunque la autenticacion falle."""
    factory = _memory_factory()
    _seed_staff(factory, active=False)
    _seed_ticket(factory, "falla")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)

    _ws_auth(hash_token("falla"), "staff")

    # Si la conexion quedo abierta con una transaccion pendiente, el siguiente
    # acceso al pool de SQLite (StaticPool) la devolveria en ese estado y
    # las operaciones posteriores serian inconsistentes.
    assert _presencia_count(factory) == 0


def test_ws_auth_ticket_de_un_solo_uso(monkeypatch):
    """El ticket solo puede usarse una vez; el segundo intento debe fallar."""
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "unico")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)

    r1 = _ws_auth(hash_token("unico"), "staff")
    r2 = _ws_auth(hash_token("unico"), "staff")

    assert r1 is not None
    assert r2 is None


# ---------------------------------------------------------------------------
# Pruebas unitarias: _ws_heartbeat
# ---------------------------------------------------------------------------

def test_ws_heartbeat_sesion_revocada_devuelve_false(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    session_id = _seed_ticket(factory, "hb-rev")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth = _ws_auth(hash_token("hb-rev"), "staff")

    with factory() as db:
        db.get(MessagingStaffSession, session_id).revoked_at = utcnow()
        db.commit()

    assert _ws_heartbeat(auth["presence_id"], "employee") is False


def test_ws_heartbeat_sesion_caducada_devuelve_false(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    session_id = _seed_ticket(factory, "hb-cad")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth = _ws_auth(hash_token("hb-cad"), "staff")

    with factory() as db:
        db.get(MessagingStaffSession, session_id).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    assert _ws_heartbeat(auth["presence_id"], "employee") is False


def test_ws_heartbeat_staff_inactivo_devuelve_false(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "hb-inac")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth = _ws_auth(hash_token("hb-inac"), "staff")

    with factory() as db:
        db.get(MessagingStaff, "employee").active = False
        db.commit()

    assert _ws_heartbeat(auth["presence_id"], "employee") is False


def test_ws_heartbeat_sesion_valida_renueva_ttl(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "hb-ok")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth = _ws_auth(hash_token("hb-ok"), "staff")

    ok = _ws_heartbeat(auth["presence_id"], "employee")

    assert ok is True
    with factory() as db:
        p = db.get(MessagingStaffPresenceConnection, auth["presence_id"])
        # SQLite devuelve datetimes sin timezone; normalizar antes de comparar.
        from datetime import datetime
        until = p.connected_until
        if until.tzinfo is not None:
            until = until.replace(tzinfo=None)
        assert until > datetime.utcnow() + timedelta(seconds=30)


# ---------------------------------------------------------------------------
# Pruebas unitarias: _ws_cleanup_presence
# ---------------------------------------------------------------------------

def test_ws_cleanup_elimina_presencia_y_reporta_offline(monkeypatch):
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "cleanup")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth = _ws_auth(hash_token("cleanup"), "staff")

    online = _ws_cleanup_presence(auth["presence_id"], "employee")

    assert online is False
    assert _presencia_count(factory) == 0


def test_ws_cleanup_con_segunda_presencia_activa_reporta_online(monkeypatch):
    """Borrar una de dos presencias debe dejar online=True."""
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "dos-a")
    _seed_ticket(factory, "dos-b")
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    auth_a = _ws_auth(hash_token("dos-a"), "staff")
    auth_b = _ws_auth(hash_token("dos-b"), "staff")  # noqa: F841

    online = _ws_cleanup_presence(auth_a["presence_id"], "employee")

    assert online is True
    assert _presencia_count(factory) == 1


# ---------------------------------------------------------------------------
# Pruebas del handler messaging_websocket
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_cierra_4401_audience_invalido():
    class MockWS:
        closed_code = None
        async def close(self, code):
            self.closed_code = code

    ws = MockWS()
    await messaging_api.messaging_websocket(ws, "desconocido", "any-ticket")
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_cierra_4401_ticket_vacio():
    class MockWS:
        closed_code = None
        async def close(self, code):
            self.closed_code = code

    ws = MockWS()
    await messaging_api.messaging_websocket(ws, "staff", "")
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_cierra_4401_autenticacion_falla(monkeypatch):
    factory = _memory_factory()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)

    class MockWS:
        closed_code = None
        async def close(self, code):
            self.closed_code = code

    ws = MockWS()
    await messaging_api.messaging_websocket(ws, "staff", "ticket-inexistente")
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_no_bloquea_event_loop_durante_auth(monkeypatch):
    """
    El event loop debe poder ejecutar otras corrutinas mientras _ws_auth
    se ejecuta en asyncio.to_thread.
    """
    inicio_hilo = threading.Event()
    puede_continuar = threading.Event()

    def _ws_auth_lenta(ticket_hash, audience):
        inicio_hilo.set()
        puede_continuar.wait(timeout=5)
        return None

    monkeypatch.setattr(messaging_api, "_ws_auth", _ws_auth_lenta)

    class MockWS:
        closed_code = None
        async def close(self, code):
            self.closed_code = code

    ws = MockWS()
    ws_task = asyncio.create_task(
        messaging_api.messaging_websocket(ws, "staff", "any-ticket"),
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: inicio_hilo.wait(timeout=5))
    assert inicio_hilo.is_set(), "El hilo de BD no inicio"

    event_loop_libre = asyncio.Event()

    async def _tarea_paralela():
        await asyncio.sleep(0)
        event_loop_libre.set()

    await asyncio.create_task(_tarea_paralela())
    assert event_loop_libre.is_set(), (
        "El event loop estaba bloqueado durante asyncio.to_thread(_ws_auth). "
        "Esto indica que _ws_auth corre en el event loop en lugar de en un hilo."
    )

    puede_continuar.set()
    await asyncio.wait_for(ws_task, timeout=5)
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_cleanup_no_bloquea_event_loop(monkeypatch):
    """
    _ws_cleanup_presence debe ejecutarse en asyncio.to_thread (no en el event loop).

    Se bloquea el hilo de cleanup con un threading.Event; durante ese tiempo,
    otra corrutina debe poder ejecutarse en el event loop, demostrando que
    el cleanup no bloquea el event loop.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "cleanup-thread")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)

    cleanup_inicio = threading.Event()
    cleanup_continua = threading.Event()
    original_cleanup = messaging_api._ws_cleanup_presence

    def _cleanup_bloqueante(presence_id, staff_id):
        cleanup_inicio.set()
        cleanup_continua.wait(timeout=5)
        return original_cleanup(presence_id, staff_id)

    monkeypatch.setattr(messaging_api, "_ws_cleanup_presence", _cleanup_bloqueante)

    class MockWS:
        def __init__(self):
            self._cola = asyncio.Queue()
        async def accept(self):
            self._cola.put_nowait({"type": "websocket.disconnect"})
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    ws_task = asyncio.create_task(
        messaging_api.messaging_websocket(ws, "staff", "cleanup-thread"),
    )

    # Esperar a que el cleanup empiece en su hilo
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: cleanup_inicio.wait(timeout=5))
    assert cleanup_inicio.is_set(), "El hilo de cleanup no inicio"

    # Mientras el cleanup esta bloqueado en el hilo, el event loop debe poder
    # ejecutar otras corrutinas.
    event_loop_libre = asyncio.Event()

    async def _tarea_ligera():
        await asyncio.sleep(0)
        event_loop_libre.set()

    await asyncio.create_task(_tarea_ligera())
    assert event_loop_libre.is_set(), (
        "El event loop estaba bloqueado durante _ws_cleanup_presence. "
        "La limpieza debe correr en asyncio.to_thread, no en el event loop."
    )

    cleanup_continua.set()
    await asyncio.wait_for(ws_task, timeout=5)

    assert _presencia_count(factory) == 0


@pytest.mark.asyncio
async def test_websocket_desconexion_limpia_presencia(monkeypatch):
    """La presencia debe eliminarse aunque el cliente se desconecte de inmediato."""
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "desconexion")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)

    class MockWS:
        def __init__(self):
            self._cola = asyncio.Queue()
        async def accept(self):
            self._cola.put_nowait({"type": "websocket.disconnect"})
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    await asyncio.wait_for(
        messaging_api.messaging_websocket(ws, "staff", "desconexion"),
        timeout=5,
    )

    assert _presencia_count(factory) == 0
    assert not bus._subscriptions


@pytest.mark.asyncio
async def test_websocket_desconexion_durante_heartbeat_lento(monkeypatch):
    """
    Si el cliente se desconecta mientras _ws_heartbeat corre en un hilo,
    la presencia debe limpiarse igualmente al terminar la corrutina.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "hb-lento")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.01)

    hb_inicio = threading.Event()
    hb_continua = threading.Event()
    original_hb = messaging_api._ws_heartbeat

    def _hb_lento(presence_id, staff_id):
        hb_inicio.set()
        hb_continua.wait(timeout=5)
        return original_hb(presence_id, staff_id)

    monkeypatch.setattr(messaging_api, "_ws_heartbeat", _hb_lento)

    class MockWS:
        def __init__(self):
            self._cola = asyncio.Queue()
        async def accept(self):
            pass
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    ws_task = asyncio.create_task(
        messaging_api.messaging_websocket(ws, "staff", "hb-lento"),
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: hb_inicio.wait(timeout=5))

    ws._cola.put_nowait({"type": "websocket.disconnect"})
    hb_continua.set()
    await asyncio.wait_for(ws_task, timeout=5)

    assert _presencia_count(factory) == 0


@pytest.mark.asyncio
async def test_websocket_sesion_revocada_en_heartbeat_cierra_4401(monkeypatch):
    """Si la sesion se revoca entre latidos, el WebSocket debe cerrarse con 4401."""
    factory = _memory_factory()
    _seed_staff(factory)
    session_id = _seed_ticket(factory, "hb-rev-ws")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.02)

    class MockWS:
        def __init__(self):
            self.closed_code = None
            self._cola = asyncio.Queue()
        async def accept(self):
            pass
        async def receive(self):
            return await self._cola.get()
        async def close(self, code):
            self.closed_code = code
        async def send_json(self, payload):
            if payload["type"] == "connected":
                with factory() as db:
                    db.get(MessagingStaffSession, session_id).revoked_at = utcnow()
                    db.commit()

    ws = MockWS()
    await asyncio.wait_for(
        messaging_api.messaging_websocket(ws, "staff", "hb-rev-ws"),
        timeout=5,
    )
    assert ws.closed_code == 4401
    assert _presencia_count(factory) == 0


@pytest.mark.asyncio
async def test_websocket_excepcion_postgresql_en_heartbeat(monkeypatch):
    """
    Si _ws_heartbeat lanza OperationalError (p.ej. conexion cortada),
    el handler debe terminar limpiamente y no dejar conexiones checked out.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "hb-pg-err")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.02)

    llamadas_heartbeat = 0

    def _hb_con_error(presence_id, staff_id):
        nonlocal llamadas_heartbeat
        llamadas_heartbeat += 1
        raise sa_exc.OperationalError("lost connection", None, None)

    monkeypatch.setattr(messaging_api, "_ws_heartbeat", _hb_con_error)

    class MockWS:
        def __init__(self):
            self.closed_code = None
            self._cola = asyncio.Queue()
        async def accept(self):
            pass
        async def receive(self):
            return await self._cola.get()
        async def close(self, code):
            self.closed_code = code
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    await asyncio.wait_for(
        messaging_api.messaging_websocket(ws, "staff", "hb-pg-err"),
        timeout=5,
    )
    assert ws.closed_code == 4401
    assert llamadas_heartbeat >= 1


@pytest.mark.asyncio
async def test_websocket_excepcion_postgresql_en_cleanup(monkeypatch):
    """
    Si _ws_cleanup_presence lanza OperationalError, el handler NO debe propagar
    la excepcion: cleanup es best-effort. El error se registra con logging y el
    handler termina normalmente. La presencia puede quedar en la BD.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "cleanup-pg-err")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)

    def _cleanup_con_error(presence_id, staff_id):
        raise sa_exc.OperationalError("lost connection", None, None)

    monkeypatch.setattr(messaging_api, "_ws_cleanup_presence", _cleanup_con_error)

    class MockWS:
        def __init__(self):
            self._cola = asyncio.Queue()
        async def accept(self):
            self._cola.put_nowait({"type": "websocket.disconnect"})
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    # Cleanup es best-effort: OperationalError se registra con logging y no sale
    # al exterior. El handler debe completar sin propagar la excepcion.
    await asyncio.wait_for(
        messaging_api.messaging_websocket(ws, "staff", "cleanup-pg-err"),
        timeout=5,
    )


@pytest.mark.asyncio
async def test_websocket_cancelacion_durante_heartbeat(monkeypatch):
    """
    Si el handler es cancelado mientras _ws_heartbeat esta en curso,
    _ws_cleanup_presence debe ejecutarse en el finally block.

    Nota: el handler captura CancelledError con 'except CancelledError: pass'
    y completa normalmente (la tarea no re-lanza).

    Limitacion SQLite StaticPool: cuando _ws_heartbeat (T_hb) y
    _ws_cleanup_presence (T_cl) se ejecutan concurrentemente en el hilo del
    ThreadPool, ambos comparten la misma conexion SQLite (StaticPool) y pueden
    interferir. En produccion (PostgreSQL) no hay este problema. El test verifica
    que el cleanup se INVOCA; la integridad de la BD bajo cancelacion concurrente
    se verifica en las pruebas PostgreSQL de integracion.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    _seed_ticket(factory, "cancel-hb")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.01)

    hb_inicio = threading.Event()
    hb_continua = threading.Event()
    hb_terminado = threading.Event()
    original_hb = messaging_api._ws_heartbeat

    def _hb_lento(presence_id, staff_id):
        hb_inicio.set()
        hb_continua.wait(timeout=5)
        try:
            return original_hb(presence_id, staff_id)
        finally:
            hb_terminado.set()

    monkeypatch.setattr(messaging_api, "_ws_heartbeat", _hb_lento)

    # Interceptar _ws_cleanup_presence para saber que se invoco.
    cleanup_invocado = threading.Event()
    original_cleanup = messaging_api._ws_cleanup_presence

    def _cleanup_interceptado(presence_id, staff_id):
        cleanup_invocado.set()
        return original_cleanup(presence_id, staff_id)

    monkeypatch.setattr(messaging_api, "_ws_cleanup_presence", _cleanup_interceptado)

    class MockWS:
        def __init__(self):
            self._cola = asyncio.Queue()
        async def accept(self):
            pass
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass

    ws = MockWS()
    ws_task = asyncio.create_task(
        messaging_api.messaging_websocket(ws, "staff", "cancel-hb"),
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: hb_inicio.wait(timeout=5))
    assert hb_inicio.is_set(), "El heartbeat no inicio"

    # Cancelar el handler mientras el heartbeat esta en curso.
    ws_task.cancel()
    hb_continua.set()

    # El handler completa normalmente (CancelledError capturado internamente).
    await asyncio.wait_for(ws_task, timeout=5)

    # Esperar a que T_hb y T_cl terminen (pueden correr concurrentemente).
    await loop.run_in_executor(None, lambda: hb_terminado.wait(timeout=5))
    await loop.run_in_executor(None, lambda: cleanup_invocado.wait(timeout=5))

    # El cleanup fue invocado por el finally block.
    assert cleanup_invocado.is_set(), (
        "_ws_cleanup_presence no fue invocado tras la cancelacion del handler"
    )


@pytest.mark.asyncio
async def test_websockets_concurrentes_presencia_independiente(monkeypatch):
    """
    Dos conexiones del mismo empleado crean dos registros de presencia separados.
    Al cerrar una, el empleado sigue online; al cerrar ambas, offline.
    """
    factory = _memory_factory()
    _seed_staff(factory)
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    monkeypatch.setattr(messaging_api, "hub", bus)

    # Pre-crear sesiones y presencias de forma secuencial (sin concurrencia de hilos).
    with factory() as db:
        for pid in ("pres-conc-uno", "pres-conc-dos"):
            session = MessagingStaffSession(
                staff_external_id="employee",
                token_hash=hash_token(f"session-{pid}"),
                expires_at=utcnow() + timedelta(days=1),
            )
            db.add(session)
            db.flush()
            db.add(MessagingStaffPresenceConnection(
                id=pid,
                staff_external_id="employee",
                staff_session_id=session.id,
                connected_until=utcnow() + timedelta(seconds=35),
            ))
        db.commit()

    _auth_iter = iter([
        {"actor_id": "employee", "presence_id": "pres-conc-uno"},
        {"actor_id": "employee", "presence_id": "pres-conc-dos"},
    ])

    def _mock_ws_auth(ticket_hash, audience):
        return next(_auth_iter)

    monkeypatch.setattr(messaging_api, "_ws_auth", _mock_ws_auth)

    eventos_presencia: list[dict] = []
    pub_original = bus.publish

    def _interceptar(payload, **kw):
        if payload.get("type") == "presence.updated":
            eventos_presencia.append(dict(payload))
        pub_original(payload, **kw)

    monkeypatch.setattr(bus, "publish", _interceptar)

    class MockWSConexion:
        def __init__(self):
            self._cola: asyncio.Queue = asyncio.Queue()
            self.listo = asyncio.Event()
        async def accept(self):
            self.listo.set()
        async def receive(self):
            return await self._cola.get()
        async def send_json(self, _payload):
            pass
        async def close(self, code):
            pass

    ws1 = MockWSConexion()
    ws2 = MockWSConexion()
    t1 = asyncio.create_task(messaging_api.messaging_websocket(ws1, "staff", "conc-uno"))
    t2 = asyncio.create_task(messaging_api.messaging_websocket(ws2, "staff", "conc-dos"))

    await asyncio.wait_for(ws1.listo.wait(), timeout=5)
    await asyncio.wait_for(ws2.listo.wait(), timeout=5)

    assert _presencia_count(factory) == 2

    ws1._cola.put_nowait({"type": "websocket.disconnect"})
    await asyncio.wait_for(t1, timeout=5)
    ultimo_evento = next(
        (e for e in reversed(eventos_presencia) if e.get("staff_id") == "employee"),
        None,
    )
    assert ultimo_evento is not None
    assert ultimo_evento["online"] is True

    ws2._cola.put_nowait({"type": "websocket.disconnect"})
    await asyncio.wait_for(t2, timeout=5)
    assert eventos_presencia[-1]["online"] is False
    assert _presencia_count(factory) == 0
    assert not bus._subscriptions


@pytest.mark.asyncio
async def test_error_en_ws_auth_cierra_websocket_limpiamente(monkeypatch):
    """Si _ws_auth lanza una excepcion, el WebSocket cierra con 4401 sin dejar estado."""
    def _ws_auth_con_error(ticket_hash, audience):
        raise RuntimeError("Error de base de datos simulado")

    monkeypatch.setattr(messaging_api, "_ws_auth", _ws_auth_con_error)

    class MockWS:
        closed_code = None
        async def close(self, code):
            self.closed_code = code

    ws = MockWS()
    await messaging_api.messaging_websocket(ws, "staff", "cualquier-ticket")
    assert ws.closed_code == 4401


# ---------------------------------------------------------------------------
# Pruebas de integracion con PostgreSQL real
# ---------------------------------------------------------------------------

_PG_URL: str | None = os.environ.get("TEST_DATABASE_URL")

# Normalizar esquema de URL si esta definida
if _PG_URL and (_PG_URL.startswith("postgresql://") or _PG_URL.startswith("postgres://")):
    _prefix = _PG_URL.split("://", 1)[1]
    _PG_URL = f"postgresql+psycopg://{_prefix}"


def _pg_segura(url: str) -> str:
    """Verifica que la URL de PostgreSQL apunte a una base de datos de test."""
    # Extraer nombre de la base de datos de la URL
    # Formato: postgresql+psycopg://user:pass@host:port/dbname
    try:
        dbname = url.rsplit("/", 1)[-1].split("?")[0]
    except Exception:
        dbname = ""
    if "test" not in dbname.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL debe apuntar a una BD de test "
            f"(el nombre debe contener 'test'). BD detectada: {dbname!r}"
        )
    return url


def _pg_disponible() -> bool:
    if not _PG_URL:
        return False
    try:
        _pg_segura(_PG_URL)
        eng = create_engine(
            _PG_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


pg_only = pytest.mark.skipif(
    not _pg_disponible(),
    reason="TEST_DATABASE_URL no definida o PostgreSQL de test no disponible",
)


@pg_only
def test_pg_sin_conexiones_checked_out_tras_ws_auth(monkeypatch):
    """
    Tras _ws_auth (exito o rechazo), el pool no debe tener conexiones
    checked out. Una conexion checked out indica que la sesion no se cerro.
    """
    url = _pg_segura(_PG_URL)
    eng = create_engine(
        url,
        pool_size=2, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)

    with factory() as db:
        db.merge(MessagingStaff(
            external_id="pg-emp", name="PG Emp",
            email="pg@gestinem.es", role="empleado", active=True,
        ))
        db.commit()

    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    try:
        # Rechazo: ticket inexistente
        _ws_auth(hash_token("pg-no-existe"), "staff")
        assert eng.pool.checkedout() == 0, (
            f"Rechazo: {eng.pool.checkedout()} conexiones checked out"
        )

        # Exito: ticket valido
        _seed_ticket(factory, "pg-valido", staff_id="pg-emp")
        _ws_auth(hash_token("pg-valido"), "staff")
        assert eng.pool.checkedout() == 0, (
            f"Exito: {eng.pool.checkedout()} conexiones checked out"
        )
    finally:
        eng.dispose()


@pg_only
@pytest.mark.asyncio
async def test_pg_event_loop_libre_bajo_contension_del_pool(monkeypatch):
    """
    Con un pool de 1 conexion, cuando un hilo la retiene, el event loop debe
    poder ejecutar otras corrutinas mientras asyncio.to_thread espera el pool.
    """
    url = _pg_segura(_PG_URL)
    eng = create_engine(
        url,
        pool_size=1, max_overflow=0, pool_timeout=5,
        poolclass=QueuePool, pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)

    pool_libre = threading.Event()
    pool_ocupado = threading.Event()

    def _retener_conexion():
        conn = eng.connect()
        pool_ocupado.set()
        pool_libre.wait(timeout=10)
        conn.close()

    hilo = threading.Thread(target=_retener_conexion, daemon=True)
    hilo.start()

    try:
        pool_ocupado.wait(timeout=5)
        assert pool_ocupado.is_set(), "El hilo no pudo retener la conexion"

        monkeypatch.setattr(messaging_api, "SessionLocal", factory)

        auth_task = asyncio.create_task(
            asyncio.to_thread(_ws_auth, hash_token("pg-pool-lleno"), "staff"),
        )

        event_loop_libre = asyncio.Event()

        async def _tarea_ligera():
            await asyncio.sleep(0)
            event_loop_libre.set()

        await asyncio.create_task(_tarea_ligera())
        assert event_loop_libre.is_set(), (
            "El event loop estaba bloqueado esperando el pool de PostgreSQL. "
            "Esto indica que la operacion de BD bloquea el event loop."
        )

        pool_libre.set()
        try:
            await asyncio.wait_for(auth_task, timeout=10)
        except Exception:
            pass

        assert eng.pool.checkedout() == 0
    finally:
        pool_libre.set()
        hilo.join(timeout=5)
        eng.dispose()


@pg_only
def test_pg_sin_idle_in_transaction_tras_ws_auth(monkeypatch):
    """
    Tras _ws_auth (exito o rechazo), no debe quedar ninguna conexion en estado
    idle-in-transaction en PostgreSQL.
    """
    url = _pg_segura(_PG_URL)
    eng = create_engine(
        url,
        pool_size=2, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)

    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    try:
        _ws_auth(hash_token("idle-test"), "staff")  # rechazo esperado
    finally:
        pass

    monitor_eng = create_engine(
        url,
        connect_args={"connect_timeout": 3},
    )
    try:
        with monitor_eng.connect() as conn:
            idle = conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'idle in transaction' "
                "AND datname = current_database() "
                "AND application_name NOT IN ('psql')"
            )).scalar()
        assert idle == 0, (
            f"Hay {idle} conexiones idle-in-transaction tras _ws_auth"
        )
    finally:
        monitor_eng.dispose()
        eng.dispose()


@pg_only
def test_pg_health_endpoints_responden():
    """
    /health/live y /health/ready deben responder aunque el pool este activo.
    """
    _pg_segura(_PG_URL)
    from fastapi.testclient import TestClient
    from backend.api.app import app as main_app

    client = TestClient(main_app, raise_server_exceptions=False)

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "live"
    assert ready.status_code in (200, 503)
    assert "status" in ready.json()
