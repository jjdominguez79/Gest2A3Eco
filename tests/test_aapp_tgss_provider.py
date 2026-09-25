from urllib.parse import urlsplit

import pytest

from services.aapp.certificados import (
    SS_CERT_RADIO,
    SS_URL_INFORMES,
    SS_URL_VIDA_LABORAL,
    obtener_proveedor,
)
from services.aapp.base import OpcionesSync


@pytest.mark.parametrize("tipo", sorted(SS_CERT_RADIO))
def test_tgss_ofrece_certificado_al_origen_exacto_de_ipce(tipo):
    proveedor = obtener_proveedor(tipo)
    url_login = urlsplit("https://ipce.seg-social.es/IPCE/Login")
    origen_login = f"{url_login.scheme}://{url_login.netloc}"

    origenes = proveedor._origenes()

    assert origen_login in origenes
    assert len(origenes) == len(set(origenes))
    assert proveedor.urls[tipo] == SS_URL_INFORMES
    assert {
        "https://sede.seg-social.gob.es",
        "https://sp.seg-social.es",
        "https://sede.seg-social.es",
        "https://w6.seg-social.es",
        "https://w2.seg-social.es",
        "https://idp.seg-social.es",
        "https://idp.seg-social.gob.es",
        "https://portal.seg-social.gob.es",
    }.issubset(origenes)


def test_aeat_no_ofrece_certificado_al_dominio_de_tgss():
    proveedor = obtener_proveedor("AEAT_CORRIENTE")

    assert "https://ipce.seg-social.es" not in proveedor._origenes()


def test_vida_laboral_usa_la_portada_oficial_de_importass():
    proveedor = obtener_proveedor("TGSS_VIDA_LABORAL")

    assert proveedor is not None
    assert proveedor.urls["TGSS_VIDA_LABORAL"] == SS_URL_VIDA_LABORAL
    assert "https://portal.seg-social.gob.es" in proveedor._origenes()


class _ControlAccesoVidaLaboral:
    def __init__(self, pagina, selector, existe):
        self.pagina = pagina
        self.selector = selector
        self.existe = existe

    @property
    def first(self):
        return self

    def count(self):
        return int(self.existe)

    def is_visible(self):
        return self.existe

    def click(self, timeout=None):
        self.pagina.clicks.append(self.selector)

    def check(self, timeout=None):
        self.pagina.checks.append(self.selector)


class _PaginaAccesoVidaLaboral:
    def __init__(self):
        self.clicks = []
        self.checks = []

    def locator(self, selector):
        existe = any(fragmento in selector for fragmento in (
            "#boton-lanzamiento-operacion",
            "#btn-atria-continuar",
            "opcion-atria",
        ))
        return _ControlAccesoVidaLaboral(self, selector, existe)

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


def test_vida_laboral_inicia_identificacion_como_interesado(monkeypatch):
    proveedor = obtener_proveedor("TGSS_VIDA_LABORAL")
    pagina = _PaginaAccesoVidaLaboral()
    login = []
    monkeypatch.setattr(
        proveedor,
        "_ss_login_idp",
        lambda page, _opciones: login.append(page),
    )

    activa = proveedor._ss_acceso(
        pagina, None, OpcionesSync(), "TGSS_VIDA_LABORAL",
    )

    assert activa is pagina
    assert any("boton-lanzamiento-operacion" in item for item in pagina.clicks)
    assert any("btn-atria-continuar" in item for item in pagina.clicks)
    assert len(pagina.checks) == 1
    assert login == [pagina]


class _Eventos:
    def __init__(self):
        self.eventos = {}

    def on(self, nombre, callback):
        self.eventos.setdefault(nombre, []).append(callback)

    def remove_listener(self, nombre, callback):
        self.eventos[nombre].remove(callback)

    def emitir(self, nombre, value):
        for callback in list(self.eventos.get(nombre, [])):
            callback(value)


class _DescargaTGSS:
    def __init__(self, body):
        self.body = body

    def save_as(self, destino):
        with open(destino, "wb") as fh:
            fh.write(self.body)


class _RespuestaTGSS:
    url = "https://sp.seg-social.es/ProsaInternet/OnlineAccessUtf8"
    headers = {"content-type": "application/pdf"}

    def __init__(self, body):
        self.contenido = body

    def body(self):
        return self.contenido


class _BotonImprimir:
    def __init__(self, pagina, existe=True):
        self.pagina = pagina
        self.existe = existe

    @property
    def first(self):
        return self

    def count(self):
        return int(self.existe)

    def click(self, timeout=None):
        self.pagina.clicks += 1
        contexto = self.pagina.context
        modo = self.pagina.modo
        body = b"<html>Error</html>" if modo == "html" else b"%PDF-1.7\nTGSS"
        if modo in {"descarga", "html"}:
            self.pagina.emitir("download", _DescargaTGSS(body))
        elif modo == "popup":
            nueva = _PaginaImprimir()
            nueva.context = contexto
            contexto.pages.append(nueva)
            contexto.emitir("page", nueva)
            nueva.emitir("download", _DescargaTGSS(body))
        elif modo != "sin_pdf":
            contexto.emitir("response", _RespuestaTGSS(body))
        if modo == "click_interrumpido":
            raise RuntimeError("Navigation interrupted by download")


class _PaginaImprimir(_Eventos):
    def __init__(self, modo="descarga", boton=True):
        super().__init__()
        self.modo = modo
        self.boton = boton
        self.clicks = 0
        self.esperas = 0
        self.context = _Eventos()
        self.context.pages = [self]

    def locator(self, selector):
        es_descarga = (
            "SPM.ACC.IMPRIMIR" in selector
            or "Descargar vida laboral" in selector
        )
        return _BotonImprimir(self, self.boton and es_descarga)

    def is_closed(self):
        return self.esperas > 0

    def wait_for_timeout(self, timeout):
        self.esperas += 1


@pytest.mark.parametrize("tipo", sorted(SS_CERT_RADIO))
@pytest.mark.parametrize("modo", ["descarga", "respuesta", "popup", "click_interrumpido"])
def test_tgss_captura_imprimir_sin_pedir_otra_solicitud(tmp_path, tipo, modo):
    pagina = _PaginaImprimir(modo)
    destino = tmp_path / "certificado.pdf"

    obtenido = obtener_proveedor(tipo)._descargar_documento(
        pagina, OpcionesSync(ruta_pdf_destino=str(destino), timeout_ms=10), tipo,
    )

    assert obtenido == str(destino)
    assert destino.read_bytes().startswith(b"%PDF-")
    assert pagina.clicks == 1
    assert not (tmp_path / "certificado.pdf.part").exists()
    assert not any(pagina.context.eventos.values())
    assert all(not any(pg.eventos.values()) for pg in pagina.context.pages)


@pytest.mark.parametrize("modo", ["html", "sin_pdf"])
def test_tgss_no_guarda_html_como_pdf_ni_repite_imprimir(tmp_path, modo):
    pagina = _PaginaImprimir(modo)
    destino = tmp_path / "certificado.pdf"

    obtenido = obtener_proveedor("TGSS_CORRIENTE")._descargar_boton_tgss(
        pagina, OpcionesSync(ruta_pdf_destino=str(destino), timeout_ms=10),
        "TGSS_CORRIENTE",
    )

    assert obtenido is None
    assert not destino.exists()
    assert not (tmp_path / "certificado.pdf.part").exists()
    assert pagina.clicks == 1
    assert not any(pagina.context.eventos.values())


def test_tgss_sin_imprimir_no_pulsa_otros_botones(tmp_path):
    pagina = _PaginaImprimir(boton=False)
    assert obtener_proveedor("TGSS_CORRIENTE")._descargar_boton_tgss(
        pagina, OpcionesSync(carpeta_descargas=str(tmp_path)), "TGSS_CORRIENTE",
    ) is None
    assert pagina.clicks == 0


def test_vida_laboral_captura_el_pdf_de_importass(tmp_path):
    pagina = _PaginaImprimir("descarga")
    destino = tmp_path / "vida_laboral.pdf"

    obtenido = obtener_proveedor("TGSS_VIDA_LABORAL")._descargar_documento(
        pagina,
        OpcionesSync(ruta_pdf_destino=str(destino), timeout_ms=10),
        "TGSS_VIDA_LABORAL",
    )

    assert obtenido == str(destino)
    assert destino.read_bytes().startswith(b"%PDF-")
    assert pagina.clicks == 1


def test_diagnostico_no_muestra_sesiones_ni_tickets_de_la_sede():
    proveedor = obtener_proveedor("TGSS_CORRIENTE")
    assert proveedor._url_diagnostico_segura(
        "https://sp.seg-social.es/ProsaInternet/OnlineAccessUtf8;jsessionid=secreto"
        "?ticket=privado#datos"
    ) == "https://sp.seg-social.es/ProsaInternet/OnlineAccessUtf8"
