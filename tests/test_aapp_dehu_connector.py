from services.aapp.cert_store import CertMaterial
from services.aapp.base import OpcionesSync
from services.aapp.dehu_playwright import ConectorDEHU, _map_estado


def test_estados_dehu_no_convierten_historico_en_pendiente():
    assert _map_estado("ACCEPTED") == "ACEPTADA"
    assert _map_estado("REJECTED") == "RECHAZADA"
    assert _map_estado("EXPIRED") == "VENCIDA"
    assert _map_estado("REALIZADA") == "REALIZADA"


def test_registro_realizado_sin_estado_se_mantiene_como_realizado():
    connector = ConectorDEHU()
    rows = connector._map_registros(
        [{
            "identifier": "DEHU-1",
            "concept": "Notificacion historica",
            "emitterEntity": "Agencia Estatal de Administracion Tributaria",
            "emitterSourceEntity": "AEAT",
            "nifTitular": "B12345678",
            "_endpoint": "/api/v1/realized_notifications",
        }],
        CertMaterial(
            cert_id="cert-1",
            nombre="Cliente Uno",
            nif_titular="B12345678",
            ruta_archivo="cliente.pfx",
            password="",
        ),
        "B12345678",
    )

    assert rows[0].estado == "REALIZADA"
    assert rows[0].descripcion == "Agencia Estatal de Administracion Tributaria"
    assert rows[0].metadatos["emitterEntity"].startswith("Agencia Estatal")


def test_api_dehu_empieza_en_pagina_uno_no_filtra_y_lee_comunicaciones():
    calls = []

    class Response:
        ok = True
        status = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class Request:
        def get(self, url, **_kwargs):
            calls.append(url)
            if "/communications?" in url:
                return Response({
                    "items": [{"identifier": "COM-1", "nifTitular": "B22222222"}],
                    "total": 1,
                    "limit": 100,
                    "page": 1,
                })
            return Response({"items": [], "total": 0, "limit": 100, "page": 1})

    page = type("Page", (), {"context": type("Context", (), {"request": Request()})()})()
    rows = ConectorDEHU()._fetch_api(
        page,
        "https://dehu.redsara.es",
        OpcionesSync(nif_filtro="B11111111"),
    )

    assert rows[0]["_category"] == "COMUNICACION"
    assert all("page=1" in url for url in calls)
    assert all("titularNif" not in url for url in calls)
    assert any("/realized-notifications?" in url for url in calls)
