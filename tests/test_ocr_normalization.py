"""
Tests unitarios para los parsers de importes y fechas OCR Azure.

Cubre:
  - _parse_importe: todos los formatos ES/EN con simbolos de moneda
  - _parse_fecha: formatos dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd
  - Normalizacion completa simulando respuestas Azure (valueString, valueCurrency, content)
  - Caso de referencia real: B56210032 / F260191 / 2026-07-22 / 280.98 / 59.02 / 340.00
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace

# Importar parsers desde los dos modulos afectados
from services.ocr.engines.azure_invoice_engine import (
    _parse_importe as engine_parse_importe,
    _parse_fecha   as engine_parse_fecha,
    _azure_float   as engine_azure_float,
    _azure_fecha   as engine_azure_fecha,
    AzureInvoiceEngine,
)
from backend.api.ocr_service import (
    _parse_importe as backend_parse_importe,
    _parse_fecha   as backend_parse_fecha,
    _azure_float   as backend_azure_float,
    _azure_fecha   as backend_azure_fecha,
    _mapear_documento,
)


# ── Helpers de construccion de campos simulados ──────────────────────────────

def _field_currency(amount: float, content: str = ""):
    """Simula un campo Azure valueCurrency."""
    return SimpleNamespace(
        value=SimpleNamespace(amount=amount, currency_symbol="€"),
        value_string=None,
        content=content or f"{amount:.2f} €",
        confidence=0.95,
    )


def _field_string(s: str):
    """Simula un campo Azure valueString (modelo personalizado)."""
    return SimpleNamespace(
        value=s,
        value_string=s,
        content=s,
        confidence=0.90,
    )


def _field_content_only(s: str):
    """Simula un campo sin value pero con content."""
    return SimpleNamespace(
        value=None,
        value_string=None,
        content=s,
        confidence=0.80,
    )


def _field_date(date_obj):
    """Simula un campo Azure valueDate."""
    return SimpleNamespace(
        value=date_obj,
        value_string=None,
        content=str(date_obj),
        confidence=0.95,
    )


def _field_string_date(s: str):
    """Simula un campo fecha como valueString."""
    return SimpleNamespace(
        value=s,
        value_string=s,
        content=s,
        confidence=0.88,
    )


# ── Tests del parser de importes ──────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("340,00€",    340.0),
    ("280,98€",    280.98),
    ("59,02€",     59.02),
    ("1.234,56 €", 1234.56),
    ("1,234.56",   1234.56),
    ("1234.56",    1234.56),
    ("1234,56",    1234.56),
    ("€340,00",    340.0),
    ("",           0.0),
    (None,         0.0),
    ("0",          0.0),
    ("0,00",       0.0),
    # "1.000" sin coma es ambiguo (1.0 EN vs 1000 ES); sin contexto no se puede
    # resolver. Azure siempre envia importes con decimales explicitos (ej: "1.000,00")
    # asi que este caso borde no aparece en la practica con el modelo personalizado.
    ("210,00",     210.0),
])
def test_engine_parse_importe(raw, expected):
    assert engine_parse_importe(raw) == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize("raw,expected", [
    ("340,00€",    340.0),
    ("280,98€",    280.98),
    ("59,02€",     59.02),
    ("1.234,56 €", 1234.56),
    ("1,234.56",   1234.56),
    ("1234.56",    1234.56),
    ("1234,56",    1234.56),
    ("€340,00",    340.0),
    ("",           0.0),
    (None,         0.0),
])
def test_backend_parse_importe(raw, expected):
    assert backend_parse_importe(raw) == pytest.approx(expected, abs=0.001)


# ── Tests del parser de fechas ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("22/07/2026",  "2026-07-22"),
    ("22-07-2026",  "2026-07-22"),
    ("2026-07-22",  "2026-07-22"),
    ("1/1/2026",    "2026-01-01"),
    (None,          ""),
    ("",            ""),
])
def test_engine_parse_fecha(raw, expected):
    assert engine_parse_fecha(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("22/07/2026",  "2026-07-22"),
    ("22-07-2026",  "2026-07-22"),
    ("2026-07-22",  "2026-07-22"),
    (None,          ""),
    ("",            ""),
])
def test_backend_parse_fecha(raw, expected):
    assert backend_parse_fecha(raw) == expected


# ── Tests de azure_float con distintos tipos de campo ────────────────────────

def test_azure_float_currency_object():
    """Caso 1: campo valueCurrency → usa .amount directamente."""
    f = _field_currency(340.00, "340,00 €")
    assert engine_azure_float(f) == pytest.approx(340.0)
    assert backend_azure_float(f) == pytest.approx(340.0)


def test_azure_float_value_string_con_euro():
    """Caso 2: campo valueString con '340,00€' → debe parsear correctamente."""
    f = _field_string("340,00€")
    assert engine_azure_float(f) == pytest.approx(340.0)
    assert backend_azure_float(f) == pytest.approx(340.0)


def test_azure_float_content_only_con_euro():
    """Caso 3: solo content '340,00€' → debe parsear correctamente."""
    f = _field_content_only("340,00€")
    assert engine_azure_float(f) == pytest.approx(340.0)
    assert backend_azure_float(f) == pytest.approx(340.0)


def test_azure_float_campo_none():
    """Caso 5: campo None → 0.0."""
    assert engine_azure_float(None) == 0.0
    assert backend_azure_float(None) == 0.0


def test_azure_float_contenido_invalido():
    """Caso 6: contenido 'N/A' → 0.0."""
    f = _field_string("N/A")
    assert engine_azure_float(f) == 0.0
    assert backend_azure_float(f) == 0.0


# ── Tests de azure_fecha con distintos tipos de campo ────────────────────────

def test_azure_fecha_value_date_object():
    """Campo valueDate como objeto date → isoformat."""
    import datetime
    f = _field_date(datetime.date(2026, 7, 22))
    assert engine_azure_fecha(f) == "2026-07-22"
    assert backend_azure_fecha(f) == "2026-07-22"


def test_azure_fecha_value_string_slash():
    """Caso 4: fecha como valueString '22/07/2026' → '2026-07-22'."""
    f = _field_string_date("22/07/2026")
    assert engine_azure_fecha(f) == "2026-07-22"
    assert backend_azure_fecha(f) == "2026-07-22"


def test_azure_fecha_value_string_guion():
    """Fecha como valueString '22-07-2026' → '2026-07-22'."""
    f = _field_string_date("22-07-2026")
    assert engine_azure_fecha(f) == "2026-07-22"
    assert backend_azure_fecha(f) == "2026-07-22"


def test_azure_fecha_value_string_iso():
    """Fecha ya en ISO '2026-07-22' → '2026-07-22' sin cambios."""
    f = _field_string_date("2026-07-22")
    assert engine_azure_fecha(f) == "2026-07-22"
    assert backend_azure_fecha(f) == "2026-07-22"


def test_azure_fecha_campo_none():
    assert engine_azure_fecha(None) == ""
    assert backend_azure_fecha(None) == ""


# ── Test de normalizacion completa: caso real de referencia ──────────────────

def test_normalizacion_completa_motor_engine_caso_real():
    """
    Caso real: proveedor B56210032, factura F260191, fecha 22/07/2026,
    base 280,98€, IVA 59,02€, total 340,00€ — todos como valueString.

    El resultado debe coincidir exactamente con los valores esperados.
    """
    import datetime

    field_str = _field_string
    field_curr = _field_currency

    doc = SimpleNamespace(fields={
        "ProveedorNif":    field_str("B56210032"),
        "ProveedorNombre": field_str("Proveedor Ejemplo SL"),
        "NumeroFactura":   field_str("F260191"),
        "FechaFactura":    field_str("22/07/2026"),
        "TotalFactura":    field_str("340,00€"),
        "BaseTotal":       field_str("280,98€"),
        "IvaTotal":        field_str("59,02€"),
    })

    result = AzureInvoiceEngine("endpoint", "key", "facturas-produccion-v1")._mapear_documento(doc, None)

    assert result.proveedor_nif  == "B56210032"
    assert result.numero_factura == "F260191"
    assert result.fecha_factura  == "2026-07-22"
    assert result.base_total     == pytest.approx(280.98, abs=0.01)
    assert result.iva_total      == pytest.approx(59.02,  abs=0.01)
    assert result.total          == pytest.approx(340.00, abs=0.01)


def test_normalizacion_completa_motor_engine_valuecurrency():
    """
    Mismo caso real pero los importes vienen como valueCurrency.
    """
    doc = SimpleNamespace(fields={
        "ProveedorNif":    _field_string("B56210032"),
        "ProveedorNombre": _field_string("Proveedor Ejemplo SL"),
        "NumeroFactura":   _field_string("F260191"),
        "FechaFactura":    _field_string("22/07/2026"),
        "TotalFactura":    _field_currency(340.00, "340,00 €"),
        "BaseTotal":       _field_currency(280.98, "280,98 €"),
        "IvaTotal":        _field_currency(59.02,  "59,02 €"),
    })

    result = AzureInvoiceEngine("endpoint", "key", "facturas-produccion-v1")._mapear_documento(doc, None)

    assert result.proveedor_nif  == "B56210032"
    assert result.numero_factura == "F260191"
    assert result.fecha_factura  == "2026-07-22"
    assert result.base_total     == pytest.approx(280.98, abs=0.01)
    assert result.iva_total      == pytest.approx(59.02,  abs=0.01)
    assert result.total          == pytest.approx(340.00, abs=0.01)


def test_normalizacion_backend_caso_real():
    """
    Simula la respuesta del backend (dict de campos) con el caso real.
    Usa _mapear_documento del backend que trabaja con objetos del SDK.
    """
    doc = SimpleNamespace(fields={
        "ProveedorNif":    _field_string("B56210032"),
        "ProveedorNombre": _field_string("Proveedor Ejemplo SL"),
        "NumeroFactura":   _field_string("F260191"),
        "FechaFactura":    _field_string("22/07/2026"),
        "TotalFactura":    _field_string("340,00€"),
        "BaseTotal":       _field_string("280,98€"),
        "IvaTotal":        _field_string("59,02€"),
    })

    result = _mapear_documento(doc, model_id="facturas-produccion-v1")

    assert result["proveedor_nif"]  == "B56210032"
    assert result["numero_factura"] == "F260191"
    assert result["fecha_factura"]  == "2026-07-22"
    assert result["base_total"]     == pytest.approx(280.98, abs=0.01)
    assert result["iva_total"]      == pytest.approx(59.02,  abs=0.01)
    assert result["total"]          == pytest.approx(340.00, abs=0.01)


def test_normalizacion_campos_no_existen():
    """Caso 5: campos no existen → valores cero/vacios, no excepcion."""
    doc = SimpleNamespace(fields={})
    result = AzureInvoiceEngine("endpoint", "key")._mapear_documento(doc, None)
    assert result.total      == 0.0
    assert result.base_total == 0.0
    assert result.iva_total  == 0.0
    assert result.fecha_factura == ""


def test_normalizacion_contenido_invalido():
    """Caso 6: contenido invalido 'N/A' → cero sin excepcion."""
    doc = SimpleNamespace(fields={
        "TotalFactura": _field_string("N/A"),
        "BaseTotal":    _field_string("N/A"),
        "IvaTotal":     _field_string("N/A"),
    })
    result = AzureInvoiceEngine("endpoint", "key")._mapear_documento(doc, None)
    assert result.total      == 0.0
    assert result.base_total == 0.0
    assert result.iva_total  == 0.0


def test_normalizacion_to_dict_contrato():
    """El resultado tiene todos los campos del contrato OcrInvoiceResult."""
    doc = SimpleNamespace(fields={
        "ProveedorNif":  _field_string("B56210032"),
        "NumeroFactura": _field_string("F260191"),
        "FechaFactura":  _field_string("22/07/2026"),
        "TotalFactura":  _field_string("340,00€"),
        "BaseTotal":     _field_string("280,98€"),
        "IvaTotal":      _field_string("59,02€"),
    })
    result = AzureInvoiceEngine("endpoint", "key", "facturas-produccion-v1")._mapear_documento(doc, None)
    d = result.to_dict()
    for campo in ("proveedor_nif", "numero_factura", "fecha_factura",
                  "base_total", "iva_total", "total", "bases_iva", "errores"):
        assert campo in d, f"Campo '{campo}' ausente en to_dict()"
    assert d["proveedor_nif"]  == "B56210032"
    assert d["numero_factura"] == "F260191"
    assert d["fecha_factura"]  == "2026-07-22"
    assert d["base_total"]     == pytest.approx(280.98, abs=0.01)
    assert d["iva_total"]      == pytest.approx(59.02,  abs=0.01)
    assert d["total"]          == pytest.approx(340.00, abs=0.01)
