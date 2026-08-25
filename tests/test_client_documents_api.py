"""Tests para la API de documentos del area del cliente."""

import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/test",
)

import pytest
from starlette.testclient import TestClient

from backend.api.messaging_security import hash_token


# ---------- stubs ----------

def _utcnow():
    return datetime.now(timezone.utc)


class _FakeOrg:
    def __init__(self, **kw):
        defaults = dict(
            id="org-1", company_code="E001", name="Test",
            active=True, client_documents_enabled=True,
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
    def __init__(self):
        self.client_id = "cli-1"
        self.token_hash = hash_token("test-token")
        self.revoked_at = None
        self.expires_at = _utcnow() + timedelta(days=1)


class _FakeDoc:
    def __init__(self, **kw):
        defaults = dict(
            id="doc-1", organization_id="org-1", document_type="factura",
            source_system="desktop_invoice", source_id="FAC-001",
            source_version=1, display_name="Factura 001",
            description="", document_date=_utcnow(),
            fiscal_year=2026, amount=Decimal("100.00"), currency="EUR",
            file_name="fac001.pdf", content_type="application/pdf",
            file_size=1024, sha256="abc123", blob_key="org-1/abc/fac001.pdf",
            status="published", replaced_by_id=None, withdrawal_reason="",
            published_at=_utcnow(), withdrawn_at=None, updated_at=_utcnow(),
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeStorage:
    def __init__(self):
        self.files = {}

    def put(self, content, filename, *, organization_id=""):
        key = f"{organization_id}/{uuid.uuid4().hex}/{filename}"
        self.files[key] = content
        return key

    def get(self, key):
        return self.files.get(key, b"contenido pdf fake")

    def delete(self, key):
        self.files.pop(key, None)

    @staticmethod
    def compute_sha256(content):
        import hashlib
        return hashlib.sha256(content).hexdigest()


class _InMemoryDb:
    """DB en memoria simplificada para tests de documentos."""

    def __init__(self):
        self._session = _FakeSession()
        self._client = _FakeClient()
        self._org = _FakeOrg()
        self._docs = {}
        self._reads = {}
        self._objects = []

    def scalar(self, stmt):
        stmt_str = str(stmt)
        if "msg_sessions" in stmt_str:
            return self._session
        if "client_documents" in stmt_str and "source_system" in stmt_str:
            # Busqueda por source
            for d in self._docs.values():
                return d  # simplificado
            return None
        if "client_document_reads" in stmt_str:
            key = f"read-search"
            return self._reads.get(key)
        return None

    def scalars(self, stmt):
        class _Result:
            def __init__(self, items):
                self._items = items
            def all(self):
                return self._items
        stmt_str = str(stmt)
        if "client_document_reads" in stmt_str:
            return _Result(list(self._reads.keys()))
        return _Result(list(self._docs.values()))

    def get(self, model, pk):
        from backend.api.messaging_models import MessagingOrganization, MessagingClient
        from backend.api.client_models import ClientDocument
        tname = getattr(model, '__tablename__', '')
        if tname == 'msg_organizations':
            return self._org if pk == "org-1" else None
        if tname == 'msg_clients':
            return self._client if pk == "cli-1" else None
        if tname == 'client_documents':
            return self._docs.get(pk)
        return None

    def add(self, obj):
        self._objects.append(obj)

    def flush(self):
        for obj in self._objects:
            if hasattr(obj, 'id') and hasattr(obj, 'blob_key'):
                self._docs[obj.id] = obj

    def commit(self):
        self.flush()

    def refresh(self, obj):
        pass

    def close(self):
        pass


def _build_app(db=None, storage=None, override_internal_auth=False):
    from fastapi import FastAPI
    from backend.api.client_documents_api import router, _db
    from backend.api.security import require_workstation_or_internal

    app = FastAPI()
    app.include_router(router)

    if db is not None:
        app.dependency_overrides[_db] = lambda: db
    if override_internal_auth:
        app.dependency_overrides[require_workstation_or_internal] = lambda: "test"

    if storage is not None:
        import backend.api.client_documents_api as mod
        mod._storage = storage

    return app


# ---------- tests publicacion interna ----------

class TestPublishDocument:
    def test_publicacion_exitosa(self):
        db = _InMemoryDb()
        storage = _FakeStorage()
        app = _build_app(db, storage=storage, override_internal_auth=True)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "organization_id": "org-1",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-001",
                "source_version": "1",
                "display_name": "Factura 001",
                "fiscal_year": "2026",
                "amount": "100.00",
            },
            files={"file": ("factura.pdf", b"contenido pdf", "application/pdf")},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Factura 001"
        assert data["document_type"] == "factura"
        assert data["status"] == "published"

    def test_publicacion_idempotente(self):
        db = _InMemoryDb()
        existing = _FakeDoc()
        db._docs["doc-1"] = existing
        original_scalar = db.scalar
        def patched_scalar(stmt):
            stmt_str = str(stmt)
            if "source_system" in stmt_str and "client_documents" in stmt_str:
                return existing
            return original_scalar(stmt)
        db.scalar = patched_scalar

        storage = _FakeStorage()
        app = _build_app(db, storage=storage, override_internal_auth=True)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "organization_id": "org-1",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-001",
                "source_version": "1",
                "display_name": "Factura 001",
            },
            files={"file": ("factura.pdf", b"otro contenido", "application/pdf")},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert len(storage.files) == 0


# ---------- tests listado cliente ----------

class TestListDocuments:
    def test_listado_autenticado(self):
        db = _InMemoryDb()
        doc = _FakeDoc()
        db._docs["doc-1"] = doc

        original_scalar = db.scalar
        def patched_scalar(stmt):
            stmt_str = str(stmt)
            if "count" in stmt_str.lower() or "anon" in stmt_str.lower():
                return 1
            return original_scalar(stmt)
        db.scalar = patched_scalar

        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/documents/",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_sin_autenticar(self):
        db = _InMemoryDb()
        db._session = None
        db.scalar = lambda stmt: None
        app = _build_app(db)
        client = TestClient(app)
        resp = client.get("/api/v1/messaging/client/documents/")
        assert resp.status_code == 401


# ---------- tests descarga ----------

class TestDownloadDocument:
    def test_descarga_exitosa(self):
        db = _InMemoryDb()
        doc = _FakeDoc()
        db._docs["doc-1"] = doc

        storage = _FakeStorage()
        storage.files[doc.blob_key] = b"pdf content here"

        app = _build_app(db, storage=storage)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/documents/doc-1/download",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.content == b"pdf content here"

    def test_descarga_documento_retirado(self):
        db = _InMemoryDb()
        doc = _FakeDoc(status="withdrawn")
        db._docs["doc-1"] = doc

        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/documents/doc-1/download",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 410

    def test_aislamiento_organizacion(self):
        db = _InMemoryDb()
        doc = _FakeDoc(organization_id="org-2")
        db._docs["doc-1"] = doc

        app = _build_app(db)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/messaging/client/documents/doc-1/download",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 404


class TestMarkAsRead:
    def test_marcar_leido(self):
        db = _InMemoryDb()
        doc = _FakeDoc()
        db._docs["doc-1"] = doc

        app = _build_app(db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/messaging/client/documents/doc-1/read",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200


class TestWithdrawDocument:
    def test_retirar_documento(self):
        db = _InMemoryDb()
        doc = _FakeDoc()
        db._docs["doc-1"] = doc

        app = _build_app(db, override_internal_auth=True)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/messaging/client/documents/internal/doc-1/withdraw",
            data={"reason": "Factura erronea"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert doc.status == "withdrawn"
        assert doc.withdrawal_reason == "Factura erronea"
