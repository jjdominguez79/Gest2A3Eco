from services.aapp.base import OpcionesSync
from services.aapp.certificados import SedePlaywrightProvider


class _Locator:
    def __init__(self, selector, actions):
        self.selector = selector
        self.actions = actions

    def count(self):
        return 1

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


def test_aeat_no_aplica_formulario_ecot_a_otros_certificados():
    page = _Page()
    provider = SedePlaywrightProvider("AEAT", {"AEAT_CENSAL"}, "https://example.test")

    assert provider._aeat_preparar_solicitud(
        page, OpcionesSync(log=lambda _message: None), "AEAT_CENSAL",
    ) is False
    assert page.actions == []
