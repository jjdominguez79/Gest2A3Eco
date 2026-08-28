"""Tests de concurrencia para adquisicion atomica de notificaciones (PostgreSQL).

Requieren una base de datos PostgreSQL real para verificar que INSERT ... ON CONFLICT
... RETURNING es atomico bajo concurrencia real. Se saltan si TEST_POSTGRES_URL no
esta definida.

Uso:
    TEST_POSTGRES_URL=postgresql+psycopg://user:pass@host/db \\
    DGT_INTERNAL_API_KEY=test pytest tests/test_notification_concurrency_pg.py -v
"""

import os
import threading
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definida; tests de PostgreSQL omitidos",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_engine():
    """Motor PostgreSQL compartido para el modulo."""
    from sqlalchemy import create_engine
    from backend.api.database import Base

    os.environ.setdefault("DGT_INTERNAL_API_KEY", "test-pg-concurrent")
    os.environ.setdefault("DGT_DATABASE_URL", TEST_POSTGRES_URL)

    engine = create_engine(TEST_POSTGRES_URL, pool_size=5, max_overflow=10)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_factory(pg_engine):
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest.fixture()
def pg_org_invoice(pg_factory):
    """Crea una organizacion, cliente y factura listos para enviar notificaciones."""
    from backend.api.client_models import (
        ClientInvoice,
        ClientInvoiceProcessingQueue,
    )
    from backend.api.messaging_models import (
        MessagingClient,
        MessagingOrganization,
        MessagingSession,
    )
    from backend.api.messaging_security import hash_token

    with pg_factory() as db:
        org = MessagingOrganization(
            company_code=f"PGT{uuid.uuid4().hex[:6].upper()}",
            name="PG Test Org",
            active=True,
            client_invoicing_enabled=True,
            client_documents_enabled=True,
        )
        db.add(org)
        db.flush()

        client = MessagingClient(
            organization_id=org.id,
            email="pg@example.com",
            name="PG Client",
            active=True,
        )
        db.add(client)
        db.flush()

        session_obj = MessagingSession(
            client_id=client.id,
            token_hash=hash_token(f"pg-token-{uuid.uuid4().hex}"),
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        db.add(session_obj)
        db.flush()

        inv = ClientInvoice(
            organization_id=org.id,
            customer_id=None,
            fiscal_year=2025,
            series_code="PG",
            invoice_number=1,
            status="rendered",
            recipient_email="dest@example.com",
            created_by_client_id=client.id,
        )
        db.add(inv)
        db.flush()

        queue_item = ClientInvoiceProcessingQueue(
            invoice_id=inv.id,
            queue_status="pdf_uploaded",
            pdf_blob_key="test/invoice.pdf",
        )
        db.add(queue_item)
        db.commit()

        yield {"org": org, "client": client, "invoice": inv, "queue": queue_item}

        # Limpieza
        db.delete(queue_item)
        db.delete(inv)
        db.delete(session_obj)
        db.delete(client)
        db.delete(org)
        db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(pg_factory):
    """Construye una FastAPI con la DB PostgreSQL inyectada."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.client_invoices_api import _db, router
    from backend.api.security import require_workstation_or_internal

    app = FastAPI()
    app.include_router(router)

    def override():
        with pg_factory() as db:
            yield db

    app.dependency_overrides[_db] = override
    app.dependency_overrides[require_workstation_or_internal] = lambda: "test"
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests de concurrencia para email
# ---------------------------------------------------------------------------

class TestEmailConcurrencyPostgres:

    def test_concurrent_acquire_only_one_wins(self, pg_factory, pg_org_invoice):
        """Dos hilos concurrentes intentan enviar email; solo uno gana el lock."""
        invoice_id = pg_org_invoice["invoice"].id

        client = _make_app(pg_factory)
        barrier = threading.Barrier(2)
        results = []

        def send():
            barrier.wait()  # Sincronizar inicio
            with patch("backend.api.client_invoices_api.send_mail", return_value=True):
                with patch("backend.api.client_invoices_api._get_storage") as mock_storage:
                    mock_storage.return_value.get.return_value = b"pdf-content"
                    resp = client.post(
                        f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                        headers={"X-Internal-Key": "test-pg-concurrent"},
                    )
            results.append(resp.status_code)

        threads = [threading.Thread(target=send) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Ambas deben responder 200 (una envia, la otra detecta in_progress/already_sent)
        assert all(s == 200 for s in results), f"Respuestas: {results}"

    def test_send_mail_called_exactly_once(self, pg_factory, pg_org_invoice):
        """send_mail se llama exactamente una vez aunque dos hilos compitan."""
        invoice_id = pg_org_invoice["invoice"].id

        # Reiniciar estado: eliminar cualquier log previo
        from backend.api.client_models import ClientInvoiceNotificationLog
        from sqlalchemy import delete as sa_delete
        with pg_factory() as db:
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.commit()

        # Tambien resetear status de la factura
        from backend.api.client_models import ClientInvoice
        with pg_factory() as db:
            inv = db.get(ClientInvoice, invoice_id)
            inv.status = "rendered"
            db.commit()

        client = _make_app(pg_factory)
        barrier = threading.Barrier(2)
        mock_send = MagicMock(return_value=True)

        def send():
            barrier.wait()
            with patch("backend.api.client_invoices_api.send_mail", mock_send):
                with patch("backend.api.client_invoices_api._get_storage") as ms:
                    ms.return_value.get.return_value = b"pdf-bytes"
                    client.post(
                        f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                        headers={"X-Internal-Key": "test-pg-concurrent"},
                    )

        threads = [threading.Thread(target=send) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # send_mail debe haberse llamado exactamente una vez
        assert mock_send.call_count == 1, (
            f"send_mail se llamo {mock_send.call_count} veces (esperado: 1)"
        )

    def test_second_acquire_after_sent_returns_already_sent(self, pg_factory, pg_org_invoice):
        """Un segundo intento de envio con status=sent devuelve already_sent."""
        invoice_id = pg_org_invoice["invoice"].id

        from backend.api.client_models import ClientInvoiceNotificationLog
        from sqlalchemy import delete as sa_delete
        with pg_factory() as db:
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.commit()

        from backend.api.client_models import ClientInvoice
        with pg_factory() as db:
            inv = db.get(ClientInvoice, invoice_id)
            inv.status = "rendered"
            db.commit()

        client = _make_app(pg_factory)

        # Primer envio exitoso
        with patch("backend.api.client_invoices_api.send_mail", return_value=True):
            with patch("backend.api.client_invoices_api._get_storage") as ms:
                ms.return_value.get.return_value = b"pdf"
                resp1 = client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )
        assert resp1.status_code == 200

        # Segundo intento: debe devolver already_sent sin llamar a send_mail
        mock_send = MagicMock(return_value=True)
        with patch("backend.api.client_invoices_api.send_mail", mock_send):
            with patch("backend.api.client_invoices_api._get_storage") as ms:
                ms.return_value.get.return_value = b"pdf"
                resp2 = client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )
        assert resp2.status_code == 200
        body = resp2.json()
        assert body.get("already_sent") is True
        assert mock_send.call_count == 0

    def test_sending_status_blocks_acquire(self, pg_factory, pg_org_invoice):
        """Una fila en estado 'sending' bloquea un segundo intento de adquisicion."""
        invoice_id = pg_org_invoice["invoice"].id

        from backend.api.client_models import ClientInvoiceNotificationLog
        from sqlalchemy import delete as sa_delete
        import secrets
        from datetime import timezone

        with pg_factory() as db:
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.add(ClientInvoiceNotificationLog(
                invoice_id=invoice_id,
                notification_type="email",
                recipient="dest@example.com",
                status="sending",
                claim_token=secrets.token_hex(16),
                claimed_at=datetime.now(timezone.utc),
            ))
            db.commit()

        client = _make_app(pg_factory)
        mock_send = MagicMock(return_value=True)
        with patch("backend.api.client_invoices_api.send_mail", mock_send):
            with patch("backend.api.client_invoices_api._get_storage") as ms:
                ms.return_value.get.return_value = b"pdf"
                resp = client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )
        assert resp.status_code == 200
        assert resp.json().get("in_progress") is True
        assert mock_send.call_count == 0

    def test_unknown_status_blocks_acquire(self, pg_factory, pg_org_invoice):
        """Una fila en estado 'unknown' bloquea un segundo intento de adquisicion."""
        invoice_id = pg_org_invoice["invoice"].id

        from backend.api.client_models import ClientInvoiceNotificationLog
        from sqlalchemy import delete as sa_delete

        with pg_factory() as db:
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.add(ClientInvoiceNotificationLog(
                invoice_id=invoice_id,
                notification_type="email",
                recipient="dest@example.com",
                status="unknown",
            ))
            db.commit()

        client = _make_app(pg_factory)
        mock_send = MagicMock(return_value=True)
        with patch("backend.api.client_invoices_api.send_mail", mock_send):
            with patch("backend.api.client_invoices_api._get_storage") as ms:
                ms.return_value.get.return_value = b"pdf"
                resp = client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )
        assert resp.status_code == 200
        assert resp.json().get("in_progress") is True
        assert mock_send.call_count == 0

    def test_failed_status_allows_reacquire(self, pg_factory, pg_org_invoice):
        """Una fila en estado 'failed' permite ser reintentada."""
        invoice_id = pg_org_invoice["invoice"].id

        from backend.api.client_models import ClientInvoiceNotificationLog, ClientInvoice
        from sqlalchemy import delete as sa_delete

        with pg_factory() as db:
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.add(ClientInvoiceNotificationLog(
                invoice_id=invoice_id,
                notification_type="email",
                recipient="dest@example.com",
                status="failed",
                detail="error previo",
            ))
            db.commit()

        with pg_factory() as db:
            inv = db.get(ClientInvoice, invoice_id)
            inv.status = "rendered"
            db.commit()

        client = _make_app(pg_factory)
        mock_send = MagicMock(return_value=True)
        with patch("backend.api.client_invoices_api.send_mail", mock_send):
            with patch("backend.api.client_invoices_api._get_storage") as ms:
                ms.return_value.get.return_value = b"pdf"
                resp = client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-email",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )
        assert resp.status_code == 200
        assert mock_send.call_count == 1, (
            f"send_mail se llamo {mock_send.call_count} veces (esperado: 1)"
        )


# ---------------------------------------------------------------------------
# Tests de concurrencia para FCM
# ---------------------------------------------------------------------------

class TestFcmConcurrencyPostgres:

    def test_fcm_concurrent_sends_once(self, pg_factory, pg_org_invoice):
        """Dos hilos concurrentes intentan enviar FCM; send_fcm se llama solo una vez."""
        invoice_id = pg_org_invoice["invoice"].id
        client_id = pg_org_invoice["client"].id

        # Crear dispositivo push
        from backend.api.messaging_models import MessagingAppDevice
        from backend.api.client_models import ClientInvoiceNotificationLog
        from sqlalchemy import delete as sa_delete

        fcm_token = f"fcm-test-token-{uuid.uuid4().hex}"

        with pg_factory() as db:
            device = MessagingAppDevice(
                user_type="client",
                user_id=client_id,
                push_token=fcm_token,
                platform="android",
                active=True,
            )
            db.add(device)
            db.execute(
                sa_delete(ClientInvoiceNotificationLog).where(
                    ClientInvoiceNotificationLog.invoice_id == invoice_id,
                )
            )
            db.commit()

        from backend.api.messaging_firebase import FcmResult

        client = _make_app(pg_factory)
        barrier = threading.Barrier(2)
        mock_fcm = MagicMock(return_value=FcmResult(success=True, permanent_failure=False))

        def send_fcm():
            barrier.wait()
            with patch("backend.api.client_invoices_api.send_fcm", mock_fcm):
                client.post(
                    f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/send-fcm",
                    headers={"X-Internal-Key": "test-pg-concurrent"},
                )

        threads = [threading.Thread(target=send_fcm) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert mock_fcm.call_count == 1, (
            f"send_fcm se llamo {mock_fcm.call_count} veces (esperado: 1)"
        )

        # Cleanup
        with pg_factory() as db:
            db.delete(db.get(MessagingAppDevice, device.id))
            db.commit()
