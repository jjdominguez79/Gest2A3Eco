import hashlib
import os
from pathlib import Path

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import messaging_api
from backend.api.database import Base
from backend.api.messaging_api import get_db, router
from backend.api.messaging_models import MessagingStaff


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("MESSAGING_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("MESSAGING_CONTENT_STORAGE_DIR", str(tmp_path / "content"))
    monkeypatch.setenv("MESSAGING_PUBLIC_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("MESSAGING_APP_WEB_URL", "https://app.example.test")
    monkeypatch.delenv("MESSAGING_AZURE_CONNECTION_STRING", raising=False)
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router)

    def override_db():
        with factory() as db:
            yield db

    admin = MessagingStaff(
        external_id="admin",
        name="Administrador",
        email="admin@gestinem.es",
        role="admin",
        active=True,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[messaging_api._require_admin] = lambda: admin
    return TestClient(app, base_url="https://api.example.test")


def _payload(subject: str) -> dict:
    return {
        "subject": subject,
        "intro_text": "Hola {{nombre_cliente}},\n\nTexto configurable.",
        "closing_text": "El enlace dura {{horas_caducidad}} horas.",
    }


def test_admin_publica_correo_y_manual_sin_desplegar(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    initial = client.get("/api/v1/messaging/staff/admin/invitation-content")
    assert initial.status_code == 200
    assert initial.json()["active"]["id"] == "default"
    assert initial.json()["draft"] is None
    assert initial.json()["manual_url"] == (
        "https://api.example.test/api/v1/messaging/public/client-manual"
    )

    invalid = client.put(
        "/api/v1/messaging/staff/admin/invitation-content/draft",
        json={**_payload("Invitacion"), "intro_text": "{{variable_desconocida}}"},
    )
    assert invalid.status_code == 422

    draft = client.put(
        "/api/v1/messaging/staff/admin/invitation-content/draft",
        json=_payload("Invitacion configurable"),
    )
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"

    invalid_pdf = client.put(
        "/api/v1/messaging/staff/admin/invitation-content/manual",
        files={"manual": ("manual.pdf", b"no es pdf", "application/pdf")},
    )
    assert invalid_pdf.status_code == 422

    pdf = b"%PDF-1.7\nmanual configurable\n%%EOF"
    uploaded = client.put(
        "/api/v1/messaging/staff/admin/invitation-content/manual",
        files={"manual": ("Manual clientes.pdf", pdf, "application/pdf")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["has_custom_manual"] is True
    assert uploaded.json()["manual_size"] == len(pdf)

    published = client.post(
        "/api/v1/messaging/staff/admin/invitation-content/publish",
    )
    assert published.status_code == 200
    assert published.json()["version"] == 1
    assert published.json()["status"] == "published"

    manual = client.get("/api/v1/messaging/public/client-manual")
    assert manual.status_code == 200
    assert manual.content == pdf
    assert manual.history[0].status_code == 307
    assert manual.url.query.decode() == f"v={hashlib.sha256(pdf).hexdigest()[:12]}"
    assert manual.headers["cache-control"].startswith("no-store")
    assert manual.headers["pragma"] == "no-cache"
    assert manual.headers["x-content-version"] == "1"
    assert manual.headers["content-type"].startswith("application/pdf")

    current = client.get("/api/v1/messaging/staff/admin/invitation-content").json()
    assert current["active"]["subject"] == "Invitacion configurable"
    assert current["draft"] is None


def test_historial_restauracion_vista_previa_y_correo_prueba(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for subject in ("Primera version", "Segunda version"):
        assert client.put(
            "/api/v1/messaging/staff/admin/invitation-content/draft",
            json=_payload(subject),
        ).status_code == 200
        assert client.post(
            "/api/v1/messaging/staff/admin/invitation-content/publish",
        ).status_code == 200

    history = client.get(
        "/api/v1/messaging/staff/admin/invitation-content/history",
    ).json()
    assert [item["version"] for item in history] == [2, 1]
    assert history[0]["status"] == "published"
    assert history[1]["status"] == "archived"

    restored = client.post(
        f"/api/v1/messaging/staff/admin/invitation-content/history/{history[1]['id']}/restore",
    )
    assert restored.status_code == 200
    assert restored.json()["subject"] == "Primera version"
    assert restored.json()["status"] == "draft"

    preview = client.post(
        "/api/v1/messaging/staff/admin/invitation-content/preview",
        json=_payload("Vista previa {{nombre_cliente}}"),
    )
    assert preview.status_code == 200
    assert preview.json()["subject"] == "Vista previa Cliente de prueba"
    assert "Activar mi cuenta" in preview.json()["html"]
    assert "Consultar el manual" in preview.json()["html"]

    sent = {}

    def fake_send(to, name, url, **kwargs):
        sent.update(to=to, name=name, url=url, **kwargs)
        return True

    monkeypatch.setattr(messaging_api, "mail_configured", lambda: True)
    monkeypatch.setattr(messaging_api, "send_invitation", fake_send)
    response = client.post(
        "/api/v1/messaging/staff/admin/invitation-content/test",
        json={"email": "prueba@example.test"},
    )
    assert response.status_code == 200
    assert sent["to"] == "prueba@example.test"
    assert sent["content"].subject == "[PRUEBA] Primera version"
    assert sent["manual_url"].endswith("/public/client-manual")
