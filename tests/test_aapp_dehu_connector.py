from services.aapp.cert_store import CertMaterial
from services.aapp.base import OpcionesSync
from services.aapp.dehu_playwright import ConectorDEHU, ORIGENES_CLAVE, _map_estado


def test_origen_real_del_idp_clave_recibe_el_certificado():
    assert "https://pasarela-ident.clave.gob.es" in ORIGENES_CLAVE


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


def test_dehu_inicia_login_directo_si_el_frontal_no_renderiza_acceso(monkeypatch):
    connector = ConectorDEHU()
    visited = []

    class Page:
        def goto(self, url, **_kwargs):
            visited.append(url)

    monkeypatch.setattr(connector, "_diagnostico", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(connector, "_click_acceder", lambda *_args: False)
    monkeypatch.setattr(connector, "_elegir_certificado_clave", lambda *_args: None)
    monkeypatch.setattr(connector, "_esperar_login", lambda *_args: True)
    monkeypatch.setattr(connector, "_fetch_api", lambda *_args: [{"identifier": "REF-1"}])

    result = connector._flujo(
        Page(),
        "https://dehu.redsara.es",
        {},
        CertMaterial(
            cert_id="cert-1",
            nombre="Cliente Uno",
            nif_titular="B12345678",
            ruta_archivo="cliente.pfx",
            password="",
        ),
        OpcionesSync(),
        [],
    )

    assert visited == [
        "https://dehu.redsara.es/",
        "https://dehu.redsara.es/api/login/login-clave-sso",
    ]
    assert result[0].referencia == "REF-1"


def test_dehu_espera_sesion_aunque_no_este_en_modo_aprendizaje(monkeypatch):
    connector = ConectorDEHU()
    calls = []

    class Page:
        def goto(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(connector, "_diagnostico", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(connector, "_click_acceder", lambda *_args: False)
    monkeypatch.setattr(connector, "_elegir_certificado_clave", lambda *_args: None)
    monkeypatch.setattr(
        connector,
        "_esperar_login",
        lambda *_args: calls.append("authenticated") or True,
    )
    monkeypatch.setattr(connector, "_fetch_api", lambda *_args: [])
    monkeypatch.setattr(connector, "_desde_capturas", lambda *_args: [])
    monkeypatch.setattr(connector, "_abrir_notificaciones", lambda *_args: False)
    monkeypatch.setattr(connector, "_extraer_tabla", lambda *_args: [])

    connector._flujo(
        Page(),
        "https://dehu.redsara.es",
        {},
        CertMaterial(
            cert_id="cert-1",
            nombre="Cliente Uno",
            nif_titular="B12345678",
            ruta_archivo="cliente.pfx",
            password="",
        ),
        OpcionesSync(pausa_login_segundos=0),
        [],
    )

    assert calls == ["authenticated"]
