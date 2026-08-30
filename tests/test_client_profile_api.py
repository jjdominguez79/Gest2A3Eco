"""Tests para la API de perfil empresarial del cliente."""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/test",
)

import pytest
from starlette.testclient import TestClient

from backend.api.messaging_security import hash_token


# ---------- stubs ----------

class _FakeOrg:
    def __init__(self, **kw):
        defaults = dict(
            id="org-1", company_code="E001", name="Empresa Test",
            active=True, tax_id="B12345678", legal_name="Empresa Test SL",
            address="Calle Mayor 1", postal_code="28001", city="Madrid",
            province="Madrid", country="ES", phone="912345678",
            email="info@empresa.es", profile_synced_at=None,
            private_owner_external_id="",
            client_invoicing_enabled=False, client_documents_enabled=False,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeClient:
    def __init__(self, **kw):
        defaults = dict(id="cli-1", organization_id="org-1", active=True)
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeSession:
    def __init__(self, **kw):
        defaults = dict(
            client_id="cli-1",
            token_hash=hash_token("test-token"),
            revoked_at=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeDb:
    def __init__(self, org=None, client=None, session=None):
        self._org = org or _FakeOrg()
        self._client = client or _FakeClient()
        self._session = session or _FakeSession()

    def scalar(self, stmt):
        return self._session

    def get(self, model, pk):
        from backend.api.messaging_models import MessagingOrganization, MessagingClient
        if model is MessagingOrganization or (hasattr(model, '__tablename__') and model.__tablename__ == 'msg_organizations'):
            return self._org
        if model is MessagingClient or (hasattr(model, '__tablename__') and model.__tablename__ == 'msg_clients'):
            return self._client
        return None

    def commit(self):
        pass

    def close(self):
        pass

    def refresh(self, obj):
        pass


def _build_app(db=None):
    """Construye app de test con DB falsa."""
    from fastapi import FastAPI
    from backend.api.client_profile_api import router, _db

    app = FastAPI()
    app.include_router(router)

    if db is not None:
        app.dependency_overrides[_db] = lambda: db

    return app


# ---------- tests perfil ----------

class TestGetCompanyProfile:
    def test_perfil_completo(self):
        db = _FakeDb()
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/company-profile",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Empresa Test"
        assert data["tax_id"] == "B12345678"
        assert data["city"] == "Madrid"
        assert data["active"] is True

    def test_campos_vacios_omitidos(self):
        org = _FakeOrg(phone="", email="", profile_synced_at=None)
        db = _FakeDb(org=org)
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/company-profile",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "phone" not in data
        assert "email" not in data
        assert "profile_synced_at" not in data

    def test_sin_autenticar(self):
        db = _FakeDb()
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get("/api/v1/messaging/client/company-profile")
        assert resp.status_code == 401

    def test_token_invalido(self):
        db = _FakeDb(session=None)
        # scalar devuelve None para session invalida
        db.scalar = lambda stmt: None
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/company-profile",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401

    def test_cliente_inactivo(self):
        client_obj = _FakeClient(active=False)
        db = _FakeDb(client=client_obj)
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/company-profile",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 403


class TestSyncProfile:
    def test_sync_actualiza_campos(self):
        org = _FakeOrg()
        db = _FakeDb(org=org)
        original_scalar = db.scalar
        def patched_scalar(stmt):
            stmt_str = str(stmt)
            if "company_code" in stmt_str:
                return org
            return original_scalar(stmt)
        db.scalar = patched_scalar

        from backend.api.client_profile_api import router, _db
        from backend.api.security import require_master_sync_or_workstation_internal
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_db] = lambda: db
        app.dependency_overrides[require_master_sync_or_workstation_internal] = lambda: "test"

        client = TestClient(app)
        resp = client.put(
            "/api/v1/messaging/client/internal/sync-profile",
            json={
                "company_code": "E001",
                "tax_id": "B99999999",
                "legal_name": "Nueva Razon Social",
                "city": "Barcelona",
            },
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["organization_id"] == "org-1"
        assert org.tax_id == "B99999999"
        assert org.city == "Barcelona"

    def test_sync_sin_company_code(self):
        db = _FakeDb()
        from backend.api.client_profile_api import router, _db
        from backend.api.security import require_master_sync_or_workstation_internal
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_db] = lambda: db
        app.dependency_overrides[require_master_sync_or_workstation_internal] = lambda: "test"

        client = TestClient(app)
        resp = client.put(
            "/api/v1/messaging/client/internal/sync-profile",
            json={},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 400
