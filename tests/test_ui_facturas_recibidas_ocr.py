from views.ui_facturas_recibidas_ocr import _normalizar_confianza


def test_normalizar_confianza_acepta_valores_de_azure_y_porcentaje():
    assert _normalizar_confianza("0.87") == 0.87
    assert _normalizar_confianza("87%") == 0.87
    assert _normalizar_confianza("87,5") == 0.875
    assert _normalizar_confianza("invalido") == 0.0
