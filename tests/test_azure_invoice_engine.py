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


def test_acepta_resultado_estructurado_aunque_azure_no_devuelva_texto():
    service = object.__new__(OcrService)

    class Engine:
        nombre = "azure"
        def extraer(self, path):
            return OcrInvoiceResult(proveedor_nif="B12345678", numero_factura="F-1", motor="azure")

    service._motores = [Engine()]
    result = service._ejecutar_motores(None)

    assert result.motor == "azure"
