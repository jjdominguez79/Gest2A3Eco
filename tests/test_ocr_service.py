from services.ocr_service import OCRService


def test_parse_invoice_text_basic_fields():
    svc = OCRService()
    text = """
    PROVEEDOR DEMO SL
    CIF: B12345678
    Factura N: FAC-2026-001
    Fecha factura: 15/05/2026
    Base imponible: 100,00
    Cuota IVA: 21,00
    Total factura: 121,00
    """
    parsed = svc._parse_invoice_text(text)
    assert parsed["proveedor_nif"] == "B12345678"
    assert parsed["numero_factura"] == "FAC-2026-001"
    assert parsed["fecha_factura"] == "15/05/2026"
    assert parsed["base_imponible"] == 100.0
    assert parsed["cuota_iva"] == 21.0
    assert parsed["total"] == 121.0
