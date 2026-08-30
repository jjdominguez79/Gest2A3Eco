"""Tests para la API de documentos del area del cliente."""

import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/test",
)
# Para tests: habilitar area documental globalmente
os.environ.setdefault("CLIENT_DOCUMENTS_ENABLED", "true")
os.environ.setdefault("CLIENT_DOCUMENTS_ALLOW_LOCAL_STORAGE", "true")

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
        if "msg_organizations" in stmt_str:
            params = {str(value).upper() for value in stmt.compile().params.values()}
            if str(self._org.company_code).upper() in params and self._org.active:
                return self._org
            return None
        if "client_documents" in stmt_str and "source_system" in stmt_str:
            params = stmt.compile().params
            expected_hash = next(
                (str(value) for key, value in params.items() if "sha256" in key),
                None,
            )
            expected_org = next(
                (str(value) for key, value in params.items()
                 if "organization_id" in key),
                None,
            )
            for d in self._docs.values():
                if (
                    (expected_hash is None or d.sha256 == expected_hash)
                    and (expected_org is None or d.organization_id == expected_org)
                ):
                    return d
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
        if "msg_clients.id" in stmt_str:
            return _Result([self._client.id])
        if "msg_app_devices" in stmt_str:
            return _Result([])
        if "client_document_reads" in stmt_str:
            return _Result(list(self._reads.keys()))
        if stmt_str.strip().startswith("SELECT client_documents.source_version"):
            params = stmt.compile().params
            expected_org = next(
                (str(value) for key, value in params.items()
                 if "organization_id" in key),
                None,
            )
            return _Result([
                d.source_version for d in self._docs.values()
                if expected_org is None or d.organization_id == expected_org
            ])
        if "client_documents" in stmt_str and "source_system" in stmt_str:
            params = stmt.compile().params
            expected_org = next(
                (str(value) for key, value in params.items()
                 if "organization_id" in key),
                None,
            )
            is_not_equal = "client_documents.organization_id !=" in stmt_str
            return _Result([
                d for d in self._docs.values()
                if expected_org is None
                or ((d.organization_id != expected_org) if is_not_equal
                    else (d.organization_id == expected_org))
            ])
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

    def rollback(self):
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
    def test_resuelve_organizacion_por_empresa_emisora(self):
        db = _InMemoryDb()
        db._org = _FakeOrg(company_code="E00006")
        storage = _FakeStorage()
        client = TestClient(
            _build_app(db, storage=storage, override_internal_auth=True),
        )

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "company_code": "e00006",
                "customer_tax_id": "74095618Z",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-E00006-001",
                "display_name": "Factura emitida 001",
            },
            files={
                "file": ("factura.pdf", b"%PDF-1.4 contenido", "application/pdf"),
            },
            headers={"x-api-key": "test-key"},
        )

        assert resp.status_code == 200
        assert len(db._docs) == 1
        assert next(iter(db._docs.values())).organization_id == "org-1"

    def test_factura_no_usa_nif_receptor_como_destino(self):
        db = _InMemoryDb()
        storage = _FakeStorage()
        client = TestClient(
            _build_app(db, storage=storage, override_internal_auth=True),
        )

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "customer_tax_id": "74095618Z",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-SIN-EMISOR",
                "display_name": "Factura sin emisor",
            },
            files={
                "file": ("factura.pdf", b"%PDF-1.4 contenido", "application/pdf"),
            },
            headers={"x-api-key": "test-key"},
        )

        assert resp.status_code == 400
        assert "empresa emisora" in resp.json()["detail"]

    def test_repara_factura_publicada_en_organizacion_receptora(self):
        import hashlib

        content = b"%PDF-1.4 contenido corregible"
        db = _InMemoryDb()
        db._org = _FakeOrg(company_code="E00006")
        misplaced = _FakeDoc(
            id="doc-mal-ubicado",
            organization_id="org-receptor",
            source_id="FAC-A-42",
            sha256=hashlib.sha256(content).hexdigest(),
        )
        db._docs[misplaced.id] = misplaced
        client = TestClient(
            _build_app(db, storage=_FakeStorage(), override_internal_auth=True),
        )

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "company_code": "E00006",
                "previous_document_id": "doc-mal-ubicado",
                "customer_tax_id": "74095618Z",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-A-42",
                "display_name": "Factura A42",
            },
            files={"file": ("factura.pdf", content, "application/pdf")},
            headers={"x-api-key": "test-key"},
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == "doc-mal-ubicado"
        assert misplaced.organization_id == "org-1"

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
            files={"file": ("factura.pdf", b"%PDF-1.4 contenido", "application/pdf")},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Factura 001"
        assert data["document_type"] == "factura"
        assert data["status"] == "published"

    def test_publicacion_idempotente(self):
        db = _InMemoryDb()
        content = b"%PDF-1.4 otro"
        existing = _FakeDoc(sha256=_FakeStorage.compute_sha256(content))
        db._docs["doc-1"] = existing

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
            files={"file": ("factura.pdf", content, "application/pdf")},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert len(storage.files) == 0

    def test_contenido_cambiado_crea_version_y_sustituye_anterior(self):
        db = _InMemoryDb()
        existing = _FakeDoc(sha256="hash-anterior", source_version=1)
        db._docs["doc-1"] = existing
        storage = _FakeStorage()
        client = TestClient(
            _build_app(db, storage=storage, override_internal_auth=True),
        )

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data={
                "organization_id": "org-1",
                "document_type": "factura",
                "source_system": "desktop_invoice",
                "source_id": "FAC-001",
                "source_version": "1",
                "display_name": "Factura corregida",
            },
            files={
                "file": ("factura.pdf", b"%PDF-1.4 corregida", "application/pdf"),
            },
            headers={"x-api-key": "test-key"},
        )

        assert resp.status_code == 200
        assert resp.json()["source_version"] == 2
        assert existing.status == "replaced"
        assert len(storage.files) == 1

    @pytest.mark.parametrize(
        ("content", "extra_data", "expected_status"),
        [
            (b"texto", {}, 415),
            (b"%PDF-1.4 valido", {"expected_sha256": "0" * 64}, 422),
        ],
    )
    def test_rechaza_archivo_invalido_o_hash_incorrecto(
        self, content, extra_data, expected_status,
    ):
        db = _InMemoryDb()
        storage = _FakeStorage()
        client = TestClient(
            _build_app(db, storage=storage, override_internal_auth=True),
        )
        data = {
            "organization_id": "org-1",
            "document_type": "factura",
            "source_system": "desktop_invoice",
            "source_id": "FAC-001",
            "display_name": "Factura 001",
            **extra_data,
        }

        resp = client.post(
            "/api/v1/messaging/client/documents/internal/publish",
            data=data,
            files={"file": ("factura.pdf", content, "application/pdf")},
            headers={"x-api-key": "test-key"},
        )

        assert resp.status_code == expected_status
        assert storage.files == {}


def test_notificacion_documental_incluye_destino_directo(monkeypatch):
    from backend.api import messaging_firebase
    from backend.api import messaging_realtime
    from backend.api.client_documents_api import _notify_document_published

    device = SimpleNamespace(
        push_token="token-1", platform="android", active=True,
    )

    class DbStub:
        def __init__(self):
            self.calls = 0
            self.commits = 0

        def scalars(self, _stmt):
            self.calls += 1
            values = ["cli-1"] if self.calls == 1 else [device]
            return SimpleNamespace(all=lambda: values)

        def commit(self):
            self.commits += 1

    payloads = []
    realtime = []
    monkeypatch.setattr(
        messaging_realtime.hub,
        "publish",
        lambda payload, **kwargs: realtime.append((payload, kwargs)),
    )
    monkeypatch.setattr(
        messaging_firebase,
        "send_fcm",
        lambda token, payload, **kwargs: (
            payloads.append((token, payload, kwargs))
            or messaging_firebase.FcmResult(True, False)
        ),
    )

    _notify_document_published(DbStub(), _FakeDoc())

    assert payloads[0][1]["target_type"] == "document"
    assert payloads[0][1]["document_id"] == "doc-1"
    assert payloads[0][1]["type"] == "document.published"
    assert realtime[0][0]["document_id"] == "doc-1"
    assert realtime[0][1]["organization_id"] == "org-1"


@pytest.mark.parametrize(
    ("document_type", "expected"),
    [
        ("factura_emitida_online", "facturas"),
        ("certificado_aeat", "certificados"),
        ("nomina", "nominas"),
        ("modelo_303", "impuestos"),
        ("contrato_laboral", "contratos"),
        ("escritura", "otros"),
    ],
)
def test_clasifica_documentos_en_carpetas(document_type, expected):
    from backend.api.client_documents_api import _document_folder

    assert _document_folder(document_type) == expected


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


# ---------- tests feature flag publicacion ----------

class TestPublishDocumentFeatureFlag:
    """Publicacion bloqueada si area documental no esta habilitada."""

    def test_publish_returns_403_when_documents_disabled(self):
        """POST /internal/publish devuelve 403 si documents flag es false."""
        # Org con client_documents_enabled=False
        db = _InMemoryDb()
        db._org = _FakeOrg(client_documents_enabled=False)

        storage = _FakeStorage()
        app = _build_app(db, storage=storage, override_internal_auth=True)
        client = TestClient(app)

        # Parchear get_settings para que client_documents_enabled sea True globalmente
        # (el flag efectivo requiere ambos: global Y org)
        from unittest.mock import patch, MagicMock
        fake_settings = MagicMock()
        fake_settings.client_documents_enabled = True
        fake_settings.client_documents_allow_local_storage = True
        fake_settings.client_documents_azure_connection_string = ""
        fake_settings.client_invoicing_enabled = False

        with patch("backend.api.feature_flags.get_settings", return_value=fake_settings):
            resp = client.post(
                "/api/v1/messaging/client/documents/internal/publish",
                data={
                    "organization_id": "org-1",
                    "document_type": "factura",
                    "source_system": "desktop_invoice",
                    "source_id": "FAC-002",
                    "source_version": "1",
                    "display_name": "Factura 002",
                    "fiscal_year": "2026",
                },
                files={"file": ("factura.pdf", b"%PDF-1.4 contenido", "application/pdf")},
                headers={"x-api-key": "test-key"},
            )
        assert resp.status_code == 403
        assert "no habilitada" in resp.json()["detail"].lower()


# ---------- test almacenamiento obligatorio en produccion ----------

class TestStorageProductionEnforcement:
    """ClientDocumentStorage lanza RuntimeError sin Azure en produccion."""

    def test_storage_raises_without_azure_in_production(self, monkeypatch):
        """Sin Azure y con features activos, ClientDocumentStorage lanza RuntimeError."""
        from backend.api.client_storage import ClientDocumentStorage

        # Simular settings: features activos, sin Azure, sin allow_local
        from unittest.mock import MagicMock
        fake_cfg = MagicMock()
        fake_cfg.client_documents_azure_connection_string = ""
        fake_cfg.client_documents_azure_container = "documentos-cliente"
        fake_cfg.client_documents_storage_dir = "./tmp_storage"
        fake_cfg.client_documents_allow_local_storage = False
        fake_cfg.client_documents_enabled = True
        fake_cfg.client_invoicing_enabled = False

        monkeypatch.setattr(
            "backend.api.client_storage.get_settings",
            lambda: fake_cfg,
        )

        import pytest
        with pytest.raises(RuntimeError, match="CLIENT_DOCUMENTS_AZURE_CONNECTION_STRING"):
            ClientDocumentStorage()

    def test_storage_ok_with_allow_local_storage(self, monkeypatch):
        """Con allow_local_fallback=True no lanza error aunque no haya Azure."""
        from backend.api.client_storage import ClientDocumentStorage

        from unittest.mock import MagicMock
        fake_cfg = MagicMock()
        fake_cfg.client_documents_azure_connection_string = ""
        fake_cfg.client_documents_azure_container = "documentos-cliente"
        fake_cfg.client_documents_storage_dir = "./tmp_storage_test"
        fake_cfg.client_documents_allow_local_storage = False
        fake_cfg.client_documents_enabled = True
        fake_cfg.client_invoicing_enabled = False

        monkeypatch.setattr(
            "backend.api.client_storage.get_settings",
            lambda: fake_cfg,
        )

        # Forzar allow_local_fallback=True en el constructor
        storage = ClientDocumentStorage(allow_local_fallback=True)
        assert storage._container is None  # no Azure, usa disco local
