import os
from io import BytesIO
from pathlib import Path

from PIL import Image

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI, UploadFile
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
    os.environ["MESSAGING_SYNC_TOKEN"] = "sync-secret"
    os.environ["MESSAGING_STAFF_ALLOWED_DOMAIN"] = "gestinem.es"
    os.environ["MESSAGING_STAFF_ADMIN_EMAILS"] = "admin@gestinem.es"
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
    return TestClient(app, base_url="https://mensajes.example.test")


def test_avatar_aplica_orientacion_exif_de_fotos_moviles():
    source = Image.new("RGB", (120, 60), "#1c4f9c")
    for x in range(60):
        for y in range(60):
            source.putpixel((x, y), (220, 45, 45))
    exif = Image.Exif()
    exif[274] = 6  # Rotacion de 90 grados en sentido horario.
    encoded = BytesIO()
    source.save(encoded, format="JPEG", quality=95, exif=exif)
    encoded.seek(0)

    normalized = messaging_api._normalized_avatar(
        UploadFile(filename="foto-movil.jpg", file=encoded),
    )
    with Image.open(BytesIO(normalized)) as avatar:
        assert avatar.size == (256, 256)
        top = avatar.getpixel((128, 30))
        bottom = avatar.getpixel((128, 225))
        assert top[0] > top[2]
        assert bottom[2] > bottom[0]


def test_admin_preautoriza_empleado_y_primer_login_vincula_microsoft(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/staff/admin-local", headers=internal,
        json={
            "external_id": "admin-local", "name": "Administrador",
            "email": "admin@gestinem.es", "role": "admin", "active": True,
            "channels": ["laboral", "fiscal"],
        },
    ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/puesto-admin", headers=internal,
    ).json()
    admin_headers = {
        **internal, "X-Device-Id": "puesto-admin",
        "X-Device-Token": device["device_token"], "X-Staff-Id": "admin-local",
    }
    created = client.post(
        "/api/v1/messaging/staff/admin/directory", headers=admin_headers,
        json={
            "name": "Ana Laboral", "email": "ana@gestinem.es",
            "chat_alias": "Ana · Laboral", "role": "empleado",
            "active": True, "channels": ["laboral"],
        },
    )
    assert created.status_code == 201
    staff_id = created.json()["id"]
    assert created.json()["linked"] is False
    avatar = BytesIO()
    Image.new("RGB", (400, 300), "#145a86").save(avatar, format="PNG")
    uploaded = client.put(
        f"/api/v1/messaging/staff/admin/directory/{staff_id}/avatar",
        headers=admin_headers,
        files={"avatar": ("ana.png", avatar.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 200
    avatar_response = client.get(
        f"/api/v1/messaging/staff/avatars/{staff_id}", headers=admin_headers,
    )
    assert avatar_response.status_code == 200
    assert avatar_response.headers["content-type"] == "image/webp"

    class FakeMsal:
        def initiate_auth_code_flow(self, **_kwargs):
            return {"state": "state-ana", "auth_uri": "https://login.example.test"}

        def acquire_token_by_auth_code_flow(self, _flow, _params):
            return {"id_token_claims": {
                "preferred_username": "ana@gestinem.es", "oid": "entra-ana",
                "name": "Ana Laboral",
            }}

    monkeypatch.setattr(messaging_api, "_staff_msal_app", lambda: FakeMsal())
    assert client.get(
        "/api/v1/messaging/staff-auth/login", follow_redirects=False,
    ).status_code == 302
    callback = client.get(
        "/api/v1/messaging/staff-auth/callback?state=state-ana&code=ok",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    employee_token = client.cookies.get("msg_staff_session")
    me = client.get("/api/v1/messaging/staff/me").json()
    assert me["id"] == staff_id
    assert me["chat_alias"] == "Ana · Laboral"
    assert me["channels"] == ["laboral"]

    client.cookies.clear()
    directory = client.get(
        "/api/v1/messaging/staff/admin/directory", headers=admin_headers,
    ).json()
    employee = next(row for row in directory if row["id"] == staff_id)
    assert employee["linked"] is True
    assert employee["avatar_configured"] is True
    suspended = client.put(
        f"/api/v1/messaging/staff/admin/directory/{staff_id}", headers=admin_headers,
        json={
            "channels": ["laboral"], "role": "empleado", "active": False,
            "chat_alias": "Ana · Laboral",
        },
    )
    assert suspended.status_code == 200
    assert client.get(
        "/api/v1/messaging/staff/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    ).status_code == 401


def test_login_corporativo_sin_preautorizacion_es_rechazado(tmp_path, monkeypatch):
    client = _client(tmp_path)

    class FakeMsal:
        def initiate_auth_code_flow(self, **_kwargs):
            return {"state": "state-no-autorizado", "auth_uri": "https://login.example.test"}

        def acquire_token_by_auth_code_flow(self, _flow, _params):
            return {"id_token_claims": {
                "preferred_username": "desconocido@gestinem.es",
                "oid": "entra-desconocido", "name": "Desconocido",
            }}

    monkeypatch.setattr(messaging_api, "_staff_msal_app", lambda: FakeMsal())
    client.get("/api/v1/messaging/staff-auth/login", follow_redirects=False)
    response = client.get(
        "/api/v1/messaging/staff-auth/callback?state=state-no-autorizado&code=ok",
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_cuenta_cliente_prueba_genera_enlace_sin_enviar_email(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/organizations/E00000", headers=internal,
        json={"company_code": "E00000", "name": "Empresa de prueba"},
    ).status_code == 200
    sent = []
    monkeypatch.setattr(messaging_api, "mail_configured", lambda: True)
    monkeypatch.setattr(
        messaging_api, "send_invitation",
        lambda email, name, url: sent.append((email, name, url)),
    )

    invitation = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E00000", "name": "Cliente de prueba",
            "email": "prueba@gestinem.es", "send_email": False,
        },
    )
    assert invitation.status_code == 200
    assert invitation.json()["email_queued"] is False
    assert invitation.json()["url"].startswith("https://mensajes.example.test/mensajes?invite=")
    assert sent == []

    token = invitation.json()["url"].split("invite=", 1)[1]
    assert client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": token, "password": "prueba-segura-1234"},
    ).status_code == 200
    assert client.post(
        "/api/v1/messaging/auth/login",
        json={"email": "prueba@gestinem.es", "password": "prueba-segura-1234"},
    ).status_code == 200


def test_empresa_pruebas_solo_es_visible_para_su_titular(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    for staff_id, name in (("admin-owner", "Titular"), ("admin-other", "Otro admin")):
        assert client.put(
            f"/api/v1/messaging/internal/staff/{staff_id}", headers=internal,
            json={
                "external_id": staff_id, "name": name,
                "email": f"{staff_id}@gestinem.es", "role": "admin",
                "active": True, "channels": ["laboral", "fiscal"],
            },
        ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/puesto-pruebas", headers=internal,
    ).json()
    common = {
        **internal, "X-Device-Id": "puesto-pruebas",
        "X-Device-Token": device["device_token"],
    }
    owner = {**common, "X-Staff-Id": "admin-owner"}
    other = {**common, "X-Staff-Id": "admin-other"}
    assert client.put(
        "/api/v1/messaging/internal/organizations/E0000", headers=internal,
        json={
            "company_code": "E0000", "name": "Empresa de Pruebas",
            "private_owner_external_id": "admin-owner", "active": True,
        },
    ).status_code == 200

    owner_conversations = client.get(
        "/api/v1/messaging/staff/conversations", headers=owner,
    ).json()
    assert {row["kind"] for row in owner_conversations} == {"laboral", "fiscal", "private"}
    assert client.get(
        "/api/v1/messaging/staff/conversations", headers=other,
    ).json() == []
    assert client.get(
        f"/api/v1/messaging/staff/conversations/{owner_conversations[0]['id']}/messages",
        headers=other,
    ).status_code == 403

    assert any(
        row["company_code"] == "E0000"
        for row in client.get(
            "/api/v1/messaging/staff/admin/organizations", headers=owner,
        ).json()
    )
    assert all(
        row["company_code"] != "E0000"
        for row in client.get(
            "/api/v1/messaging/staff/admin/organizations", headers=other,
        ).json()
    )
    assert client.post(
        "/api/v1/messaging/staff/admin/invitations", headers=other,
        json={
            "company_code": "E0000", "name": "Prueba",
            "email": "prueba-privada@gestinem.es", "send_email": False,
        },
    ).status_code == 403

    invitation = client.post(
        "/api/v1/messaging/staff/admin/invitations", headers=owner,
        json={
            "company_code": "E0000", "name": "Prueba",
            "email": "prueba-privada@gestinem.es", "send_email": False,
        },
    )
    token = invitation.json()["url"].split("invite=", 1)[1]
    accepted = client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": token, "password": "prueba-segura-1234"},
    ).json()
    client_auth = {"Authorization": f"Bearer {accepted['token']}"}
    private = next(
        row for row in client.get(
            "/api/v1/messaging/client/conversations", headers=client_auth,
        ).json() if row["kind"] == "private"
    )
    monkeypatch.setattr(messaging_api, "push_configured", lambda: True)
    delivered_to = []
    monkeypatch.setattr(
        messaging_api, "send_push",
        lambda subscription, _payload: delivered_to.append(subscription["endpoint"]) or True,
    )
    for headers, endpoint in ((owner, "owner-device"), (other, "other-device")):
        assert client.post(
            "/api/v1/messaging/staff/push/subscriptions", headers=headers,
            json={
                "endpoint": f"https://push.example.test/{endpoint}",
                "p256dh": "public-key", "auth": "auth-key",
            },
        ).status_code == 200
    assert client.post(
        f"/api/v1/messaging/client/conversations/{private['id']}/messages",
        headers=client_auth,
        data={"body": "Mensaje directo de pruebas", "idempotency_key": "test-private"},
    ).status_code == 200
    assert delivered_to == ["https://push.example.test/owner-device"]
    visible = client.get(
        "/api/v1/messaging/staff/conversations?active_only=true", headers=owner,
    ).json()
    assert [row["kind"] for row in visible] == ["private"]


def test_worker_sincroniza_directorio_de_empresas_sin_borrar_titular_privado(tmp_path):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/staff/admin-local", headers=internal,
        json={
            "external_id": "admin-local", "name": "Administrador",
            "email": "admin@gestinem.es", "role": "admin", "active": True,
        },
    ).status_code == 200
    assert client.put(
        "/api/v1/messaging/internal/organizations/E00042", headers=internal,
        json={
            "company_code": "E00042", "name": "Nombre anterior",
            "private_owner_external_id": "admin-local", "active": True,
        },
    ).status_code == 200

    synced = client.put(
        "/api/v1/messaging/sync/organizations",
        headers={"X-Sync-Token": "sync-secret"},
        json=[
            {"company_code": "E00042", "name": "Cliente actualizado", "active": True},
            {"company_code": "E00043", "name": "Cliente nuevo", "active": True},
        ],
    )
    assert synced.status_code == 200
    assert synced.json()["synchronized"] == 2

    device = client.post(
        "/api/v1/messaging/internal/devices/puesto-admin", headers=internal,
    ).json()
    rows = client.get(
        "/api/v1/messaging/staff/admin/organizations",
        headers={
            **internal, "X-Device-Id": "puesto-admin",
            "X-Device-Token": device["device_token"], "X-Staff-Id": "admin-local",
        },
    ).json()
    updated = next(row for row in rows if row["company_code"] == "E00042")
    assert updated["name"] == "Cliente actualizado"
    assert updated["private_owner_external_id"] == "admin-local"


def test_mensaje_sin_adjunto_no_inicializa_almacenamiento(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/organizations/E00000", headers=internal,
        json={"company_code": "E00000", "name": "Empresa de prueba"},
    ).status_code == 200
    invitation = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E00000", "name": "Cliente de prueba",
            "email": "prueba@gestinem.es", "send_email": False,
        },
    ).json()
    token = invitation["url"].split("invite=", 1)[1]
    accepted = client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": token, "password": "prueba-segura-1234"},
    ).json()
    conversations = client.get(
        "/api/v1/messaging/client/conversations",
        headers={"Authorization": f"Bearer {accepted['token']}"},
    ).json()

    class StorageNoPermitido:
        def __init__(self):
            raise AssertionError("Un mensaje de texto no debe abrir el almacenamiento")

    monkeypatch.setattr(messaging_api, "MessagingStorage", StorageNoPermitido)
    response = client.post(
        f"/api/v1/messaging/client/conversations/{conversations[0]['id']}/messages",
        headers={"Authorization": f"Bearer {accepted['token']}"},
        data={"body": "Mensaje de prueba", "idempotency_key": "solo-texto"},
    )
    assert response.status_code == 200
    assert response.json()["body"] == "Mensaje de prueba"


def test_chats_internos_privados_y_grupos_respetan_permisos(tmp_path):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    users = (
        ("admin", "Administrador", "admin", []),
        ("labor", "Laura Laboral", "empleado", ["laboral"]),
        ("fiscal", "Felipe Fiscal", "empleado", ["fiscal"]),
    )
    for user_id, name, role, channels in users:
        assert client.put(
            f"/api/v1/messaging/internal/staff/{user_id}", headers=internal,
            json={
                "external_id": user_id, "name": name,
                "email": f"{user_id}@gestinem.es", "chat_alias": name.split()[0],
                "role": role, "active": True, "channels": channels,
            },
        ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/puesto-interno", headers=internal,
    ).json()

    def auth(user_id):
        return {
            **internal, "X-Device-Id": "puesto-interno",
            "X-Device-Token": device["device_token"], "X-Staff-Id": user_id,
        }

    admin_threads = client.get(
        "/api/v1/messaging/staff/internal/threads", headers=auth("admin"),
    ).json()
    assert {row["channel"] for row in admin_threads} == {"laboral", "fiscal"}
    labor_threads = client.get(
        "/api/v1/messaging/staff/internal/threads", headers=auth("labor"),
    ).json()
    assert [row["channel"] for row in labor_threads] == ["laboral"]
    fiscal_threads = client.get(
        "/api/v1/messaging/staff/internal/threads", headers=auth("fiscal"),
    ).json()
    assert [row["channel"] for row in fiscal_threads] == ["fiscal"]

    avatar = BytesIO()
    Image.new("RGB", (90, 90), "#145a86").save(avatar, format="PNG")
    assert client.put(
        "/api/v1/messaging/staff/admin/directory/labor/avatar",
        headers=auth("admin"),
        files={"avatar": ("laura.png", avatar.getvalue(), "image/png")},
    ).status_code == 200
    direct = client.post(
        "/api/v1/messaging/staff/internal/direct/labor", headers=auth("admin"),
    )
    assert direct.status_code == 201
    direct_id = direct.json()["id"]
    assert direct.json()["counterpart_id"] == "labor"
    assert direct.json()["counterpart_name"] == "Laura"
    assert direct.json()["counterpart_avatar_url"].endswith("/staff/avatars/labor")
    assert client.get(
        f"/api/v1/messaging/staff/internal/threads/{direct_id}/messages",
        headers=auth("fiscal"),
    ).status_code == 403

    labor_group = next(row for row in admin_threads if row["channel"] == "laboral")
    sent_group = client.post(
        f"/api/v1/messaging/staff/internal/threads/{labor_group['id']}/messages",
        headers=auth("admin"),
        data={"body": "Aviso para laboral", "idempotency_key": "grupo-1"},
    )
    assert sent_group.status_code == 200
    labor_threads = client.get(
        "/api/v1/messaging/staff/internal/threads", headers=auth("labor"),
    ).json()
    assert next(row for row in labor_threads if row["id"] == labor_group["id"])["unread_count"] == 1
    assert client.get(
        f"/api/v1/messaging/staff/internal/threads/{labor_group['id']}/messages",
        headers=auth("fiscal"),
    ).status_code == 403
    assert client.post(
        f"/api/v1/messaging/staff/internal/threads/{labor_group['id']}/read",
        headers=auth("labor"),
    ).status_code == 200

    reply = client.post(
        f"/api/v1/messaging/staff/internal/threads/{direct_id}/messages",
        headers=auth("labor"),
        data={"body": "Respuesta privada", "idempotency_key": "directo-1"},
    )
    assert reply.status_code == 200
    assert reply.json()["author_name"] == "Laura"
    private_messages = client.get(
        f"/api/v1/messaging/staff/internal/threads/{direct_id}/messages",
        headers=auth("admin"),
    ).json()
    assert [row["body"] for row in private_messages] == ["Respuesta privada"]


def test_chat_privado_transporte_local_y_auditoria_descarga(tmp_path, monkeypatch):
    client = _client(tmp_path)
    internal = {"X-API-Key": "test-secret"}
    for staff_id, name in (("7", "Titular"), ("8", "Empleado")):
        assert client.put(
            f"/api/v1/messaging/internal/staff/{staff_id}", headers=internal,
            json={
                "external_id": staff_id, "name": name,
                "role": "admin" if staff_id == "7" else "empleado",
                "chat_alias": "Titular fiscal" if staff_id == "7" else "",
                "active": True, "channels": ["fiscal"],
            },
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
    general = next(row for row in conversations if row["kind"] == "fiscal")
    assert client.post(
        "/api/v1/messaging/client/push/subscriptions", headers=client_auth,
        json={
            "endpoint": "https://push.example.test/client-ana",
            "p256dh": "public-key-client-ana", "auth": "auth-client-ana",
        },
    ).status_code == 200
    assert client.post(
        "/api/v1/messaging/client/push/test", headers=client_auth,
    ).status_code == 503

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
    assert client.post(
        "/api/v1/messaging/staff/push/test", headers=staff7,
    ).status_code == 503
    monkeypatch.setattr(messaging_api, "push_configured", lambda: True)
    push_payloads = []

    def fake_push(_subscription, payload):
        push_payloads.append(payload)
        return True

    monkeypatch.setattr(messaging_api, "send_push", fake_push)
    assert client.post(
        "/api/v1/messaging/staff/push/subscriptions", headers=staff7,
        json={
            "endpoint": "https://push.example.test/device-7",
            "p256dh": "public-key-device-7", "auth": "auth-device-7",
        },
    ).status_code == 200
    push_test = client.post(
        "/api/v1/messaging/staff/push/test", headers=staff7,
    )
    assert push_test.status_code == 200
    assert push_test.json()["delivered"] == 1
    client_push_test = client.post(
        "/api/v1/messaging/client/push/test", headers=client_auth,
    )
    assert client_push_test.status_code == 200
    assert client_push_test.json()["delivered"] == 1
    avatar = BytesIO()
    Image.new("RGB", (80, 80), "#145a86").save(avatar, format="PNG")
    assert client.put(
        "/api/v1/messaging/staff/admin/directory/7/avatar", headers=staff7,
        files={"avatar": ("titular.png", avatar.getvalue(), "image/png")},
    ).status_code == 200
    visible7 = client.get(
        "/api/v1/messaging/staff/conversations?active_only=true", headers=staff7,
    ).json()
    assert len(visible7) == 1
    assert next(row for row in visible7 if row["id"] == general["id"])["unread_count"] == 1
    assert len(client.get(
        "/api/v1/messaging/staff/conversations?active_only=true", headers=staff8,
    ).json()) == 1
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

    private = next(row for row in conversations if row["kind"] == "private")
    private_sent = client.post(
        f"/api/v1/messaging/client/conversations/{private['id']}/messages",
        headers=client_auth, data={"body": "Documento privado", "idempotency_key": "private-1"},
        files={"files": ("privado.pdf", b"privado", "application/pdf")},
    )
    private_attachment = private_sent.json()["attachments"][0]
    sync_headers = {"X-Sync-Token": "sync-secret"}
    pending_sync = client.get(
        "/api/v1/messaging/sync/attachments/pending", headers=sync_headers,
    ).json()
    assert [row["id"] for row in pending_sync] == [private_attachment["id"]]
    assert pending_sync[0]["channel"] == "private"
    assert client.post(
        f"/api/v1/messaging/sync/attachments/{private_attachment['id']}/claim",
        headers=sync_headers, data={"worker": "synology"},
    ).status_code == 200
    private_content = client.get(
        f"/api/v1/messaging/sync/attachments/{private_attachment['id']}/content",
        headers=sync_headers, params={"worker": "synology"},
    )
    assert private_content.content == b"privado"
    assert client.post(
        f"/api/v1/messaging/sync/attachments/{private_attachment['id']}/confirm",
        headers=sync_headers,
        data={"worker": "synology", "sha256": private_attachment["sha256"]},
    ).status_code == 200

    outgoing = client.post(
        f"/api/v1/messaging/staff/conversations/{general['id']}/messages",
        headers=staff7, data={"body": "Documento", "idempotency_key": "staff-1"},
        files={"files": ("respuesta.pdf", b"respuesta", "application/pdf")},
    )
    outgoing_id = outgoing.json()["attachments"][0]["id"]
    assert outgoing.json()["author_name"] == "Titular fiscal"
    assert any(payload["title"] == "Nuevo mensaje de Gestinem" for payload in push_payloads)
    client_messages = client.get(
        f"/api/v1/messaging/client/conversations/{general['id']}/messages",
        headers=client_auth,
    ).json()
    staff_message = next(row for row in client_messages if row["id"] == outgoing.json()["id"])
    assert staff_message["author_name"] == "Titular fiscal"
    assert staff_message["author_avatar_url"].endswith("/client/avatars/7")
    assert client.get(
        "/api/v1/messaging/client/avatars/7", headers=client_auth,
    ).headers["content-type"] == "image/webp"
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
