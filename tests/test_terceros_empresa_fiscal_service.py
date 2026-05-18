from services.terceros_empresa_fiscal_service import (
    build_cliente_factura_defaults,
    validate_tercero_empresa_rel,
)


def test_cliente_intracom_bienes_mapea_a_349_b():
    data = build_cliente_factura_defaults(
        {
            "cliente_tipo_operacion_iva": "INTRACOMUNITARIA",
            "cliente_intracomunitaria_clase": "BIENES",
        }
    )
    assert data["tipo_operacion"] == "03"
    assert data["modelo_fiscal"] == "02"


def test_cliente_intracom_servicios_mapea_a_349_s():
    data = build_cliente_factura_defaults(
        {
            "cliente_tipo_operacion_iva": "INTRACOMUNITARIA",
            "cliente_intracomunitaria_clase": "SERVICIOS",
        }
    )
    assert data["tipo_operacion"] == "03"
    assert data["modelo_fiscal"] == "11"


def test_validacion_exige_clase_intracomunitaria():
    try:
        validate_tercero_empresa_rel(
            {
                "cliente_tipo_operacion_iva": "INTRACOMUNITARIA",
            }
        )
    except ValueError as exc:
        assert "bienes o servicios" in str(exc).lower()
        return
    raise AssertionError("Se esperaba ValueError por falta de clase intracomunitaria")
