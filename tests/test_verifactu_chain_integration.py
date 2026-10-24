"""Tests de integracion de la Etapa 7: cadena Veri*FACTU, rectificativas y anulaciones.

Ver docs/adr/0001-facturacion-autonoma-cliente.md seccion 9 y
services/verifactu/README.md.
"""

import os
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

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
from backend.api.client_models import ClientInvoiceSeries, ClientVerifactuChainState
from backend.api.messaging_models import MessagingClient, MessagingOrganization, MessagingSession
from backend.api.messaging_security import hash_token


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

    with factory() as db:
        org = MessagingOrganization(
            company_code="VF01", name="Verifactu SL", active=True,
            client_invoicing_enabled=True, legal_name="Verifactu Asesores SL",
            tax_id="B55566677", address="Calle Fiscal 1", postal_code="28001",
            city="Madrid", province="Madrid", country="ES",
        )
        db.add(org)
        db.flush()
        client_row = MessagingClient(
            organization_id=org.id, email="vf@example.com",
            name="VF Client", active=True,
        )
        db.add(client_row)
        db.flush()
        session = MessagingSession(
            client_id=client_row.id, token_hash=hash_token("vf-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)

        org2 = MessagingOrganization(
            company_code="VF02", name="Other Verifactu SL", active=True,
            client_invoicing_enabled=True, legal_name="Other Verifactu SL",
            tax_id="B77788899",
        )
        db.add(org2)
        db.flush()
        client2 = MessagingClient(
            organization_id=org2.id, email="vf2@example.com",
            name="VF Client 2", active=True,
        )
        db.add(client2)
        db.flush()
        session2 = MessagingSession(
            client_id=client2.id, token_hash=hash_token("vf2-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session2)

        db.add(ClientInvoiceSeries(
            organization_id=org.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.add(ClientInvoiceSeries(
            organization_id=org2.id, fiscal_year=2026, series_code="APP",
            next_number=1, active=True,
        ))
        db.commit()

    return TestClient(app), {"Authorization": "Bearer vf-token"}, {"Authorization": "Bearer vf2-token"}, factory


def _issue(client, headers, *, tax_id: str, idem: str, amount: str = "100.00"):
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": tax_id, "legal_name": f"Cliente {tax_id} SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": amount}],
        },
    ).json()
    return client.post(
        f"/api/v1/messaging/client/invoicing/drafts/{draft['id']}/issue",
        headers={**headers, "Idempotency-Key": idem},
    ).json()


def test_first_invoice_in_organization_chains_against_empty_string_only():
    client, headers, _other, factory = _setup()
    issued = _issue(client, headers, tax_id="B10000001", idem="chain-1")

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        inv = db.get(ClientInvoice, issued["id"])
        assert inv.verifactu_chain_hash == ""  # primer registro real
        assert len(inv.verifactu_hash) == 64
        assert inv.verifactu_hash == inv.verifactu_hash.upper()
        assert inv.verifactu_xml.strip().startswith("<?xml")
        assert "PrimerRegistro" in inv.verifactu_xml


def test_second_invoice_chains_against_the_first_real_hash():
    client, headers, _other, factory = _setup()
    first = _issue(client, headers, tax_id="B10000002", idem="chain-2a")
    second = _issue(client, headers, tax_id="B10000003", idem="chain-2b")

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        inv1 = db.get(ClientInvoice, first["id"])
        inv2 = db.get(ClientInvoice, second["id"])
        assert inv2.verifactu_chain_hash == inv1.verifactu_hash
        assert inv2.verifactu_hash != inv1.verifactu_hash
        assert "RegistroAnterior" in inv2.verifactu_xml
        assert "PrimerRegistro" not in inv2.verifactu_xml


def test_two_organizations_have_independent_chains():
    client, headers, other_headers, factory = _setup()
    _issue(client, headers, tax_id="B10000004", idem="chain-org1")
    issued_other = _issue(client, other_headers, tax_id="B10000005", idem="chain-org2")

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        inv_other = db.get(ClientInvoice, issued_other["id"])
        # La otra organizacion emite su primera factura real: cadena vacia,
        # a pesar de que la primera organizacion ya tiene una factura emitida.
        assert inv_other.verifactu_chain_hash == ""


def test_chain_state_sequence_number_increments_per_organization():
    client, headers, _other, factory = _setup()
    _issue(client, headers, tax_id="B10000006", idem="chain-seq-1")
    _issue(client, headers, tax_id="B10000007", idem="chain-seq-2")

    with factory() as db:
        org = db.execute(select(MessagingOrganization).where(
            MessagingOrganization.company_code == "VF01",
        )).scalar_one()
        state = db.get(ClientVerifactuChainState, org.id)
        assert state.sequence_number == 2


def test_rectify_creates_new_invoice_referencing_the_original():
    client, headers, _other, factory = _setup()
    original = _issue(client, headers, tax_id="B10000008", idem="rect-orig")

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{original['id']}/rectify",
        headers={**headers, "Idempotency-Key": "rect-1"},
        json={
            "reason": "Error en el precio",
            "lines": [{"description": "Servicio corregido", "quantity": "1", "unit_price": "90.00"}],
        },
    )
    assert resp.status_code == 200
    rectification = resp.json()
    assert rectification["rectifies_invoice_id"] == original["id"]
    assert rectification["invoice_status"] == "issued"
    assert rectification["invoice_number"] != original["invoice_number"]

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        rect_inv = db.get(ClientInvoice, rectification["id"])
        assert "R1" in rect_inv.verifactu_xml

        original_inv = db.get(ClientInvoice, original["id"])
        assert original_inv.invoice_status == "rectified"
        assert original_inv.status == "replaced"
        # El snapshot original nunca se altera.
        assert "Error en el precio" not in original_inv.issued_snapshot


def test_cannot_rectify_a_draft_invoice():
    client, headers, _other, factory = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B10000009", "legal_name": "Draft SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "10"}],
        },
    ).json()

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{draft['id']}/rectify",
        headers={**headers, "Idempotency-Key": "rect-draft"},
        json={"reason": "x", "lines": [{"description": "y", "quantity": "1", "unit_price": "1"}]},
    )
    assert resp.status_code == 400


def test_cancel_invoice_records_anulacion_without_touching_alta_record():
    client, headers, _other, factory = _setup()
    issued = _issue(client, headers, tax_id="B10000010", idem="cancel-1")

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        before = db.get(ClientInvoice, issued["id"])
        alta_hash_before = before.verifactu_hash
        alta_xml_before = before.verifactu_xml

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}/cancel",
        headers=headers,
        json={"reason": "Factura duplicada por error"},
    )
    assert resp.status_code == 200
    cancelled = resp.json()
    assert cancelled["invoice_status"] == "cancelled"
    assert cancelled["cancellation_reason"] == "Factura duplicada por error"

    with factory() as db:
        from backend.api.client_models import ClientInvoice
        after = db.get(ClientInvoice, issued["id"])
        # El registro de alta original nunca se modifica.
        assert after.verifactu_hash == alta_hash_before
        assert after.verifactu_xml == alta_xml_before
        # El registro de anulacion es uno nuevo, distinto del de alta.
        assert after.verifactu_anulacion_hash != ""
        assert after.verifactu_anulacion_hash != alta_hash_before
        assert "RegistroAnulacion" in after.verifactu_anulacion_xml
        # La anulacion encadena contra el ultimo hash conocido (el de alta).
        root = ET.fromstring(after.verifactu_anulacion_xml)
        ns = "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd}"
        encadenamiento = root.find(f"{ns}Encadenamiento")
        registro_anterior = encadenamiento.find(f"{ns}RegistroAnterior")
        assert registro_anterior.find(f"{ns}Huella").text == alta_hash_before


def test_cancel_is_idempotent():
    client, headers, _other, factory = _setup()
    issued = _issue(client, headers, tax_id="B10000011", idem="cancel-idem")

    first = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}/cancel",
        headers=headers, json={"reason": "motivo"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{issued['id']}/cancel",
        headers=headers, json={"reason": "motivo otra vez"},
    )
    assert second.status_code == 200
    assert second.json()["invoice_status"] == "cancelled"
    # No crea un segundo registro de anulacion (no cambia el motivo
    # registrado la primera vez).
    assert second.json()["cancellation_reason"] == "motivo"


def test_cannot_cancel_a_draft_invoice():
    client, headers, _other, factory = _setup()
    cust = client.post(
        "/api/v1/messaging/client/invoicing/customers",
        headers=headers,
        json={"tax_id": "B10000012", "legal_name": "Draft Cancel SL"},
    ).json()
    draft = client.post(
        "/api/v1/messaging/client/invoicing/drafts",
        headers=headers,
        json={
            "customer_id": cust["id"],
            "lines": [{"description": "Servicio", "quantity": "1", "unit_price": "10"}],
        },
    ).json()

    resp = client.post(
        f"/api/v1/messaging/client/invoicing/invoices/{draft['id']}/cancel",
        headers=headers, json={"reason": "x"},
    )
    assert resp.status_code == 400
