"""Tests del endpoint worker/invoice/{id}/fiscal-register (Etapa 7).

Confirma que es un no-op mientras VERIFACTU_SUBMISSION_ENABLED es false
(estado actual y permanente hasta completar la Etapa 7 de verdad, ver
docs/adr/0001-facturacion-autonoma-cliente.md seccion 9) y que, si se
activa, usa el adaptador nulo y nunca marca 'accepted'.
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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base
from backend.api.client_invoices_api import _db, router
from backend.api.client_models import ClientInvoiceSeries
from backend.api.messaging_models import MessagingClient, MessagingOrganization, MessagingSession
from backend.api.messaging_security import hash_token
from backend.api.security import require_billing_worker_or_internal


@pytest.fixture(autouse=True)
def _enable_invoicing_feature(monkeypatch):
    monkeypatch.setenv("CLIENT_INVOICING_ENABLED", "true")
    monkeypatch.delenv("VERIFACTU_SUBMISSION_ENABLED", raising=False)


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
    app.dependency_overrides[require_billing_worker_or_internal] = lambda: "test"

    with factory() as db:
        org = MessagingOrganization(
            company_code="FR01", name="Fiscal Register SL", active=True,
            client_invoicing_enabled=True, legal_name="Fiscal Register SL",
            tax_id="B12312312",
        )
        db.add(org)
        db.flush()
        client_row = MessagingClient(
            organization_id=org.id, email="fr@example.com", name="FR Client", active=True,
        )
        db.add(client_row)
        db.flush()
        session = MessagingSession(
            client_id=client_row.id, token_hash=hash_token("fr-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)
        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return TestClient(app), {"Authorization": "Bearer fr-token"}


def _issue(client, headers):
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B99887766", "legal_name": "Cliente FR SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "100.00"}],
        },
    ).json()
    return client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "fr-issue-1"},
    ).json()


def test_fiscal_register_is_a_noop_while_flag_disabled():
    client, headers = _setup()
    issued = _issue(client, headers)

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/worker/invoice/{issued['id']}/fiscal-register",
        headers={"X-API-Key": "test"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"

    detail = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}", headers=headers,
    ).json()
    assert detail["fiscal_status"] == "pending"


def test_fiscal_register_with_flag_enabled_uses_null_adapter_and_never_accepts(monkeypatch):
    monkeypatch.setenv("VERIFACTU_SUBMISSION_ENABLED", "true")
    client, headers = _setup()
    issued = _issue(client, headers)

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/worker/invoice/{issued['id']}/fiscal-register",
        headers={"X-API-Key": "test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fiscal_status"] == "incident"
    assert body["fiscal_status"] != "accepted"

    detail = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}", headers=headers,
    ).json()
    assert detail["fiscal_status"] == "incident"
