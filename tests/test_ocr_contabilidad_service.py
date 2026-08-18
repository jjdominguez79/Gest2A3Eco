from services.ocr_contabilidad_service import OcrContabilidadService
from services.ocr_recibidas_service import doc_to_rows


def test_proyecta_factura_validada_a_documento_contable():
    class Gestor:
        def listar_lineas_iva_ocr(self, factura_id):
            assert factura_id == "fac-1"
            return [{
                "base": 100.0,
                "tipo_iva": 21.0,
                "cuota_iva": 21.0,
                "tipo_recargo": 0.0,
                "cuota_recargo": 0.0,
                "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
            }]

        def listar_terceros_por_empresa(self, codigo, ejercicio):
            assert (codigo, ejercicio) == ("E00570", 2026)
            return [{"id": "ter-1", "nif": "B12345678"}]

        def get_tercero_empresa(self, codigo, tercero_id, ejercicio):
            assert (codigo, tercero_id, ejercicio) == ("E00570", "ter-1", 2026)
            return {
                "subcuenta_proveedor": "40000001",
                "subcuenta_gasto": "62900001",
            }

        def upsert_factura_recibida_doc(self, payload):
            self.payload = payload

    gestor = Gestor()
    documento = {"id": "doc-1", "ruta_original": "C:/docs/factura.pdf"}
    factura = {
        "id": "fac-1",
        "nif_proveedor": "B12345678",
        "nombre_proveedor": "Proveedor SL",
        "numero_factura": "F-1",
        "fecha_factura": "2026-08-08",
        "fecha_contable": "2026-08-12",
        "pagada": True,
        "suplidos": 12.0,
        "cuenta_suplidos": "55509999",
        "base_total": 100.0,
        "iva_total": 21.0,
        "total_factura": 121.0,
        "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
    }

    payload = OcrContabilidadService(
        gestor, "E00570", 2026
    ).proyectar_factura_validada(documento, factura)

    assert payload == gestor.payload
    assert payload["id"] == "doc-1"
    assert payload["estado_contable"] == "pendiente_contabilizar"
    assert payload["tercero_id"] == "ter-1"
    assert payload["cuenta_proveedor"] == "40000001"
    assert payload["cuenta_gasto"] == "62900001"
    assert payload["lineas"][0]["base_imponible"] == 100.0
    assert payload["datos_extra"]["documento_ocr_id"] == "doc-1"
    assert payload["fecha_asiento"] == "2026-08-12"
    assert payload["pagada"] == 1
    assert payload["suplidos"] == 12.0
    assert payload["cuenta_suplidos"] == "55509999"


def test_suplidos_solo_se_proyectan_en_el_primer_tramo_fiscal():
    filas = doc_to_rows(
        {
            "fecha_factura": "2026-08-08", "numero_factura": "F-1",
            "suplidos": 12.0, "cuenta_suplidos": "55509999",
        },
        [
            {"base_imponible": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0},
            {"base_imponible": 50.0, "tipo_iva": 10.0, "cuota_iva": 5.0},
        ],
    )
    assert [fila["Suplidos"] for fila in filas] == [12.0, 0.0]
    assert all(fila["Cuenta Suplidos"] == "55509999" for fila in filas)
