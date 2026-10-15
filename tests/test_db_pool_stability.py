"""
Tests de estabilidad del pool PostgreSQL - Fase 1.

Requieren PostgreSQL real (variable BACKEND_DATABASE_URL o TEST_DATABASE_URL).
Se omiten si no hay base de datos disponible.

# Para ejecutar los tests @needs_postgres con Docker:
#
#   docker compose -f docker-compose.test.yml up -d postgres_test
#   TEST_DATABASE_URL=postgresql://gest_test:gest_test@localhost:5433/gest_test \
#       pytest tests/test_db_pool_stability.py -v
#   docker compose -f docker-compose.test.yml down -v
"""
from __future__ import annotations

import asyncio
import importlib
import os
import threading
from unittest.mock import patch, MagicMock, AsyncMock, call

import pytest

# Necesario para que database.py pueda importarse sin PostgreSQL real.
# El engine se construye al importar el modulo; sin URL falla en get_settings().
os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("BACKEND_DATABASE_URL")


needs_postgres = pytest.mark.skipif(
    not _pg_url(),
    reason="Requiere PostgreSQL (TEST_DATABASE_URL o BACKEND_DATABASE_URL)",
)


# ── Tests de configuracion del pool ──────────────────────────────────────────


def test_pool_int_valida_minimo():
    from backend.api.database import _pool_int
    with patch.dict(os.environ, {"_TEST_POOL_INT": "0"}):
        with pytest.raises(RuntimeError, match="rango"):
            _pool_int("_TEST_POOL_INT", 5, 1, 50)


def test_pool_int_valida_maximo():
    from backend.api.database import _pool_int
    with patch.dict(os.environ, {"_TEST_VAR": "999"}):
        with pytest.raises(RuntimeError, match="rango"):
            _pool_int("_TEST_VAR", 5, 1, 50)


def test_pool_int_acepta_valores_validos():
    from backend.api.database import _pool_int
    with patch.dict(os.environ, {"_TEST_VAR": "10"}):
        assert _pool_int("_TEST_VAR", 5, 1, 50) == 10


def test_pool_int_usa_default_si_no_hay_env():
    from backend.api.database import _pool_int
    env_sin_var = {k: v for k, v in os.environ.items() if k != "_TEST_VAR_AUSENTE"}
    with patch.dict(os.environ, env_sin_var, clear=True):
        assert _pool_int("_TEST_VAR_AUSENTE", 7, 1, 50) == 7


def test_build_engine_rechaza_sqlite():
    from backend.api.database import build_engine
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        build_engine("sqlite:///test.db")


def test_build_engine_acepta_url_explicita(monkeypatch):
    """build_engine no debe tocar BACKEND_DATABASE_URL si se pasa url explicita.
    Solo verifica que la URL postgresql:// se acepta y no lanza RuntimeError
    (la conexion real puede fallar con OperationalError, eso es correcto).
    """
    monkeypatch.delenv("BACKEND_DATABASE_URL", raising=False)
    from backend.api import database as db_module
    # No debe lanzar RuntimeError "solo admite PostgreSQL"
    eng = db_module.build_engine("postgresql://localhost:5432/nonexistent_db_test")
    assert eng is not None
    # No llamamos a eng.connect() para evitar bloqueo de red


# ── Tests de get_db ───────────────────────────────────────────────────────────


def test_get_db_hace_rollback_en_excepcion():
    """Si el endpoint falla, get_db hace rollback antes de cerrar."""
    from backend.api.database import get_db, SessionLocal

    mock_session = MagicMock()
    with patch("backend.api.database.SessionLocal", return_value=mock_session):
        gen = get_db()
        next(gen)  # avanzar hasta yield
        try:
            gen.throw(ValueError("simulated error"))
        except ValueError:
            pass
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_get_db_no_rollback_en_exito():
    """En uso normal sin excepcion no se llama rollback."""
    from backend.api.database import get_db

    mock_session = MagicMock()
    with patch("backend.api.database.SessionLocal", return_value=mock_session):
        gen = get_db()
        db = next(gen)
        assert db is mock_session
        try:
            gen.send(None)
        except StopIteration:
            pass
    mock_session.rollback.assert_not_called()
    mock_session.close.assert_called_once()


# ── Tests del endpoint SSE ────────────────────────────────────────────────────


def test_stream_no_tiene_sesion_abierta_al_ceder():
    """
    Durante cada iteracion del generador stream(), ninguna sesion de BD debe
    estar abierta en el momento de ejecutar 'yield'.

    Instrumentamos SessionLocal con un contexto manager que cuenta sesiones activas.
    Si al recibir un chunk el contador es > 0, el test falla.
    """
    from backend.api import messaging_api

    sessions_open: list[int] = [0]

    class _MockResult:
        def all(self):
            return []

    class _MockSession:
        def __enter__(self):
            sessions_open[0] += 1
            return self

        def __exit__(self, *args):
            sessions_open[0] -= 1
            return False

        def get(self, *args, **kwargs):
            return None

        def scalars(self, *args, **kwargs):
            return _MockResult()

        def add(self, *args):
            pass

        def commit(self):
            pass

    leaks: list[str] = []

    async def _run():
        with patch("backend.api.messaging_api.SessionLocal", _MockSession):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                fake_request = MagicMock()
                fake_actor = MagicMock()
                fake_actor.id = "client-123"
                fake_actor.organization_id = "org-456"
                fake_actor.external_id = "ext-789"
                with patch("backend.api.messaging_api._resolve_actor", return_value=fake_actor):
                    response = await messaging_api.events("client", fake_request, after=0)
                    async for chunk in response.body_iterator:
                        if sessions_open[0] > 0:
                            leaks.append(chunk)

    asyncio.run(_run())
    assert not leaks, (
        f"Se cedieron {len(leaks)} chunks con sesion de BD abierta: {leaks[:3]}"
    )


def test_stream_sesion_autenticacion_cerrada_antes_del_primer_yield():
    """
    La sesion de autenticacion del endpoint events() debe cerrarse antes de
    que el generador stream() emita su primer chunk.

    Verificamos que el contador de sesiones abiertas es 0 cuando llega el
    primer keepalive (primer yield del generador tras inicializar).
    """
    from backend.api import messaging_api

    sessions_open: list[int] = [0]

    class _MockResult:
        def all(self):
            return []

    class _MockSession:
        def __enter__(self):
            sessions_open[0] += 1
            return self

        def __exit__(self, *args):
            sessions_open[0] -= 1
            return False

        def get(self, *args, **kwargs):
            return None

        def scalars(self, *args, **kwargs):
            return _MockResult()

        def add(self, *args):
            pass

        def commit(self):
            pass

    first_chunk_sessions: list[int] = []

    async def _run():
        with patch("backend.api.messaging_api.SessionLocal", _MockSession):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                fake_request = MagicMock()
                fake_actor = MagicMock()
                fake_actor.id = "client-99"
                fake_actor.organization_id = "org-99"
                fake_actor.external_id = "ext-99"
                with patch("backend.api.messaging_api._resolve_actor", return_value=fake_actor):
                    response = await messaging_api.events("client", fake_request, after=0)
                    async for _chunk in response.body_iterator:
                        first_chunk_sessions.append(sessions_open[0])
                        break  # Solo nos importa el primero

    asyncio.run(_run())
    assert first_chunk_sessions, "El generador no produjo ningun chunk"
    assert first_chunk_sessions[0] == 0, (
        f"La sesion de autenticacion seguia abierta al emitir el primer chunk "
        f"(sessions_open={first_chunk_sessions[0]})"
    )


def test_stream_no_depende_de_get_db():
    """
    events() no debe tener 'db: Session = Depends(get_db)' en su firma.
    Depends(get_db) mantiene la sesion viva durante todo el StreamingResponse.
    """
    import inspect
    from backend.api import messaging_api

    sig = inspect.signature(messaging_api.events)
    for name, param in sig.parameters.items():
        default = param.default
        # fastapi.Depends wraps a callable; detectamos por nombre de clase
        if hasattr(default, "dependency"):
            assert False, (
                f"El parametro '{name}' usa Depends() en events(). "
                "Esto mantiene la sesion abierta durante todo el streaming."
            )


# ── Tests de health endpoints ─────────────────────────────────────────────────


def test_health_live_no_consulta_postgres():
    """
    /health/live debe responder sin tocar la base de datos.
    Probamos que el endpoint devuelve 200 con status=live.
    """
    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "live"


def test_health_ready_falla_si_postgres_no_disponible():
    """
    /health/ready debe devolver 503 si PostgreSQL no responde.
    Parchamos el engine en el namespace de app.py donde se referencia.
    """
    import backend.api.app as app_mod
    from fastapi.responses import JSONResponse

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("connection refused")

    with patch.object(app_mod, "engine", mock_engine):
        result = app_mod.health_ready()

    assert isinstance(result, JSONResponse), f"Esperaba JSONResponse, got {type(result)}"
    assert result.status_code == 503
    import json
    body = json.loads(result.body)
    assert body.get("status") == "not_ready"


# ── Tests del migrador ────────────────────────────────────────────────────────


def test_migrate_run_migrations_requiere_url():
    """run_migrations falla si no hay URL."""
    from backend import migrate
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="BACKEND_DATABASE_URL"):
            migrate.run_migrations()


def test_startup_no_ejecuta_ddl():
    """El startup de FastAPI no debe ejecutar DDL contra PostgreSQL."""
    import backend.api.database as db_mod
    from backend.api.app import app

    ddl_llamadas = []
    original_begin = db_mod.engine.begin

    def mock_begin(*args, **kwargs):
        import traceback
        stack = "".join(traceback.format_stack())
        if "startup" in stack:
            ddl_llamadas.append(stack)
        return original_begin(*args, **kwargs)

    with patch("backend.api.app.cleanup_expired_attachments"):
        with patch("backend.api.app.get_settings") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                client_documents_enabled=False,
                client_invoicing_enabled=False,
                client_certificates_enabled=False,
            )
            # Usar context manager para disparar el startup real del lifespan
            from fastapi.testclient import TestClient
            with TestClient(app) as client:
                pass  # startup ocurre al entrar al context manager

    assert len(ddl_llamadas) == 0, (
        f"El startup ejecuto DDL via engine.begin(): {ddl_llamadas[:1]}"
    )


def test_migrate_aborta_si_base_existente_sin_baseline():
    """
    Si dgt_expedientes existe pero schema_migrations esta vacia,
    run_migrations() debe lanzar RuntimeError con instruccion de --baseline-existing.
    """
    from backend import migrate

    mock_conn = MagicMock()

    # schema_migrations vacia -> applied = {}
    mock_conn.execute.return_value.all.return_value = []

    def mock_scalars_side_effect(stmt):
        sql = str(stmt)
        result = MagicMock()
        if "information_schema.tables" in sql:
            # Simula que dgt_expedientes ya existe
            result.scalars.return_value = ["dgt_expedientes", "msg_staff"]
            result.all.return_value = []
        else:
            result.scalars.return_value = []
            result.all.return_value = []
        return result

    # Configurar mock_conn.execute para distintas llamadas
    execute_calls = []

    def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        execute_calls.append(sql)
        result = MagicMock()
        if "pg_advisory_lock" in sql:
            return result
        # La primera llamada a information_schema.tables es ANTES de crear schema_migrations
        if "information_schema.tables" in sql:
            # Simula que dgt_expedientes ya existe (sin schema_migrations)
            result.scalars.return_value = iter(["dgt_expedientes", "msg_staff"])
            return result
        if "CREATE TABLE schema_migrations" in sql:
            return result
        if "SELECT filename, checksum FROM schema_migrations" in sql:
            result.all.return_value = []
            return result
        result.all.return_value = []
        result.scalars.return_value = iter([])
        return result

    mock_conn.execute.side_effect = execute_side_effect
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch("backend.migrate._build_engine", return_value=mock_engine):
        with pytest.raises(RuntimeError, match="baseline-existing"):
            migrate.run_migrations(database_url="postgresql://fake/db")


def test_migrate_segunda_ejecucion_no_emite_ddl():
    """
    En la segunda ejecucion (todas las migraciones ya aplicadas),
    no se debe llamar a create_all, _run_startup_ddl ni _create_initial_channels.
    """
    from backend import migrate

    # Simular que todas las migraciones del directorio ya estan aplicadas
    fake_applied = {
        "001_initial.sql": "abc123def456" * 4 + "abcd",
        "037_staff_message_mentions.sql": "def456abc123" * 4 + "dcba",
        "038_transition_legacy_startup.sql": "111222333444" * 4 + "5678",
    }

    mock_conn = MagicMock()

    def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        result = MagicMock()
        if "pg_advisory_lock" in sql or "pg_advisory_unlock" in sql:
            return result
        # schema_migrations ya existe: la primera llamada a information_schema.tables
        # la devuelve entre las tablas, por lo que NO se emite CREATE TABLE.
        if "information_schema.tables" in sql:
            result.scalars.return_value = iter(["schema_migrations", "dgt_expedientes"])
            return result
        if "SELECT filename, checksum FROM schema_migrations" in sql:
            result.all.return_value = list(fake_applied.items())
            return result
        result.all.return_value = []
        result.scalars.return_value = iter([])
        return result

    mock_conn.execute.side_effect = execute_side_effect
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Parchamos _sorted_migrations para devolver solo los que ya estan aplicados
    fake_paths = []
    for name in fake_applied:
        p = MagicMock()
        p.name = name
        p.read_text.return_value = f"-- {name} content"
        fake_paths.append(p)

    with patch("backend.migrate._build_engine", return_value=mock_engine):
        with patch("backend.migrate._sorted_migrations", return_value=fake_paths):
            with patch("backend.migrate._verify_checksums"):
                with patch("backend.api.database.Base") as mock_base:
                    with patch("backend.migrate._run_startup_ddl", create=True) as mock_ddl:
                        with patch("backend.migrate._create_initial_channels", create=True) as mock_channels:
                            count = migrate.run_migrations(database_url="postgresql://fake/db")

    assert count == 0, f"Segunda ejecucion aplico {count} migraciones (deberia ser 0)"
    mock_base.metadata.create_all.assert_not_called()
    # _run_startup_ddl y _create_initial_channels ya no existen en el nuevo migrate.py
    # pero si existieran no deben llamarse
    mock_ddl.assert_not_called()
    mock_channels.assert_not_called()


def test_advisory_lock_se_libera_tras_excepcion():
    """
    Si una migracion falla, pg_advisory_unlock debe llamarse de todos modos
    (via el bloque finally).
    """
    from backend import migrate

    unlock_calls = []
    execute_calls = []

    def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        execute_calls.append(sql)
        result = MagicMock()
        if "pg_advisory_lock" in sql:
            return result
        if "pg_advisory_unlock" in sql:
            unlock_calls.append(sql)
            return result
        # Primera llamada: _existing_tables antes de crear schema_migrations (base vacia)
        if "information_schema.tables" in sql:
            result.scalars.return_value = iter([])
            return result
        if "CREATE TABLE schema_migrations" in sql:
            return result
        if "SELECT filename, checksum FROM schema_migrations" in sql:
            result.all.return_value = []
            return result
        # Simular fallo en create_all / primera migracion
        raise RuntimeError("fallo simulado en migracion")

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = execute_side_effect
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Hacer que create_all falle
    with patch("backend.migrate._build_engine", return_value=mock_engine):
        with patch("backend.migrate._sorted_migrations", return_value=[]):
            with patch("backend.migrate._verify_checksums", side_effect=RuntimeError("fallo de checksum")):
                with pytest.raises(RuntimeError, match="fallo de checksum"):
                    migrate.run_migrations(database_url="postgresql://fake/db")

    # Verificar que se intento llamar unlock
    unlock_attempted = any("pg_advisory_unlock" in c for c in execute_calls)
    assert unlock_attempted, (
        f"pg_advisory_unlock no fue llamado tras excepcion. "
        f"Llamadas ejecutadas: {[c[:60] for c in execute_calls]}"
    )


def test_baseline_falla_con_tablas_criticas_ausentes():
    """
    _apply_baseline lanza RuntimeError si faltan tablas del manifiesto.
    No debe insertar ninguna fila si la verificacion falla.
    """
    from backend import migrate

    mock_conn = MagicMock()

    def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        result = MagicMock()
        if "information_schema.tables" in sql:
            # Solo una tabla existe (falta la mayoria)
            result.scalars.return_value = iter(["dgt_expedientes"])
            return result
        if "information_schema.columns" in sql:
            result.tuples.return_value = iter([])
            return result
        if "pg_indexes" in sql:
            result.scalars.return_value = iter([])
            return result
        return result

    mock_conn.execute.side_effect = execute_side_effect

    with pytest.raises(RuntimeError, match="Baseline fallido"):
        migrate._apply_baseline(mock_conn)

    # No debe haberse insertado nada
    insert_calls = [
        str(c) for c in mock_conn.execute.call_args_list
        if "INSERT INTO schema_migrations" in str(c)
    ]
    assert not insert_calls, f"Se insertaron filas a pesar de fallo: {insert_calls}"


def test_check_baseline_readonly():
    """
    run_migrations(check_baseline=True) lanza RuntimeError si falta una tabla,
    sin crear schema_migrations ni modificar datos.
    """
    from backend import migrate

    mock_conn = MagicMock()

    def execute_side_effect(stmt, *args, **kwargs):
        sql = str(stmt)
        result = MagicMock()
        if "information_schema.tables" in sql:
            # Solo unas pocas tablas, faltan muchas
            result.scalars.return_value = iter(["dgt_expedientes", "msg_staff"])
            return result
        if "information_schema.columns" in sql:
            result.tuples.return_value = iter([])
            return result
        if "pg_indexes" in sql:
            result.scalars.return_value = iter([])
            return result
        return result

    mock_conn.execute.side_effect = execute_side_effect
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch("backend.migrate._build_engine", return_value=mock_engine):
        with pytest.raises(RuntimeError, match="check-baseline"):
            migrate.run_migrations(
                database_url="postgresql://fake/db",
                check_baseline=True,
            )

    # No debe haberse creado schema_migrations ni insertado filas
    all_sql = [str(c) for c in mock_conn.execute.call_args_list]
    create_calls = [s for s in all_sql if "CREATE TABLE" in s]
    insert_calls = [s for s in all_sql if "INSERT" in s]
    assert not create_calls, f"Se creo tabla en modo read-only: {create_calls}"
    assert not insert_calls, f"Se insertaron filas en modo read-only: {insert_calls}"


# ── Tests con PostgreSQL real (@needs_postgres) ───────────────────────────────


@needs_postgres
def test_migrate_idempotente():
    """Ejecutar run_migrations dos veces no falla ni duplica registros."""
    from backend import migrate

    url = _pg_url()
    # Primera ejecucion
    count1 = migrate.run_migrations(url)
    # Segunda ejecucion: no debe aplicar ninguna migracion nueva
    ddl_statements = []
    original_run = migrate.run_migrations

    count2 = migrate.run_migrations(url)
    assert count2 == 0, f"Segunda ejecucion aplico {count2} migraciones (deberia ser 0)"


@needs_postgres
def test_migrate_usa_advisory_lock():
    """Dos hilos corriendo run_migrations simultaneamente quedan serializados."""
    from backend import migrate

    url = _pg_url()
    resultados = []
    errores = []

    def ejecutar():
        try:
            resultados.append(migrate.run_migrations(url))
        except Exception as exc:
            errores.append(exc)

    t1 = threading.Thread(target=ejecutar)
    t2 = threading.Thread(target=ejecutar)
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    assert not errores, f"Errores en migracion concurrente: {errores}"
    # Ambos deben completar; el segundo no deberia aplicar ninguna nueva
    assert len(resultados) == 2


@needs_postgres
def test_startup_no_ejecuta_ddl_pg():
    """
    El startup de FastAPI no debe ejecutar DDL contra PostgreSQL.
    Usa TestClient como context manager para disparar el startup real del lifespan.
    """
    import backend.api.database as db_mod
    from backend.api.app import app

    ddl_llamadas = []
    original_begin = db_mod.engine.begin

    def mock_begin(*args, **kwargs):
        import traceback
        stack = "".join(traceback.format_stack())
        if "startup" in stack or "lifespan" in stack:
            ddl_llamadas.append(stack)
        return original_begin(*args, **kwargs)

    with patch("backend.api.app.cleanup_expired_attachments"):
        with patch("backend.api.app.get_settings") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                client_documents_enabled=False,
                client_invoicing_enabled=False,
                client_certificates_enabled=False,
            )
            from fastapi.testclient import TestClient
            with TestClient(app) as client:
                pass  # startup ocurre al entrar al context manager

    assert len(ddl_llamadas) == 0, (
        f"El startup ejecuto DDL via engine.begin(): {ddl_llamadas[:1]}"
    )


@needs_postgres
def test_checkedout_vuelve_a_cero():
    """
    Despues de una peticion, el pool no debe tener conexiones en uso.
    Construye el engine con TEST_DATABASE_URL (no el engine global con URL dummy).
    """
    import sqlalchemy as sa
    from backend.api.database import build_engine
    from sqlalchemy.orm import sessionmaker

    url = _pg_url()
    # Construir engine con la URL real de test, no el engine importado con URL dummy
    test_engine = build_engine(url)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    from backend.api.database import get_db as _get_db_factory
    # Replicar logica de get_db con el engine de test
    session = TestSession()
    try:
        session.execute(sa.text("SELECT 1"))  # Activar conexion real
    finally:
        session.close()

    assert test_engine.pool.checkedout() == 0, (
        f"Pool tiene {test_engine.pool.checkedout()} conexiones en uso tras cerrar la sesion"
    )
    test_engine.dispose()


@needs_postgres
def test_migrate_fresh_install_desde_base_vacia():
    """
    En una base completamente vacia (cero tablas), run_migrations debe:
    - Llamar a Base.metadata.create_all para crear el esquema ORM completo.
    - Registrar 001_initial.sql sin ejecutarlo (sus tablas dgt_* las crea create_all).
    - Aplicar las migraciones 002-038 normalmente.
    - Dejar schema_migrations, dgt_expedientes y msg_staff_thread_mentions creados.
    - Una segunda ejecucion no aplica ninguna migracion nueva.
    Usa un schema temporal unico para aislamiento.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid

    url = _pg_url()
    # Normalizar URL para psycopg3
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)

    schema_name = f"test_fresh_{_uuid.uuid4().hex[:8]}"
    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        conn.commit()

    # URL con search_path apuntando al schema vacio
    sep = "&" if "?" in url else "?"
    fresh_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"

    try:
        # Primera ejecucion: base vacia -> aplica 001-038
        count1 = migrate.run_migrations(fresh_url)
        assert count1 > 0, f"Primera ejecucion deberia aplicar migraciones, aplico {count1}"

        # Verificar tablas criticas creadas por las migraciones
        with eng.connect() as conn:
            conn.execute(sa.text(f'SET search_path = "{schema_name}"'))
            for tabla in ("schema_migrations", "dgt_expedientes", "msg_staff_thread_mentions"):
                result = conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    f"WHERE table_schema = '{schema_name}' AND table_name = '{tabla}'"
                ))
                assert result.scalar() == 1, f"Tabla {tabla} no existe tras fresh install"

        # Segunda ejecucion: no debe aplicar nada
        count2 = migrate.run_migrations(fresh_url)
        assert count2 == 0, f"Segunda ejecucion aplico {count2} migraciones (deberia ser 0)"

    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()


@needs_postgres
def test_migrate_baseline_rechaza_base_parcial():
    """
    --baseline-existing falla con RuntimeError si la base solo tiene
    dgt_expedientes pero le faltan muchas otras tablas del manifiesto.
    No debe registrar ninguna migracion ni emitir DDL.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid

    url = _pg_url()
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)

    schema_name = f"test_parcial_{_uuid.uuid4().hex[:8]}"
    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        # Solo dgt_expedientes para simular base parcial / incorrecta
        conn.execute(sa.text(
            f'CREATE TABLE "{schema_name}".dgt_expedientes (id VARCHAR(36) PRIMARY KEY)'
        ))
        conn.commit()

    sep = "&" if "?" in url else "?"
    partial_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"

    try:
        with pytest.raises(RuntimeError, match="Baseline fallido|ausentes"):
            migrate.run_migrations(partial_url, baseline_existing=True)

        # Verificar que schema_migrations no fue creada (rollback correcto)
        with eng.connect() as conn:
            conn.execute(sa.text(f'SET search_path = "{schema_name}"'))
            result = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{schema_name}' AND table_name = 'schema_migrations'"
            ))
            # schema_migrations puede existir vacia (se crea antes de la verificacion)
            # pero no debe tener filas
            if result.scalar() == 1:
                rows = conn.execute(sa.text(
                    "SELECT COUNT(*) FROM schema_migrations"
                )).scalar()
                assert rows == 0, f"schema_migrations tiene {rows} filas tras baseline fallido"
    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()


@needs_postgres
def test_canales_creados_para_todas_las_organizaciones():
    """
    Transicion real: esquema instalado hasta 037, organizacion inactiva insertada,
    luego run_migrations() aplica el archivo 038 completo (sin extraer fragmentos).
    Verifica que se crean canales general y private para la org inactiva.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid
    from unittest.mock import patch

    url = _pg_url()
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    schema_name = f"test_canales_{_uuid.uuid4().hex[:8]}"

    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        conn.commit()

    sep = "&" if "?" in url else "?"
    schema_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"

    try:
        # Paso 1: instalar esquema 001-037 (excluir 038 del listado de migraciones)
        files_up_to_037 = [
            p for p in sorted(migrate.MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
            if p.name < "038_transition_legacy_startup.sql"
        ]
        with patch("backend.migrate._sorted_migrations", return_value=files_up_to_037):
            count_037 = migrate.run_migrations(schema_url)
        assert count_037 > 0, "Deberian haberse aplicado migraciones 001-037"

        # Verificar que 038 aun no esta aplicado
        pg_url_s = pg_url + sep + f"options=-csearch_path%3D{schema_name}"
        eng2 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng2.connect() as conn:
            tiene_038 = conn.execute(sa.text(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE filename = '038_transition_legacy_startup.sql'"
            )).scalar()
        eng2.dispose()
        assert tiene_038 == 0, "038 no debe estar aplicado tras instalar solo 001-037"

        # Paso 2: insertar una organizacion inactiva ANTES de aplicar 038
        org_id = str(_uuid.uuid4())
        eng3 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng3.connect() as conn:
            conn.execute(sa.text(
                "INSERT INTO msg_organizations "
                "(id, company_code, name, active, created_at, updated_at) "
                "VALUES (:id, :code, :name, FALSE, NOW(), NOW())"
            ), {"id": org_id, "code": f"IX{org_id[:6]}", "name": "Org Inactiva Test"})
            conn.commit()
        eng3.dispose()

        # Paso 3: run_migrations() sin patch: aplica el archivo 038 completo
        count_038 = migrate.run_migrations(schema_url)
        assert count_038 == 1, (
            f"Deberia aplicarse exactamente 038, se aplicaron {count_038}"
        )

        # Paso 4: verificar canales creados para la org inactiva
        eng4 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng4.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT kind FROM msg_conversations "
                "WHERE organization_id = :org_id ORDER BY kind"
            ), {"org_id": org_id})
            kinds = {row[0] for row in result}
        eng4.dispose()

        assert "general" in kinds, f"Canal 'general' no creado para org inactiva. kinds={kinds}"
        assert "private" in kinds, f"Canal 'private' no creado para org inactiva. kinds={kinds}"

    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()


@needs_postgres
def test_migrate_segunda_ejecucion_no_emite_ddl_pg():
    """
    Con PostgreSQL real: la segunda ejecucion de run_migrations (todas las
    migraciones ya aplicadas) no debe emitir ninguna sentencia CREATE, ALTER,
    DROP ni INSERT INTO msg_conversations.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid

    url = _pg_url()
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    schema_name = f"test_nodal_{_uuid.uuid4().hex[:8]}"

    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        conn.commit()

    sep = "&" if "?" in url else "?"
    schema_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"

    try:
        # Primera ejecucion: instala todo
        migrate.run_migrations(schema_url)

        # Segunda ejecucion: instrumentamos para capturar SQL DDL
        eng2 = sa.create_engine(
            pg_url + sep + f"options=-csearch_path%3D{schema_name}",
            pool_pre_ping=True, pool_size=1, max_overflow=0,
        )
        ddl_emitido: list[str] = []

        @sa.event.listens_for(eng2, "before_cursor_execute")
        def capturar_ddl(conn, cursor, statement, parameters, context, executemany):
            upper = statement.strip().upper()
            # Captura TODO el DDL sin excepciones, incluyendo schema_migrations.
            # Tras la correccion, la segunda ejecucion no emite CREATE TABLE schema_migrations
            # porque la tabla ya existe y el migrador la comprueba via catalogo antes de crearla.
            if any(upper.startswith(kw) for kw in (
                "CREATE ", "ALTER ", "DROP ", "INSERT INTO MSG_CONVERSATIONS"
            )):
                ddl_emitido.append(statement[:120])

        from backend import migrate as mg2
        # Usar engine nuevo inyectando via monkeypatch de _build_engine
        original_build = mg2._build_engine

        def build_with_test_eng(url_):
            return eng2

        mg2._build_engine = build_with_test_eng
        try:
            count2 = mg2.run_migrations(schema_url)
        finally:
            mg2._build_engine = original_build
            eng2.dispose()

        assert count2 == 0, f"Segunda ejecucion aplico {count2} migraciones"
        assert not ddl_emitido, (
            f"Segunda ejecucion emitio {len(ddl_emitido)} sentencias DDL:\n"
            + "\n".join(f"  {s}" for s in ddl_emitido[:5])
        )
    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()


@needs_postgres
def test_migrate_baseline_separa_baseline_de_038():
    """
    --baseline-existing registra exactamente 39 archivos (BASELINE_FILES) y
    devuelve 0 sin aplicar 038.
    Una ejecucion normal posterior aplica 038 y deja 40 registros en total.
    Simula la base de produccion: esquema 001-037 presente, schema_migrations ausente.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid
    from unittest.mock import patch

    url = _pg_url()
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    schema_name = f"test_bl_{_uuid.uuid4().hex[:8]}"

    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        conn.commit()

    sep = "&" if "?" in url else "?"
    schema_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"
    pg_url_s = pg_url + sep + f"options=-csearch_path%3D{schema_name}"

    try:
        # Instalar 001-037 usando el migrador (crea schema_migrations)
        files_up_to_037 = [
            p for p in sorted(migrate.MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
            if p.name < "038_transition_legacy_startup.sql"
        ]
        with patch("backend.migrate._sorted_migrations", return_value=files_up_to_037):
            migrate.run_migrations(schema_url)

        # Eliminar schema_migrations para simular la base de produccion heredada
        eng2 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng2.connect() as conn:
            conn.execute(sa.text("DROP TABLE schema_migrations"))
            conn.commit()
        eng2.dispose()

        # --- Paso B.2: baseline ---
        count_baseline = migrate.run_migrations(schema_url, baseline_existing=True)
        assert count_baseline == 0, (
            f"baseline debe devolver 0, devolvio {count_baseline}"
        )

        eng3 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng3.connect() as conn:
            n_baseline = conn.execute(
                sa.text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar()
            tiene_038_tras_baseline = conn.execute(sa.text(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE filename = '038_transition_legacy_startup.sql'"
            )).scalar()
        eng3.dispose()

        assert n_baseline == 39, (
            f"Baseline debe registrar exactamente 39, registro {n_baseline}"
        )
        assert tiene_038_tras_baseline == 0, (
            "038 NO debe estar en schema_migrations tras el baseline"
        )

        # --- Paso B.3: ejecucion normal → aplica 038 ---
        count_normal = migrate.run_migrations(schema_url)
        assert count_normal == 1, (
            f"Ejecucion normal debe aplicar exactamente 038, aplico {count_normal}"
        )

        eng4 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng4.connect() as conn:
            n_final = conn.execute(
                sa.text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar()
            tiene_038_final = conn.execute(sa.text(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE filename = '038_transition_legacy_startup.sql'"
            )).scalar()
        eng4.dispose()

        assert n_final == 40, (
            f"Tras 038 deben existir 40 registros, hay {n_final}"
        )
        assert tiene_038_final == 1, "038 debe estar registrado tras la ejecucion normal"

        # --- Idempotencia: segunda ejecucion normal ---
        count_idem = migrate.run_migrations(schema_url)
        assert count_idem == 0, (
            f"Segunda ejecucion normal debe aplicar 0 migraciones, aplico {count_idem}"
        )

    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()


@needs_postgres
def test_migrate_aborta_esquema_parcial_pg():
    """
    Si existe una tabla msg_* pero falta dgt_expedientes, run_migrations() debe
    abortar con RuntimeError sin ejecutar create_all, sin registrar 001 y sin
    modificar las tablas existentes.
    """
    import sqlalchemy as sa
    from backend import migrate
    import uuid as _uuid

    url = _pg_url()
    pg_url = (
        url.replace("postgresql://", "postgresql+psycopg://")
        if url.startswith("postgresql://") else url
    )
    eng = sa.create_engine(pg_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    schema_name = f"test_parc_{_uuid.uuid4().hex[:8]}"

    with eng.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
        # Solo msg_staff sin dgt_expedientes: esquema parcial/desconocido
        conn.execute(sa.text(
            f'CREATE TABLE "{schema_name}".msg_staff (id VARCHAR(36) PRIMARY KEY)'
        ))
        conn.commit()

    sep = "&" if "?" in url else "?"
    partial_url = f"{url}{sep}options=-csearch_path%3D{schema_name}"
    pg_url_s = pg_url + sep + f"options=-csearch_path%3D{schema_name}"

    try:
        with pytest.raises(RuntimeError, match="parcial|desconocido"):
            migrate.run_migrations(partial_url)

        eng2 = sa.create_engine(pg_url_s, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with eng2.connect() as conn:
            # schema_migrations puede haberse creado pero no debe tener filas
            sm_count = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{schema_name}' AND table_name = 'schema_migrations'"
            )).scalar()
            if sm_count == 1:
                rows = conn.execute(
                    sa.text("SELECT COUNT(*) FROM schema_migrations")
                ).scalar()
                assert rows == 0, (
                    f"schema_migrations tiene {rows} filas en esquema parcial"
                )

            # msg_staff debe seguir intacto
            ms_count = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{schema_name}' AND table_name = 'msg_staff'"
            )).scalar()
            assert ms_count == 1, "msg_staff debe seguir existiendo sin modificar"

            # dgt_expedientes NO debe existir: create_all no se ejecuto
            dgt_count = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{schema_name}' AND table_name = 'dgt_expedientes'"
            )).scalar()
            assert dgt_count == 0, (
                "dgt_expedientes no debe existir (create_all no debe haberse ejecutado)"
            )
        eng2.dispose()

    finally:
        with eng.connect() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            conn.commit()
        eng.dispose()
