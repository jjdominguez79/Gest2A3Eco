"""Tests de integracion ligera del modulo OCR (OcrParserService via OCRService)."""
from services.ocr_parser_service import OcrParserService


def test_parsear_factura_basica_extrae_campos_principales():
    svc = OcrParserService()
    texto = """\
    PROVEEDOR DEMO SL
    CIF: B12345678
    Factura N: FAC-2026-001
    Fecha factura: 15/05/2026
    Base imponible: 100,00
    Cuota IVA: 21,00
    Total factura: 121,00
    """
    r = svc.parsear_y_validar(texto)
    assert r.proveedor_nif == "B12345678"
    assert r.numero_factura == "FAC-2026-001"
    assert r.fecha_factura == "15/05/2026"
    assert r.base_imponible == 100.0
    assert r.cuota_iva == 21.0
    assert r.total == 121.0
    assert r.bandeja == "pendiente_revision"


def test_parsear_sin_nif_produce_bandeja_error():
    svc = OcrParserService()
    texto = """\
    Empresa sin identificacion fiscal
    Factura N: F-001
    Fecha factura: 01/01/2026
    Total factura: 100,00
    """
    r = svc.parsear_y_validar(texto)
    assert r.bandeja == "error"
    assert r.proveedor_nif == ""
    assert r.errores_criticos


def test_parsear_devuelve_lineas_fiscales_en_legacy_dict():
    svc = OcrParserService()
    texto = """\
    Proveedor SA
    CIF: A12345678
    Factura N: T-001
    Fecha factura: 01/06/2026
    21%   1.000,00   210,00
    Total: 1.210,00
    """
    r = svc.parsear_y_validar(texto)
    d = r.to_legacy_dict()
    assert isinstance(d["lineas"], list)
    assert len(d["lineas"]) >= 1
    assert d["bandeja"] == "pendiente_revision"
