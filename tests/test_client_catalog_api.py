"""Tests de la Etapa 4: catalogo de productos y servicios.

Ver docs/adr/0001-facturacion-autonoma-cliente.md.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
from backend.api.client_catalog_api import router as catalog_router
from backend.api.client_invoices_api import _db, router as invoices_router
from backend.api.client_models import ClientInvoiceSeries
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
    app.include_router(invoices_router)
    app.include_router(catalog_router)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[_db] = override
    app.dependency_overrides[require_workstation_or_internal] = lambda: "test"

    with factory() as db:
        org = MessagingOrganization(
            company_code="CAT01", name="Catalog SL",
            active=True, client_invoicing_enabled=True,
        )
        db.add(org)
        db.flush()
        client_row = MessagingClient(
            organization_id=org.id, email="cat@example.com",
            name="Cat Client", active=True,
        )
        db.add(client_row)
        db.flush()
        session = MessagingSession(
            client_id=client_row.id, token_hash=hash_token("cat-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)

        org2 = MessagingOrganization(
            company_code="CAT02", name="Other Catalog SL",
            active=True, client_invoicing_enabled=True,
        )
        db.add(org2)
        db.flush()
        client2 = MessagingClient(
            organization_id=org2.id, email="cat2@example.com",
            name="Cat Client 2", active=True,
        )
        db.add(client2)
        db.flush()
        session2 = MessagingSession(
            client_id=client2.id, token_hash=hash_token("cat2-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session2)
        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return (
        TestClient(app),
        {"Authorization": "Bearer cat-token"},
        {"Authorization": "Bearer cat2-token"},
    )


CATALOG_URL = "/api/v1/messaging/client/invoicing/catalog/items"


def test_create_and_get_catalog_item():
    client, headers, _other = _setup()
    resp = client.post(
        CATALOG_URL, headers=headers,
        json={
            "item_type": "service", "description": "Asesoria mensual",
            "unit": "mes", "unit_price": "150.0000", "vat_rate": "21.00",
        },
    )
    assert resp.status_code == 200
    item = resp.json()
    assert item["description"] == "Asesoria mensual"
    assert item["active"] is True
    assert item["revision"] == 1

    get_resp = client.get(f"{CATALOG_URL}/{item['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == item["id"]


def test_create_rejects_missing_description():
    client, headers, _other = _setup()
    resp = client.post(
        CATALOG_URL, headers=headers,
        json={"item_type": "product", "unit_price": "10"},
    )
    assert resp.status_code == 400


def test_create_rejects_invalid_item_type():
    client, headers, _other = _setup()
    resp = client.post(
        CATALOG_URL, headers=headers,
        json={"item_type": "widget", "description": "X", "unit_price": "10"},
    )
    assert resp.status_code == 400


def test_list_supports_search_and_pagination():
    client, headers, _other = _setup()
    for i in range(5):
        client.post(
            CATALOG_URL, headers=headers,
            json={"item_type": "product", "description": f"Producto {i}", "unit_price": "10"},
        )
    client.post(
        CATALOG_URL, headers=headers,
        json={"item_type": "service", "description": "Consultoria especial", "unit_price": "99"},
    )

    all_resp = client.get(CATALOG_URL, headers=headers, params={"limit": 3}).json()
    assert all_resp["total"] == 6
    assert len(all_resp["items"]) == 3

    search_resp = client.get(CATALOG_URL, headers=headers, params={"q": "especial"}).json()
    assert search_resp["total"] == 1
    assert search_resp["items"][0]["description"] == "Consultoria especial"


def test_update_increments_revision_and_deactivate_is_soft():
    client, headers, _other = _setup()
    item = client.post(
        CATALOG_URL, headers=headers,
        json={"item_type": "service", "description": "Servicio v1", "unit_price": "100"},
    ).json()
    assert item["revision"] == 1

    updated = client.put(
        f"{CATALOG_URL}/{item['id']}", headers=headers,
        json={"description": "Servicio v2", "unit_price": "120"},
    ).json()
    assert updated["revision"] == 2
    assert updated["description"] == "Servicio v2"
    assert Decimal(updated["unit_price"]) == Decimal("120")

    delete_resp = client.delete(f"{CATALOG_URL}/{item['id']}", headers=headers)
    assert delete_resp.status_code == 200

    # Baja logica: el articulo sigue existiendo, solo se desactiva.
    get_resp = client.get(f"{CATALOG_URL}/{item['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["active"] is False


def test_catalog_items_are_isolated_by_organization():
    client, headers, other_headers = _setup()
    item = client.post(
        CATALOG_URL, headers=headers,
        json={"item_type": "service", "description": "Privado", "unit_price": "50"},
    ).json()

    # La otra organizacion no puede verlo ni editarlo.
    resp = client.get(f"{CATALOG_URL}/{item['id']}", headers=other_headers)
    assert resp.status_code == 404

    resp = client.put(
        f"{CATALOG_URL}/{item['id']}", headers=other_headers,
        json={"unit_price": "1"},
    )
    assert resp.status_code == 404

    listed = client.get(CATALOG_URL, headers=other_headers).json()
    assert listed["total"] == 0


def test_adding_catalog_item_to_draft_copies_values_and_later_edits_do_not_affect_it():
    """Criterio de aceptacion de la Etapa 4: copia inmutable a la linea."""
    client, headers, _other = _setup()
    item = client.post(
        CATALOG_URL, headers=headers,
        json={
            "item_type": "service", "description": "Hora de consultoria",
            "unit_price": "80.0000", "vat_rate": "21.00",
        },
    ).json()

    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B55555000", "legal_name": "Catalog Usage SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"catalog_item_id": item["id"], "quantity": "3"}],
        },
    ).json()

    line = draft["lines"][0]
    assert line["catalog_item_id"] == item["id"]
    assert line["description"] == "Hora de consultoria"
    assert Decimal(line["unit_price"]) == Decimal("80.0000")
    assert Decimal(line["vat_rate"]) == Decimal("21.00")
    assert Decimal(line["quantity"]) == Decimal("3")

    # Editar el articulo despues no debe alterar la linea ya copiada.
    client.put(
        f"{CATALOG_URL}/{item['id']}", headers=headers,
        json={"description": "Hora de consultoria (precio revisado)", "unit_price": "95.0000"},
    )

    draft_after = client.get(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}", headers=headers,
    ).json()
    unchanged_line = draft_after["lines"][0]
    assert unchanged_line["description"] == "Hora de consultoria"
    assert Decimal(unchanged_line["unit_price"]) == Decimal("80.0000")


def test_adding_unknown_catalog_item_to_draft_fails_clearly():
    client, headers, _other = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B66666000", "legal_name": "Unknown Item SL"},
    ).json()
    resp = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"catalog_item_id": "does-not-exist", "quantity": "1"}],
        },
    )
    assert resp.status_code == 400
