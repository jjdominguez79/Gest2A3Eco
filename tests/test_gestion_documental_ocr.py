import pytest

from models.gestor_base import GestorBase
from services.gestion_documental_service import GestionDocumentalService


class _Gestor:
    def __init__(self, categoria_id):
        self.documento = {
            "id": "archivo-1",
            "codigo_empresa": "E00001",
            "ejercicio": 2026,
            "categoria_id": categoria_id,
            "ruta": "factura.pdf",
            "permite_ocr": 1,
            "ocr_documento_id": "",
        }
        self.vinculo = None

    def get_documento_archivo(self, _documento_id):
        return dict(self.documento)

    def vincular_documento_archivo_ocr(self, documento_id, ocr_documento_id):
        self.vinculo = (documento_id, ocr_documento_id)


def test_catalogo_documental_incluye_facturas_emitidas_para_ocr():
    class _Conn:
        def __init__(self):
            self.parametros = []

        def execute(self, _sql, params):
            self.parametros.append(params)

    gestor = object.__new__(GestorBase)
    gestor.conn = _Conn()

    gestor._seed_categorias_documentales()

    assert (
        "facturas_emitidas", "Facturas emitidas", "FACTURAS_EMITIDAS", 1, 15,
    ) in gestor.conn.parametros


@pytest.mark.parametrize(
    ("categoria_id", "tipo_esperado"),
    (
        ("facturas_recibidas", "factura_recibida"),
        ("facturas_emitidas", "factura_emitida"),
    ),
)
def test_enviar_a_ocr_conserva_el_tipo_de_factura(
    monkeypatch, categoria_id, tipo_esperado,
):
    gestor = _Gestor(categoria_id)
    recibido = {}

    class _OcrService:
        def __init__(self, _gestor, empresa, ejercicio, **opciones):
            recibido.update({
                "empresa": empresa,
                "ejercicio": ejercicio,
                **opciones,
            })

        def procesar_archivo(self, ruta):
            recibido["ruta"] = ruta
            return {"documento_id": "ocr-1"}

    monkeypatch.setattr(
        "services.gestion_documental_service.OcrService", _OcrService,
    )

    GestionDocumentalService(gestor, graph=object()).enviar_a_ocr(
        "archivo-1", usuario="Empleado",
    )

    assert recibido["tipo_documento"] == tipo_esperado
    assert gestor.vinculo == ("archivo-1", "ocr-1")


@pytest.mark.parametrize(
    ("categoria_id", "tipo_esperado"),
    (
        ("facturas_recibidas", "factura_recibida"),
        ("facturas_emitidas", "factura_emitida"),
    ),
)
def test_cola_ocr_conserva_el_tipo_de_factura(
    monkeypatch, categoria_id, tipo_esperado,
):
    gestor = _Gestor(categoria_id)
    gestor.encolar_trabajo_ocr = lambda _trabajo: ("trabajo-1", True)
    recibido = {}

    class _BackgroundService:
        def __init__(self, _gestor):
            pass

        def encolar(self, **trabajo):
            recibido.update(trabajo)
            return "trabajo-1", True

    monkeypatch.setattr(
        "services.gestion_documental_service.OcrBackgroundService",
        _BackgroundService,
    )

    creado = GestionDocumentalService(gestor, graph=object())._encolar_ocr(
        "archivo-1", usuario="Empleado",
    )

    assert creado is True
    assert recibido["tipo_documento"] == tipo_esperado
