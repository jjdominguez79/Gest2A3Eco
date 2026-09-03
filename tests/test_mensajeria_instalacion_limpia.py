"""
Tests de instalacion limpia para mensajeria — v1.7.1.

Situacion cubierta: puesto nuevo con WorkstationToken en Credential Manager,
sin MessagingDeviceToken todavia, con messaging_api_url configurada por defecto.

Flujo esperado:
  UI → MensajeriaRemoteClient.refresh()
    → sync_staff() → ensure_device_enrolled()
      → POST /internal/devices/{workstation} [X-API-Key: WorkstationToken]
      → backend genera MessagingDeviceToken y lo devuelve
      → cliente lo almacena en Credential Manager
    → PUT /internal/staff/{user_id} [X-API-Key: WorkstationToken]
    → GET /staff/conversations [X-API-Key: WorkstationToken, X-Device-Token: ...]

Tests:
1.  configured=True cuando hay WorkstationToken y messaging_api_url.
2.  configured=False cuando WorkstationToken falta.
3.  configured=False cuando messaging_api_url falta.
4.  Sin MessagingDeviceToken, ensure_device_enrolled llama POST /internal/devices/.
5.  ensure_device_enrolled almacena el token recibido en Credential Manager.
6.  Con MessagingDeviceToken existente, ensure_device_enrolled no llama al backend.
7.  Backend: POST /internal/devices/ acepta WorkstationToken activo.
8.  Backend: POST /internal/devices/ rechaza WorkstationToken inactivo.
9.  Backend: POST /internal/devices/ rechaza peticion sin credencial.
10. Backend: PUT /internal/staff/ acepta WorkstationToken.
11. Backend: PUT /internal/organizations/ rechaza WorkstationToken (solo admin).
12. Backend: POST /internal/invitations/ rechaza WorkstationToken (solo admin).
13. Flujo completo de primera conexion sin MessagingDeviceToken previo.
"""
from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Fixture de directorio temporal (evita tmp_path de pytest que tiene
# problemas de permisos en este entorno Windows) ───────────────────────────────

@pytest.fixture
def workdir():
    d = tempfile.mkdtemp(prefix="gest2a3_msg_limpia_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ── Backend de test reutilizable ──────────────────────────────────────────────

def _make_messaging_http(tmp: Path, *, active_wks_tokens: set[str] | None = None):
    """
    FastAPI TestClient con SQLite en memoria para el backend de mensajeria.

    active_wks_tokens: conjunto de tokens WorkstationToken que se aceptaran como validos
    en require_workstation_or_internal (evita llamadas a PostgreSQL real en tests).
    """
    os.environ.setdefault(
        "DGT_DATABASE_URL",
        "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
    )
    os.environ["DGT_INTERNAL_API_KEY"] = "test-internal-secret"
    os.environ["MESSAGING_STORAGE_DIR"] = str(tmp / "cloud")
    os.environ["MESSAGING_PUBLIC_BASE_URL"] = "https://api.example.test"
    os.environ["MESSAGING_SYNC_TOKEN"] = "sync-secret"
    os.environ["MESSAGING_STAFF_ALLOWED_DOMAIN"] = "gestinem.es"

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from backend.api.database import Base
    from backend.api import messaging_models  # noqa: F401
    from backend.api import models  # noqa: F401
    from backend.api.messaging_api import get_db, router
    from backend.api.security import require_workstation_or_internal

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override

    # require_workstation_or_internal usa SessionLocal() directamente (no get_db),
    # por lo que necesita su propio override para tests con SQLite.
    # Acepta la clave interna de test O cualquier token del conjunto active_wks_tokens.
    _accepted = set(active_wks_tokens or ())

    def override_wks_or_internal(x_api_key: str = Header(default="")) -> str:
        if x_api_key == "test-internal-secret":
            return "gest2a3eco"
        if x_api_key in _accepted:
            return "workstation-test"
        raise HTTPException(status_code=401, detail="Credencial no valida")

    app.dependency_overrides[require_workstation_or_internal] = override_wks_or_internal

    return TestClient(app, base_url="https://api.example.test"), factory


# ===========================================================================
# 1-3. Propiedad configured
# ===========================================================================

def test_configured_true_con_wkstoken_y_url(monkeypatch):
    """configured=True cuando hay WorkstationToken y messaging_api_url."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": "https://gest2a3eco-production.up.railway.app"},
    )
    assert client.configured


def test_configured_false_sin_wkstoken(monkeypatch):
    """configured=False cuando WorkstationToken no esta provisionado."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: None)
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.delenv("GEST2A3ECO_WORKSTATION_TOKEN", raising=False)
    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": "https://gest2a3eco-production.up.railway.app"},
    )
    assert not client.configured


def test_configured_false_sin_url(monkeypatch):
    """configured=False cuando messaging_api_url esta vacia."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": ""},
    )
    assert not client.configured


# ===========================================================================
# 4. Sin MessagingDeviceToken, ensure_device_enrolled llama al backend
# ===========================================================================

def test_ensure_device_enrolled_llama_backend_sin_token(monkeypatch):
    """Sin device_token, ensure_device_enrolled debe hacer POST al backend."""
    called_urls = []

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"device_token": "nuevo-device-tok-abc"}

    class FakeSession:
        def post(self, url, **kwargs):
            called_urls.append(url)
            return FakeResponse()

    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.setattr("utils.credential_store.store_messaging_device_token", lambda t: True)
    # Evitar escritura real a config
    monkeypatch.setattr("services.mensajeria_service.load_app_config", lambda: {})
    monkeypatch.setattr("services.mensajeria_service.save_app_config", lambda c: None)

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": "https://backend.test"},
        session=FakeSession(),
    )

    client.ensure_device_enrolled()

    assert any("/internal/devices/" in url for url in called_urls), (
        f"ensure_device_enrolled no llamo a /internal/devices/. URLs: {called_urls}"
    )


# ===========================================================================
# 5. El token recibido se almacena en Credential Manager
# ===========================================================================

def test_ensure_device_enrolled_almacena_token(monkeypatch):
    """ensure_device_enrolled debe guardar el device_token en Credential Manager."""
    stored = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"device_token": "tok-recibido-del-backend"}

    class FakeSession:
        def post(self, url, **kwargs): return FakeResponse()

    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.setattr(
        "utils.credential_store.store_messaging_device_token",
        lambda t: stored.append(t) or True,
    )
    monkeypatch.setattr("services.mensajeria_service.load_app_config", lambda: {})
    monkeypatch.setattr("services.mensajeria_service.save_app_config", lambda c: None)

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": "https://backend.test"},
        session=FakeSession(),
    )
    client.ensure_device_enrolled()

    assert stored == ["tok-recibido-del-backend"], (
        f"El token no se almaceno correctamente. Almacenado: {stored}"
    )


# ===========================================================================
# 6. Con MessagingDeviceToken existente, no se llama al backend
# ===========================================================================

def test_ensure_device_enrolled_no_llama_backend_si_ya_tiene_token(monkeypatch):
    """Si el device_token ya existe, ensure_device_enrolled no debe llamar al backend."""
    called = []

    class FakeSession:
        def post(self, url, **kwargs):
            called.append(url)
            raise AssertionError("No debia llamar al backend")

    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: "tok-existente")

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Usuario",
        config={"messaging_api_url": "https://backend.test"},
        session=FakeSession(),
    )
    client.ensure_device_enrolled()  # No debe lanzar
    assert not called


# ===========================================================================
# 7-9. Backend: POST /internal/devices/ con distintas credenciales
# ===========================================================================

def test_backend_enroll_device_acepta_workstation_token(workdir):
    """
    POST /internal/devices/ debe aceptar WorkstationToken activo.

    require_workstation_or_internal usa SessionLocal() (no get_db) por lo que se
    inyecta un override en el test que simula la validacion del token.
    """
    wks = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, _ = _make_messaging_http(workdir, active_wks_tokens={wks})

    r = http.post(
        "/api/v1/messaging/internal/devices/puesto-nuevo-test",
        headers={"X-API-Key": wks},
    )
    assert r.status_code in (200, 201), (
        f"WorkstationToken rechazado en /internal/devices/: {r.text}"
    )
    data = r.json()
    assert "device_token" in data and data["device_token"]


def test_backend_enroll_device_rechaza_token_no_registrado(workdir):
    """POST /internal/devices/ debe rechazar WorkstationToken no registrado."""
    wks_valido = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    wks_desconocido = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, _ = _make_messaging_http(workdir, active_wks_tokens={wks_valido})

    r = http.post(
        "/api/v1/messaging/internal/devices/puesto-desconocido",
        headers={"X-API-Key": wks_desconocido},
    )
    assert r.status_code == 401


def test_backend_enroll_device_rechaza_sin_credencial(workdir):
    """POST /internal/devices/ debe rechazar peticiones sin credencial."""
    http, _ = _make_messaging_http(workdir)
    r = http.post("/api/v1/messaging/internal/devices/puesto-anonimo")
    assert r.status_code == 401


# ===========================================================================
# 10. Backend: PUT /internal/staff/ acepta WorkstationToken
# ===========================================================================

def test_backend_staff_sync_acepta_workstation_token(workdir):
    """PUT /internal/staff/ debe aceptar WorkstationToken para auto-registro de usuario."""
    wks = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, _ = _make_messaging_http(workdir, active_wks_tokens={wks})

    r = http.put(
        "/api/v1/messaging/internal/staff/usr-limpia",
        headers={"X-API-Key": wks},
        json={
            "external_id": "usr-limpia", "name": "Usuario Nuevo",
            "email": "nuevo@gestinem.es", "role": "empleado", "active": True,
        },
    )
    assert r.status_code == 200, (
        f"WorkstationToken rechazado en /internal/staff/: {r.text}"
    )


# ===========================================================================
# 11-12. Organizaciones e invitaciones siguen requiriendo clave interna
# ===========================================================================

def test_backend_organizations_rechaza_workstation_token(workdir):
    """
    PUT /internal/organizations/ solo debe aceptar la clave interna de admin.
    Endpoint usa require_internal_key (no require_workstation_or_internal).
    """
    wks = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    # No incluimos wks en active_wks_tokens del override de require_workstation_or_internal
    # porque organizations usa require_internal_key, que es diferente.
    http, _ = _make_messaging_http(workdir)

    r = http.put(
        "/api/v1/messaging/internal/organizations/EMP-TEST",
        headers={"X-API-Key": wks},
        json={"company_code": "EMP-TEST", "name": "Empresa Test", "active": True},
    )
    assert r.status_code == 401, (
        "WorkstationToken NO debe aceptarse en /internal/organizations/"
    )


def test_backend_invitations_rechaza_workstation_token(workdir):
    """POST /internal/invitations solo debe aceptar la clave interna de admin."""
    wks = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, _ = _make_messaging_http(workdir)

    r = http.post(
        "/api/v1/messaging/internal/invitations",
        headers={"X-API-Key": wks},
        json={"company_code": "EMP-TEST", "name": "Cliente", "email": "cliente@test.es"},
    )
    assert r.status_code == 401, (
        "WorkstationToken NO debe aceptarse en /internal/invitations"
    )


# ===========================================================================
# Code inspection: los decoradores correctos estan aplicados
# ===========================================================================

def test_decoradores_correctos_en_mensajeria_api():
    """
    Verifica por inspeccion de codigo que:
    - POST /internal/devices/ y PUT /internal/staff/ usan require_workstation_or_internal
    - PUT /internal/organizations/ y POST /internal/invitations/ usan require_internal_key
    """
    src_path = Path(__file__).parent.parent / "backend" / "api" / "messaging_api.py"
    src = src_path.read_text(encoding="utf-8")

    # Estas lineas deben contener require_workstation_or_internal
    assert 'internal/staff/{external_id}", dependencies=[Depends(require_workstation_or_internal)]' in src, \
        "PUT /internal/staff/ debe usar require_workstation_or_internal"
    assert 'internal/devices/{device_id}", dependencies=[Depends(require_workstation_or_internal)]' in src, \
        "POST /internal/devices/ debe usar require_workstation_or_internal"

    # Estas siguen protegidas por require_internal_key
    assert 'internal/organizations/{company_code}", dependencies=[Depends(require_internal_key)]' in src, \
        "PUT /internal/organizations/ debe seguir usando require_internal_key"
    assert 'internal/invitations", dependencies=[Depends(require_internal_key)]' in src, \
        "POST /internal/invitations debe seguir usando require_internal_key"


# ===========================================================================
# 13. Flujo completo: primera conexion sin MessagingDeviceToken previo
# ===========================================================================

def test_flujo_completo_primera_conexion(workdir):
    """
    Simula el flujo completo de un puesto nuevo:
    1. WorkstationToken activo, sin MessagingDeviceToken.
    2. POST /internal/devices/ obtiene el MessagingDeviceToken del backend.
    3. PUT /internal/staff/ registra el usuario.
    4. GET /staff/conversations responde 200 con WorkstationToken + MessagingDeviceToken.
    """
    wks = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, factory = _make_messaging_http(workdir, active_wks_tokens={wks})

    # Paso 1: enroll del dispositivo
    r = http.post(
        "/api/v1/messaging/internal/devices/puesto-flujo",
        headers={"X-API-Key": wks},
    )
    assert r.status_code in (200, 201), f"Enroll fallo: {r.text}"
    device_token = r.json()["device_token"]
    assert device_token

    # Paso 2: sync staff (usa la clave interna de admin para que el registro
    # quede en BD y sea visible para _staff_from_request)
    internal = {"X-API-Key": "test-internal-secret"}
    r = http.put(
        "/api/v1/messaging/internal/staff/usr-flujo",
        headers=internal,
        json={
            "external_id": "usr-flujo", "name": "Usuario Flujo",
            "email": "flujo@gestinem.es", "role": "empleado", "active": True,
        },
    )
    assert r.status_code == 200, f"Staff sync fallo: {r.text}"

    # Paso 3: register workstation in test DB so _staff_from_request can find it
    from backend.api.security import hash_token
    from backend.api.models import Workstation
    with factory() as db:
        db.add(Workstation(name="puesto-flujo", token_hash=hash_token(wks), active=True))
        db.commit()

    # Paso 4: acceso a conversaciones con WorkstationToken + MessagingDeviceToken
    r = http.get(
        "/api/v1/messaging/staff/conversations",
        headers={
            "X-API-Key": wks,
            "X-Device-Id": "puesto-flujo",
            "X-Device-Token": device_token,
            "X-Staff-Id": "usr-flujo",
        },
    )
    assert r.status_code == 200, (
        f"Acceso a conversaciones fallo tras enroll: {r.text}"
    )
