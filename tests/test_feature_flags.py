"""Tests para feature flags de la plataforma cliente.

Cubre:
- Combinaciones global + org
- Autorizacion admin
- Auditoria de cambios
- Aislamiento entre organizaciones
- Bloqueo de funciones desactivadas
"""

import os

import pytest

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.database import Base
from backend.api.messaging_api import get_db, router
from backend.api.messaging_models import MessagingOrganization
from backend.api.client_models import ClientFeatureFlagAudit
from backend.api import messaging_models  # noqa: F401
from backend.api import client_models  # noqa: F401
from backend.api.feature_flags import (
    is_documents_enabled,
    is_invoicing_enabled,
    require_documents_enabled,
    require_invoicing_enabled,
)


@pytest.fixture(autouse=True)
def _restore_global_feature_flags():
    """Evita que los cambios directos de entorno contaminen otras pruebas."""
    names = ("CLIENT_DOCUMENTS_ENABLED", "CLIENT_INVOICING_ENABLED")
    original = {name: os.environ.get(name) for name in names}
    yield
    for name, value in original.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _setup():
    """Monta app de prueba con SQLite in-memory, orgs y staff via API."""
    os.environ["DGT_INTERNAL_API_KEY"] = "test-secret"
    os.environ["MESSAGING_STAFF_ALLOWED_DOMAIN"] = "gestinem.es"
    os.environ["MESSAGING_STAFF_ADMIN_EMAILS"] = "admin@gestinem.es"
    os.environ["MESSAGING_PUBLIC_BASE_URL"] = "https://test.gestinem.es"
    # Flags globales desactivadas por defecto
    os.environ["CLIENT_DOCUMENTS_ENABLED"] = "false"
    os.environ["CLIENT_INVOICING_ENABLED"] = "false"

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

    app.dependency_overrides[get_db] = override

    internal = {"X-API-Key": "test-secret"}

    client = TestClient(app, base_url="https://api.example.test")

    # Crear organizaciones via API
    assert client.put(
        "/api/v1/messaging/internal/organizations/ORG01", headers=internal,
        json={"company_code": "ORG01", "name": "Empresa Uno"},
    ).status_code == 200
    assert client.put(
        "/api/v1/messaging/internal/organizations/ORG02", headers=internal,
        json={"company_code": "ORG02", "name": "Empresa Dos"},
    ).status_code == 200

    # Activar flags de ORG02 directamente en DB
    with factory() as db:
        org2 = db.scalars(
            select(MessagingOrganization).where(
                MessagingOrganization.company_code == "ORG02"
            )
        ).one()
        org2.client_documents_enabled = True
        org2.client_invoicing_enabled = True
        db.commit()
        org1 = db.scalars(
            select(MessagingOrganization).where(
                MessagingOrganization.company_code == "ORG01"
            )
        ).one()
        org1_id = org1.id
        org2_id = org2.id

    # Crear staff via API
    assert client.put(
        "/api/v1/messaging/internal/staff/admin-local", headers=internal,
        json={
            "external_id": "admin-local", "name": "Administrador",
            "email": "admin@gestinem.es", "role": "admin", "active": True,
            "channels": [],
        },
    ).status_code == 200
    assert client.put(
        "/api/v1/messaging/internal/staff/empleado-local", headers=internal,
        json={
            "external_id": "empleado-local", "name": "Empleada",
            "email": "empleada@gestinem.es", "role": "empleado", "active": True,
            "channels": [],
        },
    ).status_code == 200

    # Registrar dispositivos via API
    dev_admin = client.post(
        "/api/v1/messaging/internal/devices/puesto-admin",
        headers=internal,
    ).json()
    dev_empleado = client.post(
        "/api/v1/messaging/internal/devices/puesto-empleado",
        headers=internal,
    ).json()

    admin_headers = {
        **internal,
        "X-Device-Id": "puesto-admin",
        "X-Device-Token": dev_admin["device_token"],
        "X-Staff-Id": "admin-local",
    }
    empleado_headers = {
        **internal,
        "X-Device-Id": "puesto-empleado",
        "X-Device-Token": dev_empleado["device_token"],
        "X-Staff-Id": "empleado-local",
    }

    return client, factory, admin_headers, empleado_headers, org1_id, org2_id


# -- Combinaciones de feature flags --

class TestFeatureFlagCombinations:
    """Verifica la logica AND entre flag global y flag de org."""

    def test_ambas_false_resultado_false(self):
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "false"
        org = MessagingOrganization(
            company_code="X", name="X", client_documents_enabled=False,
        )
        assert is_documents_enabled(org) is False

    def test_global_true_org_false_resultado_false(self):
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "true"
        org = MessagingOrganization(
            company_code="X", name="X", client_documents_enabled=False,
        )
        assert is_documents_enabled(org) is False

    def test_global_false_org_true_resultado_false(self):
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "false"
        org = MessagingOrganization(
            company_code="X", name="X", client_documents_enabled=True,
        )
        assert is_documents_enabled(org) is False

    def test_ambas_true_resultado_true(self):
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "true"
        org = MessagingOrganization(
            company_code="X", name="X", client_documents_enabled=True,
        )
        assert is_documents_enabled(org) is True

    def test_invoicing_misma_logica(self):
        os.environ["CLIENT_INVOICING_ENABLED"] = "true"
        org = MessagingOrganization(
            company_code="X", name="X", client_invoicing_enabled=True,
        )
        assert is_invoicing_enabled(org) is True

        os.environ["CLIENT_INVOICING_ENABLED"] = "false"
        assert is_invoicing_enabled(org) is False


class TestRequireFlags:
    """Verifica que require_* lanza excepciones apropiadas."""

    def test_require_documents_org_inexistente(self):
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            try:
                require_documents_enabled(db, "inexistente")
                assert False, "Deberia lanzar HTTPException"
            except Exception as exc:
                assert exc.status_code == 404

    def test_require_documents_desactivado(self):
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "false"
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            org = MessagingOrganization(
                company_code="T", name="T", client_documents_enabled=True,
            )
            db.add(org)
            db.commit()
            try:
                require_documents_enabled(db, org.id)
                assert False, "Deberia lanzar HTTPException"
            except Exception as exc:
                assert exc.status_code == 403


# -- Autorizacion admin --

class TestAdminAuthorization:
    """Solo los admin pueden gestionar feature flags."""

    def test_admin_puede_ver_features(self):
        client, factory, admin_h, _, _, _ = _setup()
        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_code"] == "ORG01"
        assert "client_documents_enabled" in data
        assert "effective_documents" in data

    def test_empleado_no_puede_ver_features(self):
        client, factory, _, empleado_h, _, _ = _setup()
        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=empleado_h,
        )
        assert resp.status_code == 403

    def test_admin_puede_modificar_features(self):
        client, factory, admin_h, _, _, _ = _setup()
        resp = client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
            json={"client_documents_enabled": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_documents_enabled"] is True
        assert data["changes"] == 1

    def test_empleado_no_puede_modificar_features(self):
        client, factory, _, empleado_h, _, _ = _setup()
        resp = client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=empleado_h,
            json={"client_documents_enabled": True},
        )
        assert resp.status_code == 403


# -- Auditoria --

class TestFeatureFlagAudit:
    """Cada cambio de flag genera un registro de auditoria."""

    def test_activar_flag_genera_audit(self):
        client, factory, admin_h, _, _, _ = _setup()
        resp = client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
            json={"client_documents_enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["changes"] == 1

        with factory() as db:
            audits = db.scalars(
                select(ClientFeatureFlagAudit).where(
                    ClientFeatureFlagAudit.flag_name == "client_documents_enabled"
                )
            ).all()
            assert len(audits) == 1
            audit = audits[0]
            assert audit.old_value is False
            assert audit.new_value is True
            assert audit.changed_by == "admin@gestinem.es"
            assert audit.changed_at is not None

    def test_mismo_valor_no_genera_audit(self):
        client, factory, admin_h, _, _, _ = _setup()
        # ORG01 tiene documents=False, enviar False no cambia nada
        resp = client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
            json={"client_documents_enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["changes"] == 0

        with factory() as db:
            count = db.scalar(
                select(func.count()).select_from(ClientFeatureFlagAudit)
            )
            assert count == 0

    def test_dos_flags_generan_dos_audits(self):
        client, factory, admin_h, _, _, _ = _setup()
        resp = client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
            json={
                "client_documents_enabled": True,
                "client_invoicing_enabled": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["changes"] == 2

        with factory() as db:
            audits = db.scalars(select(ClientFeatureFlagAudit)).all()
            assert len(audits) == 2
            flag_names = {a.flag_name for a in audits}
            assert flag_names == {
                "client_documents_enabled",
                "client_invoicing_enabled",
            }


# -- Aislamiento entre organizaciones --

class TestOrganizationIsolation:
    """Cambios en una org no afectan a otra."""

    def test_activar_en_org1_no_afecta_org2(self):
        client, factory, admin_h, _, _, _ = _setup()

        # Activar documents en ORG01
        client.patch(
            "/api/v1/messaging/staff/admin/organizations/ORG01/features",
            headers=admin_h,
            json={"client_documents_enabled": True},
        )

        # ORG02 mantiene su estado original (True)
        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/ORG02/features",
            headers=admin_h,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_documents_enabled"] is True
        assert data["client_invoicing_enabled"] is True

    def test_org_inexistente_devuelve_404(self):
        client, _, admin_h, _, _, _ = _setup()
        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/NOEXISTE/features",
            headers=admin_h,
        )
        assert resp.status_code == 404


# -- Flag efectivo (global AND org) via endpoint --

class TestEffectiveFlags:
    """El endpoint devuelve tanto el flag de org como el efectivo."""

    def test_effective_false_cuando_global_false(self):
        client, factory, admin_h, _, _, _ = _setup()
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "false"

        # ORG02 tiene documents=True a nivel org
        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/ORG02/features",
            headers=admin_h,
        )
        data = resp.json()
        assert data["client_documents_enabled"] is True
        assert data["effective_documents"] is False  # global=false

    def test_effective_true_cuando_global_true_y_org_true(self):
        client, factory, admin_h, _, _, _ = _setup()
        os.environ["CLIENT_DOCUMENTS_ENABLED"] = "true"

        resp = client.get(
            "/api/v1/messaging/staff/admin/organizations/ORG02/features",
            headers=admin_h,
        )
        data = resp.json()
        assert data["client_documents_enabled"] is True
        assert data["effective_documents"] is True
