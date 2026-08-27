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
        http, factory, inv_id, _, client_id = _setup()
        with factory() as db:
            db.add(MessagingAppDevice(
                user_type="client", user_id=client_id,
                platform="android", push_token="fcm-test", active=True,
            ))
            db.commit()
        mock_mod = MagicMock()
        mock_mod.send_fcm = MagicMock()
        with patch.dict("sys.modules", {"backend.api.messaging_firebase": mock_mod}):
            resp = http.post(f"{PREFIX}/worker/invoice/{inv_id}/send-fcm")
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1

    def test_fcm_error_no_falla(self):
        http, factory, inv_id, _, client_id = _setup()
        with factory() as db:
            db.add(MessagingAppDevice(
                user_type="client", user_id=client_id,
                platform="ios", push_token="bad", active=True,
            ))
            db.commit()
        mock_mod = MagicMock()
        mock_mod.send_fcm = MagicMock(side_effect=RuntimeError("FCM down"))
        with patch.dict("sys.modules", {"backend.api.messaging_firebase": mock_mod}):
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
