"""
Tests de autenticacion de mensajeria con WorkstationToken (release 1.6.3).

Requisitos verificados:
  1. MensajeriaRemoteClient usa WorkstationToken como credencial.
  2. MessagingApiKey no tiene prioridad ni se usa como fallback.
  3. Sin WorkstationToken → configured=False y error claro en _url().
  4. MessagingDeviceToken sigue presente en cabeceras cuando existe.
  5. Endpoints /staff/* de mensajeria aceptan WorkstationToken.
  6. Credenciales internas (/internal/*) y sync (/sync/*) siguen protegidas.
  7. messaging_api_key legacy no se persiste en disco ni se lee desde env.
"""
from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from pathlib import Path

import pytest


# ── Fixture de directorio temporal sin depender del tmp_path de pytest ────────

@pytest.fixture
def workdir():
    d = tempfile.mkdtemp(prefix="gest2a3_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mensajeria_client(monkeypatch, *, wks_token="g2a3_wks_test", device_token="dev-tok-abc"):
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: wks_token)
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: device_token)
    from services.mensajeria_service import MensajeriaRemoteClient
    return MensajeriaRemoteClient(
        user_id=1, user_name="Test",
        config={"messaging_api_url": "https://example.test"},
    )


def _make_messaging_http(tmp: Path):
    """FastAPI TestClient con SQLite en memoria para probar el backend de mensajeria."""
    os.environ.setdefault(
        "DGT_DATABASE_URL",
        "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
    )
    os.environ["DGT_INTERNAL_API_KEY"] = "test-internal-secret"
    os.environ["MESSAGING_STORAGE_DIR"] = str(tmp / "cloud")
    os.environ["MESSAGING_PUBLIC_BASE_URL"] = "https://api.example.test"
    os.environ["MESSAGING_SYNC_TOKEN"] = "sync-secret"
    os.environ["MESSAGING_STAFF_ALLOWED_DOMAIN"] = "gestinem.es"

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from backend.api.database import Base
    from backend.api import messaging_models  # noqa: F401 – registra tablas messaging
    from backend.api import models  # noqa: F401 – registra tabla Workstation
    from backend.api.messaging_api import get_db, router

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
    return TestClient(app, base_url="https://api.example.test"), factory


def _make_messaging_http_with_wks(tmp: Path, wks_token: str):
    """Como _make_messaging_http pero acepta un WorkstationToken especifico en require_workstation_or_internal."""
    http, factory = _make_messaging_http(tmp)
    from fastapi import Header, HTTPException
    from backend.api.security import require_workstation_or_internal

    _app = http.app

    def override_wks(x_api_key: str = Header(default="")) -> str:
        if x_api_key == "test-internal-secret":
            return "gest2a3eco"
        if x_api_key == wks_token:
            return "workstation-test"
        raise HTTPException(status_code=401, detail="Credencial no valida")

    _app.dependency_overrides[require_workstation_or_internal] = override_wks
    return http, factory


# ── 1. MensajeriaRemoteClient usa WorkstationToken ───────────────────────────

def test_cliente_usa_workstation_token(monkeypatch):
    """api_key debe ser el WorkstationToken, no ninguna otra credencial."""
    client = _make_mensajeria_client(monkeypatch, wks_token="g2a3_wks_abc123")
    assert client.api_key == "g2a3_wks_abc123"
    assert client.api_key.startswith("g2a3_wks_")


# ── 2. MessagingApiKey no se usa como fallback ────────────────────────────────

def test_messaging_api_key_no_es_fallback(monkeypatch):
    """
    Aunque MessagingApiKey existiera en el almacen, no debe usarse.
    MensajeriaRemoteClient no importa ni llama a get_messaging_api_key().
    """
    called = []

    import utils.credential_store as cstore
    monkeypatch.setattr(cstore, "get_workstation_token", lambda: "g2a3_wks_real")
    monkeypatch.setattr(cstore, "get_messaging_device_token", lambda: None)
    monkeypatch.setattr(cstore, "get_messaging_api_key", lambda: called.append(True) or "msg-legacy")

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Test",
        config={"messaging_api_url": "https://example.test"},
    )

    assert not called, "get_messaging_api_key() fue llamada – MessagingApiKey NO debe usarse"
    assert client.api_key == "g2a3_wks_real"


# ── 3. Sin WorkstationToken → configured=False y error claro ─────────────────

def test_sin_workstation_token_configured_es_false(monkeypatch):
    """configured debe ser False cuando no hay WorkstationToken."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: None)
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.delenv("GEST2A3ECO_WORKSTATION_TOKEN", raising=False)

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Test",
        config={"messaging_api_url": "https://example.test"},
    )
    assert not client.configured


def test_sin_workstation_token_url_lanza_error_con_mensaje_claro(monkeypatch):
    """_url() debe lanzar ValueError mencionando WorkstationToken."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: None)
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.delenv("GEST2A3ECO_WORKSTATION_TOKEN", raising=False)

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Test",
        config={"messaging_api_url": "https://example.test"},
    )
    with pytest.raises(ValueError, match="WorkstationToken"):
        client._url("/staff/conversations")


def test_workstation_token_desde_env_var(monkeypatch):
    """Si keyring no tiene token pero GEST2A3ECO_WORKSTATION_TOKEN esta en env, debe usarlo."""
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: None)
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    monkeypatch.setenv("GEST2A3ECO_WORKSTATION_TOKEN", "g2a3_wks_env_token")

    from services.mensajeria_service import MensajeriaRemoteClient
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Test",
        config={"messaging_api_url": "https://example.test"},
    )
    assert client.api_key == "g2a3_wks_env_token"
    assert client.configured


# ── 4. MessagingDeviceToken sigue en cabeceras ────────────────────────────────

def test_messaging_device_token_presente_en_cabeceras(monkeypatch):
    """X-Device-Token debe enviarse si MessagingDeviceToken esta en el almacen."""
    client = _make_mensajeria_client(monkeypatch, wks_token="g2a3_wks_x", device_token="device-xyz")
    headers = client._headers()
    assert headers["X-Device-Token"] == "device-xyz"
    assert headers["X-API-Key"] == "g2a3_wks_x"


def test_messaging_device_token_ausente_no_falla(monkeypatch):
    """Sin MessagingDeviceToken el cliente sigue construyendose sin error."""
    client = _make_mensajeria_client(monkeypatch, wks_token="g2a3_wks_x", device_token=None)
    headers = client._headers()
    assert headers.get("X-Device-Token", "") == ""
    assert headers["X-API-Key"] == "g2a3_wks_x"


# ── 5. Endpoints /staff/* aceptan WorkstationToken ───────────────────────────

def test_endpoint_staff_acepta_workstation_token(workdir):
    """GET /staff/conversations debe responder 200 cuando se autentica con WorkstationToken."""
    http, factory = _make_messaging_http(workdir)
    internal = {"X-API-Key": "test-internal-secret"}

    r = http.put(
        "/api/v1/messaging/internal/staff/usr-wks1", headers=internal,
        json={
            "external_id": "usr-wks1", "name": "WksUser",
            "email": "wks@gestinem.es", "role": "empleado",
            "active": True, "channels": ["laboral"],
        },
    )
    assert r.status_code == 200, r.text

    r = http.post("/api/v1/messaging/internal/devices/puesto-wks1", headers=internal)
    assert r.status_code in (200, 201), r.text
    device_token = r.json()["device_token"]

    wks_token = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    from backend.api.security import hash_token
    from backend.api.models import Workstation
    with factory() as db:
        db.add(Workstation(name="puesto-wks1", token_hash=hash_token(wks_token), active=True))
        db.commit()

    r = http.get("/api/v1/messaging/staff/conversations", headers={
        "X-API-Key": wks_token,
        "X-Device-Id": "puesto-wks1",
        "X-Device-Token": device_token,
        "X-Staff-Id": "usr-wks1",
    })
    assert r.status_code == 200, f"WorkstationToken rechazado en /staff/*: {r.text}"


def test_workstation_token_inactivo_rechazado(workdir):
    """Un WorkstationToken cuyo registro esta inactivo debe ser rechazado."""
    http, factory = _make_messaging_http(workdir)
    internal = {"X-API-Key": "test-internal-secret"}

    http.put(
        "/api/v1/messaging/internal/staff/usr-wks2", headers=internal,
        json={"external_id": "usr-wks2", "name": "WksUser2", "email": "wks2@gestinem.es",
              "role": "empleado", "active": True},
    )
    r = http.post("/api/v1/messaging/internal/devices/puesto-wks2", headers=internal)
    device_token = r.json()["device_token"]

    wks_token = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    from backend.api.security import hash_token
    from backend.api.models import Workstation
    with factory() as db:
        db.add(Workstation(name="puesto-wks2", token_hash=hash_token(wks_token), active=False))
        db.commit()

    r = http.get("/api/v1/messaging/staff/conversations", headers={
        "X-API-Key": wks_token,
        "X-Device-Id": "puesto-wks2",
        "X-Device-Token": device_token,
        "X-Staff-Id": "usr-wks2",
    })
    assert r.status_code == 401


# ── 6. Credenciales internas y sync siguen protegidas ────────────────────────

def test_sync_token_erroneo_rechazado(workdir):
    """GET /sync/attachments/pending debe devolver 401 con token sync incorrecto."""
    http, _ = _make_messaging_http(workdir)
    r = http.get("/api/v1/messaging/sync/attachments/pending", headers={"X-Sync-Token": "wrong"})
    assert r.status_code == 401


def test_sync_token_correcto_aceptado(workdir):
    """GET /sync/attachments/pending debe aceptar el token sync correcto."""
    http, _ = _make_messaging_http(workdir)
    r = http.get("/api/v1/messaging/sync/attachments/pending", headers={"X-Sync-Token": "sync-secret"})
    assert r.status_code == 200


def test_internal_endpoint_rechaza_workstation_token(workdir):
    """
    PUT /internal/organizations/* y POST /internal/invitations solo aceptan la clave
    interna de admin. Son operaciones de administracion (alta de empresa, invitacion a
    cliente) que el escritorio no debe poder hacer autonomamente.

    PUT /internal/staff/* y POST /internal/devices/* SI aceptan WorkstationToken porque
    son operaciones de auto-registro que el puesto hace por si mismo en el primer inicio.
    """
    http, factory = _make_messaging_http(workdir)
    wks_token = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    from backend.api.security import hash_token
    from backend.api.models import Workstation
    with factory() as db:
        db.add(Workstation(name="puesto-admin-test", token_hash=hash_token(wks_token), active=True))
        db.commit()

    # Organizations y invitations rechazan WorkstationToken
    r = http.put(
        "/api/v1/messaging/internal/organizations/EMP001",
        headers={"X-API-Key": wks_token},
        json={"company_code": "EMP001", "name": "Empresa Test", "active": True},
    )
    assert r.status_code == 401, "WorkstationToken no debe aceptarse en /internal/organizations/"

    r = http.post(
        "/api/v1/messaging/internal/invitations",
        headers={"X-API-Key": wks_token},
        json={"company_code": "EMP001", "name": "Cliente", "email": "cliente@test.es"},
    )
    assert r.status_code == 401, "WorkstationToken no debe aceptarse en /internal/invitations"


def test_internal_staff_y_devices_aceptan_workstation_token(workdir):
    """
    PUT /internal/staff/* y POST /internal/devices/* deben aceptar WorkstationToken.
    Son operaciones de auto-registro que el puesto realiza en el primer inicio.

    Nota de implementacion: require_workstation_or_internal usa SessionLocal() directamente,
    por lo que se inyecta un override en el test para evitar acceso a PostgreSQL real.
    """
    wks_token = f"g2a3_wks_{secrets.token_urlsafe(32)}"
    http, _ = _make_messaging_http_with_wks(workdir, wks_token)

    # Staff sync acepta WorkstationToken
    r = http.put(
        "/api/v1/messaging/internal/staff/usr-self",
        headers={"X-API-Key": wks_token},
        json={
            "external_id": "usr-self", "name": "Self User",
            "email": "self@gestinem.es", "role": "empleado", "active": True,
        },
    )
    assert r.status_code == 200, f"WorkstationToken rechazado en /internal/staff/: {r.text}"

    # Device enrollment acepta WorkstationToken
    r = http.post(
        "/api/v1/messaging/internal/devices/puesto-self-reg",
        headers={"X-API-Key": wks_token},
    )
    assert r.status_code in (200, 201), f"WorkstationToken rechazado en /internal/devices/: {r.text}"
    assert "device_token" in r.json()


def test_credencial_aleatoria_rechazada_en_staff(workdir):
    """Una clave aleatoria (no WorkstationToken ni internal key) es rechazada en /staff/*."""
    http, factory = _make_messaging_http(workdir)
    internal = {"X-API-Key": "test-internal-secret"}
    http.put(
        "/api/v1/messaging/internal/staff/usr-rand", headers=internal,
        json={"external_id": "usr-rand", "name": "R", "email": "r@gestinem.es",
              "role": "empleado", "active": True},
    )
    r = http.post("/api/v1/messaging/internal/devices/puesto-rand", headers=internal)
    device_token = r.json()["device_token"]

    r = http.get("/api/v1/messaging/staff/conversations", headers={
        "X-API-Key": "not-a-valid-key",
        "X-Device-Id": "puesto-rand",
        "X-Device-Token": device_token,
        "X-Staff-Id": "usr-rand",
    })
    assert r.status_code == 401


# ── 7. messaging_api_key legacy no persiste ni se lee desde env ───────────────

def test_messaging_api_key_no_se_persiste_en_disco(workdir, monkeypatch):
    """save_app_config no debe escribir messaging_api_key en el fichero JSON."""
    import json
    config_path = workdir / "config.local.json"
    import utils.utilidades as utils_mod
    monkeypatch.setattr(utils_mod, "_config_local_path", lambda: config_path)

    from utils.utilidades import save_app_config
    save_app_config({"messaging_api_key": "should-not-appear", "messaging_api_url": "https://x.test"})

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "messaging_api_key" not in saved, "messaging_api_key no debe persistirse en disco"
    assert saved.get("messaging_api_url") == "https://x.test"


def test_messaging_api_key_no_leido_desde_env(monkeypatch):
    """GEST2A3ECO_MESSAGING_API_KEY ya no mapea a messaging_api_key en config."""
    monkeypatch.setenv("GEST2A3ECO_MESSAGING_API_KEY", "env-leaked-key")
    import utils.utilidades as utils_mod
    monkeypatch.setattr(utils_mod, "_load_json_file", lambda _: {})
    from utils.utilidades import load_app_config
    cfg = load_app_config()
    assert cfg.get("messaging_api_key") != "env-leaked-key", (
        "GEST2A3ECO_MESSAGING_API_KEY no debe mapearse a messaging_api_key"
    )


def test_delete_messaging_api_key_llamado_en_startup(monkeypatch):
    """
    delete_messaging_api_key debe existir en credential_store y ser invocable
    (se llama al arrancar para purgar la credencial legacy del Credential Manager).
    """
    from utils.credential_store import delete_messaging_api_key
    import utils.credential_store as cstore
    monkeypatch.setattr(cstore, "_keyring_available", lambda: False)
    delete_messaging_api_key()  # no debe lanzar
