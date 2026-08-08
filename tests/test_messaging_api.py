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

from backend.dgt_api.database import Base
from backend.dgt_api import messaging_api
from backend.dgt_api.messaging_api import get_db, router
from backend.dgt_api import messaging_models  # noqa: F401


def _client(tmp_path: Path):
    os.environ["DGT_INTERNAL_API_KEY"] = "test-secret"
    os.environ["MESSAGING_STORAGE_DIR"] = str(tmp_path / "cloud")
    os.environ["MESSAGING_PUBLIC_BASE_URL"] = "https://mensajes.example.test"
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
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
    return TestClient(app)


def test_chat_privado_transporte_local_y_auditoria_descarga(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    for staff_id, name in (("7", "Titular"), ("8", "Empleado")):
        assert client.put(
            f"/api/v1/messaging/internal/staff/{staff_id}", headers=internal,
            json={"external_id": staff_id, "name": name, "role": "empleado", "active": True},
        ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/puesto-1", headers=internal,
    ).json()
    assert client.put(
        "/api/v1/messaging/internal/organizations/E00001", headers=internal,
        json={"company_code": "E00001", "name": "Cliente Uno", "private_owner_external_id": "7"},
    ).status_code == 200
    invited = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={"company_code": "E00001", "name": "Ana", "email": "ana@example.test"},
    ).json()
    token = invited["url"].split("invite=", 1)[1]
    accepted = client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": token, "password": "segura-12345"},
    )
    assert accepted.status_code == 200
    client_auth = {"Authorization": f"Bearer {accepted.json()['token']}"}
    conversations = client.get(
        "/api/v1/messaging/client/conversations", headers=client_auth,
    ).json()
    general = next(row for row in conversations if row["kind"] == "general")

    sent = client.post(
        f"/api/v1/messaging/client/conversations/{general['id']}/messages",
        headers=client_auth,
        data={"body": "Adjunto factura", "idempotency_key": "client-1"},
        files={"files": ("factura.pdf", b"%PDF-demo", "application/pdf")},
    )
    assert sent.status_code == 200
    incoming_id = sent.json()["attachments"][0]["id"]
    device_headers = {"X-Device-Id": "puesto-1", "X-Device-Token": device["device_token"]}
    staff7 = {**internal, **device_headers, "X-Staff-Id": "7"}
    staff8 = {**internal, **device_headers, "X-Staff-Id": "8"}
    visible7 = client.get("/api/v1/messaging/staff/conversations", headers=staff7).json()
    assert len(visible7) == 2
    assert next(row for row in visible7 if row["id"] == general["id"])["unread_count"] == 1
    assert len(client.get("/api/v1/messaging/staff/conversations", headers=staff8).json()) == 1
    assert client.post(
        f"/api/v1/messaging/staff/conversations/{general['id']}/read", headers=staff7,
    ).status_code == 200
    visible7 = client.get("/api/v1/messaging/staff/conversations", headers=staff7).json()
    assert next(row for row in visible7 if row["id"] == general["id"])["unread_count"] == 0

    assert client.post(
        f"/api/v1/messaging/staff/attachments/{incoming_id}/claim",
        headers=staff7, data={"workstation": "puesto-1"},
    ).status_code == 200
    content = client.get(
        f"/api/v1/messaging/staff/attachments/{incoming_id}/content",
        headers=staff7, params={"workstation": "puesto-1"},
    )
    assert content.content == b"%PDF-demo"
    digest = __import__("hashlib").sha256(content.content).hexdigest()
    assert client.post(
        f"/api/v1/messaging/staff/attachments/{incoming_id}/confirm-local",
        headers=staff7, data={"workstation": "puesto-1", "sha256": digest},
    ).status_code == 200
    assert client.get("/api/v1/messaging/staff/attachments/pending", headers=staff7).json() == []

    outgoing = client.post(
        f"/api/v1/messaging/staff/conversations/{general['id']}/messages",
        headers=staff7, data={"body": "Documento", "idempotency_key": "staff-1"},
        files={"files": ("respuesta.pdf", b"respuesta", "application/pdf")},
    )
    outgoing_id = outgoing.json()["attachments"][0]["id"]
    assert outgoing.json()["attachments"][0]["expires_at"]
    assert client.get(
        f"/api/v1/messaging/client/attachments/{outgoing_id}", headers=client_auth,
    ).content == b"respuesta"
    audit = client.get(
        f"/api/v1/messaging/staff/attachments/{outgoing_id}/downloads", headers=staff7,
    ).json()
    assert len(audit) == 1 and audit[0]["client_name"] == "Ana"

    reset_urls = []
    monkeypatch.setattr(messaging_api, "mail_configured", lambda: True)
    monkeypatch.setattr(
        messaging_api, "send_password_reset",
        lambda _to, _name, url: reset_urls.append(url),
    )
    forgotten = client.post(
        "/api/v1/messaging/auth/forgot-password",
        json={"email": "ana@example.test"},
    )
    assert forgotten.status_code == 202 and reset_urls
    reset_token = reset_urls[0].split("reset=", 1)[1]
    changed = client.post(
        "/api/v1/messaging/auth/reset-password",
        json={"token": reset_token, "password": "nueva-segura-6789"},
    )
    assert changed.status_code == 200
    assert client.post(
        "/api/v1/messaging/auth/login",
        json={"email": "ana@example.test", "password": "segura-12345"},
    ).status_code == 401
    assert client.post(
        "/api/v1/messaging/auth/login",
        json={"email": "ana@example.test", "password": "nueva-segura-6789"},
    ).status_code == 200
