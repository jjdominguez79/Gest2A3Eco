from models.facturas_common import render_emitidas_cabecera_512


def test_render_emitidas_cabecera_512_preserva_numero_largo_sii():
    num_largo = "2026/A/0000000123456789"

    reg = render_emitidas_cabecera_512(
        codigo_empresa="570",
        fecha="20/05/2026",
        tipo_registro="1",
        cuenta_tercero="43000000",
        ndig_plan=8,
        tipo_factura="1",
        num_factura="123",
        desc_apunte="N. Fra. 123",
        importe_total=1210.0,
        fecha_operacion="20/05/2026",
        fecha_factura="20/05/2026",
        num_factura_largo_sii=num_largo,
    )

    assert reg[252:252 + len(num_largo)] == num_largo
