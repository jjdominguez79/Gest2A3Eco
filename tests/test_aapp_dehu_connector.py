import json
from urllib.parse import parse_qs, urlsplit

import pytest

from services.aapp.cert_store import CertMaterial
from services.aapp.base import OpcionesSync
from services.aapp.dehu_playwright import (
    ConectorDEHU,
    ORIGENES_CLAVE,
    _map_estado,
    _token_sesion,
    _url_sin_consulta,
)


def test_origen_real_del_idp_clave_recibe_el_certificado():
    assert "https://pasarela-ident.clave.gob.es" in ORIGENES_CLAVE


def test_estados_dehu_no_convierten_historico_en_pendiente():
    assert _map_estado("ACCEPTED") == "ACEPTADA"
    assert _map_estado("REJECTED") == "RECHAZADA"
    assert _map_estado("EXPIRED") == "VENCIDA"
    assert _map_estado("REALIZADA") == "REALIZADA"
    assert _map_estado("UNREAD") == "PENDIENTE"
    assert _map_estado("NOT_READ") == "PENDIENTE"
    assert _map_estado("READ") == "LEIDA"


def test_solo_mapea_pendientes_y_no_leidas():
    material = CertMaterial("cert-1", "Cliente", "B12345678", "cliente.pfx", "")
    rows = ConectorDEHU()._map_registros([
        {"identifier": "1", "state": "READ"},
        {"identifier": "2", "state": "ACCEPTED"},
        {"identifier": "3", "state": "LEIDA"},
        {"identifier": "4", "state": "UNREAD"},
        {"identifier": "5", "state": "NOT_READ"},
        {"identifier": "6", "_endpoint": "/api/v1/realized_notifications"},
    ], material)
    assert [row.referencia for row in rows] == ["4", "5"]


def test_bandeja_vacia_no_reutiliza_historico_capturado(monkeypatch):
    connector = ConectorDEHU()
    for nombre in ("_diagnostico", "_elegir_certificado_clave", "_esperar_login"):
        monkeypatch.setattr(connector, nombre, lambda *_args, **_kwargs: None)
    monkeypatch.setattr(connector, "_click_acceder", lambda *_args: False)
    monkeypatch.setattr(connector, "_fetch_api", lambda *_args: [])
    monkeypatch.setattr(connector, "_desde_capturas", lambda *_args: pytest.fail("No debe usar capturas"))
    page = type("Page", (), {"goto": lambda *_args, **_kwargs: None})()
    material = CertMaterial("cert-1", "Cliente", "B12345678", "cliente.pfx", "")
    assert connector._flujo(page, "https://dehu.redsara.es", {}, material, OpcionesSync(), []) == []


def test_registro_realizado_sin_estado_se_excluye():
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

    assert rows == []


def test_api_dehu_empieza_en_pagina_uno_no_filtra_y_lee_comunicaciones():
    calls = []
    request_headers = []

    class Response:
        ok = True
        status = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class Request:
        def get(self, url, **kwargs):
            calls.append(url)
            request_headers.append(kwargs.get("headers") or {})
            if "/communications?" in url:
                return Response({
                    "items": [{"identifier": "COM-1", "nifTitular": "B22222222"}],
                    "total": 1,
                    "limit": 50,
                    "page": 1,
                })
            return Response({"items": [], "total": 0, "limit": 50, "page": 1})

    page = type("Page", (), {"context": type("Context", (), {"request": Request()})()})()
    rows = ConectorDEHU()._fetch_api(
        page,
        "https://dehu.redsara.es",
        OpcionesSync(nif_filtro="B11111111"),
        [{
            "url": "https://dehu.redsara.es/api/v1/user/dGVzdA==",
            "body": {"token": "jwt-efimero"},
        }],
    )

    assert rows[0]["_category"] == "COMUNICACION"
    assert all("page=1" in url for url in calls)
    assert all("titularNif=" in url for url in calls)
    assert all("B11111111" not in url for url in calls)
    assert not any("/realized_notifications?" in url for url in calls)
    assert all(headers["Authorization"] == "Bearer jwt-efimero" for headers in request_headers)
    communications_url = next(url for url in calls if "/communications?" in url)
    for url in (communications_url,):
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        assert query["limit"] == ["50"]
        assert query["page"] == ["1"]
        assert query["titularNif"] == [""]
    communications_query = parse_qs(
        urlsplit(communications_url).query,
        keep_blank_values=True,
    )
    assert communications_query["availabilityDate[left_date]"] == [""]
    assert communications_query["availabilityDate[right_date]"] == [""]


def test_api_dehu_no_acepta_resultado_parcial_si_falla_una_pagina():
    class Response:
        def __init__(self, ok, data=None, status=200):
            self.ok = ok
            self.status = status
            self._data = data

        def json(self):
            return self._data

    class Request:
        def get(self, url, **_kwargs):
            if "/notifications?" in url and "page=1" in url:
                return Response(True, {
                    "items": [{"identifier": "N-1"}],
                    "total": 51,
                    "limit": 50,
                    "page": 1,
                })
            if "/notifications?" in url:
                return Response(False, status=503)
            return Response(True, {"items": [], "total": 0, "limit": 50, "page": 1})

    page = type("Page", (), {"context": type("Context", (), {"request": Request()})()})()
    capturas = [{
        "url": "https://dehu.redsara.es/api/v1/user/dGVzdA==",
        "body": {"token": "jwt"},
    }]

    with pytest.raises(RuntimeError, match="/api/v1/notifications"):
        ConectorDEHU()._fetch_api(
            page,
            "https://dehu.redsara.es",
            OpcionesSync(),
            capturas,
        )


def test_token_sesion_solo_acepta_respuesta_autenticada_de_usuario():
    captures = [
        {"url": "https://dehu.redsara.es/api/config/user-gate", "body": {"token": "no"}},
        {"url": "https://dehu.redsara.es/api/v1/user/dGVzdA==", "body": {"token": "jwt"}},
    ]

    assert _token_sesion(captures) == "jwt"


def test_diagnostico_no_persiste_token_contenido_ni_identificador(tmp_path):
    class Page:
        def screenshot(self, **_kwargs):
            return None

        def content(self):
            return "<html>diagnostico</html>"

    identificador = "QUJDREVGR0hJSktMTU5PUA=="
    capturas = [{
        "url": f"https://dehu.redsara.es/api/v1/user/{identificador}?code=secreto",
        "status": 200,
        "resource_type": "xhr",
        "content_type": "application/json",
        "body": {
            "token": "jwt-muy-secreto",
            "refreshToken": "refresh-muy-secreto",
            "items": [{"nifTitular": "B12345678", "concept": "Privado"}],
            "total": 1,
        },
    }]

    ConectorDEHU()._diagnostico(
        Page(),
        OpcionesSync(modo_diagnostico=True, carpeta_diagnostico=str(tmp_path)),
        "seguro",
        capturas,
    )

    ruta = next(tmp_path.glob("dehu_api_seguro_*.json"))
    texto = ruta.read_text(encoding="utf-8")
    data = json.loads(texto)
    assert "jwt-muy-secreto" not in texto
    assert "refresh-muy-secreto" not in texto
    assert "B12345678" not in texto
    assert "Privado" not in texto
    assert identificador not in texto
    assert data[0]["url"].endswith("/api/v1/user/[identificador-omitido]")
    assert data[0]["body_summary"]["items_count"] == 1


def test_url_de_traza_oculta_consulta_e_identificador_de_usuario():
    segura = _url_sin_consulta(
        "https://dehu.redsara.es/api/v1/user/QUJDRA==?code=secreto"
    )

    assert segura == (
        "https://dehu.redsara.es/api/v1/user/[identificador-omitido]"
    )


def test_fallo_de_red_traza_motivo_sin_consulta_ni_identificador():
    callbacks = {}
    trazas = []

    class Page:
        def on(self, evento, callback):
            callbacks[evento] = callback

    ConectorDEHU()._instalar_captura_red(
        Page(),
        [],
        OpcionesSync(log=trazas.append),
    )
    request = type("Request", (), {
        "url": "https://dehu.redsara.es/api/v1/user/QUJDRA==?token=secreto",
        "failure": "net::ERR_FAILED",
    })()

    callbacks["requestfailed"](request)

    assert trazas == [
        "[DEHU][requestfailed] "
        "https://dehu.redsara.es/api/v1/user/[identificador-omitido]: "
        "net::ERR_FAILED"
    ]


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


def test_selector_certificado_espera_el_dom_tardio_de_clave():
    connector = ConectorDEHU()
    clicked = []

    class Locator:
        @property
        def first(self):
            return self

        def count(self):
            # La implementacion antigua descartaba el selector por esta
            # lectura instantanea antes de que terminase la navegacion SAML.
            return 0

        def click(self, **_kwargs):
            clicked.append(True)

    class Page:
        def locator(self, selector):
            assert selector == "button[onclick*=\"'AFIRMA'\"]"
            return Locator()

        def wait_for_load_state(self, *_args, **_kwargs):
            return None

    traces = []
    connector._elegir_certificado_clave(
        Page(),
        OpcionesSync(log=traces.append),
    )

    assert clicked == [True]
    assert "AFIRMA" in traces[0]
