from types import SimpleNamespace

from services.ocr.engines.azure_invoice_engine import AzureInvoiceEngine
from services.ocr.ocr_service import OcrService
from services.ocr.types import OcrInvoiceResult


def test_mapea_campos_estructurados_del_sdk_actual():
    field = lambda value, content=None, confidence=0.9: SimpleNamespace(value=value, content=content, confidence=confidence)
    doc = SimpleNamespace(fields={
        "VendorName": field("Proveedor SL", "Proveedor SL"),
        "VendorTaxId": field("B12345678", "B12345678"),
        "InvoiceId": field("F-2026-1", "F-2026-1"),
        "InvoiceDate": field(__import__("datetime").date(2026, 7, 29)),
        "InvoiceTotal": field(SimpleNamespace(amount=121.0)),
        "SubTotal": field(SimpleNamespace(amount=100.0)),
        "TotalTax": field(SimpleNamespace(amount=21.0)),
    })

    result = AzureInvoiceEngine("endpoint", "key")._mapear_documento(doc, None)

    assert result.proveedor_nif == "B12345678"
    assert result.numero_factura == "F-2026-1"
    assert result.fecha_factura == "2026-07-29"
    assert result.total == 121.0
    assert result.bases_iva[0].tipo_iva == 21.0


def test_usa_el_texto_de_azure_como_respaldo_si_faltan_campos():
    doc = SimpleNamespace(fields={})
    texto = "Proveedor Demo SL\nCIF: B12345678\nFactura N: F-22\nFecha factura: 15/05/2026\nTotal factura: 121,00"

    result = AzureInvoiceEngine("endpoint", "key")._mapear_documento(doc, None, texto=texto)

    assert result.proveedor_nif == "B12345678"
    assert result.numero_factura == "F-22"
    assert result.total == 121.0


def test_acepta_resultado_estructurado_aunque_azure_no_devuelva_texto():
    service = object.__new__(OcrService)

    class Engine:
        nombre = "azure"
        def extraer(self, path):
            return OcrInvoiceResult(proveedor_nif="B12345678", numero_factura="F-1", motor="azure")

    service._motores = [Engine()]
    result = service._ejecutar_motores(None)

    assert result.motor == "azure"


def test_prefiere_razon_social_y_convierte_porcentaje_iva_de_azure():
    field = lambda value, content=None, confidence=0.9: SimpleNamespace(value=value, content=content, confidence=confidence)
    tax_item = field({
        "Rate": field("10,00%", "10,00%"),
        "Amount": field(SimpleNamespace(amount=25.31), "25,31"),
    })
    doc = SimpleNamespace(fields={
        "VendorName": field("Frozen Food elmar", "Frozen Food elmar"),
        "VendorAddressRecipient": field("ELMAR FROZEN FOOD SLU", "ELMAR FROZEN FOOD SLU"),
        "VendorTaxId": field("B27849421", "B27849421"),
        "InvoiceId": field("XST26 07994", "XST26 07994"),
        "InvoiceTotal": field(SimpleNamespace(amount=278.41)),
        "SubTotal": field(SimpleNamespace(amount=253.10)),
        "TotalTax": field(SimpleNamespace(amount=25.31)),
        "TaxDetails": field([tax_item]),
    })

    result = AzureInvoiceEngine("endpoint", "key")._mapear_documento(doc, None)

    assert result.proveedor_nombre == "ELMAR FROZEN FOOD SLU"
    assert [(linea.tipo_iva, linea.base, linea.cuota_iva) for linea in result.bases_iva] == [
        (10.0, 253.10, 25.31)
    ]
