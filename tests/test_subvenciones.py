"""Pruebas del catálogo BDNS, alcance territorial y avisos idempotentes."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault(
    "DGT_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import client_models, messaging_models  # noqa: F401
from backend.api.client_models import ClientFeatureFlagAudit
from backend.api.database import Base
from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token
from backend.api import subvenciones_api
from backend.api.subvenciones_models import (
    SubvencionConfiguracion,
    SubvencionConvocatoria,
    SubvencionEntrega,
    SubvencionEjecucion,
    SubvencionPreferencia,
    SubvencionSuscripcion,
)
from backend.api.subvenciones_service import (
    BdnsClient,
    SubvencionesService,
    clasificar,
    coincide_cliente,
    normalizar,
    territorio_organizacion,
)


def _call(**changes) -> SubvencionConvocatoria:
    values = {
        "codigo_bdns": "123456",
        "titulo": "Ayuda de prueba",
        "ambito": "AUTONOMICA",
        "alcance_nacional": False,
        "ccaa_json": ["ES30"],
        "provincias_json": [],
        "municipio_nombre": "",
        "municipio_slug": "",
        "es_provincial": False,
        "fecha_recepcion": date.today(),
        "fecha_fin": date.today() + timedelta(days=20),
        "visible": True,
    }
    values.update(changes)
    return SubvencionConvocatoria(**values)


def test_clasifica_ambitos_bdns():
    autonomica = clasificar({
        "organo": {"nivel1": "AUTONOMICO", "nivel2": "Comunidad de Madrid"},
        "regiones": [{"descripcion": "ES30 Comunidad de Madrid"}],
    })
    assert autonomica["ambito"] == "AUTONOMICA"
    assert autonomica["ccaa_json"] == ["ES30"]

    estatal = clasificar({
        "organo": {"nivel1": "ESTADO"},
        "regiones": [{"descripcion": "ES Espana"}],
    })
    assert estatal["alcance_nacional"] is True


def test_normaliza_convocatoria_y_conserva_fuentes():
    result = normalizar({
        "codigoBDNS": 789,
        "descripcion": "Modernizacion del comercio",
        "organo": {"nivel1": "ESTADO", "nivel2": "Ministerio"},
        "fechaRecepcion": "04/10/2026",
        "presupuestoTotal": "120000.50",
        "tiposBeneficiarios": [{"descripcion": "Pymes"}],
        "documentos": [{"id": 42, "descripcion": "Convocatoria"}],
    })
    assert result["codigo_bdns"] == "789"
    assert result["fecha_recepcion"] == date(2026, 10, 4)
    assert result["presupuesto"] == 120000.5
    assert result["beneficiarios_json"] == ["Pymes"]
    assert any(link["tipo"] == "documento" for link in result["enlaces_json"])
    assert len(result["hash_fuente"]) == 64


def test_bdns_pagina_sin_filtro_inestable_y_corta_por_fecha():
    class Response:
        content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {"numeroConvocatoria": "2", "fechaRecepcion": "2026-10-04"},
                    {"numeroConvocatoria": "1", "fechaRecepcion": "2026-09-01"},
                ],
                "last": False,
            }

    class Http:
        def __init__(self):
            self.calls = []

        def get(self, url, params):
            self.calls.append((url, params))
            return Response()

    http = Http()
    client = BdnsClient(http)
    client.pause = 0
    rows = client.listar_desde(date(2026, 10, 1))
    assert [row["numeroConvocatoria"] for row in rows] == ["2"]
    assert len(http.calls) == 1
    assert "fechaDesde" not in http.calls[0][1]


def test_coincidencia_por_domicilio_y_suscripciones_adicionales():
    org = MessagingOrganization(
        company_code="E00001", name="Empresa", postal_code="28001", city="Madrid",
    )
    territory = territorio_organizacion(org)
    assert territory["ccaa"] == "ES30"
    assert territory["provincia"] == "ES300"

    assert coincide_cliente(_call(), org, None, []) is True

    preferences = SubvencionPreferencia(
        incluir_nacionales=False, usar_territorio_empresa=False,
    )
    valencia = SubvencionSuscripcion(
        client_id="client", nivel="AUTONOMICA", codigo="ES52", nombre="Valencia",
    )
    call = _call(ccaa_json=["ES52"])
    assert coincide_cliente(call, org, preferences, [valencia]) is True
    assert coincide_cliente(call, org, preferences, []) is False

    provincial = _call(
        ambito="LOCAL", es_provincial=True, ccaa_json=["ES30"],
        provincias_json=[],
    )
    madrid = SubvencionSuscripcion(
        client_id="client", nivel="PROVINCIAL", codigo="ES300", nombre="Madrid",
    )
    assert coincide_cliente(provincial, org, preferences, [madrid]) is True


def test_aviso_push_es_idempotente(monkeypatch):
    monkeypatch.setenv("CLIENT_SUBSIDIES_ENABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sent = []

    def fake_send(token, payload, *, platform):
        sent.append((token, payload, platform))
        return SimpleNamespace(success=True, permanent_failure=False)

    monkeypatch.setattr(
        "backend.api.subvenciones_service.messaging_firebase.send_fcm", fake_send,
    )
    with factory() as db:
        org = MessagingOrganization(
            company_code="E00001", name="Empresa", active=True,
            postal_code="28001", city="Madrid", client_subsidies_enabled=True,
        )
        db.add(org)
        db.flush()
        client = MessagingClient(
            organization_id=org.id, name="Cliente", email="cliente@example.com",
            active=True,
        )
        db.add(client)
        db.flush()
        db.add_all([
            SubvencionPreferencia(
                client_id=client.id, notificaciones_activas=True,
                incluir_nacionales=True, usar_territorio_empresa=True,
            ),
            MessagingAppDevice(
                user_type="client", user_id=client.id, platform="android",
                push_token="token-de-prueba-suficientemente-largo", active=True,
            ),
            SubvencionConfiguracion(id="global", avisos_activos=True),
        ])
        call = _call(alcance_nacional=True)
        db.add(call)
        run = SubvencionEjecucion()
        db.add(run)
        db.commit()

        service = SubvencionesService(db, bdns=SimpleNamespace())
        service.notificar(run, date.today())
        service.notificar(run, date.today())

        assert len(sent) == 1
        assert sent[0][1]["target_type"] == "subvencion"
        assert sent[0][1]["subvencion_id"] == "123456"
        assert db.scalar(select(func.count()).select_from(SubvencionEntrega)) == 1
        delivery = db.scalar(select(SubvencionEntrega))
        assert delivery.estado == "enviado"
        assert delivery.intentos == 1


def test_api_cliente_guarda_territorios_y_filtra_para_mi(monkeypatch):
    monkeypatch.setenv("CLIENT_SUBSIDIES_ENABLED", "true")
    monkeypatch.setenv("BACKEND_INTERNAL_API_KEY", "internal-test-secret")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    token = "sesion-cliente-de-prueba"
    with factory() as db:
        org = MessagingOrganization(
            company_code="E00002", name="Empresa", active=True,
            postal_code="28001", city="Madrid", client_subsidies_enabled=True,
        )
        db.add(org)
        db.flush()
        client = MessagingClient(
            organization_id=org.id, name="Cliente", email="api@example.com", active=True,
        )
        db.add(client)
        db.flush()
        db.add(MessagingSession(
            client_id=client.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.add_all([
            _call(codigo_bdns="MAD", ccaa_json=["ES30"]),
            _call(codigo_bdns="VAL", ccaa_json=["ES52"]),
        ])
        db.commit()

    app = FastAPI()
    app.include_router(subvenciones_api.router)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[subvenciones_api._db] = override_db
    api = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    response = api.get(
        "/api/v1/messaging/client/subvenciones", headers=headers,
        params={"para_mi": True},
    )
    assert response.status_code == 200
    assert [item["codigo_bdns"] for item in response.json()["elementos"]] == ["MAD"]

    saved = api.put(
        "/api/v1/messaging/client/subvenciones/preferencias",
        headers=headers,
        json={
            "notificaciones_activas": True,
            "incluir_nacionales": False,
            "usar_territorio_empresa": False,
            "suscripciones": [
                {"nivel": "AUTONOMICA", "codigo": "ES52", "nombre": "Valencia"},
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["suscripciones"][0]["codigo"] == "ES52"

    response = api.get(
        "/api/v1/messaging/client/subvenciones", headers=headers,
        params={"para_mi": True},
    )
    assert [item["codigo_bdns"] for item in response.json()["elementos"]] == ["VAL"]
    detail = api.get(
        "/api/v1/messaging/client/subvenciones/VAL", headers=headers,
    )
    assert detail.status_code == 200
    assert "texto oficial" in detail.json()["aviso_legal"]

    changed = api.patch(
        "/api/v1/messaging/client/subvenciones/internal/organizaciones/E00002",
        headers={"X-API-Key": "internal-test-secret"},
        json={"activa": False},
    )
    assert changed.status_code == 200
    assert changed.json()["activa"] is False
    with factory() as db:
        audit = db.scalar(select(ClientFeatureFlagAudit).where(
            ClientFeatureFlagAudit.flag_name == "client_subsidies_enabled",
        ))
        assert audit is not None
        assert audit.old_value is True and audit.new_value is False
