"""Test de concurrencia real (PostgreSQL) para la cadena Veri*FACTU.

Verifica que ``SELECT ... FOR UPDATE`` sobre ``client_verifactu_chain_state``
impide que dos emisiones simultaneas de la misma organizacion encadenen
contra el mismo hash "anterior" (lo que romperia la cadena: dos registros
distintos con el mismo verifactu_chain_hash). Se salta si TEST_POSTGRES_URL
no esta definida (mismo patron que
tests/test_invoice_numbering_concurrency_pg.py).
"""

import os
import threading
import uuid
from datetime import datetime, timezone

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

    os.environ.setdefault("DGT_INTERNAL_API_KEY", "test-pg-chain")
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

    app = FastAPI()
    app.include_router(router)

    def override():
        with pg_factory() as db:
            yield db

    app.dependency_overrides[_db] = override
    return TestClient(app)


@pytest.fixture()
def pg_org_with_drafts(pg_factory):
    from backend.api.client_models import (
        ClientInvoice,
        ClientInvoiceAccountingQueue,
        ClientInvoiceCustomer,
        ClientInvoiceLine,
        ClientInvoiceProcessingQueue,
        ClientInvoiceSeries,
        ClientVerifactuChainState,
    )
    from backend.api.messaging_models import (
        MessagingClient,
        MessagingOrganization,
        MessagingSession,
    )
    from backend.api.messaging_security import hash_token

    n_drafts = 10

    with pg_factory() as db:
        org = MessagingOrganization(
            company_code=f"CHN{uuid.uuid4().hex[:6].upper()}",
            name="Chain Concurrency Org", active=True,
            client_invoicing_enabled=True, legal_name="Chain Concurrency Org SL",
            tax_id="B11223344",
        )
        db.add(org)
        db.flush()

        client_row = MessagingClient(
            organization_id=org.id, email="chain@example.com",
            name="Chain Client", active=True,
        )
        db.add(client_row)
        db.flush()

        token = f"chain-token-{uuid.uuid4().hex}"
        session_obj = MessagingSession(
            client_id=client_row.id, token_hash=hash_token(token),
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        db.add(session_obj)

        customer = ClientInvoiceCustomer(
            organization_id=org.id, tax_id="B55443322",
            tax_id_normalized="B55443322", legal_name="Cliente Cadena SL",
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
        for _ in range(n_drafts):
            inv = ClientInvoice(
                organization_id=org.id, customer_id=customer.id,
                fiscal_year=2026, series_code="APP", status="draft",
                created_by_client_id=client_row.id,
            )
            db.add(inv)
            db.flush()
            db.add(ClientInvoiceLine(
                invoice_id=inv.id, line_number=1, description="Servicio",
                quantity=1, unit_price=100,
            ))
            draft_ids.append(inv.id)
            idempotency_keys.append(f"chain-{uuid.uuid4().hex}")

        db.commit()

        yield {
            "org_id": org.id, "token": token,
            "draft_ids": draft_ids, "idempotency_keys": idempotency_keys,
        }

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
        db.query(ClientVerifactuChainState).filter(
            ClientVerifactuChainState.organization_id == org.id,
        ).delete(synchronize_session=False)
        db.delete(customer)
        db.delete(series)
        db.delete(session_obj)
        db.delete(client_row)
        db.delete(org)
        db.commit()


def test_concurrent_issue_never_breaks_the_verifactu_chain(pg_app_client, pg_org_with_drafts):
    """N emisiones simultaneas deben producir una cadena continua y unica.

    Sin SELECT FOR UPDATE sobre client_verifactu_chain_state, dos hilos
    podrian leer el mismo last_hash y generar dos registros con el mismo
    verifactu_chain_hash (cadena rota/bifurcada).
    """
    from backend.api.client_models import ClientInvoice, ClientVerifactuChainState

    headers = {"Authorization": f"Bearer {pg_org_with_drafts['token']}"}
    draft_ids = pg_org_with_drafts["draft_ids"]
    idempotency_keys = pg_org_with_drafts["idempotency_keys"]

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
        if resp.status_code != 200:
            with lock:
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

    from sqlalchemy import select

    # Verificacion directa contra la BD: recomponer la cadena a partir de
    # verifactu_hash/verifactu_chain_hash y comprobar que es una lista
    # enlazada unica (sin bifurcaciones ni huecos) de longitud N.
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    engine = create_engine(TEST_POSTGRES_URL)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        invoices = db.scalars(
            select(ClientInvoice).where(
                ClientInvoice.organization_id == pg_org_with_drafts["org_id"],
            )
        ).all()
        assert len(invoices) == len(draft_ids)

        hashes = [inv.verifactu_hash for inv in invoices]
        assert len(set(hashes)) == len(hashes)  # todas las huellas son unicas

        chain_hashes = {inv.verifactu_hash: inv.verifactu_chain_hash for inv in invoices}
        # Reconstruir la cadena desde el unico registro con chain_hash=""
        roots = [h for h, prev in chain_hashes.items() if prev == ""]
        assert len(roots) == 1, "debe haber exactamente un primer registro real"

        visited = {roots[0]}
        current = roots[0]
        # prev -> next: localizar el registro cuyo chain_hash es 'current'
        remaining = dict(chain_hashes)
        del remaining[current]
        while remaining:
            next_hash = next(
                (h for h, prev in remaining.items() if prev == current), None,
            )
            assert next_hash is not None, "la cadena esta rota (hueco encontrado)"
            assert next_hash not in visited
            visited.add(next_hash)
            del remaining[next_hash]
            current = next_hash

        assert len(visited) == len(draft_ids)

        state = db.get(ClientVerifactuChainState, pg_org_with_drafts["org_id"])
        assert state.sequence_number == len(draft_ids)
    engine.dispose()
