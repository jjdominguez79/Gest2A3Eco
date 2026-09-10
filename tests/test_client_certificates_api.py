from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace

os.environ.setdefault(
    "BACKEND_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.client_certificates_api import _db, router
from backend.api.client_models import ClientCertificateRequest, ClientCertificateSecret
from backend.api.database import Base
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token, utcnow
from backend.api.security import require_aapp_worker_key, require_workstation_or_internal


def _setup(monkeypatch, *, enabled=True):
    monkeypatch.setenv("CLIENT_CERTIFICATES_ENABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    token = "cliente-certificados-token"
    with factory() as db:
        org = MessagingOrganization(
            company_code="E00001",
            name="Cliente Uno",
            active=True,
            client_certificates_enabled=enabled,
        )
        db.add(org)
        db.flush()
        client = MessagingClient(
            organization_id=org.id,
            name="Cliente",
            email="cliente@example.test",
            active=True,
        )
        db.add(client)
        db.flush()
        db.add(MessagingSession(
            client_id=client.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=1),
        ))
        db.add(ClientCertificateSecret(
            organization_id=org.id,
            encrypted_blob_key=f"{org.id}/test.g2cert",
            pfx_sha256="a" * 64,
            file_name="test.pfx",
            common_name="Certificado de pruebas",
            valid_until=utcnow() + timedelta(days=365),
            active=True,
        ))
        db.commit()
        org_id = org.id

    app = FastAPI()
    app.include_router(router)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[_db] = override_db
    app.dependency_overrides[require_workstation_or_internal] = lambda: "test"
    app.dependency_overrides[require_aapp_worker_key] = lambda: "test-worker"
    return TestClient(app), factory, org_id, {"Authorization": f"Bearer {token}"}


def test_cliente_crea_y_lista_solicitud(monkeypatch):
    client, factory, org_id, headers = _setup(monkeypatch)

    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={
            "certificate_type": "AEAT_CORRIENTE",
            "idempotency_key": "solicitud-1",
        },
    )

    assert created.status_code == 201
    assert created.json()["status"] == "queued"
    assert created.json()["organization_id"] == org_id
    listed = client.get(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    with factory() as db:
        item = db.scalars(select(ClientCertificateRequest)).one()
        assert item.requester_type == "client"


def test_idempotencia_devuelve_la_misma_solicitud(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)
    payload = {
        "certificate_type": "TGSS_CORRIENTE",
        "idempotency_key": "misma-operacion",
    }

    first = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json=payload,
    )
    second = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


def test_impide_dos_solicitudes_activas_del_mismo_tipo(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)
    first = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CENSAL", "idempotency_key": "uno"},
    )
    second = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CENSAL", "idempotency_key": "dos"},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_flag_desactivado_bloquea_autoservicio(monkeypatch):
    client, _, _, headers = _setup(monkeypatch, enabled=False)

    response = client.get(
        "/api/v1/messaging/client/certificates/types", headers=headers,
    )

    assert response.status_code == 403


def test_cliente_no_puede_solicitar_sin_certificado_central(monkeypatch):
    client, factory, org_id, headers = _setup(monkeypatch)
    with factory() as db:
        secret = db.scalar(select(ClientCertificateSecret).where(
            ClientCertificateSecret.organization_id == org_id,
        ))
        db.delete(secret)
        db.commit()

    status = client.get(
        "/api/v1/messaging/client/certificates/certificate-status",
        headers=headers,
    )
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CORRIENTE"},
    )

    assert status.status_code == 200
    assert status.json() == {"configured": False, "status": "missing"}
    assert created.status_code == 409
    assert "no configurado" in created.json()["detail"]


def test_cliente_solo_puede_cancelar_una_solicitud_en_cola(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "TGSS_LICITACION"},
    ).json()

    cancelled = client.post(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}/cancel",
        headers=headers,
    )
    repeated = client.post(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}/cancel",
        headers=headers,
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert repeated.status_code == 409


def test_escritorio_reemplaza_certificado_y_elimina_el_blob_anterior(monkeypatch):
    client, factory, org_id, _headers = _setup(monkeypatch)
    eliminados = []

    class _Storage:
        def put(self, encrypted, organization_id):
            assert encrypted == b"sobre-cifrado"
            assert organization_id == org_id
            return f"{organization_id}/nuevo.g2cert"

        def delete(self, key):
            eliminados.append(key)

    monkeypatch.setattr(
        "backend.api.client_certificates_api.inspect_pfx",
        lambda _content, _password: SimpleNamespace(
            pfx_sha256="b" * 64,
            common_name="Certificado renovado",
            tax_id="B12345678",
            issuer="FNMT",
            serial_number="ABC123",
            valid_from=utcnow(),
            valid_until=utcnow() + timedelta(days=730),
        ),
    )
    monkeypatch.setattr(
        "backend.api.client_certificates_api.encrypt_material",
        lambda _content, _password, _org_id: b"sobre-cifrado",
    )
    monkeypatch.setattr(
        "backend.api.client_certificates_api.ClientCertificateVaultStorage",
        _Storage,
    )

    response = client.post(
        "/api/v1/messaging/client/certificates/internal/certificate",
        data={"company_code": "E00001", "password": "nueva-clave"},
        files={"file": ("renovado.pfx", b"pfx-renovado", "application/x-pkcs12")},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["version"] == 2
    assert eliminados == [f"{org_id}/test.g2cert"]
    with factory() as db:
        secret = db.scalar(select(ClientCertificateSecret).where(
            ClientCertificateSecret.organization_id == org_id,
        ))
        assert secret.encrypted_blob_key == f"{org_id}/nuevo.g2cert"
        assert secret.file_name == "renovado.pfx"
        assert secret.common_name == "Certificado renovado"
        assert secret.version == 2


def test_worker_claim_y_reintento_con_token(monkeypatch):
    client, factory, _, headers = _setup(monkeypatch)
    client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    )

    claim = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    )

    assert claim.status_code == 200
    item = claim.json()["item"]
    assert item["status"] == "processing"
    assert item["attempt_count"] == 1
    failed = client.post(
        f"/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/fail",
        json={
            "claim_token": item["claim_token"],
            "error_code": "portal_temporal",
            "error_message": "Sede no disponible",
            "retry_after_seconds": 60,
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "queued"
    with factory() as db:
        stored = db.get(ClientCertificateRequest, item["id"])
        assert stored.next_attempt_at is not None
        assert stored.claim_token == ""
