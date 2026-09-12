from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

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
from backend.api.client_models import (
    ClientCertificateRequest,
    ClientCertificateSecret,
    ClientDehuNotification,
    ClientDocument,
)
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


def test_worker_guarda_bandeja_dehu_idempotente_y_escritorio_la_lista(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={
            "certificate_type": "DEHU_SYNC",
            "idempotency_key": "dehu-central-1",
        },
    )
    assert created.status_code == 201
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    payload = {
        "claim_token": claimed["claim_token"],
        "notifications": [{
            "reference": "DEHU-REF-1",
            "mailbox_id": "mailbox-1",
            "subject": "Requerimiento de prueba",
            "holder_tax_id": "B12345678",
            "available_date": "2026-09-12",
            "expiration_date": "2026-09-22",
            "status": "PENDIENTE",
            "source_endpoint": "/api/v1/notifications",
            "metadata": {"sentReference": "ENV-1"},
        }],
    }
    url = (
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{claimed['id']}/dehu-notifications"
    )
    assert client.post(url, json=payload).status_code == 200
    payload["notifications"][0]["subject"] = "Requerimiento actualizado"
    assert client.post(url, json=payload).status_code == 200

    listed = client.get(
        "/api/v1/messaging/client/certificates/internal/dehu-notifications",
        params={"company_code": "E00001"},
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["subject"] == "Requerimiento actualizado"
    assert listed.json()["items"][0]["company_code"] == "E00001"
    with factory() as db:
        assert len(list(db.scalars(select(ClientDehuNotification)).all())) == 1


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


def test_impide_repetir_el_mismo_certificado_aunque_el_anterior_terminase(monkeypatch):
    client, factory, _, headers = _setup(monkeypatch)
    first = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_IAE", "idempotency_key": "primera"},
    )
    with factory() as db:
        item = db.get(ClientCertificateRequest, first.json()["id"])
        item.status = "completed"
        db.commit()

    second = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_IAE", "idempotency_key": "segunda"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "hoy" in second.json()["detail"]


def test_contratistas_exige_y_normaliza_datos_del_contratante(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)

    missing = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CONTRATISTAS"},
    )
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={
            "certificate_type": "AEAT_CONTRATISTAS",
            "parameters": {
                "contracting_party_tax_id": "b-12345678",
                "contracting_party_name": "Empresa contratante SL",
            },
        },
    )

    assert missing.status_code == 422
    assert created.status_code == 201
    assert created.json()["parameters"] == {
        "contracting_party_tax_id": "B12345678",
        "contracting_party_name": "Empresa contratante SL",
    }


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


def test_escritorio_lista_solicitudes_centrales_con_empresa(monkeypatch):
    client, _, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "AEAT_CENSAL"},
    )

    response = client.get(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
    )

    assert created.status_code == 201
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert item["id"] == created.json()["id"]
    assert item["company_code"] == "E00001"
    assert item["company_name"] == "Cliente Uno"


def test_escritorio_reintenta_solicitud_sin_crear_duplicado(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "AEAT_CORRIENTE"},
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "needs_action"
        item.attempt_count = 2
        item.error_code = "portal_interactivo"
        item.error_message = "No se encontro el tramite"
        item.result_summary = "Requiere revision"
        item.claim_token = "token-anterior"
        db.commit()

    response = client.post(
        f"/api/v1/messaging/client/certificates/internal/requests/{created['id']}/retry",
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "queued"
    assert response.json()["attempt_count"] == 0
    assert response.json()["error_message"] is None
    with factory() as db:
        assert len(db.scalars(select(ClientCertificateRequest)).all()) == 1


def test_escritorio_elimina_solo_intento_fallido_sin_documento(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "AEAT_CORRIENTE"},
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "failed"
        item.error_message = "Intento de prueba"
        db.commit()

    deleted = client.delete(
        f"/api/v1/messaging/client/certificates/internal/requests/{created['id']}",
    )

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": created["id"]}
    with factory() as db:
        assert db.get(ClientCertificateRequest, created["id"]) is None


def test_escritorio_adelanta_reintento_automatico_aplazado(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "AEAT_CORRIENTE"},
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.next_attempt_at = utcnow() + timedelta(minutes=5)
        item.error_message = "Reintento automatico aplazado"
        db.commit()

    response = client.post(
        f"/api/v1/messaging/client/certificates/internal/requests/{created['id']}/retry",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["error_message"] is None
    with factory() as db:
        assert db.get(ClientCertificateRequest, created["id"]).next_attempt_at is None


def test_cliente_solo_reintenta_sus_solicitudes_reintentables(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).json()

    response = client.post(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}/retry",
        headers=headers,
    )

    assert response.status_code == 409


def test_cliente_reintenta_su_solicitud_con_intervencion(monkeypatch):
    client, factory, _, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "needs_action"
        item.error_message = "El portal requiere revision"
        db.commit()

    response = client.post(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}/retry",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["error_message"] is None


def test_escritorio_descarga_documento_de_solicitud_central(monkeypatch):
    client, factory, org_id, _headers = _setup(monkeypatch)
    with factory() as db:
        document = ClientDocument(
            organization_id=org_id,
            document_type="certificado_aeat",
            source_system="aapp_worker",
            source_id="sol-doc",
            source_version=1,
            display_name="Certificado censal",
            file_name="censal.pdf",
            content_type="application/pdf",
            file_size=8,
            sha256="c" * 64,
            blob_key=f"{org_id}/censal.pdf",
            status="published",
        )
        db.add(document)
        db.flush()
        request_item = ClientCertificateRequest(
            organization_id=org_id,
            requester_type="desktop",
            requester_id="desktop",
            certificate_type="AEAT_CENSAL",
            idempotency_key="sol-doc",
            status="completed",
            document_id=document.id,
        )
        db.add(request_item)
        db.commit()
        request_id = request_item.id

    storage = MagicMock()
    storage.get.return_value = b"%PDF-1.7"
    monkeypatch.setattr(
        "backend.api.client_certificates_api.ClientDocumentStorage",
        lambda: storage,
    )

    response = client.get(
        f"/api/v1/messaging/client/certificates/internal/requests/{request_id}/document",
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7"
    assert response.headers["content-disposition"] == 'attachment; filename="censal.pdf"'


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


def test_dehu_solo_se_puede_encolar_desde_el_escritorio(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)

    public_response = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "DEHU_SYNC"},
    )
    internal_response = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC"},
    )

    assert public_response.status_code == 422
    assert internal_response.status_code == 201
    assert internal_response.json()["issuing_organization"] == "DEHU"


def test_worker_completa_sin_documento_una_sincronizacion_dehu(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC"},
    )
    claim = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]

    response = client.post(
        f"/api/v1/messaging/client/certificates/internal/worker/requests/{claim['id']}/complete",
        json={
            "claim_token": claim["claim_token"],
            "document_id": None,
            "result_summary": "No habia documentos nuevos",
        },
    )

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["document_id"] is None
    with factory() as db:
        stored = db.get(ClientCertificateRequest, claim["id"])
        assert stored.document_id is None
