"""Tests de concurrencia real (PostgreSQL) para la numeracion de series APP.

Requieren una base de datos PostgreSQL real para verificar que
``assign_invoice_number`` (SELECT ... FOR UPDATE) nunca asigna el mismo
numero dos veces bajo emision simultanea. Se saltan si TEST_POSTGRES_URL no
esta definida (igual que tests/test_notification_concurrency_pg.py).

Uso:
    TEST_POSTGRES_URL=postgresql+psycopg://user:pass@host/db \\
    DGT_INTERNAL_API_KEY=test pytest tests/test_invoice_numbering_concurrency_pg.py -v
"""

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definida; tests de PostgreSQL omitidos",
)


@pytest.fixture(scope="module")
def pg_engine():
    from sqlalchemy import create_engine
    from backend.api.database import Base

    os.environ.setdefault("DGT_INTERNAL_API_KEY", "test-pg-numbering")
    os.environ.setdefault("DGT_DATABASE_URL", TEST_POSTGRES_URL)
    os.environ["CLIENT_INVOICING_ENABLED"] = "true"

    engine = create_engine(TEST_POSTGRES_URL, pool_size=20, max_overflow=20)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_factory(pg_engine):
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest.fixture()
def pg_app_client(pg_factory):
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
    app.dependency_overrides[require_workstation_or_internal] = lambda: "pg-test"
    return TestClient(app)


@pytest.fixture()
def pg_org_with_drafts(pg_factory):
    """Crea una organizacion, N borradores listos para emitir y limpia al final."""
    from backend.api.client_models import (
        ClientInvoice,
        ClientInvoiceAccountingQueue,
        ClientInvoiceCustomer,
        ClientInvoiceLine,
        ClientInvoiceProcessingQueue,
        ClientInvoiceSeries,
    )
    from backend.api.messaging_models import (
        MessagingClient,
        MessagingOrganization,
        MessagingSession,
    )
    from backend.api.messaging_security import hash_token

    n_drafts = 12
    created_ids: dict = {}

    with pg_factory() as db:
        org = MessagingOrganization(
            company_code=f"NUM{uuid.uuid4().hex[:6].upper()}",
            name="Numbering Concurrency Org",
            active=True,
            client_invoicing_enabled=True,
        )
        db.add(org)
        db.flush()

        client_row = MessagingClient(
            organization_id=org.id, email="numbering@example.com",
            name="Numbering Client", active=True,
        )
        db.add(client_row)
        db.flush()

        token = f"numbering-token-{uuid.uuid4().hex}"
        session_obj = MessagingSession(
            client_id=client_row.id,
            token_hash=hash_token(token),
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        db.add(session_obj)

        customer = ClientInvoiceCustomer(
            organization_id=org.id, tax_id="B99999999",
            tax_id_normalized="B99999999", legal_name="Concurrencia SL",
        )
        db.add(customer)
        db.flush()

        series = ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        )
        db.add(series)

        draft_ids = []
        idempotency_keys = []
        for i in range(n_drafts):
            inv = ClientInvoice(
                organization_id=org.id, customer_id=customer.id,
                fiscal_year=2026, series_code="APP", status="draft",
                created_by_client_id=client_row.id,
            )
            db.add(inv)
            db.flush()
            line = ClientInvoiceLine(
                invoice_id=inv.id, line_number=1, description="Servicio",
                quantity=1, unit_price=100,
            )
            db.add(line)
            draft_ids.append(inv.id)
            idempotency_keys.append(f"numbering-{uuid.uuid4().hex}")

        db.commit()

        created_ids = {
            "org_id": org.id,
            "token": token,
            "draft_ids": draft_ids,
            "idempotency_keys": idempotency_keys,
        }

        yield created_ids

        # Limpieza
        db.query(ClientInvoiceAccountingQueue).filter(
            ClientInvoiceAccountingQueue.organization_id == org.id,
        ).delete(synchronize_session=False)
        db.query(ClientInvoiceProcessingQueue).filter(
            ClientInvoiceProcessingQueue.organization_id == org.id,
        ).delete(synchronize_session=False)
        db.query(ClientInvoiceLine).filter(
            ClientInvoiceLine.invoice_id.in_(draft_ids),
        ).delete(synchronize_session=False)
        db.query(ClientInvoice).filter(
            ClientInvoice.organization_id == org.id,
        ).delete(synchronize_session=False)
        db.delete(customer)
        db.delete(series)
        db.delete(session_obj)
        db.delete(client_row)
        db.delete(org)
        db.commit()


def test_concurrent_issue_never_duplicates_invoice_number(pg_app_client, pg_org_with_drafts):
    """N emisiones simultaneas deben producir N numeros unicos y consecutivos.

    Prueba real contra PostgreSQL de ``SELECT ... FOR UPDATE`` en
    ``assign_invoice_number``: sin el bloqueo de fila, dos hilos podrian leer
    el mismo ``next_number`` antes de que el otro confirme su incremento.
    """
    headers = {"Authorization": f"Bearer {pg_org_with_drafts['token']}"}
    draft_ids = pg_org_with_drafts["draft_ids"]
    idempotency_keys = pg_org_with_drafts["idempotency_keys"]

    results: list[int] = []
    errors: list[str] = []
    lock = threading.Lock()
    start_barrier = threading.Barrier(len(draft_ids))

    def issue(draft_id: str, idem_key: str) -> None:
        try:
            start_barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            pass
        resp = pg_app_client.post(
            f"/api/v1/messaging/client/invoicing/drafts/{draft_id}/issue",
            headers={**headers, "Idempotency-Key": idem_key},
        )
        with lock:
            if resp.status_code == 200:
                results.append(resp.json()["invoice_number"])
            else:
                errors.append(f"{resp.status_code}: {resp.text}")

    threads = [
        threading.Thread(target=issue, args=(draft_id, key))
        for draft_id, key in zip(draft_ids, idempotency_keys)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert len(results) == len(draft_ids)
    # Ningun numero se repite.
    assert len(set(results)) == len(results)
    # La secuencia es exactamente 1..N, sin huecos causados por reintentos.
    assert sorted(results) == list(range(1, len(draft_ids) + 1))
