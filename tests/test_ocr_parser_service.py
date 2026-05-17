"""Tests unitarios de OcrParserService y sus funciones auxiliares puras."""
import pytest

from services.ocr_parser_service import (
    OcrParserService,
    _detectar_tabla_iva,
    _detectar_pares_tipo_iva,
    _detectar_nif,
    _parse_amount,
)


# ── Fixtures de texto ─────────────────────────────────────────────────────────

FACTURA_COMPLETA = """\
Proveedor Demo SL
CIF: B12345678
Factura N: FAC-2026-001
Fecha factura: 15/05/2026
Base imponible: 1.000,00
Cuota IVA: 210,00
Total factura: 1.210,00
"""

FACTURA_SIN_NIF = """\
EMPRESA REGIONAL SL
Fecha de emision: 10/05/2026
Base imponible: 500,00
Cuota: 105,00
Total a pagar: 605,00
"""

FACTURA_SIN_NUMERO = """\
Proveedor SA
CIF: A12345678
Fecha de emision: 10/05/2026
Importe total: 121,00
"""

FACTURA_MULTIBASE_TABLA = """\
PROVEEDOR DEMO SA
CIF: A12345678
Factura N: T-100
Fecha factura: 01/06/2026

Tipo IVA    Base            Cuota
21%         600,00          126,00
10%         400,00           40,00

Total: 1.166,00
"""

FACTURA_MULTIBASE_PARES = """\
Empresa XYZ SL
NIF: B98765432
Factura Num: P-200
Fecha factura: 02/06/2026

Base 21%: 1.000,00
IVA 21%: 210,00
Base 10%: 500,00
IVA 10%: 50,00

Total factura: 1.760,00
"""

TEXTO_NIF_LABEL_LUEGO_OTRO_CAMPO = """\
Empresa sin NIF
Factura No: F-001
"""


# ── Parsing completo ──────────────────────────────────────────────────────────

def test_parsear_factura_completa_pendiente_revision():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_COMPLETA)
    assert r.bandeja == "pendiente_revision"
    assert r.proveedor_nif == "B12345678"
    assert r.numero_factura == "FAC-2026-001"
    assert r.fecha_factura == "15/05/2026"
    assert r.total == 1210.0
    assert not r.errores_criticos


def test_parsear_sin_nif_produce_error():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_SIN_NIF)
    assert r.bandeja == "error"
    assert any("NIF" in e for e in r.errores_criticos)


def test_parsear_sin_numero_factura_produce_error():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_SIN_NUMERO)
    assert r.bandeja == "error"
    assert any("factura" in e.lower() for e in r.errores_criticos)


def test_parsear_texto_vacio_produce_error():
    svc = OcrParserService()
    r = svc.parsear_y_validar("")
    assert r.bandeja == "error"
    assert r.errores_criticos


# ── Multi-base: tabla ─────────────────────────────────────────────────────────

def test_parsear_multibase_tabla_produce_dos_lineas():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_MULTIBASE_TABLA)
    assert r.bandeja == "pendiente_revision"
    assert len(r.lineas_fiscales) == 2
    tipos = {l.tipo_iva for l in r.lineas_fiscales}
    assert 21.0 in tipos and 10.0 in tipos


def test_parsear_multibase_tabla_suma_bases():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_MULTIBASE_TABLA)
    assert r.base_imponible == pytest.approx(1000.0, abs=0.01)
    assert r.cuota_iva == pytest.approx(166.0, abs=0.01)


def test_detectar_tabla_iva_directo():
    texto = "21%   1.000,00   210,00\n10%   500,00   50,00"
    lineas = _detectar_tabla_iva(texto)
    assert len(lineas) == 2
    assert lineas[0].tipo_iva == 21.0
    assert lineas[0].base_imponible == 1000.0
    assert lineas[0].cuota_iva == 210.0
    assert lineas[1].tipo_iva == 10.0
    assert lineas[1].base_imponible == 500.0


# ── Multi-base: pares explícitos ──────────────────────────────────────────────

def test_parsear_multibase_pares_produce_dos_lineas():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_MULTIBASE_PARES)
    assert r.bandeja == "pendiente_revision"
    assert len(r.lineas_fiscales) == 2
    tipos = {l.tipo_iva for l in r.lineas_fiscales}
    assert 21.0 in tipos and 10.0 in tipos


def test_detectar_pares_tipo_iva_directo():
    texto = "Base 21%: 1.000,00\nIVA 21%: 210,00\nBase 10%: 500,00\nIVA 10%: 50,00"
    lineas = _detectar_pares_tipo_iva(texto)
    assert len(lineas) == 2
    by_tipo = {l.tipo_iva: l for l in lineas}
    assert by_tipo[21.0].base_imponible == 1000.0
    assert by_tipo[21.0].cuota_iva == 210.0
    assert by_tipo[10.0].base_imponible == 500.0
    assert by_tipo[10.0].cuota_iva == 50.0


# ── Validacion de totales ─────────────────────────────────────────────────────

def test_total_incoherente_produce_aviso_no_critico():
    texto = """\
    Empresa ABC SA
    CIF: B11223344
    Factura N: F-001
    Fecha factura: 01/01/2026
    Base imponible: 100,00
    Cuota IVA: 21,00
    Total factura: 200,00
    """
    svc = OcrParserService()
    r = svc.parsear_y_validar(texto)
    # NIF y numero detectados → no es error critico
    assert r.bandeja == "pendiente_revision"
    assert r.errores_criticos == []
    # Pero si hay aviso de incoherencia
    assert any("incoher" in a.lower() or "diferencia" in a.lower() for a in r.avisos)


def test_total_cero_produce_aviso_no_critico():
    texto = """\
    Empresa XYZ SL
    NIF: B55667788
    Factura N: F-002
    Fecha factura: 01/01/2026
    """
    svc = OcrParserService()
    r = svc.parsear_y_validar(texto)
    assert r.bandeja == "pendiente_revision"
    assert r.total == 0.0
    assert any("total" in a.lower() for a in r.avisos)


# ── Deteccion NIF: no cruza salto de linea ────────────────────────────────────

def test_nif_no_cruza_salto_de_linea():
    """Regresion: label NIF en una linea + valor en la siguiente no se detecta como NIF."""
    r = OcrParserService().parsear_y_validar(TEXTO_NIF_LABEL_LUEGO_OTRO_CAMPO)
    assert r.proveedor_nif == ""


def test_detectar_nif_cif_estandar():
    assert _detectar_nif("CIF: B12345678") == "B12345678"
    assert _detectar_nif("NIF: 12345678A") == "12345678A"
    assert _detectar_nif("NIF: X1234567A") == "X1234567A"


def test_detectar_nif_sin_etiqueta():
    assert _detectar_nif("Empresa B12345678 SA") == "B12345678"


def test_detectar_nif_no_detecta_cadenas_invalidas():
    # Texto sin etiqueta NIF/CIF ni patron valido de NIF
    assert _detectar_nif("Total a pagar: 1.234,56 euros") == ""
    assert _detectar_nif("Calle Mayor 42, 28001 Madrid") == ""


# ── Formatos de importe ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 1234.56),
    ("1,234.56", 1234.56),
    ("1234,56",  1234.56),
    ("1234.56",  1234.56),
    ("1.000",    1000.0),
    ("210,00",   210.0),
    ("0",        0.0),
    ("",         0.0),
])
def test_parse_amount_formatos(raw, expected):
    assert _parse_amount(raw) == pytest.approx(expected, abs=0.001)


# ── to_legacy_dict mantiene contrato ─────────────────────────────────────────

def test_to_legacy_dict_contrato_campos():
    svc = OcrParserService()
    r = svc.parsear_y_validar(FACTURA_COMPLETA)
    d = r.to_legacy_dict()
    for campo in ("proveedor_nif", "numero_factura", "fecha_factura",
                  "base_imponible", "cuota_iva", "total",
                  "bandeja", "error_mensaje", "lineas", "avisos"):
        assert campo in d, f"Campo '{campo}' ausente en to_legacy_dict()"
    assert isinstance(d["lineas"], list)
