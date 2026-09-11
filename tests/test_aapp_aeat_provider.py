from services.aapp.base import OpcionesSync
from services.aapp.certificados import SedePlaywrightProvider


class _Locator:
    def __init__(self, selector, actions):
        self.selector = selector
        self.actions = actions

    def count(self):
        return 1

    @property
    def first(self):
        return self

    def check(self, timeout=None):
        self.actions.append(("check", self.selector))

    def click(self, timeout=None):
        self.actions.append(("click", self.selector))


class _Page:
    def __init__(self):
        self.actions = []

    def locator(self, selector):
        return _Locator(selector, self.actions)

    def wait_for_load_state(self, state, timeout=None):
        self.actions.append(("wait", state))


def test_aeat_corriente_prepara_solicitud_generica_en_nombre_propio():
    page = _Page()
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CORRIENTE"}, "https://example.test")

    acted = provider._aeat_preparar_solicitud(
        page, OpcionesSync(log=lambda _message: None), "AEAT_CORRIENTE",
    )

    assert acted is page
    assert page.actions[:4] == [
        ("check", "#fTipoRepresentacion0"),
        ("check", "#fTipoCertificado4"),
        ("check", "#fMomentoDeterminacionEcot0"),
        ("click", "#validarSolicitud"),
    ]
    assert ("click", "input[id^='FirmayEnvia_']") in page.actions


def test_aeat_no_aplica_formulario_ecot_a_otros_certificados():
    page = _Page()
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CENSAL"}, "https://example.test")

    assert provider._aeat_preparar_solicitud(
        page, OpcionesSync(log=lambda _message: None), "AEAT_CENSAL",
    ) is False
    assert page.actions == []


class _ControlSeguro:
    def inner_text(self, timeout=None):
        return "Validar solicitud"

    def evaluate(self, _expression):
        return "button"

    def get_attribute(self, name):
        return {
            "type": "submit",
            "id": "validarSolicitud",
            "name": "validarSolicitud",
            "value": "72044071K",
        }.get(name)


class _ListaControles:
    def count(self):
        return 1

    def nth(self, _index):
        return _ControlSeguro()


class _PaginaSegura:
    def title(self):
        return "Certificados Tributarios"

    def locator(self, _selector):
        return _ListaControles()


def test_resumen_pagina_no_incluye_valores_del_contribuyente():
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CORRIENTE"}, "https://example.test")

    resumen = provider._resumir_pagina(_PaginaSegura())

    assert "Certificados Tributarios" in resumen
    assert "validarSolicitud" in resumen
    assert "72044071K" not in resumen


class _PaginaFirma:
    def __init__(self):
        self.actions = []
        self.frames = [self]

    def is_closed(self):
        return False

    def locator(self, selector):
        return _Locator(selector, self.actions)

    def wait_for_load_state(self, state, timeout=None):
        self.actions.append(("wait", state))


class _PaginaOrigen(_PaginaFirma):
    def __init__(self, pagina_firma):
        super().__init__()
        self.context = type("Contexto", (), {"pages": [self, pagina_firma]})()

    def wait_for_timeout(self, _timeout):
        pass


def test_aeat_confirma_firma_en_la_ventana_emergente():
    firma = _PaginaFirma()
    origen = _PaginaOrigen(firma)
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CORRIENTE"}, "https://example.test")

    activa = provider._aeat_confirmar_firma(
        origen, OpcionesSync(log=lambda _message: None),
    )

    assert activa is firma
    assert ("check", "input[type='checkbox']") in firma.actions
    assert ("click", "input[id^='FirmayEnvia_'], input[value*='Firmar'], button:has-text('Firmar')") in firma.actions


class _Descarga:
    def save_as(self, destino):
        with open(destino, "wb") as fichero:
            fichero.write(b"%PDF-1.7\nprueba")


class _EsperaDescarga:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    @property
    def value(self):
        return _Descarga()


class _PaginaDescarga:
    def __init__(self):
        self.actions = []

    def locator(self, selector):
        return _Locator(selector, self.actions)

    def expect_download(self, timeout=None):
        return _EsperaDescarga()


def test_aeat_captura_el_boton_final_como_pdf(tmp_path):
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CORRIENTE"}, "https://example.test")
    destino = tmp_path / "certificado.pdf"

    obtenido = provider._descargar_boton_aeat(
        _PaginaDescarga(),
        OpcionesSync(ruta_pdf_destino=str(destino), log=lambda _message: None),
        "AEAT_CORRIENTE",
    )

    assert obtenido == str(destino)
    assert destino.read_bytes().startswith(b"%PDF-")
