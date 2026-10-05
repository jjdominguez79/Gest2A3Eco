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
    PROVINCIAS,
    SubvencionesService,
    clasificar,
    coincide_cliente,
    municipios_ine,
    normalizar,
    territorio_organizacion,
)
from backend.api.subvenciones_boletines import BoeClient, _feed_entries


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


def test_boe_descompone_una_norma_en_ayudas_sin_publicar_suplementos():
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <documento><metadatos>
      <identificador>BOE-A-2026-20265</identificador>
      <departamento>Jefatura del Estado</departamento>
      <titulo>Real Decreto-ley 25/2026, de 29 de septiembre.</titulo>
      <fecha_publicacion>20260930</fecha_publicacion>
      <url_pdf>https://boe.es/prueba.pdf</url_pdf>
    </metadatos><texto>
      <p class='articulo'>Articulo 28. Ayuda extraordinaria para el gasoleo profesional.</p>
      <p class='parrafo'>Se prorroga para los meses de octubre, noviembre y diciembre de 2026 la ayuda para titulares de vehiculos.</p>
      <p class='articulo'>Articulo 29. Suplemento de credito para financiar las ayudas.</p>
      <p class='parrafo'>Se aprueba un suplemento de credito.</p>
      <p class='articulo'>Articulo 30. Ayuda directa para profesionales del transporte.</p>
      <p class='parrafo'>Seran beneficiarios los autonomos y sociedades. La solicitud se presentara entre el 1 de noviembre de 2026 y el 31 de diciembre de 2026.</p>
    </texto></documento>"""
    records = BoeClient()._parse_document(xml, {
        "identificador": "BOE-A-2026-20265",
        "titulo": "Real Decreto-ley 25/2026",
    })
    assert [item["codigo_bdns"] for item in records] == [
        "BOE-A-2026-20265-28", "BOE-A-2026-20265-30",
    ]
    assert records[0]["fecha_fin"] == date(2026, 12, 31)
    assert records[1]["fecha_inicio"] == date(2026, 11, 1)
    assert records[1]["naturaleza"] == "ayuda_directa"


def test_feed_oficial_acepta_rss_y_atom():
    rss = b"""<rss><channel><item><title>Extracto de convocatoria de ayudas</title>
      <link>https://boletin.example/1</link><pubDate>Mon, 05 Oct 2026 +0200</pubDate>
      <description>Plazo de presentacion</description></item></channel></rss>"""
    atom = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry>
      <title>Subvencion directa</title><link href='https://boletin.example/2'/>
      <updated>2026-10-05</updated></entry></feed>"""
    assert list(_feed_entries(rss))[0]["published"] == date(2026, 10, 5)
    assert list(_feed_entries(atom))[0]["link"] == "https://boletin.example/2"


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

    alicante = _call(
        ambito="LOCAL", ccaa_json=["ES52"], municipio_nombre="Alicante",
        municipio_slug="alicante",
    )
    official_municipality = SubvencionSuscripcion(
        client_id="client", nivel="MUNICIPAL", codigo="INE:03014",
        nombre="Alacant/Alicante (Alicante/Alacant)",
    )
    assert coincide_cliente(
        alicante, org, preferences, [official_municipality],
    ) is True


def test_catalogo_territorial_oficial_es_completo_y_nombra_islas():
    municipalities = municipios_ine()
    assert len(municipalities) == 8132
    assert any(
        item["codigo_ine"] == "39075" and item["nombre"] == "Santander"
        for item in municipalities
    )
    assert PROVINCIAS["ES531,ES532,ES533"] == "Illes Balears"
    assert PROVINCIAS["ES703,ES706,ES707,ES709"] == "Santa Cruz de Tenerife"


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
        hidden_org = MessagingOrganization(
            company_code="E00003", name="Empresa sin ayudas", active=True,
            client_subsidies_enabled=False,
        )
        db.add(hidden_org)
        db.flush()
        db.add(MessagingClient(
            organization_id=hidden_org.id, name="Cliente oculto",
            email="oculto@example.com", active=True,
        ))
        db.add(MessagingSession(
            client_id=client.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.add_all([
            _call(codigo_bdns="MAD", ccaa_json=["ES30"]),
            _call(codigo_bdns="VAL", ccaa_json=["ES52"]),
            _call(codigo_bdns="OCULTA", visible=False),
            _call(
                codigo_bdns="FINALIZADA", abierto=False,
                fecha_fin=date.today() - timedelta(days=1),
            ),
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

    internal_headers = {"X-API-Key": "internal-test-secret"}
    territories = api.get(
        "/api/v1/messaging/client/subvenciones/territorios",
        headers=headers,
    )
    assert territories.status_code == 200
    assert len(territories.json()) == len(subvenciones_api.CCAA) + len(PROVINCIAS)
    assert all(item["nivel"] != "MUNICIPAL" for item in territories.json())
    assert all(not item["nombre"].startswith("ES") for item in territories.json())
    municipality_results = api.get(
        "/api/v1/messaging/client/subvenciones/territorios",
        headers=headers,
        params={"q": "Santander"},
    )
    assert {
        (item["codigo"], item["nombre"]) for item in municipality_results.json()
        if item["nivel"] == "MUNICIPAL"
    } == {("INE:39075", "Santander (Cantabria)")}

    subscriptions = api.get(
        "/api/v1/messaging/client/subvenciones/internal/suscripciones",
        headers=internal_headers,
    )
    assert subscriptions.status_code == 200
    assert [item["codigo_empresa"] for item in subscriptions.json()] == ["E00002"]
    assert subscriptions.json()[0]["configurada"] is True
    dashboard = api.get(
        "/api/v1/messaging/client/subvenciones/internal/dashboard",
        headers=internal_headers,
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["totales"]["suscriptores"] == 1

    current_calls = api.get(
        "/api/v1/messaging/client/subvenciones/internal/convocatorias",
        headers=internal_headers,
    )
    assert current_calls.status_code == 200
    assert {item["codigo_bdns"] for item in current_calls.json()} == {"MAD", "VAL"}
    hidden_calls = api.get(
        "/api/v1/messaging/client/subvenciones/internal/convocatorias",
        headers=internal_headers,
        params={"visibilidad": "ocultas"},
    )
    assert [item["codigo_bdns"] for item in hidden_calls.json()] == ["OCULTA"]
    finished_calls = api.get(
        "/api/v1/messaging/client/subvenciones/internal/convocatorias",
        headers=internal_headers,
        params={"estado": "finalizadas", "visibilidad": "todas"},
    )
    assert [item["codigo_bdns"] for item in finished_calls.json()] == ["FINALIZADA"]
    restored = api.patch(
        "/api/v1/messaging/client/subvenciones/internal/convocatorias/OCULTA",
        headers=internal_headers,
        json={"visible": True},
    )
    assert restored.status_code == 200
    assert restored.json()["visible"] is True
    current_calls = api.get(
        "/api/v1/messaging/client/subvenciones/internal/convocatorias",
        headers=internal_headers,
    )
    assert "OCULTA" in {item["codigo_bdns"] for item in current_calls.json()}

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
        headers=internal_headers,
        json={"activa": False},
    )
    assert changed.status_code == 200
    assert changed.json()["activa"] is False
    dashboard = api.get(
        "/api/v1/messaging/client/subvenciones/internal/dashboard",
        headers=internal_headers,
    )
    assert dashboard.json()["totales"]["suscriptores"] == 0
    bulk = api.patch(
        "/api/v1/messaging/client/subvenciones/internal/organizaciones",
        headers=internal_headers,
        json={"codigos": ["E00002", "E00003"], "activa": True},
    )
    assert bulk.status_code == 200
    assert bulk.json() == {"ok": True, "seleccionadas": 2, "actualizadas": 2}
    with factory() as db:
        audit = db.scalar(select(ClientFeatureFlagAudit).where(
            ClientFeatureFlagAudit.flag_name == "client_subsidies_enabled",
            ClientFeatureFlagAudit.old_value.is_(True),
            ClientFeatureFlagAudit.new_value.is_(False),
        ))
        assert audit is not None
        assert audit.old_value is True and audit.new_value is False
