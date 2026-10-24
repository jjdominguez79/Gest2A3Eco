"""Tests de la Etapa 3: emision desacoplada de la contabilidad.

Ver docs/adr/0001-facturacion-autonoma-cliente.md seccion 5. Cubren el
criterio de aceptacion central del encargo: un cliente sin tercero/subcuenta
asignada por el escritorio, o con el escritorio completamente desconectado,
debe poder emitir una factura fiscalmente valida.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base
from backend.api.client_invoices_api import _db, router
from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceAccountingQueue,
    ClientInvoiceProcessingQueue,
    ClientInvoiceSeries,
)
from backend.api.messaging_models import MessagingClient, MessagingOrganization, MessagingSession
from backend.api.messaging_security import hash_token
from backend.api.security import require_workstation_or_internal


@pytest.fixture(autouse=True)
def _enable_invoicing_feature(monkeypatch):
    monkeypatch.setenv("CLIENT_INVOICING_ENABLED", "true")


def _setup():
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
            company_code="DEC01", name="Decoupled SL",
            active=True, client_invoicing_enabled=True,
        )
        db.add(org)
        db.flush()
        client = MessagingClient(
            organization_id=org.id, email="dec@example.com",
            name="Dec Client", active=True,
        )
        db.add(client)
        db.flush()
        session = MessagingSession(
            client_id=client.id, token_hash=hash_token("dec-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)
        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return TestClient(app), {"Authorization": "Bearer dec-token"}, factory, org.id


def _create_customer_and_draft(client, headers, *, tax_id: str, fiscal_year: int | None = None):
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": tax_id, "legal_name": f"Cliente {tax_id} SL"},
    ).json()
    draft_payload = {
        "customer_id": cust["id"],
        "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "100.00"}],
    }
    if fiscal_year is not None:
        draft_payload["fiscal_year"] = fiscal_year
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json=draft_payload,
    ).json()
    return cust, draft


def test_issue_succeeds_without_any_desktop_sync():
    """Criterio de aceptacion: emitir con cliente sin subcuenta asignada."""
    client, headers, factory, _org_id = _setup()
    cust, draft = _create_customer_and_draft(client, headers, tax_id="B90000001")

    # El cliente sigue pendiente de import al escritorio: no se llama a
    # worker/customer/{id}/confirm en ningun momento.
    with factory() as db:
        from backend.api.client_models import ClientInvoiceCustomer
        stored = db.get(ClientInvoiceCustomer, cust["id"])
        assert stored.pending_desktop_import is True
        assert stored.desktop_subcuenta == ""

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "decoupled-1"},
    )
    assert resp.status_code == 200
    issued = resp.json()
    assert issued["invoice_number"] == 1
    assert issued["invoice_status"] == "issued"


def test_issue_succeeds_with_invoice_worker_completely_absent():
    """Emitir no requiere que ningun worker haya llamado nunca al backend."""
    client, headers, factory, org_id = _setup()
    _cust, draft = _create_customer_and_draft(client, headers, tax_id="B90000002")

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "decoupled-2"},
    )
    assert resp.status_code == 200
    inv_id = resp.json()["id"]

    with factory() as db:
        pq = db.scalar(
            select(ClientInvoiceProcessingQueue).where(
                ClientInvoiceProcessingQueue.invoice_id == inv_id,
            )
        )
        aq = db.scalar(
            select(ClientInvoiceAccountingQueue).where(
                ClientInvoiceAccountingQueue.invoice_id == inv_id,
            )
        )
        assert pq is not None and pq.queue_status == "pending"
        assert aq is not None and aq.queue_status == "pending"
        assert aq.organization_id == org_id


def test_accounting_queue_is_independent_from_processing_queue():
    """Dos colas separadas por disenio: una no bloquea ni depende de la otra."""
    client, headers, factory, _org_id = _setup()
    _cust, draft = _create_customer_and_draft(client, headers, tax_id="B90000003")
    inv_id = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "decoupled-3"},
    ).json()["id"]

    # invoice_worker reclama y falla permanentemente la importacion contable.
    claim = client.post(
        "/api/v1/messaging/client/invoicing/worker/accounting/claim",
        headers=headers,
        json={"worker_id": "desktop-1"},
    ).json()
    assert claim["claimed"] is True
    assert claim["invoice_id"] == inv_id

    err = client.post(
        f"/api/v1/messaging/client/invoicing/worker/accounting/{inv_id}/error",
        headers=headers,
        json={"error": "El tercero no se pudo crear", "needs_review": True},
    )
    assert err.status_code == 200
    assert err.json()["retryable"] is False

    detail = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{inv_id}", headers=headers,
    ).json()
    # La factura sigue siendo fiscalmente valida: el fallo contable solo
    # afecta a accounting_sync_status.
    assert detail["invoice_status"] == "issued"
    assert detail["fiscal_status"] == "pending"
    assert detail["pdf_status"] == "pending"
    assert detail["delivery_status"] == "pending"
    assert detail["accounting_sync_status"] == "review_required"


def test_accounting_confirm_marks_imported_without_touching_fiscal_state():
    client, headers, factory, _org_id = _setup()
    _cust, draft = _create_customer_and_draft(client, headers, tax_id="B90000004")
    inv_id = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "decoupled-4"},
    ).json()["id"]

    client.post(
        "/api/v1/messaging/client/invoicing/worker/accounting/claim",
        headers=headers,
        json={"worker_id": "desktop-1"},
    )
    confirm = client.post(
        f"/api/v1/messaging/client/invoicing/worker/accounting/{inv_id}/confirm",
        headers=headers,
        json={
            "desktop_tercero_id": "tercero-123",
            "desktop_subcuenta": "43000099",
            "desktop_invoice_ref": "FAC-2026-0099",
        },
    )
    assert confirm.status_code == 200

    detail = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{inv_id}", headers=headers,
    ).json()
    assert detail["accounting_sync_status"] == "imported"
    assert detail["invoice_status"] == "issued"

    # Idempotente: confirmar otra vez no cambia nada ni falla.
    confirm_again = client.post(
        f"/api/v1/messaging/client/invoicing/worker/accounting/{inv_id}/confirm",
        headers=headers,
        json={"desktop_tercero_id": "tercero-123", "desktop_subcuenta": "43000099"},
    )
    assert confirm_again.status_code == 200
    assert confirm_again.json()["already_imported"] is True


def test_accounting_error_is_retryable_by_default():
    client, headers, factory, _org_id = _setup()
    _cust, draft = _create_customer_and_draft(client, headers, tax_id="B90000005")
    inv_id = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "decoupled-5"},
    ).json()["id"]

    client.post(
        "/api/v1/messaging/client/invoicing/worker/accounting/claim",
        headers=headers, json={"worker_id": "desktop-1"},
    )
    err = client.post(
        f"/api/v1/messaging/client/invoicing/worker/accounting/{inv_id}/error",
        headers=headers,
        json={"error": "timeout temporal"},
    )
    assert err.json()["retryable"] is True

    with factory() as db:
        aq = db.scalar(
            select(ClientInvoiceAccountingQueue).where(
                ClientInvoiceAccountingQueue.invoice_id == inv_id,
            )
        )
        assert aq.queue_status == "error"
        assert aq.retry_count == 1
        assert aq.claimed_by == ""

    # Puede volver a reclamarse inmediatamente (lease liberado).
    reclaim = client.post(
        "/api/v1/messaging/client/invoicing/worker/accounting/claim",
        headers=headers, json={"worker_id": "desktop-2"},
    )
    assert reclaim.json()["claimed"] is True


def test_fiscal_year_change_keeps_independent_numbering():
    """Cambiar de ejercicio no reutiliza ni continua la numeracion anterior."""
    client, headers, factory, org_id = _setup()
    with factory() as db:
        db.add(ClientInvoiceSeries(
            organization_id=org_id, fiscal_year=2027, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    _cust_a, draft_2026 = _create_customer_and_draft(
        client, headers, tax_id="B90000006", fiscal_year=2026,
    )
    issued_2026 = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft_2026['id']}/issue",
        headers={**headers, "Idempotency-Key": "fy-2026-1"},
    ).json()
    assert issued_2026["invoice_number"] == 1
    assert issued_2026["fiscal_year"] == 2026

    _cust_b, draft_2027 = _create_customer_and_draft(
        client, headers, tax_id="B90000007", fiscal_year=2027,
    )
    issued_2027 = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft_2027['id']}/issue",
        headers={**headers, "Idempotency-Key": "fy-2027-1"},
    ).json()
    # El ejercicio 2027 empieza de nuevo en 1, con total independencia del
    # contador de 2026 (mismo series_code, distinta clave unica).
    assert issued_2027["invoice_number"] == 1
    assert issued_2027["fiscal_year"] == 2027
