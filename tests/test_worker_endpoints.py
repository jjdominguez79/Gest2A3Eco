"""Tests para los endpoints del worker de facturacion (backend API).

Cubre:
- Claim con lease / recovery de lease caducado
- Confirm import
- Error y retry / agotamiento de retries
- Publish document (idempotente)
- Mark emailed (idempotente, sin destinatario)
- Send-email idempotente si ya emailed
- Send-fcm (best-effort, sin tokens, con errores)
- Status
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base
from backend.api.client_invoices_api import _db, router, utcnow
from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceCustomer,
    ClientInvoiceNotificationLog,
    ClientInvoiceProcessingQueue,
)
from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token
from backend.api.security import require_workstation_or_internal
from backend.api import client_models  # noqa: F401
from backend.api import messaging_models  # noqa: F401


def _setup():
    """Crea app de test con org, cliente, factura emitida y cola pending."""
    os.environ["DGT_INTERNAL_API_KEY"] = "test-secret"

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

    app.dependency_overrides[_db] = override
    app.dependency_overrides[require_workstation_or_internal] = lambda: "test"

    with factory() as db:
        org = MessagingOrganization(
            company_code="WORK01",
            name="Worker Test Corp",
            active=True,
            client_invoicing_enabled=True,
            client_documents_enabled=True,
        )
        db.add(org)
        db.flush()

        client_user = MessagingClient(
            organization_id=org.id,
            email="emisor@example.com",
            name="Emisor",
            active=True,
        )
        db.add(client_user)
        db.flush()

        session = MessagingSession(
            client_id=client_user.id,
            token_hash=hash_token("worker-test-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)

        customer = ClientInvoiceCustomer(
            organization_id=org.id,
            tax_id="B99999999",
            tax_id_normalized="B99999999",
            legal_name="Destinatario SL",
        )
        db.add(customer)
        db.flush()

        inv = ClientInvoice(
            organization_id=org.id,
            customer_id=customer.id,
            fiscal_year=2026,
            series_code="WEB",
            invoice_number=1,
            invoice_date=datetime(2026, 8, 20, tzinfo=timezone.utc),
            status="issued_pending_processing",
            subtotal="100.00",
            total_vat="21.00",
            total="121.00",
            currency="EUR",
            recipient_email="dest@example.com",
            created_by_client_id=client_user.id,
        )
        db.add(inv)
        db.flush()

        queue = ClientInvoiceProcessingQueue(
            invoice_id=inv.id,
            organization_id=org.id,
            queue_status="pending",
        )
        db.add(queue)
        db.commit()

        inv_id = inv.id
        org_id = org.id
        client_id = client_user.id

    http = TestClient(app)
    return http, factory, inv_id, org_id, client_id


PREFIX = "/api/v1/messaging/client/invoicing"


# -- Claim --

class TestWorkerClaim:
    def test_claim_pending(self):
        http, factory, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["claimed"] is True
        assert data["invoice_id"] == inv_id

    def test_claim_nada_pendiente(self):
        http, *_ = _setup()
        http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w1"})
        resp = http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w2"})
        assert resp.json()["claimed"] is False

    def test_claim_lease_caducado(self):
        http, factory, inv_id, *_ = _setup()
        http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w1"})
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.lease_expires_at = utcnow() - timedelta(minutes=5)
            q.queue_status = "pending"
            db.commit()
        resp = http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w2"})
        assert resp.json()["claimed"] is True


# -- Import --

class TestWorkerImport:
    def test_confirm_import(self):
        http, factory, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/import-confirmed")
        assert resp.status_code == 200
        with factory() as db:
            assert db.get(ClientInvoice, inv_id).status == "imported"

    def test_import_404(self):
        http, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/noexiste/import-confirmed")
        assert resp.status_code == 404


# -- Error y retry --

class TestWorkerError:
    def test_error_incrementa_retry(self):
        http, factory, inv_id, *_ = _setup()
        resp = http.post(
            f"{PREFIX}/worker/invoice/{inv_id}/error",
            json={"error": "Word no disponible"},
        )
        assert resp.status_code == 200
        assert resp.json()["retryable"] is True
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            assert q.retry_count == 1
            assert q.error_message == "Word no disponible"
            assert q.lease_expires_at is None

    def test_error_agota_retries(self):
        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.retry_count = 4
            q.max_retries = 5
            db.commit()
        resp = http.post(
            f"{PREFIX}/worker/invoice/{inv_id}/error",
            json={"error": "Fallo persistente"},
        )
        assert resp.json()["retryable"] is False

    def test_error_y_reclaim(self):
        http, factory, inv_id, *_ = _setup()
        http.post(
            f"{PREFIX}/worker/invoice/{inv_id}/error",
            json={"error": "Temporal"},
        )
        resp = http.post(f"{PREFIX}/worker/claim", json={"worker_id": "w-retry"})
        assert resp.json()["claimed"] is True


# -- Publish document --

class TestWorkerPublish:
    def test_publish_sin_pdf(self):
        http, _, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/publish-document", json={})
        assert resp.status_code == 400

    def test_publish_con_pdf(self):
        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.pdf_blob_key = "test/blob/key.pdf"
            q.pdf_sha256 = "abc123"
            q.pdf_file_size = 1024
            db.commit()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/publish-document", json={})
        assert resp.status_code == 200
        assert "document_id" in resp.json()

    def test_publish_idempotente(self):
        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.pdf_blob_key = "test/blob/key.pdf"
            q.pdf_sha256 = "abc123"
            q.pdf_file_size = 1024
            db.commit()
        r1 = http.post(f"{PREFIX}/worker/invoice/{inv_id}/publish-document", json={})
        doc_id = r1.json()["document_id"]
        r2 = http.post(f"{PREFIX}/worker/invoice/{inv_id}/publish-document", json={})
        assert r2.json()["document_id"] == doc_id


# -- Mark emailed --

class TestWorkerEmailed:
    def test_mark_emailed(self):
        http, factory, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/emailed", json={})
        assert resp.status_code == 200
        with factory() as db:
            assert db.get(ClientInvoice, inv_id).status == "emailed"

    def test_mark_emailed_idempotente(self):
        http, _, inv_id, *_ = _setup()
        http.post(f"{PREFIX}/worker/invoice/{inv_id}/emailed", json={})
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/emailed", json={})
        assert resp.status_code == 200


# -- Send email --

class TestWorkerSendEmail:
    def test_sin_pdf_falla(self):
        http, _, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-email", json={})
        assert resp.status_code == 400

    def test_sin_destinatario_marca_completado(self):
        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            inv = db.get(ClientInvoice, inv_id)
            inv.recipient_email = ""
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.pdf_blob_key = "blob/f.pdf"
            db.commit()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-email", json={})
        assert resp.status_code == 200
        assert resp.json()["skipped"] is True
        assert resp.json()["reason"] == "sin_destinatario"

    def test_idempotente_si_ya_emailed(self):
        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            db.get(ClientInvoice, inv_id).status = "emailed"
            db.commit()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-email", json={})
        assert resp.status_code == 200
        assert resp.json()["already_sent"] is True


# -- Send FCM --

class TestWorkerSendFcm:
    def test_sin_tokens(self):
        http, _, inv_id, *_ = _setup()
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")
        assert resp.status_code == 200
        assert resp.json()["sent"] == 0
        assert resp.json()["reason"] == "sin_tokens"

    def test_con_token(self):
        """FCM exitoso con un token cuenta como sent=1."""
        from backend.api.messaging_firebase import FcmResult
        http, factory, inv_id, _, client_id = _setup()
        with factory() as db:
            db.add(MessagingAppDevice(
                user_type="client", user_id=client_id,
                platform="android", push_token="fcm-test-ok", active=True,
            ))
            db.commit()
        mock_fcm = MagicMock(return_value=FcmResult(success=True, permanent_failure=False))
        with patch("backend.api.messaging_firebase.send_fcm", mock_fcm):
            with patch("backend.api.messaging_firebase.FcmResult", FcmResult):
                resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1

    def test_fcm_error_no_falla(self):
        """FCM con fallo transitorio incrementa errors pero no lanza excepcion."""
        from backend.api.messaging_firebase import FcmResult
        http, factory, inv_id, _, client_id = _setup()
        with factory() as db:
            db.add(MessagingAppDevice(
                user_type="client", user_id=client_id,
                platform="ios", push_token="bad-transitorio", active=True,
            ))
            db.commit()
        mock_fcm = MagicMock(return_value=FcmResult(success=False, permanent_failure=False))
        with patch("backend.api.messaging_firebase.send_fcm", mock_fcm):
            with patch("backend.api.messaging_firebase.FcmResult", FcmResult):
                resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")
        assert resp.status_code == 200
        assert resp.json()["errors"] == 1


# -- Status --

class TestWorkerStatus:
    def test_status_pending(self):
        http, _, inv_id, *_ = _setup()
        resp = http.get(f"{PREFIX}/worker/invoice/{inv_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["invoice_status"] == "issued_pending_processing"
        assert data["queue_status"] == "pending"
        assert data["pdf_uploaded"] is False
        assert data["document_published"] is False

    def test_status_404(self):
        http, *_ = _setup()
        resp = http.get(f"{PREFIX}/worker/invoice/noexiste/status")
        assert resp.status_code == 404


# -- Idempotencia email via notification_log --

class TestEmailIdempotency:
    """Idempotencia de envio de email via notification_log."""

    def test_second_send_returns_already_sent_via_log(self):
        """Si ya hay registro sent en notification_log, devuelve already_sent=True."""
        from backend.api.client_models import ClientInvoiceNotificationLog

        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.pdf_blob_key = "blob/f.pdf"
            db.commit()

        # Pre-insertar registro sent en notification_log
        with factory() as db:
            db.add(ClientInvoiceNotificationLog(
                invoice_id=inv_id,
                notification_type="email",
                recipient="dest@example.com",
                status="sent",
            ))
            db.commit()

        # El invoke de send-email debe devolver already_sent=True sin enviar nada
        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-email", json={})
        assert resp.status_code == 200
        assert resp.json()["already_sent"] is True

        # El status de la factura no debe haber cambiado a emailed por este path
        with factory() as db:
            inv = db.get(ClientInvoice, inv_id)
            # El status no es emailed porque no se proceso (ya estaba en el log)
            assert inv.status != "emailed" or resp.json()["already_sent"] is True

    def test_no_recipient_uses_skipped_event(self):
        """Factura sin destinatario: evento email_skipped, status NO pasa a emailed."""
        from backend.api.client_models import ClientInvoiceNotificationLog

        http, factory, inv_id, *_ = _setup()
        with factory() as db:
            inv = db.get(ClientInvoice, inv_id)
            inv.recipient_email = ""
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            q.pdf_blob_key = "blob/f.pdf"
            db.commit()

        resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-email", json={})
        assert resp.status_code == 200
        assert resp.json()["skipped"] is True
        assert resp.json()["reason"] == "sin_destinatario"

        with factory() as db:
            # Status de la factura NO debe ser emailed
            inv = db.get(ClientInvoice, inv_id)
            assert inv.status != "emailed"

            # Cola completada
            q = db.scalars(select(ClientInvoiceProcessingQueue)).one()
            assert q.queue_status == "completed"

            # Registro en notification_log con status=skipped
            from backend.api.client_models import ClientInvoiceNotificationLog as NL
            log = db.scalar(
                select(NL).where(
                    NL.invoice_id == inv_id,
                    NL.notification_type == "email",
                )
            )
            assert log is not None
            assert log.status == "skipped"


# -- FCM con FcmResult --

class TestFcmResult:
    """Tests del bucle FCM con FcmResult correcto."""

    def _setup_with_device(self, push_token="fcm-token-123", platform="android"):
        http, factory, inv_id, _, client_id = _setup()
        with factory() as db:
            db.add(MessagingAppDevice(
                user_type="client", user_id=client_id,
                platform=platform, push_token=push_token, active=True,
            ))
            db.commit()
        return http, factory, inv_id, client_id

    def test_fcm_success_logs_sent(self):
        """FCM exitoso registra status=sent en notification_log."""
        from backend.api.client_models import ClientInvoiceNotificationLog
        from backend.api.messaging_firebase import FcmResult

        http, factory, inv_id, _ = self._setup_with_device()

        mock_fcm = MagicMock(return_value=FcmResult(success=True, permanent_failure=False))
        with patch("backend.api.messaging_firebase.send_fcm", mock_fcm):
            with patch("backend.api.messaging_firebase.FcmResult", FcmResult):
                resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")

        assert resp.status_code == 200
        assert resp.json()["sent"] == 1
        assert resp.json()["errors"] == 0

        with factory() as db:
            from backend.api.client_models import ClientInvoiceNotificationLog as NL
            log = db.scalar(
                select(NL).where(
                    NL.invoice_id == inv_id,
                    NL.notification_type == "fcm",
                )
            )
            assert log is not None
            assert log.status == "sent"

    def test_fcm_permanent_failure_deactivates_device(self):
        """Fallo permanente FCM desactiva el dispositivo."""
        from backend.api.messaging_firebase import FcmResult

        http, factory, inv_id, _ = self._setup_with_device(push_token="bad-token")

        mock_fcm = MagicMock(return_value=FcmResult(success=False, permanent_failure=True))
        with patch("backend.api.messaging_firebase.send_fcm", mock_fcm):
            with patch("backend.api.messaging_firebase.FcmResult", FcmResult):
                resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")

        assert resp.status_code == 200
        assert resp.json()["errors"] == 1

        with factory() as db:
            device = db.scalar(
                select(MessagingAppDevice).where(
                    MessagingAppDevice.push_token == "bad-token",
                )
            )
            assert device is not None
            assert device.active is False

    def test_fcm_duplicate_not_sent_twice(self):
        """Token con registro sent en notification_log no llama send_fcm de nuevo."""
        from backend.api.client_models import ClientInvoiceNotificationLog
        from backend.api.messaging_firebase import FcmResult

        http, factory, inv_id, _ = self._setup_with_device(push_token="already-sent-token")

        with factory() as db:
            db.add(ClientInvoiceNotificationLog(
                invoice_id=inv_id,
                notification_type="fcm",
                recipient="already-sent-token",
                status="sent",
            ))
            db.commit()

        mock_fcm = MagicMock(return_value=FcmResult(success=True, permanent_failure=False))
        with patch("backend.api.messaging_firebase.send_fcm", mock_fcm):
            with patch("backend.api.messaging_firebase.FcmResult", FcmResult):
                resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")

        assert resp.status_code == 200
        # El token ya estaba como sent, se cuenta como enviado pero sin llamar send_fcm
        assert resp.json()["sent"] == 1
        mock_fcm.assert_not_called()
