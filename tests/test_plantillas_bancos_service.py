from services.plantillas_bancos_service import (
    datos_plantilla_desde_cuenta,
    etiqueta_cuenta_bancaria,
    listar_cuentas_bancarias_para_plantilla,
)


class GestorFalso:
    def listar_cuentas_bancarias(self, codigo, ejercicio):
        if ejercicio == 2026:
            return [{
                "id": 2, "descripcion": "Banco ejercicio",
                "iban": "ES02", "subcuenta_contable": "57200002",
            }]
        return [{
            "id": 1, "descripcion": "Banco general",
            "iban": "ES01", "subcuenta_contable": "57200001",
        }]


def test_lista_cuentas_del_ejercicio_y_generales():
    cuentas = listar_cuentas_bancarias_para_plantilla(
        GestorFalso(), "E00001", 2026
    )
    assert [cuenta["id"] for cuenta in cuentas] == [2, 1]


def test_cuenta_seleccionada_autocompleta_campos():
    cuenta = {
        "descripcion": "Cuenta operativa",
        "iban": "ES9121000418450200051332",
        "subcuenta_contable": "57200001",
    }
    assert datos_plantilla_desde_cuenta(cuenta) == {
        "banco": "Cuenta operativa",
        "numero_cuenta": "ES9121000418450200051332",
        "subcuenta_banco": "57200001",
    }
    assert etiqueta_cuenta_bancaria(cuenta).endswith("57200001")


def test_descripcion_vacia_usa_numero_de_cuenta_como_nombre():
    datos = datos_plantilla_desde_cuenta({
        "iban": "ES01", "subcuenta_contable": "57200000",
    })
    assert datos["banco"] == "ES01"
