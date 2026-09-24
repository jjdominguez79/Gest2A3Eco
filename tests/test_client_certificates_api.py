from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta, timezone
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

from backend.api.client_certificates_api import _db, _next_dehu_sync, router
from backend.api.client_models import (
    ClientCertificateRequest,
    ClientCertificateSecret,
    ClientDehuNotification,
    ClientDehuMailboxConfig,
    ClientDehuSyncBatch,
    ClientDevMailboxConfig,
    ClientDevNotification,
    ClientDocument,
)
from backend.api.database import Base
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
    MessagingStaff,
    MessagingStaffSession,
)
from backend.api.messaging_security import hash_token, utcnow
from backend.api.security import (
    require_aapp_worker_claim_protocol,
    require_aapp_worker_key,
    require_workstation_or_internal,
)


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
            tax_id="B12345678",
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
    app.dependency_overrides[require_aapp_worker_claim_protocol] = lambda: "test-protocol"
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


def _staff_headers(factory, *, role="admin", external_id="admin-app"):
    token = f"staff-certificate-token-{external_id}"
    with factory() as db:
        db.add(MessagingStaff(
            external_id=external_id,
            name="Administrador" if role == "admin" else "Empleado",
            email=f"{external_id}@gestinem.es",
            role=role,
            active=True,
        ))
        db.add(MessagingStaffSession(
            staff_external_id=external_id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=1),
        ))
        db.commit()
    return {"Authorization": f"Bearer {token}"}


def test_admin_app_solicita_certificado_para_cliente(monkeypatch):
    client, factory, org_id, _ = _setup(monkeypatch, enabled=False)
    headers = _staff_headers(factory)

    types = client.get(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/types",
        headers=headers,
    )
    status = client.get(
        "/api/v1/messaging/client/certificates/staff/organizations/"
        "E00001/certificate-status",
        headers=headers,
    )
    created = client.post(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CENSAL", "idempotency_key": "staff-1"},
    )
    listed = client.get(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/requests",
        headers=headers,
    )

    assert types.status_code == 200
    assert any(item["code"] == "AEAT_CENSAL" for item in types.json()["items"])
    assert status.status_code == 200
    assert status.json()["status"] == "valid"
    assert created.status_code == 201
    assert created.json()["organization_id"] == org_id
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    with factory() as db:
        item = db.get(ClientCertificateRequest, created.json()["id"])
        assert item.requester_type == "staff"
        assert item.requester_id == "admin-app"


def test_admin_app_visualiza_y_publica_certificado_revisado(monkeypatch):
    monkeypatch.setenv("CLIENT_DOCUMENTS_ENABLED", "true")
    client, factory, org_id, _ = _setup(monkeypatch, enabled=False)
    headers = _staff_headers(factory)
    created = client.post(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CENSAL", "idempotency_key": "staff-doc"},
    ).json()
    with factory() as db:
        org = db.get(MessagingOrganization, org_id)
        org.client_documents_enabled = True
        document = ClientDocument(
            organization_id=org_id,
            document_type="certificado_aeat",
            source_system="aapp_worker",
            source_id=created["id"],
            source_version=1,
            display_name="Situacion censal",
            file_name="situacion-censal.pdf",
            content_type="application/pdf",
            file_size=14,
            sha256="d" * 64,
            blob_key=f"{org_id}/situacion-censal.pdf",
            status="draft",
        )
        db.add(document)
        db.flush()
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "completed"
        item.document_id = document.id
        db.commit()
        document_id = document.id

    storage = MagicMock()
    storage.get.return_value = b"%PDF-1.7\nprueba"
    monkeypatch.setattr(
        "backend.api.client_certificates_api.ClientDocumentStorage",
        lambda: storage,
    )
    notifications = []
    monkeypatch.setattr(
        "backend.api.client_documents_api._notify_document_published",
        lambda _db, document: notifications.append(document.id),
    )
    base = (
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/"
        f"requests/{created['id']}"
    )

    listed = client.get(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/requests",
        headers=headers,
    )
    preview = client.get(f"{base}/document", headers=headers)
    published = client.post(f"{base}/publish", headers=headers)
    repeated = client.post(f"{base}/publish", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["items"][0]["document_status"] == "draft"
    assert preview.status_code == 200
    assert preview.content == b"%PDF-1.7\nprueba"
    assert preview.headers["content-disposition"] == (
        'inline; filename="situacion-censal.pdf"'
    )
    assert published.status_code == 200
    assert published.json()["document_status"] == "published"
    assert repeated.status_code == 200
    assert notifications == [document_id]
    with factory() as db:
        assert db.get(ClientDocument, document_id).status == "published"


def test_empleado_no_puede_solicitar_certificado_para_cliente(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    headers = _staff_headers(factory, role="empleado", external_id="empleado-app")

    response = client.post(
        "/api/v1/messaging/client/certificates/staff/organizations/E00001/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CENSAL"},
    )

    assert response.status_code == 403
    assert "administrador" in response.json()["detail"]


def test_admin_app_no_opera_solicitud_de_otra_empresa(monkeypatch):
    client, factory, _, client_headers = _setup(monkeypatch)
    headers = _staff_headers(factory)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=client_headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).json()
    with factory() as db:
        other = MessagingOrganization(
            company_code="E00002", name="Cliente Dos", active=True,
        )
        db.add(other)
        db.commit()

    response = client.post(
        "/api/v1/messaging/client/certificates/staff/organizations/E00002/"
        f"requests/{created['id']}/cancel",
        headers=headers,
    )

    assert response.status_code == 404


def test_worker_guarda_bandeja_dehu_idempotente_y_escritorio_la_lista(monkeypatch):
    client, factory, org_id, _ = _setup(monkeypatch)
    with factory() as db:
        db.add(ClientDehuMailboxConfig(
            organization_id=org_id, mailbox_id="mailbox-1", active=True,
        ))
        db.commit()
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


def test_worker_asigna_dehu_por_nif_titular_y_omite_desconocidos(monkeypatch):
    client, factory, source_org_id, _ = _setup(monkeypatch)
    with factory() as db:
        target = MessagingOrganization(
            company_code="E00002",
            name="Cliente representado",
            tax_id="B87654321",
            active=True,
        )
        db.add(target)
        db.flush()
        db.add(ClientDehuMailboxConfig(
            organization_id=target.id, mailbox_id="mailbox-target", active=True,
        ))
        db.commit()
        target_org_id = target.id

    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC", "idempotency_key": "dehu-red"},
    )
    assert created.status_code == 201
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    response = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{claimed['id']}/dehu-notifications",
        json={
            "claim_token": claimed["claim_token"],
            "notifications": [
                {"reference": "REF-ASIGNADA", "holder_tax_id": "B87654321"},
                {"reference": "REF-SIN-CLIENTE", "holder_tax_id": "B00000000"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["assigned_count"] == 1
    assert response.json()["unassigned_count"] == 1
    assert response.json()["unassigned_tax_ids"] == ["B00000000"]
    assert response.json()["discarded_without_active_mailbox_count"] == 1
    assert response.json()["audit_items"][0]["contracted"] is True
    assert response.json()["audit_items"][0]["company_name"] == "Cliente representado"
    assert response.json()["audit_items"][1]["contracted"] is False
    assert response.json()["audit_items"][1]["known_client"] is False
    with factory() as db:
        item = db.scalars(select(ClientDehuNotification)).one()
        assert item.organization_id == target_org_id
        assert item.organization_id != source_org_id
        assert item.mailbox_id == "mailbox-target"
        metadata = __import__("json").loads(item.metadata_json)
        assert metadata["certificate_organization_id"] == source_org_id
        assert metadata["assigned_organization_id"] == target_org_id
        assert metadata["assigned_mailbox_id"] == "mailbox-target"


def test_worker_descarta_titular_con_cliente_pero_sin_buzon_dehu_activo(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    with factory() as db:
        unsubscribed = MessagingOrganization(
            company_code="E00003",
            name="Cliente sin servicio DEHu",
            tax_id="B11223344",
            active=True,
        )
        db.add(unsubscribed)
        db.commit()

    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC", "idempotency_key": "dehu-sin-servicio"},
    )
    assert created.status_code == 201
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    response = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{claimed['id']}/dehu-notifications",
        json={
            "claim_token": claimed["claim_token"],
            "notifications": [
                {"reference": "REF-SIN-BUZON", "holder_tax_id": "B11223344"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["assigned_count"] == 0
    assert response.json()["discarded_without_active_mailbox_count"] == 1
    assert response.json()["discarded_without_active_mailbox_tax_ids"] == ["B11223344"]
    audit = response.json()["audit_items"][0]
    assert audit["known_client"] is True
    assert audit["contracted"] is False
    assert audit["company_name"] == "Cliente sin servicio DEHu"
    with factory() as db:
        assert list(db.scalars(select(ClientDehuNotification)).all()) == []


def test_programacion_dehu_encola_y_envia_un_resumen_al_terminar(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    sent = []
    monkeypatch.setattr(
        "backend.api.client_certificates_api.messaging_mail.send_mail",
        lambda to, subject, html: sent.append((to, subject, html)) or True,
    )
    configured = client.put(
        "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001",
        json={
            "mailbox_id": "mailbox-1",
            "mailbox_name": "DEHu Cliente Uno",
            "active": True,
            "periodicity": "DIARIA",
            "notification_email": "avisos@gestinem.es",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["next_sync_at"]

    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    assert claimed["certificate_type"] == "DEHU_SYNC"
    assert claimed["requester_type"] == "staff"
    assert claimed["parameters"]["automatic"] is True
    assert claimed["parameters"]["download_mode"] == "SOLO_DETECTAR"
    assert claimed["dehu_batch_id"]

    with factory() as db:
        prospect = MessagingOrganization(
            company_code="E00009",
            name="Cliente sin servicio",
            tax_id="B99999999",
            active=True,
        )
        db.add(prospect)
        db.commit()
    audit_response = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{claimed['id']}/dehu-notifications",
        json={
            "claim_token": claimed["claim_token"],
            "notifications": [
                {
                    "reference": "REF-CONTRATADA",
                    "holder_tax_id": "B12345678",
                    "subject": "Requerimiento contratado",
                    "issuing_body": "TGSS",
                    "available_date": "2026-09-13",
                    "expiration_date": "2026-09-23",
                    "metadata": {"category": "NOTIFICACION"},
                },
                {
                    "reference": "REF-OPORTUNIDAD",
                    "holder_tax_id": "B99999999",
                    "subject": "Aviso no contratado",
                    "issuing_body": "TGSS",
                    "metadata": {"category": "COMUNICACION"},
                },
            ],
        },
    )
    assert audit_response.status_code == 200

    completed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{claimed['id']}/complete",
        json={
            "claim_token": claimed["claim_token"],
            "result_summary": "2 notificaciones detectadas; 1 nueva.",
        },
    )
    assert completed.status_code == 200
    assert sent[0][0] == "avisos@gestinem.es"
    assert "1 buzones consultados" in sent[0][1]
    assert "Cliente Uno" in sent[0][2]
    assert "Avisos nuevos:</strong> 2" in sent[0][2]
    assert "Requerimiento contratado" in sent[0][2]
    assert "Aviso no contratado" in sent[0][2]
    assert "Cliente sin buzon activo" in sent[0][2]
    assert "No se han importado" in sent[0][2]
    with factory() as db:
        config = db.scalars(select(ClientDehuMailboxConfig)).one()
        batch = db.scalars(select(ClientDehuSyncBatch)).one()
        assert config.last_request_id == claimed["id"]
        assert config.next_sync_at > config.last_enqueued_at
        assert batch.status == "sent"


def test_resumen_dehu_espera_la_reconsulta_e_informa_los_intentos(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    sent = []
    monkeypatch.setattr(
        "backend.api.client_certificates_api.messaging_mail.send_mail",
        lambda to, subject, html: sent.append((to, subject, html)) or True,
    )
    assert client.put(
        "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001",
        json={
            "mailbox_id": "mailbox-1",
            "mailbox_name": "DEHu Cliente Uno",
            "active": True,
            "periodicity": "DIARIA",
            "notification_email": "avisos@gestinem.es",
        },
    ).status_code == 200

    primer_intento = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    ruta = (
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        f"{primer_intento['id']}"
    )
    fallo = client.post(ruta + "/fail", json={
        "claim_token": primer_intento["claim_token"],
        "error_code": "portal_temporal",
        "error_message": "DEHu no responde",
        "retry_after_seconds": 300,
    })
    assert fallo.status_code == 200
    assert fallo.json()["status"] == "queued"
    assert sent == []

    with factory() as db:
        solicitud = db.get(ClientCertificateRequest, primer_intento["id"])
        solicitud.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()

    segundo_intento = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    assert segundo_intento["id"] == primer_intento["id"]
    assert segundo_intento["attempt_count"] == 2
    completado = client.post(ruta + "/complete", json={
        "claim_token": segundo_intento["claim_token"],
        "result_summary": "Consulta recuperada; sin avisos nuevos.",
    })
    assert completado.status_code == 200
    assert len(sent) == 1
    assert "Reconsultados:</strong> 1" in sent[0][2]
    assert "Correcto tras reintento" in sent[0][2]
    assert "<th>Intentos</th>" in sent[0][2]
    assert "<td>2</td>" in sent[0][2]


def test_programacion_automatica_dehu_permite_desactivar_email_interno(monkeypatch):
    client, _, _, _ = _setup(monkeypatch)
    response = client.put(
        "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001",
        json={"active": True, "periodicity": "DIARIA", "notification_email": ""},
    )
    assert response.status_code == 200
    assert response.json()["next_sync_at"]


def test_programacion_automatica_encola_todos_los_buzones_activos(monkeypatch):
    client, factory, first_org_id, _ = _setup(monkeypatch)
    vencida = utcnow() - timedelta(minutes=1)
    with factory() as db:
        second = MessagingOrganization(
            company_code="E00002", name="Cliente Dos", tax_id="B87654321", active=True,
        )
        inactive = MessagingOrganization(
            company_code="E00003", name="Cliente Inactivo", tax_id="B11223344", active=True,
        )
        db.add_all([second, inactive])
        db.flush()
        db.add_all([
            ClientDehuMailboxConfig(
                organization_id=first_org_id, mailbox_id="mailbox-1",
                active=True, periodicity="DIARIA", next_sync_at=vencida,
            ),
            ClientDehuMailboxConfig(
                organization_id=second.id, mailbox_id="mailbox-2",
                active=True, periodicity="DIARIA", next_sync_at=vencida,
            ),
            ClientDehuMailboxConfig(
                organization_id=inactive.id, mailbox_id="mailbox-3",
                active=False, periodicity="DIARIA", next_sync_at=vencida,
            ),
        ])
        db.commit()

    claimed = [
        client.post(
            "/api/v1/messaging/client/certificates/internal/worker/claim",
        ).json()["item"]
        for _ in range(3)
    ]

    assert {item["parameters"]["company_code"] for item in claimed if item} == {
        "E00001", "E00002",
    }
    assert claimed[2] is None
    with factory() as db:
        requests = list(db.scalars(select(ClientCertificateRequest)).all())
        assert len(requests) == 2
        assert len({item.dehu_batch_id for item in requests}) == 1
        assert db.scalars(select(ClientDehuSyncBatch)).one().total_mailboxes == 2


def test_hora_diaria_dehu_sigue_hora_de_madrid_con_cambio_estacional():
    invierno = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    verano = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)
    assert _next_dehu_sync(invierno, "DIARIA", "08:45") == datetime(
        2026, 1, 16, 7, 45, tzinfo=timezone.utc,
    )
    assert _next_dehu_sync(verano, "DIARIA", "08:45") == datetime(
        2026, 7, 16, 6, 45, tzinfo=timezone.utc,
    )


def test_hora_diaria_dehu_se_guarda_y_no_encola_antes_de_hora(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    instante = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("backend.api.client_certificates_api.utcnow", lambda: instante)
    url = "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001"
    response = client.put(url, json={
        "active": True, "periodicity": "DIARIA",
        "daily_sync_time": "08:45", "notification_email": "",
    })
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["next_sync_at"]) == datetime(
        2026, 9, 22, 6, 45, tzinfo=timezone.utc,
    )
    with factory() as db:
        assert db.scalars(select(ClientDehuMailboxConfig)).one().daily_sync_time == "08:45"
    old_client = client.put(url, json={
        "active": True, "periodicity": "DIARIA", "notification_email": "",
    })
    assert old_client.status_code == 200
    assert old_client.json()["daily_sync_time"] == "08:45"
    assert datetime.fromisoformat(old_client.json()["next_sync_at"]).replace(
        tzinfo=timezone.utc,
    ) == datetime.fromisoformat(response.json()["next_sync_at"])
    assert client.put(url, json={
        "active": True, "periodicity": "DIARIA", "daily_sync_time": "24:00",
    }).status_code == 422


def test_resumen_segunda_consulta_solo_enumera_nuevas_y_excluye_leidas(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    sent = []
    monkeypatch.setattr(
        "backend.api.client_certificates_api.messaging_mail.send_mail",
        lambda to, subject, html: sent.append((to, subject, html)) or True,
    )
    assert client.put(
        "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001",
        json={"active": True, "periodicity": "DIARIA", "notification_email": "despacho@gestinem.es"},
    ).status_code == 200
    anteriores = [
        {"reference": "ANTIGUA", "subject": "Asunto del dia anterior", "holder_tax_id": "B12345678"},
        {"reference": "OP-ANTIGUA", "subject": "Oportunidad del dia anterior", "holder_tax_id": "B99999999"},
    ]

    def ciclo(notificaciones):
        claimed = client.post(
            "/api/v1/messaging/client/certificates/internal/worker/claim",
        ).json()["item"]
        assert claimed is not None
        prefix = "/api/v1/messaging/client/certificates/internal/worker/requests/" + claimed["id"]
        result = client.post(prefix + "/dehu-notifications", json={
            "claim_token": claimed["claim_token"], "notifications": notificaciones,
        })
        assert result.status_code == 200
        assert client.post(prefix + "/complete", json={"claim_token": claimed["claim_token"]}).status_code == 200
        return result.json()

    ciclo(anteriores)
    with factory() as db:
        config = db.scalars(select(ClientDehuMailboxConfig)).one()
        config.next_sync_at = utcnow() - timedelta(seconds=1)
        db.commit()
    result = ciclo(anteriores + [
        {"reference": "NUEVA", "subject": "Asunto recien recibido", "holder_tax_id": "B12345678"},
        {"reference": "OP-NUEVA", "subject": "Oportunidad recien recibida", "holder_tax_id": "B99999999"},
        {"reference": "LEIDA", "subject": "Asunto ya leido", "holder_tax_id": "B12345678", "status": "READ"},
        {"reference": "REALIZADA", "subject": "Asunto realizado", "holder_tax_id": "B12345678", "source_endpoint": "/api/v1/realized_notifications"},
    ])
    assert result["created_count"] == 1
    assert result["ignored_read_count"] == 2
    assert result["audit_items"][0]["new"] is False
    assert len(sent) == 2
    assert "2 avisos nuevos" in sent[1][1]
    assert "Asunto recien recibido" in sent[1][2]
    assert "Oportunidad recien recibida" in sent[1][2]
    assert "Asunto del dia anterior" not in sent[1][2]
    assert "Oportunidad del dia anterior" not in sent[1][2]
    assert "Asunto ya leido" not in sent[1][2]
    assert "Asunto realizado" not in sent[1][2]


def test_backend_no_devuelve_a_pendiente_notificacion_ya_leida(monkeypatch):
    client, factory, org_id, _ = _setup(monkeypatch)
    with factory() as db:
        db.add(ClientDehuMailboxConfig(organization_id=org_id, active=True))
        db.add(ClientDehuNotification(
            organization_id=org_id, external_reference="REF-LEIDA", status="LEIDA",
        ))
        db.commit()
    client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC"},
    )
    claimed = client.post("/api/v1/messaging/client/certificates/internal/worker/claim").json()["item"]
    result = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        + claimed["id"] + "/dehu-notifications",
        json={"claim_token": claimed["claim_token"], "notifications": [
            {"reference": "REF-LEIDA", "holder_tax_id": "B12345678", "status": "PENDIENTE"},
        ]},
    )
    assert result.json()["ignored_read_count"] == 1
    with factory() as db:
        assert db.scalars(select(ClientDehuNotification)).one().status == "LEIDA"
    historical = client.get(
        "/api/v1/messaging/client/certificates/internal/dehu-notifications",
    ).json()["items"]
    assert len(historical) == 1
    assert historical[0]["status"] == "LEIDA"


def test_backend_actualiza_a_leida_una_notificacion_pendiente_conocida(monkeypatch):
    client, factory, org_id, _ = _setup(monkeypatch)
    with factory() as db:
        db.add(ClientDehuMailboxConfig(organization_id=org_id, active=True))
        db.add(ClientDehuNotification(
            organization_id=org_id, external_reference="REF-PORTAL",
            holder_tax_id="B12345678", status="PENDIENTE",
        ))
        db.commit()
    client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC"},
    )
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    response = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        + claimed["id"] + "/dehu-notifications",
        json={"claim_token": claimed["claim_token"], "notifications": [{
            "reference": "REF-PORTAL", "holder_tax_id": "B12345678",
            "status": "READ", "source_endpoint": "/api/v1/realized_notifications",
        }]},
    )
    assert response.status_code == 200
    assert response.json()["updated_status_count"] == 1
    with factory() as db:
        assert db.scalars(select(ClientDehuNotification)).one().status == "LEIDA"


def test_dehu_incorpora_leida_tras_el_alta_sin_importar_historico(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    assert client.put(
        "/api/v1/messaging/client/certificates/internal/dehu-mailboxes/E00001",
        json={"active": True, "periodicity": "MANUAL", "mailbox_id": "dehu-1"},
    ).status_code == 200
    request = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC"},
    )
    assert request.status_code == 201
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    today = utcnow().date()
    response = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        + claimed["id"] + "/dehu-notifications",
        json={"claim_token": claimed["claim_token"], "notifications": [
            {
                "reference": "DEHU-HISTORICA", "holder_tax_id": "B12345678",
                "available_date": (today - timedelta(days=1)).isoformat(),
                "status": "READ", "source_endpoint": "/api/v1/realized_notifications",
            },
            {
                "reference": "DEHU-LEIDA-TRAS-ALTA", "holder_tax_id": "B12345678",
                "available_date": today.isoformat(), "status": "READ",
                "source_endpoint": "/api/v1/realized_notifications",
            },
        ]},
    )
    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    assert response.json()["ignored_read_count"] == 1
    with factory() as db:
        item = db.scalars(select(ClientDehuNotification)).one()
        assert item.external_reference == "DEHU-LEIDA-TRAS-ALTA"
        assert item.status == "LEIDA"


def test_dev_programado_se_encola_y_avisa_si_el_titular_no_esta_de_alta(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    response = client.put(
        "/api/v1/messaging/client/certificates/internal/dev-mailboxes/E00001",
        json={"active": True, "periodicity": "DIARIA"},
    )
    assert response.status_code == 200
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    assert claimed["certificate_type"] == "DEV_SYNC"
    result = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        + claimed["id"] + "/dev-notifications",
        json={
            "claim_token": claimed["claim_token"],
            "registration_status": "NO_ALTA",
            "registration_message": "El titular no esta dado de alta en DEV.",
            "notifications": [],
        },
    )
    assert result.status_code == 200
    with factory() as db:
        config = db.scalars(select(ClientDevMailboxConfig)).one()
        assert config.registration_status == "NO_ALTA"


def test_dev_solo_incorpora_desde_el_alta_y_actualiza_estado_portal(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    assert client.put(
        "/api/v1/messaging/client/certificates/internal/dev-mailboxes/E00001",
        json={"active": True, "periodicity": "MANUAL", "mailbox_id": "dev-1"},
    ).status_code == 200
    request = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEV_SYNC"},
    )
    assert request.status_code == 201
    claimed = client.post(
        "/api/v1/messaging/client/certificates/internal/worker/claim",
    ).json()["item"]
    today = utcnow().date()
    yesterday = today - timedelta(days=1)
    endpoint = (
        "/api/v1/messaging/client/certificates/internal/worker/requests/"
        + claimed["id"] + "/dev-notifications"
    )
    first = client.post(endpoint, json={
        "claim_token": claimed["claim_token"],
        "registration_status": "ACTIVO",
        "notifications": [
            {
                "reference": "DEV-ANTERIOR", "holder_tax_id": "B12345678",
                "available_date": yesterday.isoformat(), "status": "PENDIENTE",
            },
            {
                "reference": "DEV-NUEVA", "holder_tax_id": "B12345678",
                "available_date": today.isoformat(), "status": "PENDIENTE",
            },
        ],
    })
    assert first.status_code == 200
    assert first.json()["created_count"] == 1
    assert first.json()["ignored_historical_count"] == 1
    second = client.post(endpoint, json={
        "claim_token": claimed["claim_token"],
        "registration_status": "ACTIVO",
        "notifications": [{
            "reference": "DEV-NUEVA", "holder_tax_id": "B12345678",
            "available_date": today.isoformat(), "status": "LEIDA",
        }],
    })
    assert second.status_code == 200
    assert second.json()["updated_status_count"] == 1
    with factory() as db:
        item = db.scalars(select(ClientDevNotification)).one()
        assert item.status == "LEIDA"
    listed = client.get(
        "/api/v1/messaging/client/certificates/internal/dev-notifications",
    ).json()["items"]
    assert len(listed) == 1
    assert listed[0]["provider"] == "DEV"
    assert listed[0]["status"] == "LEIDA"


def test_dehu_permite_repetir_consulta_tras_completar_el_mismo_dia(monkeypatch):
    client, factory, _, _ = _setup(monkeypatch)
    first = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC", "idempotency_key": "dehu-primera"},
    )
    with factory() as db:
        request_item = db.get(ClientCertificateRequest, first.json()["id"])
        request_item.status = "completed"
        db.commit()
    second = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={"certificate_type": "DEHU_SYNC", "idempotency_key": "dehu-segunda"},
    )
    assert first.status_code == 201
    assert second.status_code == 201


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


@pytest.mark.parametrize("status", ["queued", "completed", "failed", "needs_action", "cancelled"])
def test_cliente_retira_solicitud_y_puede_pedir_otra_hoy(monkeypatch, status):
    client, factory, org_id, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CORRIENTE", "idempotency_key": "original"},
    ).json()
    with factory() as db:
        document = ClientDocument(
            organization_id=org_id, document_type="certificado_aeat",
            display_name="Certificado AEAT", file_name="certificado.pdf",
            content_type="application/pdf", blob_key="certificado-original.pdf",
            sha256="a" * 64,
            source_system="aapp_worker", source_id=created["id"],
        )
        db.add(document)
        db.flush()
        document_id = document.id
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = status
        if status == "completed":
            item.document_id = document_id
            item.completed_at = utcnow()
        db.commit()

    url = f"/api/v1/messaging/client/certificates/requests/{created['id']}"
    removed = client.delete(url, headers=headers)
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True
    assert client.delete(url, headers=headers).status_code == 200
    assert client.get(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
    ).json()["items"] == []
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        assert item.status == "cancelled"
        assert item.error_code == "client_removed"
        assert item.cancelled_at is not None
        assert item.claim_token == ""
        assert db.get(ClientDocument, document_id).blob_key == "certificado-original.pdf"
        if status == "completed":
            assert item.document_id == document_id
            assert item.completed_at is not None
    second = client.post(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
        json={"certificate_type": "AEAT_CORRIENTE", "idempotency_key": "nueva"},
    )
    assert second.status_code == 201
    assert second.json()["id"] != created["id"]


def test_cliente_no_retira_una_solicitud_en_tramitacion(monkeypatch):
    client, factory, _, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "processing"
        item.claim_token = "claim-en-curso"
        db.commit()
    response = client.delete(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}", headers=headers,
    )
    assert response.status_code == 409
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        assert item.status == "processing"
        assert item.claim_token == "claim-en-curso"


@pytest.mark.parametrize("own_org", [True, False])
def test_cliente_no_retira_solicitudes_del_escritorio_ni_de_otra_empresa(monkeypatch, own_org):
    client, factory, org_id, headers = _setup(monkeypatch)
    with factory() as db:
        if not own_org:
            org = MessagingOrganization(company_code="E00002", name="Otra empresa", active=True)
            db.add(org)
            db.flush()
            org_id = org.id
        item = ClientCertificateRequest(
            organization_id=org_id, requester_type="desktop" if own_org else "client",
            requester_id="otro", certificate_type="AEAT_CORRIENTE",
            idempotency_key="ajena", status="failed",
        )
        db.add(item)
        db.commit()
        request_id = item.id
    response = client.delete(
        f"/api/v1/messaging/client/certificates/requests/{request_id}", headers=headers,
    )
    assert response.status_code == 404
    with factory() as db:
        assert db.get(ClientCertificateRequest, request_id).status == "failed"


def test_cancelar_solicitud_libera_el_limite_diario(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).json()
    assert client.post(
        f"/api/v1/messaging/client/certificates/requests/{created['id']}/cancel", headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/v1/messaging/client/certificates/requests", headers=headers,
        json={"certificate_type": "TGSS_CORRIENTE"},
    ).status_code == 201


def test_contratistas_exige_cif_y_razon_social(monkeypatch):
    client, _, _, headers = _setup(monkeypatch)

    missing = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={"certificate_type": "AEAT_CONTRATISTAS"},
    )
    created_without_name = client.post(
        "/api/v1/messaging/client/certificates/requests",
        headers=headers,
        json={
            "certificate_type": "AEAT_CONTRATISTAS",
            "parameters": {"contracting_party_tax_id": "b-12345678"},
        },
    )
    assert missing.status_code == 422
    assert created_without_name.status_code == 422
    created_with_name = client.post(
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
    assert created_with_name.status_code == 201
    assert created_with_name.json()["parameters"] == {
        "contracting_party_tax_id": "B12345678",
        "contracting_party_name": "Empresa contratante SL",
    }


def test_flag_desactivado_bloquea_autoservicio(monkeypatch):
    client, _, _, headers = _setup(monkeypatch, enabled=False)

    response = client.get(
        "/api/v1/messaging/client/certificates/types", headers=headers,
    )

    assert response.status_code == 403


def test_estado_del_certificado_visible_sin_autoservicio_y_sin_secretos(monkeypatch):
    client, _, _, headers = _setup(monkeypatch, enabled=False)

    response = client.get(
        "/api/v1/messaging/client/certificates/certificate-status",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert response.json()["common_name"] == "Certificado de pruebas"
    assert "valid_until" in response.json()
    assert not ({"encrypted_blob_key", "pfx_sha256", "file_name", "serial_number"}
                & response.json().keys())


def test_certificado_aun_no_vigente_bloquea_solicitud(monkeypatch):
    client, factory, org_id, headers = _setup(monkeypatch)
    with factory() as db:
        secret = db.scalar(select(ClientCertificateSecret).where(
            ClientCertificateSecret.organization_id == org_id,
        ))
        secret.valid_from = utcnow() + timedelta(days=2)
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

    assert status.json()["status"] == "not_yet_valid"
    assert created.status_code == 409


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


def test_escritorio_elimina_certificado_de_organizacion_inactiva(monkeypatch):
    client, factory, org_id, _headers = _setup(monkeypatch)
    eliminados = []

    class _Storage:
        def delete(self, key):
            eliminados.append(key)

    monkeypatch.setattr(
        "backend.api.client_certificates_api.ClientCertificateVaultStorage",
        _Storage,
    )
    with factory() as db:
        db.get(MessagingOrganization, org_id).active = False
        db.commit()

    response = client.delete(
        "/api/v1/messaging/client/certificates/internal/certificate",
        params={"company_code": "E00001"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert eliminados == [f"{org_id}/test.g2cert"]
    with factory() as db:
        secret = db.scalar(select(ClientCertificateSecret).where(
            ClientCertificateSecret.organization_id == org_id,
        ))
        assert secret is None


def test_escritorio_elimina_certificado_de_organizacion_ya_ausente(monkeypatch):
    client, _, _, _headers = _setup(monkeypatch)

    response = client.delete(
        "/api/v1/messaging/client/certificates/internal/certificate",
        params={"company_code": "E99999"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


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


def test_escritorio_corrige_contratante_antes_de_reintentar(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={
            "certificate_type": "AEAT_CONTRATISTAS",
            "parameters": {
                "contracting_party_tax_id": "B12345678",
                "contracting_party_name": "Nombre anterior",
            },
        },
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "needs_action"
        item.parameters_json = '{"contracting_party_tax_id":"B12345678"}'
        db.commit()

    ruta = f"/api/v1/messaging/client/certificates/internal/requests/{created['id']}/retry"
    assert client.post(ruta, json={"parameters": {"contracting_party_tax_id": "B12345678"}}).status_code == 422
    response = client.post(ruta, json={"parameters": {
        "contracting_party_tax_id": "b-12345678",
        "contracting_party_name": "Empresa corregida",
    }})

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "queued"
    assert response.json()["parameters"] == {
        "contracting_party_tax_id": "B12345678",
        "contracting_party_name": "Empresa corregida",
    }
    with factory() as db:
        assert len(db.scalars(select(ClientCertificateRequest)).all()) == 1


def test_no_cambia_contratante_tras_presentar_en_aeat(monkeypatch):
    client, factory, _, _headers = _setup(monkeypatch)
    created = client.post(
        "/api/v1/messaging/client/certificates/internal/requests",
        params={"company_code": "E00001"},
        json={
            "certificate_type": "AEAT_CONTRATISTAS",
            "parameters": {
                "contracting_party_tax_id": "B12345678",
                "contracting_party_name": "Empresa original",
            },
        },
    ).json()
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        item.status = "needs_action"
        item.submitted_at = utcnow()
        db.commit()

    response = client.post(
        f"/api/v1/messaging/client/certificates/internal/requests/{created['id']}/retry",
        json={"parameters": {
            "contracting_party_tax_id": "B87654321",
            "contracting_party_name": "Otra empresa",
        }},
    )

    assert response.status_code == 409
    with factory() as db:
        item = db.get(ClientCertificateRequest, created["id"])
        assert item.status == "needs_action"
        assert 'Empresa original' in item.parameters_json


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
