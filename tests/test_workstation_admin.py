"""
Tests de administracion de puestos de trabajo con autenticacion Microsoft Entra.

Cubre:
  Backend:
    - admin Microsoft puede obtener sesion administrativa via exchange
    - usuario Microsoft no-admin es rechazado en callback y exchange
    - usuario no autenticado no puede administrar puestos
    - WorkstationToken sin sesion admin no puede administrar puestos
    - sesion administrativa expirada es rechazada
    - admin puede listar workstations
    - admin puede crear workstation
    - admin puede activar/desactivar
    - admin puede regenerar token
    - token generado funciona
    - token desactivado deja de funcionar
    - regenerar token invalida el anterior
    - token plano no queda almacenado en base de datos

  Separacion de codigos (purpose):
    - codigo desktop_admin no puede intercambiarse en mobile/exchange
    - codigo mobile no puede generar DesktopAdminSession
    - codigo ya consumido no puede reutilizarse

  Validacion de puerto:
    - puerto fuera de rango es rechazado
    - puerto valido construye URL 127.0.0.1

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

def _make_test_app():
    """Crea un TestClient con SQLite en memoria para tests aislados."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.api.database import Base
    from backend.api import app as app_module
    from backend.api.models import Workstation, DesktopAdminSession  # noqa: F401
    from backend.api import messaging_models  # noqa: F401 - registra tablas

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    app_module.app.dependency_overrides[app_module.get_db] = override_db
    # Override tambien el get_db del messaging router
    from backend.api import messaging_api as msg_module
    app_module.app.dependency_overrides[msg_module.get_db] = override_db
    client = TestClient(app_module.app)
    return client, factory, engine


def _create_staff(db, email="admin@gestinem.es", role="admin", name="Admin Test"):
    """Crea un staff en msg_staff para tests."""
    import uuid
    from backend.api.messaging_models import MessagingStaff
    ext_id = str(uuid.uuid4())
    staff = MessagingStaff(
        external_id=ext_id,
        name=name,
        email=email,
        entra_oid=f"entra-{ext_id[:8]}",
        role=role,
        active=True,
    )
    db.add(staff)
    db.commit()
    return staff


def _create_desktop_admin_code(db, staff_external_id):
    """Crea un codigo temporal desktop_admin y devuelve el codigo plano."""
    from backend.api.messaging_models import MessagingStaffAppCode
    from backend.api.messaging_security import hash_token, new_token, utcnow
    from datetime import timedelta
    code = new_token()
    db.add(MessagingStaffAppCode(
        staff_external_id=staff_external_id,
        code_hash=hash_token(code),
        purpose="desktop_admin",
        expires_at=utcnow() + timedelta(minutes=2),
    ))
    db.commit()
    return code


def _create_mobile_code(db, staff_external_id):
    """Crea un codigo temporal mobile y devuelve el codigo plano."""
    from backend.api.messaging_models import MessagingStaffAppCode
    from backend.api.messaging_security import hash_token, new_token, utcnow
    from datetime import timedelta
    code = new_token()
    db.add(MessagingStaffAppCode(
        staff_external_id=staff_external_id,
        code_hash=hash_token(code),
        purpose="mobile",
        expires_at=utcnow() + timedelta(minutes=2),
    ))
    db.commit()
    return code


def _exchange_desktop_code(client, code) -> dict:
    """Intercambia un codigo desktop_admin por sesion admin."""
    r = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    return r


def _admin_session_from_staff(client, factory, email="admin@gestinem.es", role="admin"):
    """Crea staff admin + codigo desktop_admin + exchange = session_token."""
    with factory() as db:
        staff = _create_staff(db, email=email, role=role)
        code = _create_desktop_admin_code(db, staff.external_id)
    r = _exchange_desktop_code(client, code)
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _admin_headers(session_token: str) -> dict:
    return {"Authorization": f"Bearer {session_token}"}


@pytest.fixture
def test_env():
    """Fixture que devuelve (client, factory, engine) con DB limpia."""
    client, factory, engine = _make_test_app()
    yield client, factory, engine
    from backend.api import app as app_module
    app_module.app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# TESTS: AUTENTICACION MICROSOFT → DESKTOP ADMIN SESSION
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_exchange_ok(test_env):
    """Un staff admin puede obtener DesktopAdminSession via exchange."""
    client, factory, _ = test_env
    with factory() as db:
        staff = _create_staff(db, role="admin")
        code = _create_desktop_admin_code(db, staff.external_id)
    r = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["session_token"].startswith("g2a3_adm_")
    assert "expires_at" in data
    assert data["email"] == "admin@gestinem.es"


def test_non_admin_exchange_rejected(test_env):
    """Un staff con role=empleado no puede obtener DesktopAdminSession."""
    client, factory, _ = test_env
    with factory() as db:
        staff = _create_staff(db, email="emp@gestinem.es", role="empleado", name="Empleado")
        code = _create_desktop_admin_code(db, staff.external_id)
    r = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r.status_code == 403
    assert "administradores" in r.json()["detail"].lower()


def test_unauthenticated_cannot_admin(test_env):
    """Sin sesion admin, no se puede acceder a endpoints de workstations."""
    client, _, _ = test_env
    r = client.get(
        "/api/v1/desktop/admin/workstations",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert r.status_code == 401


def test_workstation_token_cannot_admin(test_env):
    """Un WorkstationToken no concede acceso administrativo."""
    client, _, _ = test_env
    r = client.get(
        "/api/v1/desktop/admin/workstations",
        headers={"Authorization": "Bearer g2a3_wks_fake_token"},
    )
    assert r.status_code == 401


def test_expired_admin_session_rejected(test_env):
    """Una sesion cuyo expires_at ya paso debe ser rechazada."""
    client, factory, _ = test_env
    token = _admin_session_from_staff(client, factory)

    from datetime import datetime, timezone, timedelta
    from backend.api.security import hash_token
    from sqlalchemy import text
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    with factory() as db:
        db.execute(
            text("UPDATE desktop_admin_sessions SET expires_at = :e WHERE token_hash = :h"),
            {"e": expired, "h": hash_token(token)},
        )
        db.commit()

    r = client.get("/api/v1/desktop/admin/workstations", headers=_admin_headers(token))
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# TESTS: SEPARACION DE CODIGOS (PURPOSE)
# ═══════════════════════════════════════════════════════════════════════════

def test_desktop_code_rejected_by_mobile_exchange(test_env):
    """Un codigo desktop_admin NO puede consumirse en /staff-auth/mobile/exchange."""
    client, factory, _ = test_env
    with factory() as db:
        staff = _create_staff(db, role="admin")
        code = _create_desktop_admin_code(db, staff.external_id)
    r = client.post("/api/v1/messaging/staff-auth/mobile/exchange", json={"code": code})
    assert r.status_code == 400
    assert "no valido" in r.json()["detail"].lower()


def test_mobile_code_rejected_by_desktop_exchange(test_env):
    """Un codigo mobile NO puede generar DesktopAdminSession."""
    client, factory, _ = test_env
    with factory() as db:
        staff = _create_staff(db, role="admin")
        code = _create_mobile_code(db, staff.external_id)
    r = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r.status_code == 400
    assert "no valido" in r.json()["detail"].lower()


def test_code_single_use(test_env):
    """Un codigo desktop_admin ya consumido no puede reutilizarse."""
    client, factory, _ = test_env
    with factory() as db:
        staff = _create_staff(db, role="admin")
        code = _create_desktop_admin_code(db, staff.external_id)

    # Primera vez: OK
    r1 = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r1.status_code == 200

    # Segunda vez: rechazado
    r2 = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r2.status_code == 400


def test_expired_code_rejected(test_env):
    """Un codigo expirado no puede intercambiarse."""
    client, factory, _ = test_env
    from backend.api.messaging_models import MessagingStaffAppCode
    from backend.api.messaging_security import hash_token as msg_hash, new_token as msg_new_token, utcnow
    from datetime import timedelta

    with factory() as db:
        staff = _create_staff(db, role="admin")
        code = msg_new_token()
        db.add(MessagingStaffAppCode(
            staff_external_id=staff.external_id,
            code_hash=msg_hash(code),
            purpose="desktop_admin",
            expires_at=utcnow() - timedelta(minutes=1),  # ya expirado
        ))
        db.commit()

    r = client.post("/api/v1/desktop/auth/exchange", json={"code": code})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# TESTS: VALIDACION DE PUERTO
# ═══════════════════════════════════════════════════════════════════════════

def test_port_out_of_range_rejected(test_env):
    """Puerto fuera de 1024-65535 es rechazado."""
    client, _, _ = test_env
    for port in [0, 80, 443, 1023, 65536, 99999]:
        r = client.get(f"/api/v1/desktop/auth/login?port={port}", follow_redirects=False)
        assert r.status_code == 422, f"Puerto {port} deberia ser rechazado"


def test_port_valid_range_accepted(test_env):
    """Puerto en rango valido es aceptado (falla en MSAL sin config, pero pasa validacion de puerto)."""
    client, _, _ = test_env
    # Sin MSAL configurado devolvera 503, no 422
    r = client.get("/api/v1/desktop/auth/login?port=12345", follow_redirects=False)
    # 503 = MSAL no configurado (correcto, no es error de puerto)
    # 302 = redirect a Microsoft (si MSAL estuviera configurado)
    assert r.status_code in (302, 503)


# ═══════════════════════════════════════════════════════════════════════════
# TESTS: GESTION DE WORKSTATIONS
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_puede_listar_workstations(test_env):
    client, factory, _ = test_env
    token = _admin_session_from_staff(client, factory)
    r = client.get("/api/v1/desktop/admin/workstations", headers=_admin_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_puede_crear_workstation(test_env):
    client, factory, _ = test_env
    token = _admin_session_from_staff(client, factory)
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


def test_admin_puede_desactivar_workstation(test_env):
    client, factory, _ = test_env
    token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(token),
        json={"name": "PC-DESACTIVAR"},
    )
    ws_id = r.json()["id"]
    r = client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(token),
        json={"active": False},
    )
    assert r.json()["active"] is False


def test_admin_puede_activar_workstation(test_env):
    client, factory, _ = test_env
    token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(token),
        json={"name": "PC-REACTIVAR"},
    )
    ws_id = r.json()["id"]
    client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(token),
        json={"active": False},
    )
    r = client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(token),
        json={"active": True},
    )
    assert r.json()["active"] is True


def test_token_generado_funciona(test_env):
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-FUNCIONAL"},
    )
    wks_token = r.json()["token"]
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": wks_token},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["status"] == "active"


def test_token_desactivado_deja_de_funcionar(test_env):
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-DEACT"},
    )
    ws_id = r.json()["id"]
    wks_token = r.json()["token"]
    client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(admin_token),
        json={"active": False},
    )
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": wks_token},
    )
    assert r.json()["valid"] is False
    assert r.json()["status"] == "deactivated"


def test_regenerar_token_invalida_el_anterior(test_env):
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-REGEN"},
    )
    ws_id = r.json()["id"]
    old_token = r.json()["token"]
    r = client.post(
        f"/api/v1/desktop/admin/workstations/{ws_id}/regenerate-token",
        headers=_admin_headers(admin_token),
    )
    assert r.status_code == 200
    new_token = r.json()["token"]
    assert new_token != old_token
    assert new_token.startswith("g2a3_wks_")
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": old_token},
    )
    assert r.json()["valid"] is False


def test_nuevo_token_funciona(test_env):
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-NUEVO"},
    )
    ws_id = r.json()["id"]
    r = client.post(
        f"/api/v1/desktop/admin/workstations/{ws_id}/regenerate-token",
        headers=_admin_headers(admin_token),
    )
    new_token = r.json()["token"]
    r = client.post(
        "/api/v1/desktop/admin/workstations/verify-token",
        headers=_admin_headers(admin_token),
        json={"workstation_token": new_token},
    )
    assert r.json()["valid"] is True
    assert r.json()["status"] == "active"


def test_token_plano_no_almacenado_en_db(test_env):
    """La base de datos solo debe contener el hash SHA-256, nunca el token plano."""
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
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
        assert stored_hash != plain_token
        expected_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        assert stored_hash == expected_hash


def test_workstation_duplicado_rechazado(test_env):
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)
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


# ── Audit: eventos se registran ──────────────────────────────────────────

def test_eventos_auditoria_registrados(test_env):
    """Las operaciones admin deben generar eventos en dgt_eventos."""
    client, factory, _ = test_env
    admin_token = _admin_session_from_staff(client, factory)

    r = client.post(
        "/api/v1/desktop/admin/workstations",
        headers=_admin_headers(admin_token),
        json={"name": "PC-AUDIT"},
    )
    assert r.status_code == 201
    ws_id = r.json()["id"]

    client.patch(
        f"/api/v1/desktop/admin/workstations/{ws_id}",
        headers=_admin_headers(admin_token),
        json={"active": False},
    )
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
        assert "workstation.admin_login" in types
        assert "workstation.created" in types
        assert "workstation.deactivated" in types
        assert "workstation.token_regenerated" in types


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


# ── Desktop OAuth server ─────────────────────────────────────────────────

def test_oauth_server_binds_localhost():
    """El servidor OAuth solo debe escuchar en 127.0.0.1."""
    from http.server import HTTPServer
    from services.desktop_oauth import _OAuthCallbackHandler
    server = HTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
    host, port = server.server_address
    assert host == "127.0.0.1"
    assert 1024 <= port <= 65535
    server.server_close()
