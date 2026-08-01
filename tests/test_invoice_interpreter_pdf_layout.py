from services.ocr.invoice_interpreter import InvoiceInterpreter


def test_interpreta_cabecera_y_desglose_vertical_de_pdf():
    texto = """Pagina: 1/1
Refer.
Descripcion
Cantidad
FACTURA
 ELMAR FROZEN FOOD SLU
NIF B27849421
Fecha:
Factura:
30/07/2026
XST26 07994
Total parcial...............................:
253,10
I.V.A. 10,00%  s/
253,10 .....:
25,31
Total factura (EUR)...............................:
278,41
"""
    result = InvoiceInterpreter().interpretar(texto)

    assert result.proveedor_nombre == "ELMAR FROZEN FOOD SLU"
    assert result.proveedor_nif == "B27849421"
    assert result.numero_factura == "XST26 07994"
    assert result.fecha_factura == "2026-07-30"
    assert result.base_total == 253.10
    assert result.iva_total == 25.31
    assert result.total == 278.41
    assert [(linea.tipo_iva, linea.base, linea.cuota_iva) for linea in result.bases_iva] == [
        (10.0, 253.10, 25.31)
    ]
