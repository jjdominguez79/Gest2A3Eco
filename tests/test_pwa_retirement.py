"""
Pruebas de regresion para la retirada de la PWA heredada de mensajeria.

Verifica que:
- /mensajes responde 410 y no HTML de aplicacion
- /equipo/mensajes responde 410
- Los service workers transitorios limpian cache y se desregistran
- No se sirven manifests de mensajeria
- No existen endpoints Web Push/VAPID
- La configuracion no contiene VAPID
- No se generan URLs hacia /mensajes ni /equipo/mensajes
- El portal DGT sigue funcionando
"""
from __future__ import annotations

import os
import re

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base


def _make_app_client(tmp_path):
    """Construye un TestClient de la aplicacion FastAPI completa."""
    from backend.api.app import app, get_db

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app, raise_server_exceptions=True)


# ── Rutas PWA retiradas ───────────────────────────────────────────────────────

def test_mensajes_devuelve_410(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/mensajes")
    assert resp.status_code == 410
    assert "mensajeria web" in resp.text.lower() or "retirada" in resp.text.lower()
    # No debe contener HTML de aplicacion
    assert "<html" not in resp.text.lower()
    assert "manifest" not in resp.text.lower()


def test_equipo_mensajes_devuelve_410(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/equipo/mensajes")
    assert resp.status_code == 410
    assert "<html" not in resp.text.lower()


def test_mensajes_no_sirve_manifest(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/mensajes")
    assert "webmanifest" not in resp.text.lower()
    assert "manifest" not in resp.text.lower()


# ── Service workers de retirada ───────────────────────────────────────────────

def test_mensajes_sw_sirve_script_de_retirada(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/mensajes-sw.js")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers.get("content-type", "")
    body = resp.text
    # Debe desregistrarse y no cachear nada
    assert "unregister" in body
    assert "caches.delete" in body or "caches.keys" in body
    # No debe registrar rutas /mensajes
    assert "CACHE_NAME" not in body or "gestinem-messaging-" not in body
    # No debe instalarse como PWA
    assert "start_url" not in body
    # No cache
    assert "no-cache" in resp.headers.get("cache-control", "").lower()


def test_equipo_mensajes_sw_sirve_script_de_retirada(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/equipo/mensajes-sw.js")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers.get("content-type", "")
    body = resp.text
    assert "unregister" in body


# ── Manifests de mensajeria eliminados ───────────────────────────────────────

def test_messaging_webmanifest_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/static/messaging.webmanifest")
    assert resp.status_code == 404


def test_staff_messaging_webmanifest_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/static/staff-messaging.webmanifest")
    assert resp.status_code == 404


# ── Endpoints Web Push/VAPID eliminados ──────────────────────────────────────

def test_staff_push_config_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/api/v1/messaging/staff/push/config")
    assert resp.status_code in (404, 405)


def test_staff_push_subscriptions_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.post("/api/v1/messaging/staff/push/subscriptions", json={})
    assert resp.status_code in (404, 405)


def test_staff_push_test_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.post("/api/v1/messaging/staff/push/test")
    assert resp.status_code in (404, 405)


def test_client_push_config_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/api/v1/messaging/client/push/config")
    assert resp.status_code in (404, 405)


def test_client_push_subscriptions_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.post("/api/v1/messaging/client/push/subscriptions", json={})
    assert resp.status_code in (404, 405)


def test_client_push_test_no_existe(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.post("/api/v1/messaging/client/push/test")
    assert resp.status_code in (404, 405)


# ── Configuracion sin VAPID ───────────────────────────────────────────────────

def test_config_no_tiene_campos_vapid():
    from backend.api.config import Settings
    fields = {f.name for f in Settings.__dataclass_fields__.values()}
    assert "messaging_vapid_public_key" not in fields
    assert "messaging_vapid_private_key" not in fields
    assert "messaging_vapid_subject" not in fields


def test_get_settings_no_lee_vapid_env(monkeypatch):
    """get_settings() no debe fallar ni exponer VAPID aunque la variable exista."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql://test@localhost/test")
    monkeypatch.setenv("MESSAGING_VAPID_PUBLIC_KEY", "fake-key")
    from backend.api.config import get_settings
    cfg = get_settings()
    assert not hasattr(cfg, "messaging_vapid_public_key")
    assert not hasattr(cfg, "messaging_vapid_private_key")


# ── URLs de mensajeria no generadas ──────────────────────────────────────────

def test_invitacion_usa_deep_link_flutter_y_no_pwa():
    """La invitacion se entrega a Flutter sin restaurar rutas de la PWA."""
    import inspect
    from backend.api import messaging_api
    source = inspect.getsource(messaging_api.create_invitation)
    assert "background.add_task(send_invitation" in source
    assert '_app_deep_link("invite", token)' in source
    assert '_public_app_link("invite", token)' in source
    assert "/mensajes?invite=" not in source


def test_staff_auth_callback_web_no_redirige_a_equipo_mensajes():
    """El flujo web del callback de Microsoft sin app=true no debe redirigir a /equipo/mensajes."""
    import inspect
    from backend.api import messaging_api
    source = inspect.getsource(messaging_api.staff_auth_callback)
    # No debe haber un RedirectResponse a /equipo/mensajes
    assert 'RedirectResponse("/equipo/mensajes"' not in source
    assert "RedirectResponse('/equipo/mensajes'" not in source
    # Debe levantar un error HTTP 410
    assert "410" in source


def test_mensaje_notice_no_incluye_enlace_pwa():
    """send_message_notice no debe incluir enlace a la antigua PWA /mensajes."""
    import inspect
    from backend.api.messaging_mail import send_message_notice
    source = inspect.getsource(send_message_notice)
    # El HTML del email no debe incluir enlace a /mensajes
    assert 'href' not in source or '/mensajes' not in source
    # Debe indicar que se use la aplicacion
    assert "aplicacion" in source.lower() or "app" in source.lower()


# ── Portal DGT no afectado ────────────────────────────────────────────────────

def test_health_sigue_funcionando(tmp_path):
    client = _make_app_client(tmp_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_static_portal_css_sigue_disponible(tmp_path):
    """Los recursos del portal DGT no deben haber sido eliminados."""
    from pathlib import Path
    web_dir = Path(__file__).parent.parent / "backend" / "api" / "web"
    assert (web_dir / "static" / "portal.css").exists()
    assert (web_dir / "static" / "portal.js").exists()
    assert (web_dir / "templates" / "form.html").exists()


def test_no_hay_referencia_mensajes_en_app_py():
    """app.py no debe tener rutas que sirvan HTML de la PWA de mensajeria."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "backend" / "api" / "app.py").read_text(encoding="utf-8")
    # Los unicos usos de /mensajes deben ser los 410 y los service workers de retirada
    lines_with_mensajes = [
        line.strip() for line in src.splitlines()
        if "/mensajes" in line and not line.strip().startswith("#")
    ]
    for line in lines_with_mensajes:
        # No debe servir HTML de aplicacion ni manifests
        assert "messages.html" not in line
        assert "staff_messages.html" not in line
        assert "webmanifest" not in line


def test_no_hay_archivos_pwa_en_static():
    """Los archivos PWA deben haber sido eliminados del directorio static."""
    from pathlib import Path
    static_dir = Path(__file__).parent.parent / "backend" / "api" / "web" / "static"
    pwa_files = [
        "messaging.css", "messaging.js", "messaging.webmanifest",
        "messaging-sw.js", "messaging-avatar.css", "messaging-files.css",
        "messaging-notifications.css",
        "staff-messaging.css", "staff-messaging.js", "staff-messaging.webmanifest",
        "staff-messaging-sw.js", "staff-messaging-admin.css",
        "staff-messaging-responsive.css",
        "gestinem-icon-192.png", "gestinem-icon-512.png", "gestinem-logo.png",
    ]
    for name in pwa_files:
        assert not (static_dir / name).exists(), f"Archivo PWA no eliminado: {name}"
