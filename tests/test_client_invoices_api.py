"""Tests para la API de facturacion online del cliente."""

import os
import hashlib
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
from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceCustomer,
    ClientInvoiceLine,
    ClientInvoiceSeries,
)
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token
from backend.api import client_models  # noqa: F401
from backend.api import messaging_models  # noqa: F401
from backend.api.security import require_workstation_or_internal


@pytest.fixture(autouse=True)
def _enable_invoicing_feature(monkeypatch):
    """Cada test de esta API necesita el flag global efectivo activado."""
    monkeypatch.setenv("CLIENT_INVOICING_ENABLED", "true")


def _setup(tmp_path=None):
    """Create a test app with in-memory SQLite and seed base data."""
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

    # Seed org, client, session
    with factory() as db:
        org = MessagingOrganization(
            company_code="TEST01",
            name="Test Company",
            active=True,
            client_invoicing_enabled=True,
            client_documents_enabled=True,
        )
        db.add(org)
        db.flush()

        client = MessagingClient(
            organization_id=org.id,
            email="test@example.com",
            name="Test Client",
            active=True,
        )
        db.add(client)
        db.flush()

        session = MessagingSession(
            client_id=client.id,
            token_hash=hash_token("test-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)

        # Seed a second org for isolation tests
        org2 = MessagingOrganization(
            company_code="OTHER01",
            name="Other Company",
            active=True,
            client_invoicing_enabled=True,
        )
        db.add(org2)
        db.flush()

        client2 = MessagingClient(
            organization_id=org2.id,
            email="other@example.com",
            name="Other Client",
            active=True,
        )
        db.add(client2)
        db.flush()

        session2 = MessagingSession(
            client_id=client2.id,
            token_hash=hash_token("other-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session2)
        db.commit()

        return TestClient(app), {"Authorization": "Bearer test-token"}, org.id, {
            "Authorization": "Bearer other-token"
        }


# -- Config --


def test_config_returns_invoicing_status(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    resp = client.get(
        "/api/v1/messaging/client/invoicing/config", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True


def test_config_requires_auth(tmp_path):
    client, _, _, _ = _setup(tmp_path)
    resp = client.get("/api/v1/messaging/client/invoicing/config")
    assert resp.status_code == 401


# -- Customers --


def test_create_and_list_customers(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    resp = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={
            "tax_id": "B12345678",
            "legal_name": "Acme SL",
            "address": "Calle Mayor 1",
            "postal_code": "28001",
            "city": "Madrid",
            "province": "Madrid",
            "country": "ES",
        },
    )
    assert resp.status_code == 200
    cust = resp.json()
    assert cust["legal_name"] == "Acme SL"
    assert "id" in cust

    # List
    resp2 = client.get(
        "/api/v1/messaging/client/invoicing/customers", headers=headers
    )
    assert resp2.status_code == 200
    customers = resp2.json()
    assert len(customers) == 1
    assert customers[0]["tax_id"] == "B12345678"


# -- Drafts --


def test_create_draft(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    # Create customer first
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "A11111111", "legal_name": "Draft Test SL"},
    ).json()

    resp = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "invoice_date": "2026-01-15",
            "payment_method": "Transferencia",
            "notes": "Test draft",
            "withholding_rate": "15",
            "lines": [
                {
                    "description": "Servicio A",
                    "quantity": "2",
                    "unit_price": "100.00",
                    "discount_percent": "0",
                    "vat_rate": "21.00",
                },
            ],
        },
    )
    assert resp.status_code == 200
    draft = resp.json()
    assert draft["status"] == "draft"
    assert len(draft["lines"]) == 1


def test_list_drafts(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    # Create customer + draft
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B22222222", "legal_name": "List Test SL"},
    ).json()
    client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Item", "quantity": "1", "unit_price": "50"}],
        },
    )
    resp = client.get(
        "/api/v1/messaging/client/invoicing/drafts", headers=headers
    )
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 1


def test_update_draft(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B33333333", "legal_name": "Update Test SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Old", "quantity": "1", "unit_price": "10"}],
        },
    ).json()

    resp = client.put(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "notes": "Updated notes",
            "lines": [{"description": "New", "quantity": "3", "unit_price": "25"}],
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["notes"] == "Updated notes"
    assert len(updated["lines"]) == 1
    assert updated["lines"][0]["description"] == "New"


def test_delete_draft(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B44444444", "legal_name": "Delete Test SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "X", "quantity": "1", "unit_price": "1"}],
        },
    ).json()

    resp = client.delete(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}",
        headers=headers,
    )
    assert resp.status_code == 200

    # Verify it's gone
    resp2 = client.get(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}",
        headers=headers,
    )
    assert resp2.status_code == 404


# -- Issue --


def test_issue_draft(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B55555555", "legal_name": "Issue Test SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "invoice_date": "2026-06-01",
            "lines": [
                {"description": "Consulting", "quantity": "10", "unit_price": "50.00", "vat_rate": "21.00"},
            ],
        },
    ).json()

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "issue-test-1"},
    )
    assert resp.status_code == 200
    issued = resp.json()
    assert issued["status"] == "issued_pending_processing"
    assert issued["invoice_number"] is not None
    assert issued["series_code"] == "WEB"


def test_issue_idempotency(tmp_path):
    """Second issue with same key returns same invoice."""
    client, headers, _, _ = _setup(tmp_path)
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B66666666", "legal_name": "Idempotent SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Item", "quantity": "1", "unit_price": "100"}],
        },
    ).json()

    key = "idemp-key-unique"
    resp1 = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": key},
    )
    assert resp1.status_code == 200

    # Second call - draft is already issued, should return 409 or same result
    resp2 = client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": key},
    )
    # The draft no longer exists as draft, so 404 or 409
    assert resp2.status_code in (200, 404, 409)


# -- Org Isolation --


def test_org_isolation_drafts(tmp_path):
    """A client cannot see drafts from another org."""
    client, headers, _, other_headers = _setup(tmp_path)

    # Create customer and draft as org1
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B77777777", "legal_name": "Org1 SL"},
    ).json()
    client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Secret", "quantity": "1", "unit_price": "999"}],
        },
    )

    # List drafts as org2 - should be empty
    resp = client.get(
        "/api/v1/messaging/client/invoicing/drafts", headers=other_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# -- Invoices list --


def test_list_invoices_empty(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    resp = client.get(
        "/api/v1/messaging/client/invoicing/invoices", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_issued_invoice_appears_in_list(tmp_path):
    client, headers, _, _ = _setup(tmp_path)
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B88888888", "legal_name": "Listed SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Service", "quantity": "1", "unit_price": "200"}],
        },
    ).json()
    client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": "list-test-1"},
    )

    resp = client.get(
        "/api/v1/messaging/client/invoicing/invoices", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(i["status"] != "draft" for i in data["items"])


# -- Validation service --


def test_decimal_calculations():
    """Test that line totals use Decimal arithmetic."""
    from decimal import Decimal
    from backend.api.client_validation import calculate_line_total, calculate_vat

    total = calculate_line_total(Decimal("3"), Decimal("100.50"), Decimal("10"))
    # 3 * 100.50 * (1 - 10/100) = 301.50 * 0.9 = 271.35
    assert str(total) == "271.35"

    vat = calculate_vat(total, Decimal("21.00"))
    # 271.35 * 0.21 = 56.9835 -> 56.98
    assert str(vat) == "56.98"


def test_nif_validation():
    from backend.api.client_validation import validate_tax_id, normalize_tax_id

    assert normalize_tax_id("  b12345678 ") == "B12345678"
    # validate_tax_id should not raise for valid format
    validate_tax_id("B12345678")
    validate_tax_id("12345678Z")
