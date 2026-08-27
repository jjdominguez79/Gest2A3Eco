"""
Tests de administracion de puestos de trabajo.

Cubre:
  Backend:
    - admin puede listar workstations
    - admin puede crear workstation
    - usuario normal no puede crear workstation
    - usuario normal no puede listar workstations
    - usuario normal no puede desactivar workstation
    - token generado funciona
    - token desactivado deja de funcionar
    - regenerar token invalida el anterior
    - nuevo token funciona
    - token plano no queda almacenado en base de datos

  Escritorio:
    - detecta nombre del equipo
    - guarda token utilizando el servicio correcto de Credential Manager
    - no escribe token en configuracion
    - detecta equipo ya activado
    - gestiona token invalido
    - gestiona puesto desactivado
    - maneja backend no disponible
    - acciones administrativas no disponibles para usuario sin permisos
"""
from __future__ import annotations

import hashlib
import os

import pytest

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)
os.environ.setdefault("DGT_INTERNAL_API_KEY", "test-internal-secret")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_admin_user(db, username="admin", password="admin1234"):
    """Crea un usuario admin en la tabla usuarios para tests."""
    n = 2**14
    r = 8
    p = 1
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=64)
    password_hash = f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        __import__("sqlalchemy").text(
            "INSERT INTO usuarios (username, password_hash, nombre, rol, activo, must_change_password, created_at, updated_at) "
            "VALUES (:u, :ph, :n, :r, 1, 0, :c, :c)"
        ),
        {"u": username, "ph": password_hash, "n": "Admin Test", "r": "admin", "c": now},
    )
    db.commit()


def _create_employee_user(db, username="empleado1", password="emp1234"):
    """Crea un usuario empleado (no admin) en la tabla usuarios para tests."""
    n = 2**14
    r = 8
    p = 1
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=64)
    password_hash = f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        __import__("sqlalchemy").text(
            "INSERT INTO usuarios (username, password_hash, nombre, rol, activo, must_change_password, created_at, updated_at) "
            "VALUES (:u, :ph, :n, :r, 1, 0, :c, :c)"
        ),
        {"u": username, "ph": password_hash, "n": "Empleado Test", "r": "empleado", "c": now},
    )
    db.commit()


def _make_test_app():
    """Crea un TestClient con SQLite en memoria para tests aislados."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.api.database import Base
    from backend.api import app as app_module
    from backend.api.models import Workstation, DesktopAdminSession  # noqa: F401

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Crear tabla usuarios manualmente (no es un modelo SQLAlchemy del backend)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                nombre TEXT NOT NULL,
                rol TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        conn.commit()

    def override_db():
        with factory() as db:
            yield db

    app_module.app.dependency_overrides[app_module.get_db] = override_db
    client = TestClient(app_module.app)
    return client, factory, engine


@pytest.fixture
def test_env():
    """Fixture que devuelve (client, factory, engine) con DB limpia."""
    client, factory, engine = _make_test_app()
    with factory() as db:
        _create_admin_user(db)
        _create_employee_user(db)
    yield client, factory, engine
    from backend.api import app as app_module
    app_module.app.dependency_overrides.clear()


def _admin_login(client, username="admin", password="admin1234") -> str:
    """Login como admin y devuelve el session_token."""
    r = client.post("/api/v1/desktop/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _admin_headers(session_token: str) -> dict:
    return {"Authorization": f"Bearer {session_token}"}


# ═══════════════════════════════════════════════════════════════════════════
# TESTS BACKEND
# ═══════════════════════════════════════════════════════════════════════════

# ── Login admin ──────────────────────────────────────────────────────────

def test_admin_login_ok(test_env):
    client, _, _ = test_env
    r = client.post("/api/v1/desktop/auth/login", json={"username": "admin", "password": "admin1234"})
    assert r.status_code == 200
    data = r.json()
    assert "session_token" in data
    assert data["session_token"].startswith("g2a3_adm_")
    assert data["username"] == "admin"
    assert "expires_at" in data


def test_admin_login_wrong_password(test_env):
    client, _, _ = test_env
    r = client.post("/api/v1/desktop/auth/login", json={"username": "admin", "password": "wrongpass"})
    assert r.status_code == 401


def test_employee_login_rejected(test_env):
    """Un usuario con rol empleado no puede obtener sesion admin."""
    client, _, _ = test_env
    r = client.post("/api/v1/desktop/auth/login", json={"username": "empleado1", "password": "emp1234"})
    assert r.status_code == 403
    assert "administradores" in r.json()["detail"].lower()


# ── Admin puede listar workstations ──────────────────────────────────────

def test_admin_puede_listar_workstations(test_env):
    client, _, _ = test_env
    token = _admin_login(client)
    r = client.get("/api/v1/desktop/admin/workstations", headers=_admin_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Admin puede crear workstation ────────────────────────────────────────

def test_admin_puede_crear_workstation(test_env):
    client, _, _ = test_env
    token = _admin_login(client)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(token),
        json={"name": "PC-TEST-001"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "PC-TEST-001"
    assert "token" in data
    assert data["token"].startswith("g2a3_wks_")
    assert data["active"] is True


# ── Usuario normal no puede crear workstation ────────────────────────────

def test_usuario_normal_no_puede_crear_workstation(test_env):
    client, _, _ = test_env
    # Intentar login como empleado → 403
    r = client.post("/api/v1/desktop/auth/login", json={"username": "empleado1", "password": "emp1234"})
    assert r.status_code == 403

    # Sin sesion admin, no puede crear workstation
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers={"Authorization": "Bearer fake-token"},
        json={"name": "PC-HACK"},
    )
    assert r.status_code == 401


# ── Usuario normal no puede listar workstations ─────────────────────────

def test_usuario_normal_no_puede_listar_workstations(test_env):
    client, _, _ = test_env
    r = client.get(
        "/api/v1/desktop/admin/workstations",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert r.status_code == 401


# ── Usuario normal no puede desactivar workstation ───────────────────────

def test_usuario_normal_no_puede_desactivar_workstation(test_env):
    client, _, _ = test_env
    token = _admin_login(client)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(token),
        json={"name": "PC-TARGET"},
    )
    ws_id = r.json()["id"]

    # Intentar desactivar sin sesion admin
    r = client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers={"Authorization": "Bearer invalid"},
        json={"active": False},
    )
    assert r.status_code == 401


# ── Token generado funciona ──────────────────────────────────────────────

def test_token_generado_funciona(test_env):
    """El token devuelto al crear un workstation debe ser aceptado por require_workstation_or_internal."""
    client, factory, _ = test_env
    admin_token = _admin_login(client)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-FUNCIONAL"},
    )
    wks_token = r.json()["token"]

    # Verificar via el endpoint verify-token
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": wks_token},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["status"] == "active"


# ── Token desactivado deja de funcionar ──────────────────────────────────

def test_token_desactivado_deja_de_funcionar(test_env):
    client, _, _ = test_env
    admin_token = _admin_login(client)

    # Crear workstation
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-DESACTIVAR"},
    )
    ws_id = r.json()["id"]
    wks_token = r.json()["token"]

    # Desactivar
    r = client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(admin_token),
        json={"active": False},
    )
    assert r.json()["active"] is False

    # Verificar que ya no funciona
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": wks_token},
    )
    assert r.json()["valid"] is False
    assert r.json()["status"] == "deactivated"


# ── Regenerar token invalida el anterior ─────────────────────────────────

def test_regenerar_token_invalida_el_anterior(test_env):
    client, _, _ = test_env
    admin_token = _admin_login(client)

    # Crear workstation
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-REGEN"},
    )
    ws_id = r.json()["id"]
    old_token = r.json()["token"]

    # Regenerar
    r = client.post(
        f"/api/v1/desktop/admin/workstations/{ws_id}/regenerate-token",
        headers=_admin_headers(admin_token),
    )
    assert r.status_code == 200
    new_token = r.json()["token"]
    assert new_token != old_token
    assert new_token.startswith("g2a3_wks_")

    # Token antiguo ya no funciona
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": old_token},
    )
    assert r.json()["valid"] is False
    assert r.json()["status"] == "not_found"


# ── Nuevo token funciona ─────────────────────────────────────────────────

def test_nuevo_token_funciona(test_env):
    client, _, _ = test_env
    admin_token = _admin_login(client)

    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-NUEVO"},
    )
    ws_id = r.json()["id"]

    # Regenerar
    r = client.post(
        f"/api/v1/desktop/admin/workstations/{ws_id}/regenerate-token",
        headers=_admin_headers(admin_token),
    )
    new_token = r.json()["token"]

    # Nuevo token funciona
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": new_token},
    )
    assert r.json()["valid"] is True
    assert r.json()["status"] == "active"


# ── Token plano no queda en base de datos ────────────────────────────────

def test_token_plano_no_almacenado_en_db(test_env):
    """La base de datos solo debe contener el hash SHA-256, nunca el token plano."""
    client, factory, _ = test_env
    admin_token = _admin_login(client)

    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-HASH-TEST"},
    )
    plain_token = r.json()["token"]

    from sqlalchemy import text
    with factory() as db:
        rows = db.execute(text("SELECT token_hash FROM workstations WHERE name = 'PC-HASH-TEST'")).fetchall()
        assert len(rows) == 1
        stored_hash = rows[0][0]
        # El hash almacenado NO es el token plano
        assert stored_hash != plain_token
        # El hash almacenado es SHA-256 del token plano
        expected_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        assert stored_hash == expected_hash


# ── No se puede crear workstation duplicado ──────────────────────────────

def test_workstation_duplicado_rechazado(test_env):
    client, _, _ = test_env
    admin_token = _admin_login(client)
    client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-DUP"},
    )
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-DUP"},
    )
    assert r.status_code == 409


# ── Sesion admin expirada es rechazada ───────────────────────────────────

def test_sesion_admin_expirada_rechazada(test_env):
    """Una sesion cuyo expires_at ya paso debe ser rechazada."""
    client, factory, _ = test_env
    admin_token = _admin_login(client)

    # Forzar la expiracion de la sesion
    from datetime import datetime, timezone, timedelta
    from backend.api.security import hash_token
    from sqlalchemy import text
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    with factory() as db:
        db.execute(
            text("UPDATE desktop_admin_sessions SET expires_at = :e WHERE token_hash = :h"),
            {"e": expired, "h": hash_token(admin_token)},
        )
        db.commit()

    r = client.get("/api/v1/desktop/admin/workstations", headers=_admin_headers(admin_token))
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# TESTS ESCRITORIO
# ═══════════════════════════════════════════════════════════════════════════

def test_detecta_nombre_equipo():
    """get_hostname() devuelve un string no vacio."""
    from services.workstation_admin_service import get_hostname
    hostname = get_hostname()
    assert isinstance(hostname, str)
    assert len(hostname) > 0


def test_guarda_token_con_servicio_correcto(monkeypatch):
    """store_workstation_token usa el service name correcto de Credential Manager."""
    stored = {}

    def fake_set_password(service, username, value):
        stored["service"] = service
        stored["username"] = username
        stored["value"] = value

    import utils.credential_store as cstore
    monkeypatch.setattr(cstore, "_keyring_available", lambda: True)
    # keyring se importa dentro de _store_single; parcheamos _store_single directamente
    monkeypatch.setattr(cstore, "_store_single", lambda svc, usr, val: (fake_set_password(svc, usr, val), True)[1])

    cstore.store_workstation_token("g2a3_wks_test123")
    assert stored["service"] == "Gest2A3Eco/WorkstationToken"
    assert stored["username"] == "workstation"
    assert stored["value"] == "g2a3_wks_test123"


def test_no_escribe_token_en_configuracion(monkeypatch, tmp_path):
    """save_app_config no debe escribir workstation_token en JSON."""
    import json
    config_path = tmp_path / "config.local.json"
    import utils.utilidades as utils_mod
    monkeypatch.setattr(utils_mod, "_config_local_path", lambda: config_path)

    from utils.utilidades import save_app_config
    save_app_config({"workstation_token": "g2a3_wks_secret", "integrations_api_url": "https://x.test"})

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "workstation_token" not in saved, "workstation_token no debe persistirse en disco"


def test_detecta_equipo_ya_activado(monkeypatch):
    """Si el equipo ya esta activado, debe indicarlo."""
    import services.workstation_admin_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workstation_token", lambda: "g2a3_wks_active")
    monkeypatch.setattr(ws_mod, "get_hostname", lambda: "PC-TEST")

    from unittest.mock import MagicMock
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_http.get.return_value = mock_response

    svc = ws_mod.WorkstationAdminService(config={"integrations_api_url": "https://x.test"})
    svc._http = mock_http

    result = svc.check_current_workstation_status()
    assert result["status"] == "activated"


def test_gestiona_token_invalido(monkeypatch):
    """Si el token almacenado es invalido (401), debe detectarlo."""
    import services.workstation_admin_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workstation_token", lambda: "g2a3_wks_bad")
    monkeypatch.setattr(ws_mod, "get_hostname", lambda: "PC-TEST")

    from unittest.mock import MagicMock
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"detail": "Credencial no valida"}
    mock_http.get.return_value = mock_response

    svc = ws_mod.WorkstationAdminService(config={"integrations_api_url": "https://x.test"})
    svc._http = mock_http

    result = svc.check_current_workstation_status()
    assert result["status"] == "token_invalid"


def test_gestiona_puesto_desactivado(monkeypatch):
    """Si el puesto esta desactivado, el backend devuelve 401 (token invalido)."""
    import services.workstation_admin_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workstation_token", lambda: "g2a3_wks_deactivated")
    monkeypatch.setattr(ws_mod, "get_hostname", lambda: "PC-TEST")

    from unittest.mock import MagicMock
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"detail": "Credencial no valida"}
    mock_http.get.return_value = mock_response

    svc = ws_mod.WorkstationAdminService(config={"integrations_api_url": "https://x.test"})
    svc._http = mock_http

    result = svc.check_current_workstation_status()
    assert result["status"] == "token_invalid"


def test_maneja_backend_no_disponible(monkeypatch):
    """Si no se puede contactar con el backend, estado = backend_unavailable."""
    import requests
    import services.workstation_admin_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workstation_token", lambda: "g2a3_wks_ok")
    monkeypatch.setattr(ws_mod, "get_hostname", lambda: "PC-TEST")

    from unittest.mock import MagicMock
    mock_http = MagicMock()
    mock_http.get.side_effect = requests.ConnectionError("no connection")

    svc = ws_mod.WorkstationAdminService(config={"integrations_api_url": "https://x.test"})
    svc._http = mock_http

    result = svc.check_current_workstation_status()
    assert result["status"] == "backend_unavailable"


def test_sin_token_estado_no_activado(monkeypatch):
    """Si no hay token almacenado, estado = not_activated."""
    import services.workstation_admin_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workstation_token", lambda: None)
    monkeypatch.delenv("GEST2A3ECO_WORKSTATION_TOKEN", raising=False)
    monkeypatch.setattr(ws_mod, "get_hostname", lambda: "PC-TEST")

    svc = ws_mod.WorkstationAdminService(config={"integrations_api_url": "https://x.test"})

    result = svc.check_current_workstation_status()
    assert result["status"] == "not_activated"


def test_admin_ui_no_disponible_para_empleado():
    """Un usuario no admin no debe poder acceder a la gestion de puestos."""
    from models.auth import UserRecord, UserRole, UserSession
    from services.auth_service import AuthorizationService

    session = UserSession(
        user=UserRecord(id=2, username="empleado1", nombre="Emp", rol=UserRole.EMPLEADO, activo=True),
    )
    authz = AuthorizationService(session)
    assert not authz.can_manage_global_config()
    assert not authz.can_manage_users()


def test_admin_ui_disponible_para_admin():
    """Un usuario admin debe poder acceder a la gestion de puestos."""
    from models.auth import UserRecord, UserRole, UserSession
    from services.auth_service import AuthorizationService

    session = UserSession(
        user=UserRecord(id=1, username="admin", nombre="Admin", rol=UserRole.ADMIN, activo=True),
    )
    authz = AuthorizationService(session)
    assert authz.can_manage_global_config()
    assert authz.can_manage_users()


# ── Audit: eventos se registran ──────────────────────────────────────────

def test_eventos_auditoria_registrados(test_env):
    """Las operaciones admin deben generar eventos en dgt_eventos."""
    client, factory, _ = test_env
    admin_token = _admin_login(client)

    # Crear
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-AUDIT"},
    )
    assert r.status_code == 201
    ws_id = r.json()["id"]

    # Desactivar
    client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(admin_token),
        json={"active": False},
    )

    # Regenerar
    client.post(
        f"/api/v1/desktop/admin/workstations/{ws_id}/regenerate-token",
        headers=_admin_headers(admin_token),
    )

    from sqlalchemy import text
    with factory() as db:
        events = db.execute(
            text("SELECT tipo, actor FROM dgt_eventos WHERE tipo LIKE 'workstation.%' ORDER BY id")
        ).fetchall()
        types = [e[0] for e in events]
        # Debe haber: admin_login, created, deactivated, token_regenerated
        assert "workstation.admin_login" in types
        assert "workstation.created" in types
        assert "workstation.deactivated" in types
        assert "workstation.token_regenerated" in types
        # Todos por el admin
        actors = {e[1] for e in events}
        assert "admin" in actors
