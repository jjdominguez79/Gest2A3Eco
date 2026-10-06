from backend.api.ocr_training_service import _nombres_blobs


def test_nombres_blobs_dejan_documento_en_raiz_y_metadatos_separados():
    documento, metadata = _nombres_blobs(
        "E00/423",
        "7",
        r"C:\facturas\Factura numero 7.pdf",
    )

    assert documento == "gest2a3eco_E00_423_7_Factura_numero_7.pdf"
    assert "/" not in documento
    assert metadata == "_metadata/gest2a3eco_E00_423_7.json"
