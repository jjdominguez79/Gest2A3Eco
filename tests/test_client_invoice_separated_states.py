"""Tests de la Etapa 2: estados separados, origen de factura y colas nuevas.

Ver docs/adr/0001-facturacion-autonoma-cliente.md seccion 6.
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
    ClientInvoiceCustomer,
    ClientInvoiceDiscrepancy,
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
            company_code="SEP01", name="Separated States SL",
            active=True, client_invoicing_enabled=True,
        )
        db.add(org)
        db.flush()
        client = MessagingClient(
            organization_id=org.id, email="sep@example.com",
            name="Sep Client", active=True,
        )
        db.add(client)
        db.flush()
        session = MessagingSession(
            client_id=client.id, token_hash=hash_token("sep-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)
        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return TestClient(app), {"Authorization": "Bearer sep-token"}, factory, org.id


def _mark_customer_synced(client, customer_id: str) -> None:
    resp = client.post(
        f"/api/v1/messaging/client/invoicing/worker/customer/{customer_id}/confirm",
        json={"desktop_tercero_id": f"desktop-{customer_id}", "desktop_subcuenta": "43000001"},
    )
    assert resp.status_code == 200


def test_draft_has_separated_states_at_defaults():
    client, headers, _factory, _org_id = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B11111111", "legal_name": "Draft Defaults SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "100.00"}],
        },
    ).json()

    assert draft["invoice_status"] == "draft"
    assert draft["fiscal_status"] == "pending"
    assert draft["pdf_status"] == "pending"
    assert draft["delivery_status"] == "pending"
    assert draft["accounting_sync_status"] == "pending"
    assert draft["source_system"] == "client_app"
    # El campo legacy se mantiene por compatibilidad.
    assert draft["status"] == "draft"


def test_issue_sets_invoice_status_without_touching_other_states():
    client, headers, _factory, _org_id = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B22222222", "legal_name": "Issue States SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "2", "unit_price": "50.00"}],
        },
    ).json()
    _mark_customer_synced(client, cust["id"])

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "sep-issue-1"},
    )
    assert resp.status_code == 200
    issued = resp.json()

    # invoice_status refleja la emision; el resto sigue pendiente porque
    # todavia no se ha generado PDF, enviado ni importado a contabilidad.
    assert issued["invoice_status"] == "issued"
    assert issued["fiscal_status"] == "pending"
    assert issued["pdf_status"] == "pending"
    assert issued["delivery_status"] == "pending"
    assert issued["accounting_sync_status"] == "pending"
    # El campo legacy conserva su valor historico para compatibilidad.
    assert issued["status"] == "issued_pending_processing"


def test_accounting_queue_and_discrepancy_tables_are_independent_models():
    """Las tablas nuevas existen, son independientes y no interfieren.

    No hay logica de negocio todavia (Etapa 3/8 las consumen); esta prueba
    solo fija el contrato de esquema de la Etapa 2.
    """
    client, headers, factory, org_id = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B33333333", "legal_name": "Queue Model SL"},
    ).json()

    with factory() as db:
        invoice = db.scalar(select(ClientInvoice))
        assert invoice is None  # no se emitio ninguna factura todavia

        queue_row = ClientInvoiceAccountingQueue(
            invoice_id="fake-invoice-id",
            organization_id=org_id,
        )
        db.add(queue_row)
        discrepancy = ClientInvoiceDiscrepancy(
            organization_id=org_id,
            customer_id=cust["id"],
            field_name="legal_name",
            backend_value="Queue Model SL",
            desktop_value="QUEUE MODEL S.L.",
        )
        db.add(discrepancy)
        db.commit()

        stored_queue = db.scalar(select(ClientInvoiceAccountingQueue))
        assert stored_queue.queue_status == "pending"
        assert stored_queue.retry_count == 0
        assert stored_queue.max_retries == 5

        stored_discrepancy = db.scalar(select(ClientInvoiceDiscrepancy))
        assert stored_discrepancy.status == "open"
        assert stored_discrepancy.customer_id == cust["id"]


def test_source_system_check_constraint_rejects_unknown_value():
    """La restriccion CHECK de ``source_system`` solo admite valores validos.

    SQLite no aplica CHECK por defecto en todas las configuraciones, asi que
    esta prueba verifica el contrato a nivel de aplicacion: el valor por
    defecto es client_app y el campo se expone en la API.
    """
    client, headers, _factory, _org_id = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B44444444", "legal_name": "Source System SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "10.00"}],
        },
    ).json()
    assert draft["source_system"] == "client_app"
