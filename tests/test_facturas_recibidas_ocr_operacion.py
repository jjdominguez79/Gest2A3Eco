"""Persistencia de los campos fiscales editados en la revision OCR."""
from models.gestor_sqlite import GestorSQLite


def test_factura_ocr_guarda_tipo_operacion_y_linea_iva(tmp_path):
    gestor = GestorSQLite(tmp_path / "ocr.db")
    gestor.upsert_documento_ocr({
        "id": "doc-1", "empresa_id": "E00001", "nombre_archivo": "factura.pdf",
        "hash_archivo": "hash-prueba",
    })
    tercero_id = gestor.upsert_tercero({
        "nif": "B12345678", "nombre": "Proveedor Demo SL",
    })
    gestor.upsert_factura_recibida_ocr({
        "id": "fac-1",
        "documento_id": "doc-1",
        "empresa_id": "E00001",
        "proveedor_id": tercero_id,
        "nif_proveedor": "B12345678",
        "nombre_proveedor": "Proveedor Demo SL",
        "numero_factura": "F-1",
        "total_factura": 121.0,
        "base_total": 100.0,
        "iva_total": 21.0,
        "tipo_operacion_iva": "GASTO_PRORRATA",
    })
    gestor.upsert_linea_iva_ocr({
        "factura_id": "fac-1", "tipo_iva": 21.0, "base": 100.0,
        "cuota_iva": 21.0, "tipo_operacion_iva": "GASTO_PRORRATA",
    })

    factura = gestor.get_factura_recibida_ocr("fac-1")
    lineas = gestor.listar_lineas_iva_ocr("fac-1")

    assert str(factura["proveedor_id"]) == str(tercero_id)
    assert factura["tipo_operacion_iva"] == "GASTO_PRORRATA"
    assert lineas[0]["base"] == 100.0
    assert lineas[0]["cuota_iva"] == 21.0
    assert lineas[0]["tipo_operacion_iva"] == "GASTO_PRORRATA"
