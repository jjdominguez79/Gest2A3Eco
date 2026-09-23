import asyncio
import os
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image
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
from backend.api.client_profile_api import (
    _db as client_profile_db,
    router as client_profile_router,
)
from backend.api.database import Base
from backend.api.messaging_api import get_db, router
from backend.api.messaging_models import (
    MessagingAttachment,
    MessagingCampaign,
    MessagingCampaignRecipient,
    MessagingDeletionAudit,
    MessagingMessage,
    MessagingStaff,
    MessagingStaffPresenceConnection,
    MessagingStaffSession,
    MessagingWebSocketTicket,
)
from backend.api.messaging_realtime import RealtimeHub
from backend.api.messaging_security import hash_token, utcnow


def _api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("MESSAGING_STORAGE_DIR", str(tmp_path / "cloud"))
    monkeypatch.setenv("MESSAGING_PUBLIC_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("MESSAGING_APP_WEB_URL", "https://app.example.test")
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(messaging_api, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(router)
    app.include_router(client_profile_router)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[client_profile_db] = override
    return TestClient(app, base_url="https://api.example.test"), factory


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
        json={
            "company_code": "E10001", "name": "Cliente Uno",
            "private_owner_external_id": "admin",
        },
    ).status_code == 200
    invitation = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E10001", "name": "Maria",
            "email": "maria@example.test", "send_email": False,
        },
    ).json()
    invite_token = invitation["url"].split("token=", 1)[1]
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


@pytest.mark.parametrize("autor", ["client", "staff"])
def test_edicion_guarda_todas_las_versiones_solo_para_propietario(tmp_path, monkeypatch, autor):
    monkeypatch.setenv("MESSAGING_HISTORY_OWNER_EMAIL", "admin@gestinem.es")
    client, factory, staff_headers, auth, _, conv_id = _setup(tmp_path, monkeypatch)
    headers = auth if autor == "client" else staff_headers("employee")
    listado = f"/api/v1/messaging/{autor}/conversations/{conv_id}/messages"
    original = client.post(listado, headers=headers,
                           data={"body": "Original privado", "idempotency_key": "edit-1"}).json()
    ruta = f"/api/v1/messaging/{autor}/messages/{original['id']}"
    historial = f"/api/v1/messaging/staff/messages/{original['id']}/history"
    for anterior, nuevo in (("Original privado", "Segundo privado"), ("Segundo privado", "Actual")):
        editado = client.patch(ruta, headers=headers,
                               json={"body": nuevo, "original_body": anterior})
        assert editado.status_code == 200
        assert editado.json()["edited_at"]
        assert editado.json()["created_at"] == original["created_at"]
    respuesta_historial = client.get(historial, headers=staff_headers("admin"))
    assert respuesta_historial.headers["cache-control"] == "no-store"
    assert [v["body"] for v in respuesta_historial.json()] == [
        "Original privado", "Segundo privado",
    ]
    # Ni el autor cliente/empleado ni otro administrador pueden leer versiones.
    assert client.get(historial, headers=auth).status_code in (401, 403)
    assert client.get(historial, headers=staff_headers("employee")).status_code == 403
    with factory() as db:
        db.get(MessagingStaff, "employee").role = "admin"
        db.commit()
    assert client.get(historial, headers=staff_headers("employee")).status_code == 403
    for audiencia, receptor in (("client", auth), ("staff", staff_headers("employee")),
                                ("staff", staff_headers("admin"))):
        publico = client.get(f"/api/v1/messaging/{audiencia}/conversations/{conv_id}/messages",
                              headers=receptor)
        assert publico.json()[0]["body"] == "Actual"
        assert publico.json()[0]["can_view_history"] == (receptor == staff_headers("admin"))
        assert "Original privado" not in publico.text and "Segundo privado" not in publico.text
    monkeypatch.setenv("MESSAGING_HISTORY_OWNER_EMAIL", "")
    assert client.get(historial, headers=staff_headers("admin")).status_code == 403


def test_edicion_rechaza_ajenos_borrados_vacios_y_conflictos(tmp_path, monkeypatch):
    client, factory, staff_headers, auth, _, conv_id = _setup(tmp_path, monkeypatch)
    original = client.post(f"/api/v1/messaging/client/conversations/{conv_id}/messages",
        headers=auth, data={"body": "Original", "idempotency_key": "edit-denied"}).json()
    message_id = original["id"]
    ruta = f"/api/v1/messaging/client/messages/{message_id}"
    payload = {"body": "Actual", "original_body": "Original"}
    assert client.patch(f"/api/v1/messaging/staff/messages/{message_id}",
        headers=staff_headers("admin"), json=payload).status_code == 403
    assert client.patch(ruta, headers=auth, json={**payload, "body": "   "}).status_code == 422
    assert client.patch(ruta, headers=auth, json={**payload, "body": "x" * 20001}).status_code == 422
    assert client.patch(ruta, headers=auth, json={**payload, "body": "Original"}).status_code == 200
    assert client.patch(ruta, headers=auth, json=payload).status_code == 200
    assert client.patch(ruta, headers=auth, json=payload).status_code == 409
    with factory() as db:
        from backend.api.messaging_models import MessagingMessageVersion
        versiones = list(db.scalars(select(MessagingMessageVersion)))
        assert [v.body for v in versiones] == ["Original"]
    assert client.delete(ruta, headers=auth).status_code == 200
    assert client.patch(ruta, headers=auth,
        json={"body": "Otro", "original_body": "Actual"}).status_code == 409


def test_edicion_interna_historial_y_eventos_no_filtran_versiones(tmp_path, monkeypatch):
    monkeypatch.setenv("MESSAGING_HISTORY_OWNER_EMAIL", "admin@gestinem.es")
    client, factory, staff_headers, _, _, _ = _setup(tmp_path, monkeypatch)
    thread = client.post("/api/v1/messaging/staff/internal/direct/employee",
                          headers=staff_headers("admin")).json()
    listado = f"/api/v1/messaging/staff/internal/threads/{thread['id']}/messages"
    original = client.post(listado, headers=staff_headers("employee"),
                           data={"body": "Interno privado", "idempotency_key": "internal-edit"}).json()
    ruta = f"/api/v1/messaging/staff/internal/messages/{original['id']}"
    payload = {"body": "Interno actual", "original_body": "Interno privado"}
    assert client.patch(ruta, headers=staff_headers("admin"), json=payload).status_code == 403
    eventos = []
    monkeypatch.setattr(messaging_api.hub, "publish", lambda event, **kwargs: eventos.append(event))
    assert client.patch(ruta, headers=staff_headers("employee"), json=payload).status_code == 200
    assert eventos == [{"type": "message.edited", "thread_id": thread["id"], "message_id": original["id"]}]
    assert client.get(ruta + "/history", headers=staff_headers("employee")).status_code == 403
    versiones = client.get(ruta + "/history", headers=staff_headers("admin")).json()
    assert [v["body"] for v in versiones] == ["Interno privado"]
    publico = client.get(listado, headers=staff_headers("employee"))
    assert publico.json()[0]["edited_at"] and "Interno privado" not in publico.text
    assert client.delete(ruta, headers=staff_headers("employee")).status_code == 200
    assert client.get(ruta + "/history", headers=staff_headers("admin")).json() == versiones


def test_edicion_no_cambia_adjuntos_y_cita_usa_texto_actual(tmp_path, monkeypatch):
    client, _, staff_headers, auth, _, conv_id = _setup(tmp_path, monkeypatch)
    listado = f"/api/v1/messaging/client/conversations/{conv_id}/messages"
    original = client.post(listado, headers=auth,
        data={"body": "Pie antiguo", "idempotency_key": "caption-edit"},
        files=[("files", ("nota.txt", b"Documento", "text/plain"))]).json()
    assert client.post(listado, headers=auth,
        data={"body": "Respuesta", "idempotency_key": "reply-edit",
              "reply_to_message_id": original["id"]}).status_code == 200
    nuevo = client.patch(f"/api/v1/messaging/client/messages/{original['id']}", headers=auth,
        json={"body": "Pie actual", "original_body": "Pie antiguo"}).json()
    assert nuevo["attachments"] == original["attachments"]
    assert client.get(listado, headers=auth).json()[1]["reply_to"]["body_fragment"] == "Pie actual"


def test_estados_mensajes_conservan_lectura_y_distinguen_nuevos(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    path = f"/api/v1/messaging/staff/conversations/{conv_id}/messages"
    sent = client.post(path, headers=staff_headers("admin"),
                       data={"body": "Aviso", "idempotency_key": "receipt-1"})
    assert sent.status_code == 200
    initial = client.get(path, headers=staff_headers("admin")).json()[0]
    assert (initial["estado_envio"], initial["lecturas"], initial["destinatarios"]) == ("sent", 0, 1)
    assert initial["estado_destinatarios"] == [{
        "actor_type": "client", "actor_id": initial["estado_destinatarios"][0]["actor_id"],
        "nombre": "Maria", "lectura_visible": True, "leido": False, "leido_en": None,
    }]
    # Abrir la propia conversacion no confirma la lectura del destinatario.
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read",
                       headers=staff_headers("admin")).status_code == 200
    assert client.get(path, headers=staff_headers("admin")).json()[0]["estado_envio"] == "sent"
    read_path = f"/api/v1/messaging/client/conversations/{conv_id}/read"
    assert client.post(read_path, headers=auth).status_code == 200
    assert client.post(read_path, headers=auth).json()["changed"] is False
    read = client.get(path, headers=staff_headers("admin")).json()[0]
    assert (read["estado_envio"], read["lecturas"]) == ("read", 1)
    assert read["estado_destinatarios"][0]["nombre"] == "Maria"
    assert read["estado_destinatarios"][0]["leido"] is True
    assert read["estado_destinatarios"][0]["leido_en"] is not None
    assert client.delete(read_path, headers=auth).status_code == 204
    assert client.get(path, headers=staff_headers("admin")).json()[0]["estado_envio"] == "read"
    assert client.post(path, headers=staff_headers("admin"),
                       data={"body": "Otro aviso", "idempotency_key": "receipt-2"}).status_code == 200
    assert [row["estado_envio"] for row in client.get(path, headers=staff_headers("admin")).json()] == ["read", "sent"]
    # Los estados del emisor no se exponen en mensajes de otros usuarios.
    received = client.get(f"/api/v1/messaging/client/conversations/{conv_id}/messages", headers=auth).json()
    assert all("estado_envio" not in row for row in received)


def test_preferencia_estados_mensajes_es_personal_y_no_altera_lecturas(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    me = "/api/v1/messaging/staff/me"
    admin = staff_headers("admin")
    assert client.get(me, headers=admin).json()["mostrar_estados_mensajes"] is True
    assert client.patch(me, headers=admin, json={"mostrar_estados_mensajes": False}).status_code == 200
    assert client.get(me, headers=admin).json()["mostrar_estados_mensajes"] is True
    assert client.get(me, headers=staff_headers("employee")).json()["mostrar_estados_mensajes"] is True
    assert client.patch(me, json={"mostrar_estados_mensajes": True}).status_code == 401
    # La preferencia no puede modificar a otro empleado ni deja de registrar lecturas.
    assert client.patch(me, headers=admin, json={"chat_alias": "Mi alias"}).status_code == 200
    assert client.get(me, headers=admin).json()["mostrar_estados_mensajes"] is True
    path = f"/api/v1/messaging/client/conversations/{conv_id}/messages"
    assert client.post(path, headers=auth,
                       data={"body": "Pregunta", "idempotency_key": "client-receipt"}).status_code == 200
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read", headers=admin).status_code == 200
    state = client.get(path, headers=auth).json()[0]
    assert all(campo not in state for campo in ("estado_envio", "lecturas", "destinatarios"))
    unified = client.get("/api/v1/messaging/client/unified-messages", headers=auth).json()
    assert all(campo not in unified[0] for campo in ("estado_envio", "lecturas", "destinatarios"))
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read",
                       headers=staff_headers("employee")).status_code == 200
    state = client.get(path, headers=auth).json()[0]
    assert all(campo not in state for campo in ("estado_envio", "lecturas", "destinatarios"))


def test_estados_chat_interno_lectura_parcial_y_evento(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, _conv_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    threads = client.get("/api/v1/messaging/staff/internal/threads", headers=admin).json()
    direct = next(row for row in threads if row["kind"] == "direct")
    path = f"/api/v1/messaging/staff/internal/threads/{direct['id']}/messages"
    events = []
    monkeypatch.setattr(messaging_api.hub, "publish", lambda payload, **kwargs: events.append((payload, kwargs)))
    assert client.post(path, headers=admin, data={"body": "Hola", "idempotency_key": "internal-receipt"}).status_code == 200
    assert client.get(path, headers=admin).json()[0]["estado_envio"] == "sent"
    read_path = f"/api/v1/messaging/staff/internal/threads/{direct['id']}/read"
    assert client.post(read_path, headers=staff_headers("employee")).status_code == 200
    assert client.get(path, headers=admin).json()[0]["estado_envio"] == "read"
    assert events[-1] == ({"type": "message.read", "thread_id": direct["id"]},
                          {"staff_ids": {"admin", "employee"}})
    total = len(events)
    assert client.post(read_path, headers=staff_headers("employee")).status_code == 200
    assert len(events) == total
    assert client.get(path, headers=auth).status_code in {401, 403}


@pytest.mark.parametrize("clientes,empleados", [(False, False), (False, True), (True, False), (True, True)])
def test_clientes_nunca_ven_lecturas_y_privacidad_interna_es_independiente(
    tmp_path, monkeypatch, clientes, empleados,
):
    client, _factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    employee = staff_headers("employee")
    assert client.patch("/api/v1/messaging/staff/me", headers=admin, json={
        "mostrar_lecturas_clientes": clientes, "mostrar_lecturas_empleados": empleados,
    }).status_code == 200
    perfil = client.get("/api/v1/messaging/staff/me", headers=admin).json()
    assert perfil["mostrar_lecturas_clientes"] is clientes
    assert perfil["mostrar_lecturas_empleados"] is empleados
    assert perfil["mostrar_estados_mensajes"] is True
    path = f"/api/v1/messaging/client/conversations/{conv_id}/messages"
    assert client.post(path, headers=auth, data={"body": "Pregunta", "idempotency_key": "privacy-client"}).status_code == 200
    eventos = []
    monkeypatch.setattr(messaging_api.hub, "publish", lambda payload, **kwargs: eventos.append((payload, kwargs)))
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read", headers=admin).status_code == 200
    for row in (client.get(path, headers=auth).json()[0],
                client.get("/api/v1/messaging/client/unified-messages", headers=auth).json()[0]):
        assert all(campo not in row for campo in ("estado_envio", "lecturas", "destinatarios"))
    payload, destinos = eventos[-1]
    assert payload["type"] == "message.read"
    assert destinos["organization_id"] == ""
    assert ("employee" in destinos["staff_ids"]) is empleados
    assert "admin" in destinos["staff_ids"]
    threads = client.get("/api/v1/messaging/staff/internal/threads", headers=employee).json()
    direct = next(row for row in threads if row["kind"] == "direct")
    internal = f"/api/v1/messaging/staff/internal/threads/{direct['id']}/messages"
    assert client.post(internal, headers=employee, data={"body": "Consulta", "idempotency_key": "privacy-employee"}).status_code == 200
    assert client.post(f"/api/v1/messaging/staff/internal/threads/{direct['id']}/read", headers=admin).status_code == 200
    row = client.get(internal, headers=employee).json()[0]
    assert row["lecturas"] == int(empleados)
    assert row["estado_envio"] == ("read" if empleados else "sent")
    assert eventos[-1][1]["staff_ids"] == ({"admin", "employee"} if empleados else {"admin"})
    # Ocultar la propia lectura nunca impide consultar las lecturas ajenas.
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/messages", headers=admin,
                       data={"body": "Respuesta", "idempotency_key": "privacy-admin"}).status_code == 200
    assert client.post(f"/api/v1/messaging/client/conversations/{conv_id}/read", headers=auth).status_code == 200
    respuesta = next(row for row in client.get(f"/api/v1/messaging/staff/conversations/{conv_id}/messages", headers=admin).json()
                     if row["body"] == "Respuesta")
    assert respuesta["estado_envio"] == "read"
    assert client.post(internal, headers=admin, data={"body": "Respuesta", "idempotency_key": "privacy-admin-internal"}).status_code == 200
    assert client.post(f"/api/v1/messaging/staff/internal/threads/{direct['id']}/read", headers=employee).status_code == 200
    respuesta = next(row for row in client.get(internal, headers=admin).json() if row["body"] == "Respuesta")
    assert respuesta["estado_envio"] == "read"


def test_guardar_privacidad_solo_invalida_chats_con_lecturas_y_emite_un_aviso(tmp_path, monkeypatch):
    from backend.api.messaging_models import MessagingConversation, MessagingEvent, MessagingOrganization
    client, factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    path = f"/api/v1/messaging/client/conversations/{conv_id}"
    assert client.post(f"{path}/messages", headers=auth,
                       data={"body": "Pregunta", "idempotency_key": "privacy-refresh"}).status_code == 200
    assert client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read", headers=admin).status_code == 200
    with factory() as db:
        organization_id = db.get(MessagingConversation, conv_id).organization_id
        for numero in range(40):
            org = MessagingOrganization(company_code=f"E{30000 + numero}", name="Empresa sin lecturas")
            db.add(org)
            db.flush()
            db.add(MessagingConversation(organization_id=org.id, kind="fiscal"))
        db.commit()
    avisos = []
    consultas = []
    monkeypatch.setattr(messaging_api.hub, "publish", lambda payload, **kwargs: avisos.append((payload, kwargs)))
    engine = factory.kw["bind"]
    def contar(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            consultas.append(statement)
    event.listen(engine, "before_cursor_execute", contar)
    try:
        response = client.patch("/api/v1/messaging/staff/me", headers=admin,
                                json={"mostrar_lecturas_clientes": False})
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    assert response.status_code == 200
    assert len(consultas) <= 15
    assert avisos == [({"type": "message.states_updated"},
                       {"staff_ids": set(), "organization_ids": {organization_id}})]
    with factory() as db:
        actualizados = db.scalars(select(MessagingEvent).where(
            MessagingEvent.event_type == "message_states_updated",
        )).all()
        assert [row.conversation_id for row in actualizados] == [conv_id]
    perfil = client.get("/api/v1/messaging/staff/me", headers=admin).json()
    assert perfil["mostrar_lecturas_clientes"] is False
    assert perfil["mostrar_lecturas_empleados"] is True


def test_aviso_privacidad_llega_una_vez_y_solo_a_destinatarios_seleccionados():
    async def comprobar():
        bus = RealtimeHub()
        cliente = bus.subscribe(audience="client", actor_id="cliente", organization_id="empresa")
        ajeno = bus.subscribe(audience="client", actor_id="ajeno", organization_id="otra")
        empleado = bus.subscribe(audience="staff", actor_id="empleado")
        otro = bus.subscribe(audience="staff", actor_id="otro")
        bus.publish({"type": "message.states_updated"}, organization_ids={"empresa"}, staff_ids={"empleado"})
        await asyncio.sleep(0)
        assert cliente.queue.qsize() == 1
        assert empleado.queue.qsize() == 1
        assert ajeno.queue.empty()
        assert otro.queue.empty()
        assert cliente.queue.get_nowait() == {"type": "message.states_updated"}
    asyncio.run(comprobar())


def test_privacidad_se_aplica_a_lecturas_historicas_sin_borrarlas(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    me = "/api/v1/messaging/staff/me"
    path = f"/api/v1/messaging/client/conversations/{conv_id}/messages"
    client.post(path, headers=auth, data={"body": "Pregunta", "idempotency_key": "old-receipt"})
    client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read", headers=admin)
    assert "lecturas" not in client.get(path, headers=auth).json()[0]
    for compartir in (False, True, False):
        assert client.patch(me, headers=admin, json={"mostrar_lecturas_clientes": compartir}).status_code == 200
        row = client.get(path, headers=auth).json()[0]
        assert all(campo not in row for campo in ("estado_envio", "lecturas", "destinatarios"))
        # No altera la otra preferencia ni el contador de mensajes pendientes.
        assert client.get(me, headers=admin).json()["mostrar_lecturas_empleados"] is True
        conv = next(row for row in client.get("/api/v1/messaging/staff/conversations", headers=admin).json() if row["id"] == conv_id)
        assert conv["unread_count"] == 0
    assert client.patch(me, headers=staff_headers("employee"), json={"mostrar_lecturas_clientes": False}).status_code == 403
    assert client.patch(me, headers=auth, json={"mostrar_lecturas_empleados": False}).status_code in {401, 403}
    assert client.patch(me, json={"mostrar_lecturas_clientes": False}).status_code == 401


def test_privacidad_es_del_usuario_y_no_oculta_lecturas_a_otros_administradores(tmp_path, monkeypatch):
    client, _factory, staff_headers, _auth, _client_id, _conv_id = _setup(tmp_path, monkeypatch)
    assert client.put("/api/v1/messaging/internal/staff/admin2", headers={"X-API-Key": "test-secret"},
                      json={"external_id": "admin2", "name": "Admin2", "email": "admin2@gestinem.es",
                            "role": "admin", "active": True, "channels": ["fiscal"]}).status_code == 200
    admin = staff_headers("admin")
    admin2 = staff_headers("admin2")
    me = "/api/v1/messaging/staff/me"
    assert client.patch(me, headers=admin2, json={"mostrar_lecturas_clientes": False,
                                                "mostrar_lecturas_empleados": False}).status_code == 200
    assert client.get(me, headers=admin).json()["mostrar_lecturas_clientes"] is True
    assert client.get(me, headers=admin).json()["mostrar_lecturas_empleados"] is True
    direct = client.post("/api/v1/messaging/staff/internal/direct/admin2", headers=admin)
    assert direct.status_code == 201
    thread_id = direct.json()["id"]
    path = f"/api/v1/messaging/staff/internal/threads/{thread_id}/messages"
    assert client.post(path, headers=admin, data={"body": "Pregunta", "idempotency_key": "admin-to-admin"}).status_code == 200
    assert client.post(f"/api/v1/messaging/staff/internal/threads/{thread_id}/read", headers=admin2).status_code == 200
    assert client.get(path, headers=admin).json()[0]["estado_envio"] == "read"


def test_sse_no_revela_lecturas_ocultas_y_filtra_chats_internos(tmp_path, monkeypatch):
    client, factory, staff_headers, auth, _client_id, conv_id = _setup(tmp_path, monkeypatch)
    admin = staff_headers("admin")
    # Incluso una preferencia historica permisiva no expone lecturas al cliente.
    client.patch("/api/v1/messaging/staff/me", headers=admin, json={"mostrar_lecturas_clientes": True, "mostrar_lecturas_empleados": False})
    path = f"/api/v1/messaging/client/conversations/{conv_id}/messages"
    client.post(path, headers=auth, data={"body": "Pregunta", "idempotency_key": "sse-privacy"})
    client.post(f"/api/v1/messaging/staff/conversations/{conv_id}/read", headers=admin)
    threads = client.get("/api/v1/messaging/staff/internal/threads", headers=staff_headers("employee")).json()
    direct = next(row for row in threads if row["kind"] == "direct")
    client.post(f"/api/v1/messaging/staff/internal/threads/{direct['id']}/messages",
                headers=staff_headers("employee"), data={"body": "Consulta", "idempotency_key": "sse-internal"})
    client.post(f"/api/v1/messaging/staff/internal/threads/{direct['id']}/read", headers=admin)
    async def no_esperar(_seconds):
        pass
    monkeypatch.setattr(messaging_api.asyncio, "sleep", no_esperar)
    assert "event: read_updated" not in client.get("/api/v1/messaging/client/events", headers=auth).text
    assert "event: read_updated" not in client.get("/api/v1/messaging/staff/events", headers=staff_headers("employee")).text
    assert "event: read_updated" in client.get("/api/v1/messaging/staff/events", headers=admin).text
    client.patch("/api/v1/messaging/staff/me", headers=admin, json={"mostrar_lecturas_empleados": True})
    assert f'"thread_id": "{direct["id"]}"' in client.get("/api/v1/messaging/staff/events", headers=staff_headers("employee")).text
    assert client.put("/api/v1/messaging/internal/staff/otro", headers={"X-API-Key": "test-secret"},
                      json={"external_id": "otro", "name": "Otro", "role": "empleado", "active": True, "channels": ["fiscal"]}).status_code == 200
    assert f'"thread_id": "{direct["id"]}"' not in client.get("/api/v1/messaging/staff/events", headers=staff_headers("otro")).text


def test_baja_maestra_oculta_empresa_y_revoca_acceso(tmp_path, monkeypatch):
    client, factory, staff_headers, auth, client_id, _conversation_id = _setup(
        tmp_path, monkeypatch,
    )
    device = client.put(
        "/api/v1/messaging/client/app-devices",
        headers=auth,
        json={
            "platform": "android",
            "push_token": "token-baja-maestra-abcdefghijklmnopqrstuvwxyz",
        },
    )
    assert device.status_code == 200

    disabled = client.put(
        "/api/v1/messaging/client/internal/sync-profile",
        headers={"X-API-Key": "test-secret"},
        json={"company_code": "E10001", "active": False},
    )
    assert disabled.status_code == 200

    organizations = client.get(
        "/api/v1/messaging/staff/admin/organizations",
        headers=staff_headers("admin"),
    ).json()
    assert all(row["company_code"] != "E10001" for row in organizations)
    assert client.get(
        "/api/v1/messaging/client/conversations", headers=auth,
    ).status_code in {401, 403}
    assert client.post(
        "/api/v1/messaging/staff/admin/invitations",
        headers=staff_headers("admin"),
        json={
            "company_code": "E10001",
            "name": "Maria",
            "email": "maria@example.test",
            "send_email": False,
        },
    ).status_code == 409

    from backend.api.messaging_models import (
        MessagingAppDevice,
        MessagingClient,
        MessagingInvitation,
        MessagingOrganization,
        MessagingSession,
    )

    with factory() as db:
        org = db.scalar(select(MessagingOrganization).where(
            MessagingOrganization.company_code == "E10001",
        ))
        account = db.get(MessagingClient, client_id)
        sessions = db.scalars(select(MessagingSession).where(
            MessagingSession.client_id == client_id,
        )).all()
        invitations = db.scalars(select(MessagingInvitation).where(
            MessagingInvitation.client_id == client_id,
        )).all()
        app_devices = db.scalars(select(MessagingAppDevice).where(
            MessagingAppDevice.user_id == client_id,
        )).all()
        assert org.active is False
        assert account.active is False
        assert sessions and all(row.revoked_at is not None for row in sessions)
        assert invitations and all(
            row.used_at is not None or row.revoked_at is not None
            for row in invitations
        )
        assert app_devices and all(not row.active for row in app_devices)

    enabled = client.put(
        "/api/v1/messaging/client/internal/sync-profile",
        headers={"X-API-Key": "test-secret"},
        json={"company_code": "E10001", "active": True},
    )
    assert enabled.status_code == 200
    organizations = client.get(
        "/api/v1/messaging/staff/admin/organizations",
        headers=staff_headers("admin"),
    ).json()
    restored = next(row for row in organizations if row["company_code"] == "E10001")
    assert restored["client_access_status"] == "disabled"


def test_notas_de_voz_se_reproducen_y_no_entran_en_bandeja_documental(
    tmp_path, monkeypatch,
):
    client, _factory, staff_headers, client_auth, _client_id, conversation_id = (
        _setup(tmp_path, monkeypatch)
    )
    voice_bytes = b"OggS-nota-de-voz"
    sent = client.post(
        f"/api/v1/messaging/client/conversations/{conversation_id}/messages",
        headers=client_auth,
        data={"idempotency_key": "voice-client-1"},
        files={"files": ("nota_voz.opus", voice_bytes, "audio/ogg")},
    )
    assert sent.status_code == 200
    attachment = sent.json()["attachments"][0]
    assert attachment["content_type"] == "audio/ogg"

    # Una nota de voz permanece en el chat y no se archiva como documento.
    assert client.get(
        "/api/v1/messaging/staff/attachments/pending",
        headers=staff_headers("admin"),
    ).json() == []
    staff_playback = client.get(
        f"/api/v1/messaging/staff/attachments/{attachment['id']}/download",
        headers=staff_headers("admin"),
    )
    assert staff_playback.status_code == 200
    assert staff_playback.content == voice_bytes

    # El autor tambien puede volver a escuchar su propia grabacion.
    client_playback = client.get(
        f"/api/v1/messaging/client/attachments/{attachment['id']}",
        headers=client_auth,
    )
    assert client_playback.status_code == 200
    assert client_playback.content == voice_bytes

    reply_bytes = b"OggS-respuesta-del-despacho"
    reply = client.post(
        f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
        headers=staff_headers("admin"),
        data={"idempotency_key": "voice-staff-1"},
        files={"files": ("nota_voz.opus", reply_bytes, "audio/ogg")},
    )
    assert reply.status_code == 200
    reply_attachment = reply.json()["attachments"][0]
    downloaded_reply = client.get(
        f"/api/v1/messaging/client/attachments/{reply_attachment['id']}",
        headers=client_auth,
    )
    assert downloaded_reply.status_code == 200
    assert downloaded_reply.content == reply_bytes


def test_adjuntos_en_chat_interno_son_multiples_privados_y_borrables(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, _client_id, _conversation_id = _setup(
        tmp_path, monkeypatch,
    )
    employee_threads = client.get(
        "/api/v1/messaging/staff/internal/threads", headers=staff_headers("employee"),
    ).json()
    direct = next(row for row in employee_threads if row["kind"] == "direct")

    sent = client.post(
        f"/api/v1/messaging/staff/internal/threads/{direct['id']}/messages",
        headers=staff_headers("employee"),
        data={"idempotency_key": "internal-files-1"},
        files=[
            ("files", ("informe.pdf", b"%PDF-interno", "application/pdf")),
            ("files", ("datos.csv", b"a,b\n1,2", "text/csv")),
        ],
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload["body"] == ""
    assert payload["has_attachments"] is True
    assert [row["name"] for row in payload["attachments"]] == ["informe.pdf", "datos.csv"]
    assert all(row["available"] for row in payload["attachments"])

    attachment_id = payload["attachments"][0]["id"]
    downloaded = client.get(
        f"/api/v1/messaging/staff/internal/attachments/{attachment_id}",
        headers=staff_headers("admin"),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-interno"

    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/staff/outsider", headers=internal,
        json={
            "external_id": "outsider", "name": "Fuera", "email": "fuera@gestinem.es",
            "role": "empleado", "active": True, "channels": [],
        },
    ).status_code == 200
    assert client.get(
        f"/api/v1/messaging/staff/internal/attachments/{attachment_id}",
        headers=staff_headers("outsider"),
    ).status_code == 403

    with factory() as db:
        attachment = db.get(MessagingAttachment, attachment_id)
        stored_path = tmp_path / "cloud" / attachment.storage_key
        assert stored_path.exists()
    deleted = client.request(
        "DELETE",
        f"/api/v1/messaging/staff/admin/internal/messages/{payload['id']}/hard",
        headers=staff_headers("admin"),
        json={"reason": "Prueba de limpieza"},
    )
    assert deleted.status_code == 204
    assert not stored_path.exists()


def test_presencia_staff_exige_conexion_viva_y_sesion_valida(tmp_path, monkeypatch):
    client, factory, staff_headers, _auth, _client_id, _conversation_id = _setup(
        tmp_path, monkeypatch,
    )
    now = utcnow()
    with factory() as db:
        first = MessagingStaffSession(
            staff_external_id="employee", token_hash="presence-session-1",
            expires_at=now + timedelta(days=1),
        )
        second = MessagingStaffSession(
            staff_external_id="employee", token_hash="presence-session-2",
            expires_at=now + timedelta(days=1),
        )
        db.add_all([first, second])
        db.flush()
        db.add_all([
            MessagingStaffPresenceConnection(
                staff_external_id="employee", staff_session_id=first.id,
                connected_until=now - timedelta(seconds=1),
            ),
            MessagingStaffPresenceConnection(
                staff_external_id="employee", staff_session_id=second.id,
                connected_until=now + timedelta(seconds=35),
            ),
        ])
        db.commit()

    directory = client.get(
        "/api/v1/messaging/staff/admin/directory", headers=staff_headers("admin"),
    ).json()
    assert next(row for row in directory if row["id"] == "employee")["online"] is True

    with factory() as db:
        second = db.scalar(select(MessagingStaffSession).where(
            MessagingStaffSession.token_hash == "presence-session-2",
        ))
        second.revoked_at = utcnow()
        db.commit()
    directory = client.get(
        "/api/v1/messaging/staff/admin/directory", headers=staff_headers("admin"),
    ).json()
    assert next(row for row in directory if row["id"] == "employee")["online"] is False


def _ticket_presencia(factory, token):
    with factory() as db:
        session = MessagingStaffSession(
            staff_external_id="employee", token_hash=hash_token(f"session-{token}"),
            expires_at=utcnow() + timedelta(days=1),
        )
        db.add(session)
        db.flush()
        db.add(MessagingWebSocketTicket(
            user_type="staff", user_id="employee", token_hash=hash_token(token),
            staff_session_id=session.id, expires_at=utcnow() + timedelta(seconds=60),
        ))
        db.commit()
        return session.id


@pytest.mark.asyncio
async def test_presencia_se_renueva_con_eventos_continuos(tmp_path, monkeypatch):
    _client, factory, *_rest = _setup(tmp_path, monkeypatch)
    _ticket_presencia(factory, "busy-ticket")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.02)
    eventos = []

    class SocketOcupado:
        def __init__(self):
            self.entrada = asyncio.Queue()

        async def accept(self):
            pass

        async def receive(self):
            return await self.entrada.get()

        async def send_json(self, payload):
            eventos.append(payload)
            if payload["type"] == "connected":
                # Simula la caducidad; el latido debe renovarla sin silencio.
                with factory() as db:
                    row = db.scalar(select(MessagingStaffPresenceConnection))
                    row.connected_until = utcnow() - timedelta(seconds=1)
                    db.commit()
            elif payload["type"] == "ping":
                self.entrada.put_nowait({"type": "websocket.disconnect"})
            bus.publish({"type": "message.created"})
            await asyncio.sleep(0.001)

    # El cierre borra la presencia, por eso comprobamos la renovacion en el UPDATE.
    actualizaciones = []

    def registrar_actualizacion(_mapper, _connection, target):
        actualizaciones.append(target.connected_until)

    event.listen(MessagingStaffPresenceConnection, "after_update", registrar_actualizacion)
    try:
        await asyncio.wait_for(
            messaging_api.messaging_websocket(SocketOcupado(), "staff", "busy-ticket"),
            timeout=1,
        )
    finally:
        event.remove(MessagingStaffPresenceConnection, "after_update", registrar_actualizacion)
    assert any(payload["type"] == "message.created" for payload in eventos)
    assert any(payload["type"] == "ping" for payload in eventos)
    assert actualizaciones[-1] > utcnow() + timedelta(seconds=30)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MessagingStaffPresenceConnection)) == 0
    assert not bus._subscriptions


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["revocada", "caducada", "inactivo"])
async def test_presencia_revalida_acceso_aunque_haya_eventos(tmp_path, monkeypatch, estado):
    _client, factory, *_rest = _setup(tmp_path, monkeypatch)
    session_id = _ticket_presencia(factory, "ticket-revocado")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "hub", bus)
    monkeypatch.setattr(messaging_api, "INTERVALO_PRESENCIA_WS", 0.02)

    class SocketRevocado:
        codigo_cierre = None

        async def accept(self):
            pass

        async def receive(self):
            await asyncio.Future()

        async def close(self, code):
            self.codigo_cierre = code

        async def send_json(self, payload):
            if payload["type"] == "connected":
                with factory() as db:
                    session = db.get(MessagingStaffSession, session_id)
                    if estado == "revocada":
                        session.revoked_at = utcnow()
                    elif estado == "caducada":
                        session.expires_at = utcnow() - timedelta(seconds=1)
                    else:
                        db.get(MessagingStaff, "employee").active = False
                    db.commit()
            bus.publish({"type": "message.created"})
            await asyncio.sleep(0.001)

    socket = SocketRevocado()
    await asyncio.wait_for(
        messaging_api.messaging_websocket(socket, "staff", "ticket-revocado"), timeout=1,
    )
    assert socket.codigo_cierre == 4401
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MessagingStaffPresenceConnection)) == 0
    assert not bus._subscriptions


def test_cerrar_una_pestana_conserva_presencia_de_la_otra(tmp_path, monkeypatch):
    client, factory, *_rest = _setup(tmp_path, monkeypatch)
    _ticket_presencia(factory, "ticket-uno")
    _ticket_presencia(factory, "ticket-dos")
    bus = RealtimeHub()
    monkeypatch.setattr(messaging_api, "hub", bus)
    eventos = []
    publish = bus.publish

    def publicar(payload, **kwargs):
        eventos.append(payload)
        publish(payload, **kwargs)

    monkeypatch.setattr(bus, "publish", publicar)
    with client:
        with client.websocket_connect("/api/v1/messaging/ws/staff?ticket=ticket-uno") as uno:
            assert uno.receive_json()["type"] == "connected"
            with client.websocket_connect("/api/v1/messaging/ws/staff?ticket=ticket-dos") as dos:
                assert dos.receive_json()["type"] == "connected"
            assert eventos[-1]["online"] is True
            with factory() as db:
                assert messaging_api._staff_online(db, "employee") is True
    assert eventos[-1]["online"] is False
    with factory() as db:
        assert messaging_api._staff_online(db, "employee") is False
    assert not bus._subscriptions


def test_invitacion_https_entrega_deep_link_y_token_a_accept_invite(tmp_path, monkeypatch):
    client, _factory = _api(tmp_path, monkeypatch)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/organizations/E10002", headers=internal,
        json={"company_code": "E10002", "name": "Cliente Dos"},
    ).status_code == 200
    sent = []
    monkeypatch.setattr(messaging_api, "mail_configured", lambda: True)
    monkeypatch.setattr(
        messaging_api, "send_invitation",
        lambda email, name, url: sent.append((email, name, url)),
    )

    response = client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E10002", "name": "Ana",
            "email": "ana@example.test", "send_email": True,
        },
    )
    assert response.status_code == 200
    invitation = response.json()
    assert invitation["url"].startswith(
        "https://app.example.test/#/accept-invite?token="
    )
    assert sent == [("ana@example.test", "Ana", invitation["url"])]

    token = parse_qs(urlparse(urlparse(invitation["url"]).fragment).query)["token"][0]
    accepted = client.post(
        "/api/v1/messaging/auth/accept-invite",
        json={"token": token, "password": "contrasena-muy-segura"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["client"]["email"] == "ana@example.test"


def test_invitacion_flutter_asigna_y_recupera_chat_directo(tmp_path, monkeypatch):
    client, _factory = _api(tmp_path, monkeypatch)
    internal = {"X-API-Key": "test-secret"}
    for staff_id in ("admin-owner", "admin-other"):
        assert client.put(
            f"/api/v1/messaging/internal/staff/{staff_id}", headers=internal,
            json={
                "external_id": staff_id, "name": staff_id,
                "email": f"{staff_id}@gestinem.es", "role": "admin",
                "active": True, "channels": ["fiscal", "laboral"],
            },
        ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/direct-device", headers=internal,
    ).json()

    def staff_headers(staff_id):
        return {
            **internal, "X-Device-Id": "direct-device",
            "X-Device-Token": device["device_token"], "X-Staff-Id": staff_id,
        }

    assert client.put(
        "/api/v1/messaging/internal/organizations/E10003", headers=internal,
        json={"company_code": "E10003", "name": "Cliente sin titular"},
    ).status_code == 200
    invited = client.post(
        "/api/v1/messaging/staff/admin/invitations",
        headers=staff_headers("admin-owner"),
        json={
            "company_code": "E10003", "name": "Ana Cliente",
            "email": "ana-directo@example.test", "send_email": False,
        },
    )
    assert invited.status_code == 200

    organizations = client.get(
        "/api/v1/messaging/staff/admin/organizations",
        headers=staff_headers("admin-owner"),
    ).json()
    organization = next(
        row for row in organizations if row["company_code"] == "E10003"
    )
    assert organization["private_owner_external_id"] == "admin-owner"
    assert organization["client_access_status"] == "pending"
    assert organization["contact_name"] == "Ana Cliente"
    assert organization["contact_email"] == "ana-directo@example.test"
    assert organization["invitation_expires_at"]

    owner_targets = client.get(
        "/api/v1/messaging/staff/conversation-targets",
        headers=staff_headers("admin-owner"),
    ).json()
    assert any(
        row["company_code"] == "E10003" and row["kind"] == "private"
        for row in owner_targets
    )
    other_targets = client.get(
        "/api/v1/messaging/staff/conversation-targets",
        headers=staff_headers("admin-other"),
    ).json()
    assert not any(
        row["company_code"] == "E10003" and row["kind"] == "private"
        for row in other_targets
    )


def test_admin_reclama_directo_antiguo_sin_titular_al_abrirlo(tmp_path, monkeypatch):
    client, _factory = _api(tmp_path, monkeypatch)
    internal = {"X-API-Key": "test-secret"}
    assert client.put(
        "/api/v1/messaging/internal/staff/admin", headers=internal,
        json={
            "external_id": "admin", "name": "Administrador",
            "email": "admin@gestinem.es", "role": "admin", "active": True,
        },
    ).status_code == 200
    assert client.put(
        "/api/v1/messaging/internal/organizations/E10004", headers=internal,
        json={"company_code": "E10004", "name": "Cliente antiguo"},
    ).status_code == 200
    assert client.post(
        "/api/v1/messaging/internal/invitations", headers=internal,
        json={
            "company_code": "E10004", "name": "Cliente Antiguo",
            "email": "antiguo@example.test", "send_email": False,
        },
    ).status_code == 200
    device = client.post(
        "/api/v1/messaging/internal/devices/legacy-device", headers=internal,
    ).json()
    staff = {
        **internal, "X-Device-Id": "legacy-device",
        "X-Device-Token": device["device_token"], "X-Staff-Id": "admin",
    }
    targets = client.get(
        "/api/v1/messaging/staff/conversation-targets", headers=staff,
    ).json()
    direct = next(
        row for row in targets
        if row["company_code"] == "E10004" and row["kind"] == "private"
    )
    assert client.post(
        f"/api/v1/messaging/staff/conversations/{direct['id']}/start",
        headers=staff,
    ).status_code == 200
    organization = next(
        row for row in client.get(
            "/api/v1/messaging/staff/admin/organizations", headers=staff,
        ).json()
        if row["company_code"] == "E10004"
    )
    assert organization["private_owner_external_id"] == "admin"


def test_bandeja_staff_incluye_clientes_activos_sin_chat_previo(tmp_path, monkeypatch):
    client, _factory, staff_headers, _auth, _client_id, fiscal_id = _setup(
        tmp_path, monkeypatch,
    )
    admin = staff_headers("admin")
    employee = staff_headers("employee")

    admin_inbox = client.get(
        "/api/v1/messaging/staff/conversations", headers=admin,
    ).json()
    assert fiscal_id in {row["id"] for row in admin_inbox}
    admin_targets = client.get(
        "/api/v1/messaging/staff/conversation-targets", headers=admin,
    ).json()
    assert fiscal_id in {row["id"] for row in admin_targets}
    employee_targets = client.get(
        "/api/v1/messaging/staff/conversation-targets", headers=employee,
    ).json()
    assert {row["kind"] for row in employee_targets} == {"fiscal"}
    employee_inbox = client.get(
        "/api/v1/messaging/staff/conversations", headers=employee,
    ).json()
    assert [row["id"] for row in employee_inbox] == [fiscal_id]
    assert employee_inbox[0]["started_at"] is None
    assert employee_inbox[0]["last_message"] is None

    started = client.post(
        f"/api/v1/messaging/staff/conversations/{fiscal_id}/start",
        headers=employee,
    )
    assert started.status_code == 200
    assert started.json()["started_at"] is not None
    inbox = client.get(
        "/api/v1/messaging/staff/conversations", headers=employee,
    ).json()
    assert [row["id"] for row in inbox] == [fiscal_id]
    assert inbox[0]["last_message"] is None
    assert inbox[0]["unread_count"] == 0

    assert client.patch(
        "/api/v1/messaging/staff/admin/organizations/E10001/client-access",
        headers=admin, json={"active": False},
    ).status_code == 200
    assert client.get(
        "/api/v1/messaging/staff/conversations", headers=admin,
    ).json() == []
    assert client.get(
        "/api/v1/messaging/staff/conversation-targets", headers=admin,
    ).json() == []


def test_cliente_recibe_etiquetas_para_sus_tres_canales(tmp_path, monkeypatch):
    client, _factory, staff_headers, auth, _client_id, _conversation_id = _setup(
        tmp_path, monkeypatch,
    )
    avatar = BytesIO()
    Image.new("RGB", (100, 100), "#145a86").save(avatar, format="PNG")
    assert client.put(
        "/api/v1/messaging/staff/admin/directory/admin/avatar",
        headers=staff_headers("admin"),
        files={"avatar": ("admin.png", avatar.getvalue(), "image/png")},
    ).status_code == 200

    rows = client.get(
        "/api/v1/messaging/client/conversations", headers=auth,
    ).json()

    assert {row["kind"]: row["channel_label"] for row in rows} == {
        "laboral": "LA",
        "fiscal": "CF",
        "private": "AD",
    }
    private = next(row for row in rows if row["kind"] == "private")
    assert private["channel_avatar_url"].endswith("/client/avatars/admin")
    assert len(private["channel_avatar_version"]) == 12
    assert client.get(private["channel_avatar_url"], headers=auth).status_code == 200


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


def test_hard_delete_mensajes_con_adjuntos_rechazado(tmp_path, monkeypatch):
    """Los mensajes con adjuntos no admiten borrado definitivo ordinario.
    Usa 'Retirar documento' para adjuntos salientes."""
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
    # El borrado definitivo de mensajes con adjuntos esta prohibido
    resp = client.request(
        "DELETE", f"/api/v1/messaging/staff/admin/messages/{sent['id']}/hard",
        headers=staff_headers("admin"), json={"reason": "prueba"},
    )
    assert resp.status_code == 409
    # El archivo debe seguir existiendo tras el intento de borrado
    assert stored_path.is_file()


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
    assert [row["name"] for row in employee_groups] == [
        "Equipo Contable / Fiscal", "Equipo especial",
    ]
    staff_threads = client.get(
        "/api/v1/messaging/staff/internal/threads",
        headers=staff_headers("employee"),
    ).json()
    staff_thread = next(row for row in staff_threads if row["title"] == "Equipo especial")
    assert client.delete(
        f"/api/v1/messaging/staff/admin/groups/{staff_group['id']}",
        headers=admin,
    ).status_code == 204
    assert all(
        row["id"] != staff_thread["id"]
        for row in client.get(
            "/api/v1/messaging/staff/internal/threads",
            headers=staff_headers("employee"),
        ).json()
    )

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
        lambda token, payload, platform=None: delivered.append((token, payload)) or messaging_api.FcmResult(success=True, permanent_failure=False),
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
    with client:
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


def test_lectura_se_publica_al_emisor_por_websocket_en_tiempo_real(tmp_path, monkeypatch):
    client, factory, staff_headers, auth, _client_id, conversation_id = _setup(
        tmp_path, monkeypatch,
    )
    admin = staff_headers("admin")
    assert client.post(
        f"/api/v1/messaging/staff/conversations/{conversation_id}/messages",
        headers=admin,
        data={"body": "Aviso en directo", "idempotency_key": "live-read"},
    ).status_code == 200
    ticket = "live-read-ticket"
    with factory() as db:
        session = MessagingStaffSession(
            staff_external_id="admin",
            token_hash=hash_token("live-read-session"),
            expires_at=utcnow() + timedelta(days=1),
        )
        db.add(session)
        db.flush()
        db.add(MessagingWebSocketTicket(
            user_type="staff", user_id="admin", token_hash=hash_token(ticket),
            staff_session_id=session.id, expires_at=utcnow() + timedelta(seconds=60),
        ))
        db.commit()

    with client:
        with client.websocket_connect(
            f"/api/v1/messaging/ws/staff?ticket={ticket}",
        ) as websocket:
            assert websocket.receive_json()["type"] == "connected"
            response = client.post(
                f"/api/v1/messaging/client/conversations/{conversation_id}/read",
                headers=auth,
            )
            assert response.status_code == 200
            assert response.json()["changed"] is True
            events = [websocket.receive_json() for _ in range(2)]
            read_event = next(event for event in events if event["type"] == "message.read")
            assert read_event["conversation_id"] == conversation_id
            assert read_event["actor_type"] == "client"


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
    assert callback.headers["location"].startswith(
        "https://api.example.test/api/v1/messaging/public/auth-done?code="
    )
    code = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]
    exchanged = client.post(
        "/api/v1/messaging/staff-auth/mobile/exchange", json={"code": code},
    )
    assert exchanged.status_code == 200
    assert exchanged.json()["staff"]["role"] == "admin"
    assert client.post(
        "/api/v1/messaging/staff-auth/mobile/exchange", json={"code": code},
    ).status_code == 400


# ---------------------------------------------------------------------------
# Validacion de web_redirect en staff-auth/login
# ---------------------------------------------------------------------------

class _FakeMsal:
    def initiate_auth_code_flow(self, **_kwargs):
        return {"state": "s1", "auth_uri": "https://login.example.test"}


def _web_redirect_client(tmp_path, monkeypatch, web_redirect_uri: str):
    monkeypatch.setenv("MESSAGING_APP_WEB_REDIRECT_URI", web_redirect_uri)
    client, _ = _api(tmp_path, monkeypatch)
    monkeypatch.setattr(messaging_api, "_staff_msal_app", lambda: _FakeMsal())
    return client


def test_web_redirect_https_permitido(tmp_path, monkeypatch):
    uri = "https://app.gestinem.es/auth/callback"
    client = _web_redirect_client(tmp_path, monkeypatch, uri)
    r = client.get(
        f"/api/v1/messaging/staff-auth/login?app=true&web_redirect={uri}",
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_web_redirect_http_localhost_permitido(tmp_path, monkeypatch):
    uri = "http://localhost:8080/auth/callback"
    client = _web_redirect_client(tmp_path, monkeypatch, uri)
    r = client.get(
        f"/api/v1/messaging/staff-auth/login?app=true&web_redirect={uri}",
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_web_redirect_http_127_permitido(tmp_path, monkeypatch):
    uri = "http://127.0.0.1:8080/auth/callback"
    client = _web_redirect_client(tmp_path, monkeypatch, uri)
    r = client.get(
        f"/api/v1/messaging/staff-auth/login?app=true&web_redirect={uri}",
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_web_redirect_http_externo_rechazado(tmp_path, monkeypatch):
    # La URI configurada usa HTTP con host externo; aun asi debe rechazarse.
    uri = "http://evil.example.com/auth/callback"
    client = _web_redirect_client(tmp_path, monkeypatch, uri)
    r = client.get(
        f"/api/v1/messaging/staff-auth/login?app=true&web_redirect={uri}",
        follow_redirects=False,
    )
    assert r.status_code == 422


def test_web_redirect_uri_distinta_rechazada(tmp_path, monkeypatch):
    configured = "https://app.gestinem.es/auth/callback"
    other = "https://attacker.example.com/auth/callback"
    client = _web_redirect_client(tmp_path, monkeypatch, configured)
    r = client.get(
        f"/api/v1/messaging/staff-auth/login?app=true&web_redirect={other}",
        follow_redirects=False,
    )
    assert r.status_code == 422
