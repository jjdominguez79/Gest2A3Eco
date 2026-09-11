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

    assert acted is True
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
