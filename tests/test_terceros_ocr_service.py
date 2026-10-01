from services.terceros_ocr_service import TercerosOcrService


class GestorTercerosPrueba:
    def __init__(self):
        self.tipos_solicitados = None

    def listar_subcuentas_facturacion(self, _codigo, tipos, activo=True):
        self.tipos_solicitados = tuple(tipos)
        assert activo is True
        return [
            {
                "tercero_id": "tercero-a3",
                "tercero_nif": "16511073V",
                "tercero_nombre_legal": "ELISA DE GREGORIO GARCIA",
                "tipo_subcuenta": "proveedor",
                "subcuenta": "40000008",
            }
        ]

    def listar_terceros_por_empresa(self, _codigo, _ejercicio):
        return [
            {
                "id": "tercero-legacy",
                "nif": "B12345678",
                "nombre": "PROVEEDOR LEGACY",
                "subcuenta_proveedor": "40000009",
            }
        ]

    def listar_terceros(self):
        return []


def test_candidatos_empresa_incluyen_maestro_a3_y_legacy():
    gestor = GestorTercerosPrueba()
    servicio = TercerosOcrService()

    candidatos = servicio.listar_candidatos_empresa(
        gestor, "E00001", 2026, ("proveedor", "acreedor"),
    )

    assert gestor.tipos_solicitados == ("proveedor", "acreedor")
    assert candidatos[0]["id"] == "tercero-a3"
    assert candidatos[0]["nombre"] == "ELISA DE GREGORIO GARCIA"
    assert candidatos[0]["nif"] == "16511073V"
    assert candidatos[0]["subcuenta_proveedor"] == "40000008"
    assert candidatos[1]["id"] == "tercero-legacy"


def test_resolver_tercero_usa_el_mismo_maestro_que_el_selector():
    tercero = TercerosOcrService().resolver_tercero(
        GestorTercerosPrueba(), "16511073-V", "", "E00001", 2026,
    )

    assert tercero is not None
    assert tercero["id"] == "tercero-a3"
    assert tercero["subcuenta_proveedor"] == "40000008"
