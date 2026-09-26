from services.ocr.background_service import OcrBackgroundService


class _GestorCola:
    def __init__(self, trabajo):
        self.trabajo = dict(trabajo)
        self.finalizados = []
        self.fallidos = []
        self.vinculos = []

    def reclamar_trabajo_ocr(self):
        trabajo, self.trabajo = self.trabajo, None
        return trabajo

    def finalizar_trabajo_ocr(self, trabajo_id, resultado, documento_ocr_id):
        self.finalizados.append((trabajo_id, resultado, documento_ocr_id))

    def fallar_trabajo_ocr(self, trabajo_id, error, **kwargs):
        self.fallidos.append((trabajo_id, error, kwargs))
        return "pendiente"

    def vincular_documento_archivo_ocr(self, archivo_id, ocr_id):
        self.vinculos.append((archivo_id, ocr_id))


def _trabajo():
    return {
        "id": "job-1", "empresa_id": "E00001", "ejercicio": 2026,
        "ruta_origen": "factura.pdf", "tipo_documento": "factura_recibida",
        "documento_archivo_id": "archivo-1", "documento_ocr_id": "",
        "usuario": "Empleado",
    }


def test_worker_finaliza_y_vincula_documento(monkeypatch):
    class _Ocr:
        def __init__(self, *_args, **_kwargs):
            pass

        def procesar_archivo(self, path):
            assert path == "factura.pdf"
            return {"documento_id": "ocr-1", "estado": "pendiente_revision"}

    monkeypatch.setattr("services.ocr.background_service.OcrService", _Ocr)
    gestor = _GestorCola(_trabajo())

    resultado = OcrBackgroundService(gestor).procesar_pendientes()[0]

    assert resultado.estado == "completado"
    assert gestor.vinculos == [("archivo-1", "ocr-1")]
    assert gestor.finalizados[0][0::2] == ("job-1", "ocr-1")
    assert gestor.fallidos == []


def test_worker_conserva_documento_y_reintenta_si_ocr_falla(monkeypatch):
    class _Ocr:
        def __init__(self, *_args, **_kwargs):
            pass

        def procesar_archivo(self, _path):
            return {
                "documento_id": "ocr-error", "estado": "error",
                "errores": ["Backend no disponible"],
            }

    monkeypatch.setattr("services.ocr.background_service.OcrService", _Ocr)
    gestor = _GestorCola(_trabajo())

    resultado = OcrBackgroundService(gestor).procesar_pendientes()[0]

    assert resultado.estado == "pendiente"
    assert gestor.vinculos == [("archivo-1", "ocr-error")]
    assert gestor.fallidos[0][2]["documento_ocr_id"] == "ocr-error"
