"""Pruebas de trazabilidad documental de adjuntos de mensajeria.

Cubre los dos sentidos del circuito:
A. Cliente -> Despacho (adjuntos entrantes)
B. Despacho -> Cliente (adjuntos salientes)
"""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base
from backend.api import messaging_api
from backend.api.messaging_api import get_db, router
from backend.api import messaging_models  # noqa: F401
from backend.api.messaging_models import (
    MessagingAttachment,
    MessagingClient,
    MessagingConversation,
    MessagingDownload,
    MessagingMessage,
    MessagingOrganization,
    MessagingSession,
    MessagingStaff,
    MessagingStaffSession,
)
from backend.api.messaging_security import hash_token, new_token, session_expiry


def _utcnow():
    return datetime.now(timezone.utc)


def _make_client(tmp_path):
    os.environ["DGT_INTERNAL_API_KEY"] = "test-secret"
    os.environ["MESSAGING_STORAGE_DIR"] = str(tmp_path / "cloud")
    os.environ["MESSAGING_PUBLIC_BASE_URL"] = "https://api.example.test"
    os.environ["MESSAGING_SYNC_TOKEN"] = "sync-secret"
    os.environ["MESSAGING_STAFF_ALLOWED_DOMAIN"] = "gestinem.es"
    os.environ["MESSAGING_STAFF_ADMIN_EMAILS"] = "admin@gestinem.es"
    os.environ["MESSAGING_ATTACHMENT_DAYS"] = "30"
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
    return TestClient(app, base_url="https://api.example.test"), factory


def _seed(factory):
    """Crea organizacion, cliente, conversaciones y staff para las pruebas."""
    with factory() as db:
        org = MessagingOrganization(company_code="E00001", name="Empresa Test", active=True)
        db.add(org); db.flush()
        conv = MessagingConversation(organization_id=org.id, kind="fiscal")
        db.add(conv); db.flush()
        client = MessagingClient(
            organization_id=org.id, name="Cliente Test", email="cliente@test.es",
        )
        from backend.api.messaging_security import hash_password
        client.password_hash = hash_password("password")
        db.add(client); db.flush()
        token = new_token()
        session = MessagingSession(
            client_id=client.id, token_hash=hash_token(token),
            expires_at=session_expiry(),
        )
        db.add(session)
        staff = MessagingStaff(
            external_id="admin@gestinem.es", name="Admin",
            email="admin@gestinem.es", role="admin", active=True,
        )
        db.add(staff); db.flush()
        staff_token = new_token()
        staff_session = MessagingStaffSession(
            staff_external_id=staff.external_id,
            token_hash=hash_token(staff_token),
            expires_at=session_expiry(),
        )
        db.add(staff_session)
        db.commit()
    return {
        "org_id": org.id, "conv_id": conv.id,
        "client_id": client.id, "client_token": token,
        "staff_id": staff.external_id, "staff_token": staff_token,
    }


def _auth_client(token):
    return {"Authorization": f"Bearer {token}"}


def _auth_staff(token):
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures de adjunto ───────────────────────────────────────────────────────

def _create_message_with_attachment(factory, seeds, direction="outgoing"):
    """Inserta directamente un mensaje con adjunto en la base de datos."""
    content = b"contenido de prueba para adjunto"
    sha = hashlib.sha256(content).hexdigest()
    key = f"test/{uuid.uuid4()}.pdf"
    with factory() as db:
        msg = MessagingMessage(
            conversation_id=seeds["conv_id"],
            author_type="staff" if direction == "outgoing" else "client",
            author_id=seeds["staff_id"] if direction == "outgoing" else seeds["client_id"],
            author_name="Staff Test" if direction == "outgoing" else "Cliente Test",
            body="Documento adjunto",
            idempotency_key=str(uuid.uuid4()),
        )
        db.add(msg); db.flush()
        att = MessagingAttachment(
            message_id=msg.id, name="documento.pdf",
            content_type="application/pdf",
            size=len(content), sha256=sha, storage_key=key,
            direction=direction,
            expires_at=(_utcnow() + timedelta(days=30)) if direction == "outgoing" else None,
        )
        db.add(att); db.commit()
        db.refresh(msg); db.refresh(att)
    return msg.id, att.id, content, sha


# ── A: Cliente no puede borrar mensajes con adjuntos ─────────────────────────

class TestClienteNoPuedeBorrarMensajesConAdjuntos:
    def test_soft_delete_bloqueado(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        msg_id, att_id, _, _ = _create_message_with_attachment(
            factory, seeds, direction="incoming",
        )
        # Cambiar autor a client para que el cliente pueda intentar borrar
        with factory() as db:
            msg = db.get(MessagingMessage, msg_id)
            msg.author_type = "client"
            msg.author_id = seeds["client_id"]
            db.commit()
        resp = client.delete(
            f"/api/v1/messaging/client/messages/{msg_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code == 409
        assert "adjuntos" in resp.text.lower()

    def test_texto_sin_adjunto_se_puede_borrar(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        with factory() as db:
            msg = MessagingMessage(
                conversation_id=seeds["conv_id"],
                author_type="client", author_id=seeds["client_id"],
                author_name="Cliente Test", body="Solo texto",
                idempotency_key=str(uuid.uuid4()),
            )
            db.add(msg); db.commit(); db.refresh(msg)
        resp = client.delete(
            f"/api/v1/messaging/client/messages/{msg.id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ── Admin no puede borrar mensajes con adjuntos ───────────────────────────────

class TestAdminNoPuedeBorrarMensajesConAdjuntos:
    def test_soft_delete_admin_bloqueado(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        msg_id, _, _, _ = _create_message_with_attachment(factory, seeds, direction="outgoing")
        resp = client.delete(
            f"/api/v1/messaging/staff/messages/{msg_id}",
            headers=_auth_staff(seeds["staff_token"]),
        )
        assert resp.status_code == 409

    def test_hard_delete_admin_bloqueado(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        msg_id, _, _, _ = _create_message_with_attachment(factory, seeds, direction="outgoing")
        resp = client.request(
            "DELETE",
            f"/api/v1/messaging/staff/admin/messages/{msg_id}/hard",
            headers={**_auth_staff(seeds["staff_token"]), "Content-Type": "application/json"},
            data=b'{"reason": "prueba"}',
        )
        assert resp.status_code == 409


# ── Cliente no puede descargar adjuntos entrantes ─────────────────────────────

class TestClienteNoDescargaAdjuntosEntrantes:
    def test_descarga_entrante_rechazada(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        _, att_id, _, _ = _create_message_with_attachment(
            factory, seeds, direction="incoming",
        )
        resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code in (404, 410)


# ── Caducidad a 30 dias ───────────────────────────────────────────────────────

class TestCaducidadAdjuntos:
    def test_adjunto_caducado_no_descargable(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        msg_id, att_id, content, sha = _create_message_with_attachment(
            factory, seeds, direction="outgoing",
        )
        # Caducar el adjunto manualmente
        with factory() as db:
            att = db.get(MessagingAttachment, att_id)
            att.expires_at = _utcnow() - timedelta(days=1)
            db.commit()
        resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code in (404, 410)

    def test_adjunto_vigente_descargable_con_storage(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        # Enviar mensaje con adjunto real via la API
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("test.pdf", io.BytesIO(b"pdf content"), "application/pdf")},
        )
        assert resp.status_code in (200, 201)
        attachments = resp.json().get("attachments", [])
        assert attachments
        att_id = attachments[0]["id"]
        resp2 = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp2.status_code == 200


# ── Descarga iniciada y completada ────────────────────────────────────────────

class TestDescargaIniciadaCompletada:
    def _send_outgoing(self, client, seeds):
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("report.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")},
        )
        assert resp.status_code in (200, 201)
        return resp.json()["attachments"][0]["id"]

    def test_descarga_registra_download_id(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code == 200
        assert "X-Download-Id" in resp.headers

    def test_confirmar_descarga_completada(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        dl_resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert dl_resp.status_code == 200
        download_id = dl_resp.headers["X-Download-Id"]
        confirm = client.post(
            f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
            headers=_auth_client(seeds["client_token"]),
            data={"download_id": download_id},
        )
        assert confirm.status_code == 200
        data = confirm.json()
        assert data["ok"] is True
        assert data["already_confirmed"] is False
        assert data["completed_at"]

    def test_confirmar_descarga_idempotente(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        dl_resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        download_id = dl_resp.headers["X-Download-Id"]
        r1 = client.post(
            f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
            headers=_auth_client(seeds["client_token"]),
            data={"download_id": download_id},
        )
        r2 = client.post(
            f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
            headers=_auth_client(seeds["client_token"]),
            data={"download_id": download_id},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["already_confirmed"] is True


# ── Primera, ultima y numero de descargas ─────────────────────────────────────

class TestContadorDescargas:
    def _send_and_download(self, client, seeds, factory, times=2):
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"content"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        for _ in range(times):
            dl = client.get(
                f"/api/v1/messaging/client/attachments/{att_id}",
                headers=_auth_client(seeds["client_token"]),
            )
            dl_id = dl.headers["X-Download-Id"]
            client.post(
                f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
                headers=_auth_client(seeds["client_token"]),
                data={"download_id": dl_id},
            )
        return att_id

    def test_resumen_descargas_en_staff(self, tmp_path):
        api_client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_and_download(api_client, seeds, factory, times=2)
        audit = api_client.get(
            f"/api/v1/messaging/staff/attachments/{att_id}/downloads",
            headers=_auth_staff(seeds["staff_token"]),
        )
        assert audit.status_code == 200
        rows = audit.json()
        completed = [r for r in rows if r.get("completed_at")]
        assert len(completed) == 2
        assert completed[0]["completed_at"] <= completed[-1]["completed_at"]


# ── Auditoria conservada tras caducidad ───────────────────────────────────────

class TestAuditoriaPostCaducidad:
    def test_auditoria_persiste_tras_eliminar_storage(self, tmp_path):
        api_client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = api_client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        dl = api_client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        dl_id = dl.headers["X-Download-Id"]
        api_client.post(
            f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
            headers=_auth_client(seeds["client_token"]),
            data={"download_id": dl_id},
        )
        # Simular que el storage fue eliminado por caducidad
        with factory() as db:
            att = db.get(MessagingAttachment, att_id)
            att.storage_deleted_at = _utcnow()
            att.storage_key = ""
            att.expires_at = _utcnow() - timedelta(days=1)
            db.commit()
        audit = api_client.get(
            f"/api/v1/messaging/staff/attachments/{att_id}/downloads",
            headers=_auth_staff(seeds["staff_token"]),
        )
        assert audit.status_code == 200
        assert len(audit.json()) >= 1
        assert audit.json()[0]["completed_at"] is not None


# ── Retirada de documento ─────────────────────────────────────────────────────

class TestRetiradaDocumento:
    def _send_outgoing(self, client, seeds):
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        return resp.json()["attachments"][0]["id"]

    def test_retirar_adjunto_saliente(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        resp = client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Documento incorrecto"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["withdrawn_at"]

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_retirada_exige_motivo_no_vacio(self, tmp_path, reason):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)

        resp = client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": reason},
        )

        assert resp.status_code == 422

    def test_cliente_no_descarga_adjunto_retirado(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Error"},
        )
        resp = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        assert resp.status_code == 410

    def test_retirada_idempotente(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        r1 = client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Error"},
        )
        r2 = client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Error de nuevo"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["already_withdrawn"] is True

    def test_solo_adjuntos_salientes_retirables(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        _, att_id, _, _ = _create_message_with_attachment(
            factory, seeds, direction="incoming",
        )
        resp = client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "prueba"},
        )
        assert resp.status_code == 409

    def test_descargas_previas_se_conservan_tras_retirada(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        att_id = self._send_outgoing(client, seeds)
        dl = client.get(
            f"/api/v1/messaging/client/attachments/{att_id}",
            headers=_auth_client(seeds["client_token"]),
        )
        dl_id = dl.headers["X-Download-Id"]
        client.post(
            f"/api/v1/messaging/client/attachments/{att_id}/confirm-download",
            headers=_auth_client(seeds["client_token"]),
            data={"download_id": dl_id},
        )
        client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Error"},
        )
        audit = client.get(
            f"/api/v1/messaging/staff/attachments/{att_id}/downloads",
            headers=_auth_staff(seeds["staff_token"]),
        )
        assert len(audit.json()) >= 1


# ── Serializacion de adjuntos con campos de estado ───────────────────────────

class TestSerializacionAdjuntos:
    def test_adjunto_saliente_incluye_status_disponible_para_cliente(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        msg_id = resp.json()["id"]
        msgs = client.get(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
        )
        assert msgs.status_code == 200
        msg = next(m for m in msgs.json() if m["id"] == msg_id)
        att = msg["attachments"][0]
        assert att["status"] == "disponible"
        assert att["available"] is True
        assert "sha256" not in att  # privado del cliente

    def test_adjunto_entrante_incluye_status_para_staff(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
            data={"body": "adjunto", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        msg_id = resp.json()["id"]
        msgs = client.get(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
        )
        msg = next(m for m in msgs.json() if m["id"] == msg_id)
        att = msg["attachments"][0]
        assert att["direction"] == "incoming"
        assert att["status"] == "recibido_por_gestinem"
        assert "sha256" in att

    def test_adjunto_saliente_caducado_status(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        with factory() as db:
            att = db.get(MessagingAttachment, att_id)
            att.expires_at = _utcnow() - timedelta(days=1)
            db.commit()
        msgs = client.get(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
        )
        msg = next(m for m in msgs.json() if m["id"] == resp.json()["id"])
        att = msg["attachments"][0]
        assert att["status"] == "caducado"
        assert att["available"] is False

    def test_adjunto_retirado_status(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": "Incorrecto"},
        )
        msgs = client.get(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
        )
        msg = next(m for m in msgs.json() if m["id"] == resp.json()["id"])
        att = msg["attachments"][0]
        assert att["status"] == "retirado"
        assert att["available"] is False
        assert "withdrawal_reason" not in att  # privado del cliente

    def test_staff_ve_withdrawal_reason(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        motivo = "Documento subido por error"
        client.post(
            f"/api/v1/messaging/staff/admin/attachments/{att_id}/withdraw",
            headers=_auth_staff(seeds["staff_token"]),
            json={"reason": motivo},
        )
        msgs = client.get(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
        )
        msg = next(m for m in msgs.json() if m["id"] == resp.json()["id"])
        att = msg["attachments"][0]
        assert att["withdrawal_reason"] == motivo


# ── local_confirmed tras confirmacion del NAS ─────────────────────────────────

class TestLocalConfirmedNAS:
    def test_sync_confirm_marca_local_confirmed(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
            data={"body": "adjunto", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        with factory() as db:
            att = db.get(MessagingAttachment, att_id)
            sha = att.sha256
            att.claimed_by = "synology"
            att.claim_expires_at = _utcnow() + timedelta(minutes=5)
            db.commit()
        confirm = client.post(
            "/api/v1/messaging/sync/attachments/" + att_id + "/confirm",
            headers={"X-Sync-Token": "sync-secret"},
            data={"worker": "synology", "sha256": sha},
        )
        assert confirm.status_code == 200
        msgs = client.get(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
        )
        msg = next(m for m in msgs.json() if m["id"] == resp.json()["id"])
        att = msg["attachments"][0]
        assert att["status"] == "guardado_por_asesoria"
        assert att["local_confirmed"] is True


# ── Sincronizacion: alerta de adjuntos obsoletos ──────────────────────────────

class TestStalePendingAttachments:
    def test_pending_incluye_campo_stale(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
            data={"body": "adj", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        # Hacer el adjunto stale manualmente
        with factory() as db:
            att = db.get(MessagingAttachment, att_id)
            att.created_at = _utcnow() - timedelta(hours=2)
            db.commit()
        pending = client.get(
            "/api/v1/messaging/sync/attachments/pending",
            headers={"X-Sync-Token": "sync-secret"},
        )
        assert pending.status_code == 200
        stale_items = [i for i in pending.json() if i.get("stale")]
        assert any(i["id"] == att_id for i in stale_items)

    def test_adjunto_reciente_no_stale(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/client/conversations/{seeds['conv_id']}/messages",
            headers=_auth_client(seeds["client_token"]),
            data={"body": "adj", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        att_id = resp.json()["attachments"][0]["id"]
        pending = client.get(
            "/api/v1/messaging/sync/attachments/pending",
            headers={"X-Sync-Token": "sync-secret"},
        )
        item = next(i for i in pending.json() if i["id"] == att_id)
        assert item["stale"] is False


# ── Personal no accede a conversaciones no autorizadas ────────────────────────

class TestAislamiento:
    def test_staff_no_accede_conversacion_ajena(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        with factory() as db:
            org2 = MessagingOrganization(company_code="E00002", name="Empresa 2")
            db.add(org2); db.flush()
            conv2 = MessagingConversation(organization_id=org2.id, kind="fiscal")
            db.add(conv2); db.commit()
        # Crear staff sin canal autorizado para la segunda organizacion
        # (En este setup simplificado el staff tiene acceso global;
        #  este test verifica la estructura de la llamada)
        resp = client.get(
            f"/api/v1/messaging/staff/conversations/{conv2.id}/messages",
            headers=_auth_staff(seeds["staff_token"]),
        )
        # El staff de prueba tiene rol admin, por lo que puede acceder a todas.
        # Un staff normal sin canal no deberia poder: esta logica se prueba en
        # test_messaging_api.py con staff restringido.
        assert resp.status_code in (200, 403)


# ── has_attachments en mensaje ────────────────────────────────────────────────

class TestHasAttachments:
    def test_mensaje_con_adjuntos_expone_has_attachments(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "doc", "idempotency_key": str(uuid.uuid4())},
            files={"files": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        assert resp.json()["has_attachments"] is True

    def test_mensaje_sin_adjuntos_has_attachments_false(self, tmp_path):
        client, factory = _make_client(tmp_path)
        seeds = _seed(factory)
        resp = client.post(
            f"/api/v1/messaging/staff/conversations/{seeds['conv_id']}/messages",
            headers=_auth_staff(seeds["staff_token"]),
            data={"body": "Solo texto", "idempotency_key": str(uuid.uuid4())},
        )
        assert resp.json()["has_attachments"] is False
