from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from backend.api.database import Base
from backend.api.messaging_cleanup import (
    CLOSE_CONFIRMATION,
    RECOVER_CONFIRMATION,
    build_cleanup_plan,
    close_pre_release_cleanup,
    execute_cleanup_plan,
    recover_cleanup_maintenance,
)
from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingAttachment,
    MessagingCleanupAudit,
    MessagingCleanupPolicy,
    MessagingClient,
    MessagingConversation,
    MessagingDeletionAudit,
    MessagingDownload,
    MessagingEvent,
    MessagingMessage,
    MessagingOrganization,
    MessagingRead,
    MessagingStaff,
    MessagingStaffThread,
    MessagingStaffThreadMessage,
    MessagingStaffThreadRead,
)


class FakeStorage:
    def __init__(self, fail: bool = False):
        self.deleted: list[str] = []
        self.fail = fail

    def delete(self, key: str) -> None:
        if self.fail:
            raise OSError("storage unavailable")
        self.deleted.append(key)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


def _organization(db, code: str, *, is_test: bool) -> tuple[MessagingOrganization, MessagingClient, MessagingConversation]:
    organization = MessagingOrganization(
        company_code=code, name=f"Empresa {code}", is_test=is_test,
    )
    db.add(organization)
    db.flush()
    client = MessagingClient(
        organization_id=organization.id,
        name=f"Cliente {code}",
        email=f"{code.lower()}@example.test",
    )
    conversation = MessagingConversation(
        organization_id=organization.id, kind="fiscal",
    )
    db.add_all([client, conversation])
    db.flush()
    return organization, client, conversation


def _message(db, conversation_id: str, name: str, created_at: datetime) -> MessagingMessage:
    item = MessagingMessage(
        conversation_id=conversation_id,
        author_type="client",
        author_id="client",
        author_name="Cliente",
        body=name,
        idempotency_key=name,
        created_at=created_at,
    )
    db.add(item)
    db.flush()
    return item


def test_plan_rechaza_organizacion_no_marcada_como_prueba(db):
    _organization(db, "REAL01", is_test=False)
    db.commit()

    with pytest.raises(ValueError, match="no estan marcadas como prueba"):
        build_cleanup_plan(db, organization_refs=["REAL01"], reset_test=True)


def test_limpieza_por_fecha_conserva_mensajes_recientes_y_audita(db):
    now = datetime.now(timezone.utc)
    organization, client, conversation = _organization(db, "TEST01", is_test=True)
    old = _message(db, conversation.id, "old", now - timedelta(days=10))
    recent = _message(db, conversation.id, "recent", now - timedelta(hours=1))
    attachment = MessagingAttachment(
        message_id=old.id,
        name="prueba.pdf",
        content_type="application/pdf",
        size=4,
        sha256="a" * 64,
        storage_key="old/prueba.pdf",
        direction="incoming",
        created_at=old.created_at,
    )
    db.add(attachment)
    db.flush()
    db.add_all([
        MessagingDownload(
            attachment_id=attachment.id,
            client_id=client.id,
            sha256=attachment.sha256,
        ),
        MessagingRead(
            conversation_id=conversation.id,
            actor_type="client",
            actor_id=client.id,
            last_message_id=old.id,
        ),
        MessagingDeletionAudit(
            message_id=old.id,
            conversation_id=conversation.id,
            actor_id="admin",
            action="soft_delete",
        ),
        MessagingEvent(
            organization_id=organization.id,
            conversation_id=conversation.id,
            event_type="message_created",
            created_at=old.created_at,
        ),
        MessagingEvent(
            organization_id=organization.id,
            conversation_id=conversation.id,
            event_type="message_created",
            created_at=recent.created_at,
        ),
    ])
    db.commit()

    cutoff = now - timedelta(days=2)
    plan = build_cleanup_plan(db, cutoff=cutoff)
    assert plan.company_codes == ("TEST01",)
    assert plan.message_ids == (old.id,)
    assert plan.counts["attachments_to_delete"] == 1
    storage = FakeStorage()

    result = execute_cleanup_plan(
        db,
        plan,
        confirmation_code=plan.confirmation_code,
        actor="Administrador",
        reason="Fin de pruebas",
        storage=storage,
    )

    assert db.get(MessagingMessage, old.id) is None
    assert db.get(MessagingMessage, recent.id) is not None
    assert db.get(MessagingOrganization, organization.id) is not None
    assert db.get(MessagingAttachment, attachment.id) is None
    assert storage.deleted == ["old/prueba.pdf"]
    assert db.scalar(select(MessagingRead.last_message_id)) == ""
    assert db.scalar(select(MessagingDeletionAudit.id)) is None
    assert len(tuple(db.scalars(select(MessagingEvent.id)))) == 1
    audit = db.get(MessagingCleanupAudit, result.audit_id)
    assert audit.actor == "Administrador"
    assert json.loads(audit.counts_json)["messages_to_delete"] == 1
    assert json.loads(audit.storage_keys_json) == ["old/prueba.pdf"]


def test_codigo_de_confirmacion_cambia_si_aparece_otro_mensaje(db):
    now = datetime.now(timezone.utc)
    _, _, conversation = _organization(db, "TEST02", is_test=True)
    _message(db, conversation.id, "first", now - timedelta(days=5))
    db.commit()
    cutoff = now - timedelta(days=1)
    initial = build_cleanup_plan(db, cutoff=cutoff)

    _message(db, conversation.id, "second", now - timedelta(days=3))
    db.commit()
    current = build_cleanup_plan(db, cutoff=cutoff)

    assert current.confirmation_code != initial.confirmation_code
    with pytest.raises(ValueError, match="plan actual"):
        execute_cleanup_plan(
            db,
            current,
            confirmation_code=initial.confirmation_code,
            actor="Admin",
            reason="Prueba",
            storage=FakeStorage(),
        )


def test_reset_elimina_solo_organizaciones_de_prueba_y_auxiliares(db):
    now = datetime.now(timezone.utc)
    test_org, test_client, test_conversation = _organization(db, "TEST03", is_test=True)
    real_org, _, real_conversation = _organization(db, "REAL03", is_test=False)
    test_message = _message(db, test_conversation.id, "test", now)
    real_message = _message(db, real_conversation.id, "real", now)
    db.add(MessagingAppDevice(
        user_type="client",
        user_id=test_client.id,
        platform="android",
        push_token="push-test",
    ))
    db.commit()

    plan = build_cleanup_plan(db, reset_test=True)
    execute_cleanup_plan(
        db,
        plan,
        confirmation_code=plan.confirmation_code,
        actor="Admin",
        reason="Reinicio de pruebas",
        storage=FakeStorage(),
    )

    assert db.get(MessagingOrganization, test_org.id) is None
    assert db.get(MessagingClient, test_client.id) is None
    assert db.get(MessagingMessage, test_message.id) is None
    assert db.scalar(select(MessagingAppDevice.id)) is None
    assert db.get(MessagingOrganization, real_org.id) is not None
    assert db.get(MessagingMessage, real_message.id) is not None


def test_fallo_de_storage_no_revierte_bd_y_queda_en_auditoria(db):
    now = datetime.now(timezone.utc)
    _, _, conversation = _organization(db, "TEST04", is_test=True)
    message = _message(db, conversation.id, "old", now - timedelta(days=5))
    attachment = MessagingAttachment(
        message_id=message.id,
        name="fallo.pdf",
        content_type="application/pdf",
        size=4,
        sha256="b" * 64,
        storage_key="failed/fallo.pdf",
        direction="outgoing",
    )
    db.add(attachment)
    db.commit()
    plan = build_cleanup_plan(db, cutoff=now - timedelta(days=1))

    result = execute_cleanup_plan(
        db,
        plan,
        confirmation_code=plan.confirmation_code,
        actor="Admin",
        reason="Pruebas",
        storage=FakeStorage(fail=True),
    )

    assert db.get(MessagingMessage, message.id) is None
    assert result.failed_storage_keys == ("failed/fallo.pdf",)
    audit = db.get(MessagingCleanupAudit, result.audit_id)
    assert json.loads(audit.failed_storage_keys_json) == ["failed/fallo.pdf"]


def test_purga_prepublicacion_incluye_empresas_reales_y_chats_internos(
    db, monkeypatch,
):
    monkeypatch.setenv("MESSAGING_PRE_RELEASE_CLEANUP_ENABLED", "true")
    now = datetime.now(timezone.utc)
    real_org, real_client, conversation = _organization(db, "REAL10", is_test=False)
    old_external = _message(db, conversation.id, "external-old", now - timedelta(days=5))
    recent_external = _message(db, conversation.id, "external-recent", now)
    staff = MessagingStaff(external_id="staff-1", name="Empleado", role="admin")
    thread = MessagingStaffThread(key="direct:test", kind="direct")
    db.add_all([staff, thread])
    db.flush()
    old_internal = MessagingStaffThreadMessage(
        thread_id=thread.id,
        author_staff_external_id=staff.external_id,
        author_name=staff.name,
        body="internal-old",
        idempotency_key="internal-old",
        created_at=now - timedelta(days=4),
    )
    recent_internal = MessagingStaffThreadMessage(
        thread_id=thread.id,
        author_staff_external_id=staff.external_id,
        author_name=staff.name,
        body="internal-recent",
        idempotency_key="internal-recent",
        created_at=now,
    )
    db.add_all([old_internal, recent_internal])
    db.flush()
    attachment = MessagingAttachment(
        internal_message_id=old_internal.id,
        name="interno.pdf",
        content_type="application/pdf",
        size=9,
        sha256="c" * 64,
        storage_key="internal/interno.pdf",
        direction="internal",
    )
    db.add_all([
        attachment,
        MessagingRead(
            conversation_id=conversation.id,
            actor_type="client",
            actor_id=real_client.id,
            last_message_id=old_external.id,
        ),
        MessagingStaffThreadRead(
            thread_id=thread.id,
            staff_external_id=staff.external_id,
            last_message_id=old_internal.id,
        ),
    ])
    db.commit()

    plan = build_cleanup_plan(
        db, cutoff=now - timedelta(days=1), pre_release=True,
    )
    assert plan.company_codes == ("REAL10",)
    assert plan.message_ids == (old_external.id,)
    assert plan.internal_message_ids == (old_internal.id,)
    assert plan.counts["internal_messages_to_delete"] == 1

    storage = FakeStorage()
    result = execute_cleanup_plan(
        db, plan, confirmation_code=plan.confirmation_code,
        actor="Admin", reason="Limpieza previa a Play Store", storage=storage,
    )

    assert db.get(MessagingMessage, old_external.id) is None
    assert db.get(MessagingMessage, recent_external.id) is not None
    assert db.get(MessagingStaffThreadMessage, old_internal.id) is None
    assert db.get(MessagingStaffThreadMessage, recent_internal.id) is not None
    assert db.get(MessagingOrganization, real_org.id) is not None
    assert db.get(MessagingStaffThread, thread.id) is not None
    assert storage.deleted == ["internal/interno.pdf"]
    assert db.get(MessagingCleanupPolicy, "pre_release").maintenance_started_at is None
    assert db.get(MessagingCleanupAudit, result.audit_id).scope == "pre_release_global"


def test_purga_global_exige_variable_de_entorno(db, monkeypatch):
    monkeypatch.delenv("MESSAGING_PRE_RELEASE_CLEANUP_ENABLED", raising=False)
    now = datetime.now(timezone.utc)
    _organization(db, "REAL11", is_test=False)
    db.commit()
    plan = build_cleanup_plan(db, cutoff=now, pre_release=True)

    with pytest.raises(ValueError, match="MESSAGING_PRE_RELEASE_CLEANUP_ENABLED"):
        execute_cleanup_plan(
            db, plan, confirmation_code=plan.confirmation_code,
            actor="Admin", reason="Prueba", storage=FakeStorage(),
        )


def test_purga_global_recalcula_tras_bloquear_escrituras(db, monkeypatch):
    monkeypatch.setenv("MESSAGING_PRE_RELEASE_CLEANUP_ENABLED", "true")
    now = datetime.now(timezone.utc)
    _, _, conversation = _organization(db, "REAL12", is_test=False)
    first = _message(db, conversation.id, "first", now - timedelta(days=3))
    db.commit()
    plan = build_cleanup_plan(db, cutoff=now, pre_release=True)
    second = _message(db, conversation.id, "second", now - timedelta(days=2))
    db.commit()

    with pytest.raises(ValueError, match="contenido cambio"):
        execute_cleanup_plan(
            db, plan, confirmation_code=plan.confirmation_code,
            actor="Admin", reason="Prueba", storage=FakeStorage(),
        )

    assert db.get(MessagingMessage, first.id) is not None
    assert db.get(MessagingMessage, second.id) is not None
    policy = db.get(MessagingCleanupPolicy, "pre_release")
    assert policy.maintenance_started_at is None


def test_cierre_prepublicacion_es_permanente_y_recuperacion_es_auditada(
    db, monkeypatch,
):
    monkeypatch.setenv("MESSAGING_PRE_RELEASE_CLEANUP_ENABLED", "true")
    audit_id = close_pre_release_cleanup(
        db, confirmation=CLOSE_CONFIRMATION,
        actor="Admin", reason="Aplicacion publicada en Play Store",
    )
    assert db.get(MessagingCleanupAudit, audit_id).scope == "close_pre_release"
    policy = db.get(MessagingCleanupPolicy, "pre_release")
    assert policy.publication_locked_at is not None

    plan = build_cleanup_plan(
        db, cutoff=datetime.now(timezone.utc), pre_release=True,
    )
    with pytest.raises(ValueError, match="cerrada definitivamente"):
        execute_cleanup_plan(
            db, plan, confirmation_code=plan.confirmation_code,
            actor="Admin", reason="No permitido", storage=FakeStorage(),
        )

    policy.maintenance_started_at = datetime.now(timezone.utc)
    policy.maintenance_actor = "Proceso interrumpido"
    db.commit()
    recovery_id = recover_cleanup_maintenance(
        db, confirmation=RECOVER_CONFIRMATION,
        actor="Admin", reason="Recuperacion tras interrupcion",
    )
    assert db.get(MessagingCleanupPolicy, "pre_release").maintenance_started_at is None
    assert db.get(MessagingCleanupAudit, recovery_id).scope == "recover_maintenance"


@pytest.mark.asyncio
async def test_middleware_bloquea_escrituras_durante_mantenimiento(db, monkeypatch):
    from backend.api import app as app_module

    policy = MessagingCleanupPolicy(
        id="pre_release",
        maintenance_started_at=datetime.now(timezone.utc),
        maintenance_actor="Admin",
    )
    db.add(policy)
    db.commit()
    monkeypatch.setattr(app_module, "SessionLocal", lambda: db)
    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/messaging/client/messages",
        "raw_path": b"/api/v1/messaging/client/messages",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
        "root_path": "",
    })
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response(status_code=204)

    response = await app_module.block_messaging_writes_during_cleanup(
        request, call_next,
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"
    assert called is False
