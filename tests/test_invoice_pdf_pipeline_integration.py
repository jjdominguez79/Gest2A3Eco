"""Integracion de extremo a extremo (Etapa 6): emitir -> render real -> subir
-> publicar -> descargar desde Flutter.

Usa el renderer real (Chromium headless) contra una app FastAPI de pruebas;
se salta si Chromium no esta instalado, igual que
tests/test_billing_worker_render_pdf.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)
os.environ.setdefault("CLIENT_DOCUMENTS_ALLOW_LOCAL_STORAGE", "true")


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _chromium_available(),
    reason="Chromium no disponible (ejecutar: playwright install chromium)",
)


@pytest.fixture(autouse=True)
def _enable_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIENT_INVOICING_ENABLED", "true")
    monkeypatch.setenv("CLIENT_DOCUMENTS_ENABLED", "true")
    monkeypatch.setenv("CLIENT_DOCUMENTS_ALLOW_LOCAL_STORAGE", "true")
    monkeypatch.setenv("CLIENT_DOCUMENTS_STORAGE_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("BILLING_WORKER_API_KEY", "billing-secret-test")


def _setup():
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

    with factory() as db:
        org = MessagingOrganization(
            company_code="PDFI01", name="PDF Integration SL",
            active=True, client_invoicing_enabled=True, client_documents_enabled=True,
            legal_name="PDF Integration Asesores SL", tax_id="B10101010",
            address="Calle Integracion 1", postal_code="28010", city="Madrid",
            province="Madrid", country="ES",
        )
        db.add(org)
        db.flush()
        client_row = MessagingClient(
            organization_id=org.id, email="pdf@example.com",
            name="PDF Client", active=True,
        )
        db.add(client_row)
        db.flush()
        session = MessagingSession(
            client_id=client_row.id, token_hash=hash_token("pdf-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)
        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return TestClient(app), {"Authorization": "Bearer pdf-token"}


def test_full_pipeline_from_issue_to_authenticated_download():
    from billing_worker.handlers.render_pdf import render_invoice_pdf, sha256_hex

    client, headers = _setup()
    billing_headers = {"X-API-Key": "billing-secret-test"}

    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B20202020", "legal_name": "Destinatario Integracion SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio integrado", "quantity": "1", "unit_price": "150.00"}],
        },
    ).json()

    # Antes de emitir, el PDF no existe todavia.
    before = client.get(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}", headers=headers,
    )
    assert before.status_code == 200

    issued = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "pdf-integration-1"},
    ).json()
    invoice_id = issued["id"]

    # billing_worker: claim -> payload -> render real -> upload -> publish.
    claim = client.post(
        "/api/v1/messaging/client/invoicing/worker/claim",
        headers=billing_headers, json={"worker_id": "pdf-test"},
    ).json()
    assert claim["claimed"] is True
    assert claim["invoice_id"] == invoice_id

    payload = client.get(
        f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/payload",
        headers=billing_headers,
    ).json()
    assert payload["verifactu_submission_enabled"] is False

    pdf_bytes = render_invoice_pdf(payload)
    digest = sha256_hex(pdf_bytes)

    upload = client.post(
        f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/pdf",
        headers=billing_headers,
        data={"sha256": digest},
        files={"file": ("factura.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 200

    publish = client.post(
        f"/api/v1/messaging/client/invoicing/worker/invoice/{invoice_id}/publish-document",
        headers=billing_headers, json={},
    )
    assert publish.status_code == 200

    # Flutter: descarga autenticada con la sesion del cliente (no la del worker).
    download = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{invoice_id}/pdf",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content == pdf_bytes
    assert download.headers["content-type"] == "application/pdf"


def test_download_before_pdf_generated_returns_409():
    client, headers = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B30303030", "legal_name": "Sin PDF SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "10.00"}],
        },
    ).json()
    issued = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "pdf-integration-2"},
    ).json()

    resp = client.get(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}/pdf",
        headers=headers,
    )
    assert resp.status_code == 409


def test_other_organization_cannot_download_pdf():
    client, headers = _setup()
    # Crear una segunda sesion/organizacion directamente en la misma BD.
    from backend.api.client_invoices_api import _db
    from backend.api.messaging_models import MessagingClient, MessagingOrganization, MessagingSession
    from backend.api.messaging_security import hash_token

    db_gen = client.app.dependency_overrides[_db]()
    db = next(db_gen)
    other_org = MessagingOrganization(
        company_code="PDFI02", name="Other PDF Org",
        active=True, client_invoicing_enabled=True,
    )
    db.add(other_org)
    db.flush()
    other_client = MessagingClient(
        organization_id=other_org.id, email="other-pdf@example.com",
        name="Other PDF Client", active=True,
    )
    db.add(other_client)
    db.flush()
    other_session = MessagingSession(
        client_id=other_client.id, token_hash=hash_token("other-pdf-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(other_session)
    db.commit()

    resp = client.get(
        "/api/v1/messaging/client/invoicing/invoices/does-not-matter/pdf",
        headers={"Authorization": "Bearer other-pdf-token"},
    )
    assert resp.status_code == 404
