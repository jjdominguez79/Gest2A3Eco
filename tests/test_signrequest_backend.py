from backend.api.integrations import SignRequestBackend
from services.firma.firma_service import FirmaService


def _backend_con_respuestas(solicitud, documento):
    backend = SignRequestBackend.__new__(SignRequestBackend)
    backend.base_url = "https://signrequest.example/api/v1"

    def obtener(_method, url, **_kwargs):
        if "/signrequests/" in url:
            return solicitud
        return documento

    backend._json = obtener
    return backend


def test_no_marca_firmado_si_falta_un_firmante_obligatorio_aunque_haya_pdf():
    backend = _backend_con_respuestas(
        {
            "document": "https://signrequest.example/api/v1/documents/doc-1/",
            "signers": [
                {"email": "remitente@example.com", "needs_to_sign": False, "signed": False},
                {"email": "vendedor@example.com", "needs_to_sign": True, "signed": True, "order": 1},
                {"email": "comprador@example.com", "needs_to_sign": True, "signed": False, "order": 2},
            ],
        },
        {
            "uuid": "doc-1",
            "status": "si",
            "pdf": "https://files.example/firmado.pdf",
            "signing_log": {"pdf": "https://files.example/registro.pdf"},
        },
    )

    resultado = backend.consultar("firma-1")

    assert resultado["status"] == "partially_signed"
    assert [item["needs_to_sign"] for item in resultado["firmantes"]] == [False, True, True]


def test_marca_firmado_solo_con_todos_los_obligatorios_y_evidencias():
    backend = _backend_con_respuestas(
        {
            "document": "https://signrequest.example/api/v1/documents/doc-2/",
            "signers": [
                {"email": "remitente@example.com", "needs_to_sign": False, "signed": False},
                {"email": "vendedor@example.com", "needs_to_sign": True, "signed": True, "order": 1},
                {"email": "comprador@example.com", "needs_to_sign": True, "signed": True, "order": 2},
            ],
        },
        {
            "uuid": "doc-2",
            "status": "sd",
            "pdf": "https://files.example/firmado.pdf",
            "signing_log": {"pdf": "https://files.example/registro.pdf"},
        },
    )

    assert backend.consultar("firma-2")["status"] == "signed"


def test_normaliza_estados_terminales_de_signrequest():
    backend = _backend_con_respuestas(
        {
            "document": "https://signrequest.example/api/v1/documents/doc-3/",
            "signers": [
                {"email": "cliente@example.com", "needs_to_sign": True, "signed": False},
            ],
        },
        {"uuid": "doc-3", "status": "ca", "signing_log": {}},
    )

    assert backend.consultar("firma-3")["status"] == "cancelled"


def test_servicio_general_conserva_el_estado_parcial():
    assert (
        FirmaService._normalizar_estado({"status": "partially_signed"})
        == "parcialmente_firmado"
    )
