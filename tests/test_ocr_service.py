"""Tests de integracion ligera del interprete OCR tipado."""
from services.ocr.invoice_interpreter import InvoiceInterpreter
from services.ocr.types import OcrDocumentState


def test_parsear_factura_basica_extrae_campos_principales():
    svc = InvoiceInterpreter()
    texto = """\
    PROVEEDOR DEMO SL
    CIF: B12345678
    Factura N: FAC-2026-001
    Fecha factura: 15/05/2026
    Base imponible: 100,00
    Cuota IVA: 21,00
    Total factura: 121,00
    """
    r = svc.interpretar(texto)
    assert r.proveedor_nif == "B12345678"
    assert r.numero_factura == "FAC-2026-001"
    assert r.fecha_factura == "2026-05-15"
    assert r.base_total == 100.0
    assert r.iva_total == 21.0
    assert r.total == 121.0
    assert r.estado_sugerido == OcrDocumentState.PENDIENTE_REVISION


def test_parsear_sin_nif_produce_error():
    svc = InvoiceInterpreter()
    texto = """\
    Empresa sin identificacion fiscal
    Factura N: F-001
    Fecha factura: 01/01/2026
    Total factura: 100,00
    """
    r = svc.interpretar(texto)
    assert r.estado_sugerido == OcrDocumentState.ERROR
    assert r.proveedor_nif == ""
    assert r.errores


def test_parsear_devuelve_lineas_fiscales_tipadas():
    svc = InvoiceInterpreter()
    texto = """\
    Proveedor SA
    CIF: A12345678
    Factura N: T-001
    Fecha factura: 01/06/2026
    21%   1.000,00   210,00
    Total: 1.210,00
    """
    r = svc.interpretar(texto)
    assert len(r.bases_iva) >= 1
    assert r.estado_sugerido == OcrDocumentState.PENDIENTE_REVISION
