"""Integridad de la fusion real de canales en PostgreSQL.

Uso: TEST_POSTGRES_URL=postgresql+psycopg://... pytest -q \
     tests/test_general_channel_migration_pg.py
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker


TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definida; migracion PostgreSQL omitida",
)


@pytest.fixture()
def migrated_factory(monkeypatch):
    monkeypatch.setenv("BACKEND_DATABASE_URL", TEST_POSTGRES_URL)
    from backend.api.database import Base
    from backend.api import messaging_models as _messaging_models  # noqa: F401

    schema = f"test_general_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_POSTGRES_URL)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        TEST_POSTGRES_URL,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    Base.metadata.create_all(engine)
    try:
        yield engine, sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def _run_migration(engine) -> None:
    sql = (Path(__file__).parents[1] / "backend" / "migrations" /
           "030_general_client_channel.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_fusion_idempotente_conserva_trazabilidad_y_privado(migrated_factory):
    from backend.api.messaging_api import _unread_count
    from backend.api.messaging_models import (
        MessagingAppDevice,
        MessagingAttachment,
        MessagingCampaign,
        MessagingClient,
        MessagingConversation,
        MessagingConversationAlias,
        MessagingDeletionAudit,
        MessagingEvent,
        MessagingMessage,
        MessagingMessageVersion,
        MessagingOrganization,
        MessagingRead,
        MessagingReceipt,
        MessagingStaff,
    )
    from backend.api.messaging_security import utcnow

    engine, factory = migrated_factory
    with factory() as db:
        organization = MessagingOrganization(company_code="E90001", name="Migracion")
        staff = MessagingStaff(
            external_id="staff-migration", name="Empleado", email="staff@example.test",
            role="empleado", active=True,
        )
        db.add_all([organization, staff])
        db.flush()
        client = MessagingClient(
            organization_id=organization.id, name="Cliente",
            email=f"migration-{uuid.uuid4().hex}@example.test", active=True,
        )
        fiscal = MessagingConversation(
            id=str(uuid.uuid4()), organization_id=organization.id, kind="fiscal",
            state="en_curso", assigned_staff_external_id=staff.external_id,
            created_at=utcnow() - timedelta(days=3),
            updated_at=utcnow() - timedelta(days=1),
        )
        laboral = MessagingConversation(
            id=str(uuid.uuid4()), organization_id=organization.id, kind="laboral",
            state="resuelta", assigned_staff_external_id="anterior",
            created_at=utcnow() - timedelta(days=4), updated_at=utcnow(),
        )
        private = MessagingConversation(
            id=str(uuid.uuid4()), organization_id=organization.id, kind="private",
        )
        db.add_all([client, fiscal, laboral, private])
        db.flush()
        historic_alias_id = str(uuid.uuid4())
        db.add(MessagingConversationAlias(
            old_conversation_id=historic_alias_id,
            conversation_id=laboral.id,
        ))
        first = MessagingMessage(
            id=str(uuid.uuid4()), conversation_id=fiscal.id,
            author_type="client", author_id=client.id, author_name="Cliente",
            body="Fiscal", idempotency_key="duplicada",
            created_at=utcnow() - timedelta(hours=2),
        )
        second = MessagingMessage(
            id=str(uuid.uuid4()), conversation_id=laboral.id,
            author_type="staff", author_id=staff.external_id, author_name="Empleado",
            body="Laboral", idempotency_key="duplicada", reply_to_message_id=first.id,
            deleted_at=utcnow() - timedelta(minutes=30),
            created_at=utcnow() - timedelta(hours=1),
        )
        private_message = MessagingMessage(
            id=str(uuid.uuid4()), conversation_id=private.id,
            author_type="client", author_id=client.id, author_name="Cliente",
            body="Privado", idempotency_key="private",
        )
        db.add_all([first, second, private_message])
        db.flush()
        attachment = MessagingAttachment(
            id=str(uuid.uuid4()), message_id=second.id, name="prueba.pdf",
            size=4, sha256="a" * 64, storage_key=f"test/{uuid.uuid4()}",
            direction="outgoing",
        )
        db.add_all([
            attachment,
            MessagingMessageVersion(
                message_id=second.id, body="Laboral anterior",
                version_created_at=second.created_at, replaced_at=utcnow(),
                edited_by=staff.external_id, edited_by_type="staff",
            ),
            MessagingRead(
                conversation_id=fiscal.id, actor_type="client", actor_id=client.id,
                last_message_id=first.id, read_at=utcnow() - timedelta(minutes=90),
            ),
            # Solo fiscal esta confirmado: no es seguro trasladar este recibo.
            MessagingReceipt(
                target_type="conversation", target_id=fiscal.id,
                actor_type="client", actor_id=client.id,
                read_through_at=first.created_at,
            ),
            MessagingEvent(
                organization_id=organization.id, conversation_id=laboral.id,
                event_type="message_created",
            ),
            MessagingDeletionAudit(
                message_id=second.id, conversation_id=laboral.id,
                actor_id=staff.external_id, action="soft_delete",
            ),
            MessagingAppDevice(
                user_type="staff", user_id=staff.external_id, platform="web",
                push_token="migration-" + uuid.uuid4().hex,
                active_conversation_id=laboral.id,
                active_target_type="conversation", active_target_id=laboral.id,
            ),
            MessagingCampaign(
                name="Pendiente", body="Aviso", channel="fiscal",
                created_by=staff.external_id, status="pending",
            ),
        ])
        db.commit()
        ids = {
            "fiscal": fiscal.id, "laboral": laboral.id, "private": private.id,
            "messages": {first.id, second.id}, "attachment": attachment.id,
            "client": client.id, "staff": staff.external_id,
            "historic_alias": historic_alias_id,
        }

    _run_migration(engine)

    with factory() as db:
        conversations = db.scalars(select(MessagingConversation)).all()
        assert {row.kind for row in conversations} == {"general", "private"}
        general = next(row for row in conversations if row.kind == "general")
        assert general.id == ids["fiscal"]
        assert general.state == "resuelta"
        assert general.assigned_staff_external_id == "anterior"
        assert db.get(MessagingConversation, ids["private"]).kind == "private"
        assert db.get(MessagingConversationAlias, ids["laboral"]).conversation_id == general.id
        assert db.get(
            MessagingConversationAlias, ids["historic_alias"],
        ).conversation_id == general.id
        messages = db.scalars(select(MessagingMessage).where(
            MessagingMessage.conversation_id == general.id,
        )).all()
        assert {message.id for message in messages} == ids["messages"]
        assert len({message.idempotency_key for message in messages}) == 2
        assert db.get(MessagingAttachment, ids["attachment"]).message_id in ids["messages"]
        assert db.scalar(select(func.count(MessagingMessageVersion.id))) == 1
        assert db.scalar(select(func.count(MessagingReceipt.target_id)).where(
            MessagingReceipt.target_type == "conversation",
            MessagingReceipt.target_id == general.id,
        )) == 0
        reading = db.scalar(select(MessagingRead).where(
            MessagingRead.conversation_id == general.id,
            MessagingRead.actor_type == "client",
            MessagingRead.actor_id == ids["client"],
        ))
        assert reading.last_message_id == second.id
        first_migration_read_at = reading.read_at
        assert db.scalar(select(MessagingEvent.conversation_id)) == general.id
        assert db.scalar(select(MessagingDeletionAudit.conversation_id)) == general.id
        device = db.scalar(select(MessagingAppDevice))
        assert device.active_conversation_id == general.id
        assert device.active_target_id == general.id
        assert db.scalar(select(MessagingCampaign.channel)) == "general"
        new_message = MessagingMessage(
            conversation_id=general.id, author_type="staff", author_id=ids["staff"],
            author_name="Empleado", body="Posterior", idempotency_key="posterior",
        )
        db.add(new_message)
        db.commit()

    _run_migration(engine)

    with factory() as db:
        general = db.scalar(select(MessagingConversation).where(
            MessagingConversation.kind == "general",
        ))
        assert db.scalar(select(func.count(MessagingConversation.id))) == 2
        assert db.scalar(select(func.count(MessagingMessage.id)).where(
            MessagingMessage.conversation_id == general.id,
        )) == 3
        reading = db.scalar(select(MessagingRead).where(
            MessagingRead.conversation_id == general.id,
            MessagingRead.actor_type == "client",
            MessagingRead.actor_id == ids["client"],
        ))
        assert reading.read_at == first_migration_read_at
        assert _unread_count(db, general, "client", ids["client"]) == 1
