import os
from datetime import timedelta
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import messaging_api
from backend.api.database import Base
from backend.api.messaging_api import get_db, router
from backend.api.messaging_models import (
    MessagingAttachment,
    MessagingCampaign,
    MessagingCampaignRecipient,
    MessagingDeletionAudit,
    MessagingMessage,
)


def _api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("MESSAGING_STORAGE_DIR", str(tmp_path / "cloud"))
    monkeypatch.setenv("MESSAGING_PUBLIC_BASE_URL", "https://mensajes.example.test")
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(router)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app, base_url="https://mensajes.example.test"), factory


def _setup(tmp_path: Path, monkeypatch):
    client, factory = _api(tmp_path, monkeypatch)
    internal = {"X-API-Key": "test-secret"}
    for staff_id, role in (("admin", "admin"), ("employee", "empleado")):
        response = client.put(
            f"/api/v1/messaging/internal/staff/{staff_id}", headers=internal,
            json={
                "external_id": staff_id, "name": staff_id.title(),
                "email": f"{staff_id}@gestinem.es", "role": role,
                "active": True, "channels": ["fiscal"],
            },
        )
        assert response.status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/test-device", headers=internal,
    ).json()

    def staff_headers(staff_id):
        return {
            **internal, "X-Device-Id": "test-device",
            "X-Device-Token": device["device_token"], "X-Staff-Id": staff_id,
        }

    assert client.put(
        "/api/v1/messaging/internal/organizations/E10001", headers=internal,
        json={"company_code": "E10001", "name": "Cliente Uno"},
    ).status_code == 200
    invitation = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E10001", "name": "Maria",
            "email": "maria@example.test", "send_email": False,
        },
    ).json()
    invite_token = invitation["url"].split("invite=", 1)[1]
    accepted = client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": invite_token, "password": "contrasena-muy-segura"},
    ).json()
    client_token = accepted["token"]
    auth = {"Authorization": f"Bearer {client_token}"}
    conversation = next(
        row for row in client.get(
            "/api/v1/messaging/client/conversations", headers=auth,
        ).json() if row["kind"] == "fiscal"
    )
    return client, factory, staff_headers, auth, accepted["client"]["id"], conversation["id"]


def test_reply_soft_delete_hard_delete_y_permisos(tmp_path, monkeypatch):
    client, factory, staff_headers, auth, _client_id, conversation_id = _setup(tmp_path, monkeypatch)
    original = client.post(
        f"/api/v1/messaging/client/conversations/{conversation_id}/messages",
        headers=auth,
        data={"body": "Mensaje original", "idempotency_key": "original"},
    ).json()
    reply = client.post(
        f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
        headers=staff_headers("admin"),
        data={
            "body": "Respuesta", "idempotency_key": "reply",
            "reply_to_message_id": original["id"],
        },
    )
    assert reply.status_code == 200
    assert reply.json()["reply_to"] == {
        "id": original["id"], "author_name": "Maria",
        "body_fragment": "Mensaje original", "deleted": False,
    }

    forbidden = client.request(
        "DELETE", f"/api/v1/messaging/staff/messages/{original['id']}",
        headers=staff_headers("employee"), json={"reason": "no permitido"},
    )
    assert forbidden.status_code == 403
    deleted = client.request(
        "DELETE", f"/api/v1/messaging/staff/messages/{original['id']}",
        headers=staff_headers("admin"), json={"reason": "prueba"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["body"] == ""
    assert client.request(
        "DELETE", f"/api/v1/messaging/staff/admin/messages/{original['id']}/hard",
        headers=staff_headers("admin"), json={"reason": "dato de prueba"},
    ).status_code == 204
    with factory() as db:
        assert db.get(MessagingMessage, original["id"]) is None
        actions = set(db.scalars(select(MessagingDeletionAudit.action)))
        assert actions == {"soft_delete", "hard_delete"}


def test_hard_delete_elimina_adjunto_del_almacen(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, _client_id, conversation_id = _setup(tmp_path, monkeypatch)
    sent = client.post(
        f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
        headers=staff_headers("admin"), data={"body": "Documento", "idempotency_key": "with-file"},
        files={"files": ("prueba.pdf", b"contenido", "application/pdf")},
    ).json()
    with factory() as db:
        attachment = db.scalar(select(MessagingAttachment).where(MessagingAttachment.message_id == sent["id"]))
        stored_path = tmp_path / "cloud" / attachment.storage_key
        assert stored_path.is_file()
    assert client.request(
        "DELETE", f"/api/v1/messaging/staff/admin/messages/{sent['id']}/hard",
        headers=staff_headers("admin"), json={"reason": "prueba"},
    ).status_code == 204
    assert not stored_path.exists()


def test_grupos_miembros_campana_e_idempotencia(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, client_id, _conversation_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    client_list = client.post(
        "/api/v1/messaging/staff/admin/groups", headers=admin,
        json={"name": "Clientes trimestrales", "group_type": "client_list"},
    )
    assert client_list.status_code == 201
    group_id = client_list.json()["id"]
    assert client.post(
        f"/api/v1/messaging/staff/admin/groups/{group_id}/members", headers=admin,
        json={"member_type": "client", "member_id": client_id},
    ).status_code == 201
    staff_group = client.post(
        "/api/v1/messaging/staff/admin/groups", headers=admin,
        json={"name": "Equipo especial", "group_type": "staff_chat"},
    ).json()
    assert client.post(
        f"/api/v1/messaging/staff/admin/groups/{staff_group['id']}/members", headers=admin,
        json={"member_type": "staff", "member_id": "employee"},
    ).status_code == 201
    employee_groups = client.get(
        "/api/v1/messaging/staff/groups", headers=staff_headers("employee"),
    ).json()
    assert [row["name"] for row in employee_groups] == ["Equipo especial"]

    campaign = client.post(
        "/api/v1/messaging/staff/admin/campaigns", headers=admin,
        json={
            "name": "Aviso fiscal", "body": "Presenta la documentacion",
            "channel": "fiscal", "group_ids": [group_id],
        },
    )
    assert campaign.status_code == 201
    campaign_id = campaign.json()["id"]
    detail = client.get(
        f"/api/v1/messaging/staff/admin/campaigns/{campaign_id}/recipients",
        headers=admin,
    ).json()
    assert detail[0]["status"] == "sent"
    assert client.post(
        f"/api/v1/messaging/staff/admin/campaigns/{campaign_id}/retry", headers=admin,
    ).json()["already_sent"] is True
    with factory() as db:
        assert db.scalar(select(func.count(MessagingCampaignRecipient.id))) == 1
        assert db.scalar(select(func.count(MessagingMessage.id)).where(
            MessagingMessage.idempotency_key.like(f"campaign:{campaign_id}:%"),
        )) == 1


def test_campana_futura_se_rechaza_y_pasada_se_envia(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, client_id, _conversation_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    future = client.post(
        "/api/v1/messaging/staff/admin/campaigns", headers=admin,
        json={
            "name": "Aviso futuro", "body": "No debe quedar pendiente",
            "client_ids": [client_id],
            "scheduled_at": (messaging_api.utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert future.status_code == 422
    assert "programacion de campanas" in future.json()["detail"]

    immediate = client.post(
        "/api/v1/messaging/staff/admin/campaigns", headers=admin,
        json={
            "name": "Aviso inmediato", "body": "Debe enviarse ahora",
            "client_ids": [client_id],
            "scheduled_at": (messaging_api.utcnow() - timedelta(seconds=1)).isoformat(),
        },
    )
    assert immediate.status_code == 201
    with factory() as db:
        assert db.get(MessagingCampaign, immediate.json()["id"]).status == "sent"


def test_retry_parcial_no_duplica_mensajes_enviados(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, first_client_id, _conversation_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    with factory() as db:
        first_client = db.get(messaging_api.MessagingClient, first_client_id)
        second = messaging_api.MessagingClient(
            organization_id=first_client.organization_id,
            name="Ana", email="ana@example.test", password_hash="unused",
        )
        db.add(second)
        db.commit()
        second_client_id = second.id

    original_create_message = messaging_api._create_message

    def fail_second_client(db, conv, **kwargs):
        key = kwargs["idempotency_key"]
        if key.endswith(f":client:{second_client_id}"):
            raise RuntimeError("fallo transitorio")
        return original_create_message(db, conv, **kwargs)

    monkeypatch.setattr(messaging_api, "_create_message", fail_second_client)
    created = client.post(
        "/api/v1/messaging/staff/admin/campaigns", headers=admin,
        json={
            "name": "Envio parcial", "body": "Mensaje unico",
            "client_ids": [first_client_id, second_client_id],
        },
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]
    with factory() as db:
        assert db.get(MessagingCampaign, campaign_id).status == "partial"
        interrupted = db.scalar(select(MessagingCampaignRecipient).where(
            MessagingCampaignRecipient.campaign_id == campaign_id,
            MessagingCampaignRecipient.client_id == first_client_id,
        ))
        assert interrupted.status == "sent"
        interrupted.status = "error"
        interrupted.error = "interrupcion despues de confirmar el mensaje"
        db.commit()

    monkeypatch.setattr(messaging_api, "_create_message", original_create_message)
    retried = client.post(
        f"/api/v1/messaging/staff/admin/campaigns/{campaign_id}/retry", headers=admin,
    )
    assert retried.status_code == 202
    with factory() as db:
        campaign = db.get(MessagingCampaign, campaign_id)
        assert campaign.status == "sent"
        assert db.scalar(select(func.count(MessagingMessage.id)).where(
            MessagingMessage.idempotency_key.like(f"campaign:{campaign_id}:%"),
        )) == 2
        keys = list(db.scalars(select(MessagingMessage.idempotency_key).where(
            MessagingMessage.idempotency_key.like(f"campaign:{campaign_id}:%"),
        )))
        assert len(keys) == len(set(keys))


def test_selector_clientes_usa_un_join_y_mantiene_contrato(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, client_id, _conversation_id = _setup(tmp_path, monkeypatch)
    statements = []
    engine = factory.kw["bind"]

    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = client.get(
            "/api/v1/messaging/staff/admin/campaign-targets/clients",
            headers=staff_headers("admin"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert response.json() == [{
        "id": client_id,
        "name": "Maria",
        "email": "maria@example.test",
        "organization_id": response.json()[0]["organization_id"],
        "company_code": "E10001",
        "company_name": "Cliente Uno",
    }]
    target_queries = [
        statement for statement in statements
        if "FROM msg_clients" in statement or "FROM msg_organizations" in statement
    ]
    assert len(target_queries) == 1
    assert "JOIN msg_organizations" in target_queries[0]


def test_enums_de_entrada_rechazan_valores_desconocidos(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, client_id, _conversation_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    assert client.post(
        "/api/v1/messaging/staff/admin/groups", headers=admin,
        json={"name": "Invalido", "group_type": "broadcast"},
    ).status_code == 422
    group = client.post(
        "/api/v1/messaging/staff/admin/groups", headers=admin,
        json={"name": "Lista valida", "group_type": "client_list"},
    ).json()
    assert client.post(
        f"/api/v1/messaging/staff/admin/groups/{group['id']}/members", headers=admin,
        json={"member_type": "unknown", "member_id": client_id},
    ).status_code == 422
    assert client.post(
        f"/api/v1/messaging/staff/admin/groups/{group['id']}/members", headers=admin,
        json={"member_type": "client", "member_id": client_id, "role": "superuser"},
    ).status_code == 422
    assert client.put(
        "/api/v1/messaging/client/app-devices", headers=auth,
        json={"platform": "symbian", "push_token": "x" * 20},
    ).status_code == 422
    assert client.put(
        "/api/v1/messaging/internal/staff/invalid-role", headers=admin,
        json={
            "external_id": "invalid-role", "name": "Rol invalido",
            "role": "superuser",
        },
    ).status_code == 422


def test_dispositivo_fcm_mockeado_y_websocket(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, conversation_id = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(messaging_api, "fcm_configured", lambda: True)
    delivered = []
    monkeypatch.setattr(
        messaging_api, "send_fcm",
        lambda token, payload: delivered.append((token, payload)) or True,
    )
    registered = client.put(
        "/api/v1/messaging/client/app-devices", headers=auth,
        json={
            "platform": "android", "push_token": "fcm-token-abcdefghijklmnopqrstuvwxyz",
            "device_name": "Pixel", "app_version": "0.1.0",
        },
    )
    assert registered.status_code == 200
    assert registered.json()["fcm_configured"] is True
    sent = client.post(
        f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
        headers=staff_headers("admin"),
        data={"body": "Mensaje con push", "idempotency_key": "push"},
    )
    assert sent.status_code == 200
    assert delivered[0][0].startswith("fcm-token")
    assert delivered[0][1]["conversation_id"] == conversation_id

    ticket = client.post(
        "/api/v1/messaging/client/ws-ticket", headers=auth,
    ).json()["ticket"]
    with client.websocket_connect(
        f"/api/v1/messaging/ws/client?ticket={ticket}",
    ) as websocket:
        assert websocket.receive_json()["type"] == "connected"
        response = client.post(
            f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
            headers=staff_headers("admin"),
            data={"body": "En tiempo real", "idempotency_key": "websocket"},
        )
        assert response.status_code == 200
        event = websocket.receive_json()
        assert event["type"] == "message.created"
        assert event["conversation_id"] == conversation_id
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/v1/messaging/ws/client?ticket={ticket}",
        ):
            pass


def test_login_staff_app_usa_codigo_un_solo_uso(tmp_path, monkeypatch):
    client, _factory = _api(tmp_path, monkeypatch)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/staff/admin", headers=internal,
        json={
            "external_id": "admin", "name": "Admin", "email": "admin@gestinem.es",
            "role": "admin", "active": True, "channels": ["fiscal"],
        },
    ).status_code == 200

    class FakeMsal:
        def initiate_auth_code_flow(self, **_kwargs):
            return {"state": "app-state", "auth_uri": "https://login.example.test"}

        def acquire_token_by_auth_code_flow(self, _flow, _params):
            return {"id_token_claims": {
                "preferred_username": "admin@gestinem.es",
                "oid": "entra-admin", "name": "Admin",
            }}

    monkeypatch.setattr(messaging_api, "_staff_msal_app", lambda: FakeMsal())
    assert client.get(
        "/api/v1/messaging/staff-auth/login?app=true", follow_redirects=False,
    ).status_code == 302
    callback = client.get(
        "/api/v1/messaging/staff-auth/callback?state=app-state&code=ok",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"].startswith("es.gestinem.app://auth/callback?code=")
    code = callback.headers["location"].split("code=", 1)[1]
    exchanged = client.post(
        "/api/v1/messaging/staff-auth/mobile/exchange", json={"code": code},
    )
    assert exchanged.status_code == 200
    assert exchanged.json()["staff"]["role"] == "admin"
    assert client.post(
        "/api/v1/messaging/staff-auth/mobile/exchange", json={"code": code},
    ).status_code == 400
