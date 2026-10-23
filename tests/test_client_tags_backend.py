import os

from fastapi import BackgroundTasks
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault(
    "BACKEND_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from backend.api.client_profile_api import sync_client_tags_snapshot
from backend.api.database import Base
from backend.api.messaging_api import CampaignIn, create_campaign
from backend.api.messaging_models import (
    MessagingCampaignRecipient,
    MessagingClient,
    MessagingClientTag,
    MessagingOrganization,
    MessagingOrganizationTag,
    MessagingStaff,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_snapshot_sustituye_catalogo_y_asignaciones_de_etiquetas():
    db = _session()
    organization = MessagingOrganization(company_code="E00001", name="Cliente")
    db.add(organization)
    db.commit()

    result = sync_client_tags_snapshot(
        payload={
            "tags": [{
                "id": "tag-debt", "name": "Cuota pendiente",
                "color": "#D32F2F", "active": True,
            }],
            "assignments": [{
                "company_code": "E00001", "tag_ids": ["tag-debt"],
            }],
            "full_snapshot": True,
        },
        db=db,
        _auth="test",
    )

    assert result["assignments"] == 1
    assert db.get(MessagingClientTag, "tag-debt").name == "Cuota pendiente"
    assert db.scalar(select(func.count(MessagingOrganizationTag.tag_id))) == 1

    sync_client_tags_snapshot(
        payload={
            "tags": [],
            "assignments": [{"company_code": "E00001", "tag_ids": []}],
            "full_snapshot": True,
        },
        db=db,
        _auth="test",
    )
    assert db.get(MessagingClientTag, "tag-debt").active is False
    assert db.scalar(select(func.count(MessagingOrganizationTag.tag_id))) == 0
    db.close()


def test_campana_por_etiqueta_incluye_todos_los_clientes_de_la_empresa():
    db = _session()
    organization = MessagingOrganization(company_code="E00001", name="Cliente")
    admin = MessagingStaff(
        external_id="admin", name="Admin", email="admin@example.test",
        role="admin", active=True,
    )
    db.add_all([organization, admin])
    db.flush()
    clients = [
        MessagingClient(
            organization_id=organization.id, name="Cliente uno",
            email="uno@example.test", active=True,
        ),
        MessagingClient(
            organization_id=organization.id, name="Cliente dos",
            email="dos@example.test", active=True,
        ),
    ]
    db.add_all(clients + [
        MessagingClientTag(
            id="tag-fiscal", name="Fiscal", color="#1976D2", active=True,
        ),
    ])
    db.flush()
    db.add(MessagingOrganizationTag(
        organization_id=organization.id, tag_id="tag-fiscal",
    ))
    db.commit()

    response = create_campaign(
        payload=CampaignIn(
            name="Aviso fiscal", body="Mensaje", tag_ids=["tag-fiscal"],
        ),
        background=BackgroundTasks(),
        admin=admin,
        db=db,
    )

    assert response["recipient_count"] == 2
    assert db.scalar(select(func.count(MessagingCampaignRecipient.id))) == 2
    db.close()
