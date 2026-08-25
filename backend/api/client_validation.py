"""Validacion compartida para el area del cliente: NIF, importes, etc."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP


# ---------- NIF/CIF/NIE ----------

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
_CIF_PATTERN = re.compile(r"^[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]$")


def normalize_tax_id(value: str) -> str:
    """Normaliza un NIF/CIF/NIE: mayusculas, sin espacios ni guiones."""
    return re.sub(r"[\s\-.]", "", value.strip().upper())


def validate_nif(value: str) -> bool:
    """Valida un NIF espanol (8 digitos + letra)."""
    v = normalize_tax_id(value)
    if len(v) != 9:
        return False
    if v[0] in _NIE_PREFIX:
        v = _NIE_PREFIX[v[0]] + v[1:]
    if not v[:8].isdigit():
        return False
    expected = _NIF_LETTERS[int(v[:8]) % 23]
    return v[8] == expected


def validate_cif(value: str) -> bool:
    """Valida un CIF espanol."""
    v = normalize_tax_id(value)
    return bool(_CIF_PATTERN.match(v))


def validate_tax_id(value: str) -> bool:
    """Valida NIF, NIE o CIF."""
    return validate_nif(value) or validate_cif(value)


# ---------- Importes ----------

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def round_currency(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con half-up."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_line_total(
    quantity: Decimal,
    unit_price: Decimal,
    discount_percent: Decimal,
) -> Decimal:
    """Calcula el importe de una linea antes de IVA."""
    gross = quantity * unit_price
    if discount_percent:
        gross = gross * (Decimal("1") - discount_percent / Decimal("100"))
    return round_currency(gross)


def calculate_vat(base: Decimal, rate: Decimal) -> Decimal:
    """Calcula la cuota de IVA."""
    return round_currency(base * rate / Decimal("100"))


def calculate_withholding(base: Decimal, rate: Decimal) -> Decimal:
    """Calcula la retencion sobre la base."""
    return round_currency(base * rate / Decimal("100"))
