"""Tests de contrato del QR fiscal (Etapa 6).

No certifican cumplimiento VeriFactu (ver docs/adr/0001, seccion 9/14):
fijan el formato de URL tal como se ha podido contrastar con fuentes
publicas que citan el RD 1007/2023 y la Orden HAC/1177/2024, y el
comportamiento de "referencia pendiente" mientras el envio fiscal real no
este activo.
"""

from decimal import Decimal

import pytest

from billing_worker.handlers.fiscal_qr import (
    AEAT_VALIDATION_BASE_URL,
    PENDING_LEGAL_PHRASE,
    VERIFACTU_LEGAL_PHRASE,
    build_aeat_validation_url,
    build_pending_reference_payload,
)


def test_aeat_url_contains_the_four_mandatory_parameters_in_order():
    url = build_aeat_validation_url(
        nif="89890001K", numserie="12345678/G33",
        fecha="01-01-2026", importe=Decimal("241.40"),
    )
    assert url.startswith(AEAT_VALIDATION_BASE_URL + "?")
    assert "nif=89890001K" in url
    assert "fecha=01-01-2026" in url
    assert "importe=241.40" in url
    # numserie se url-codifica (la barra se convierte a %2F).
    assert "numserie=12345678%2FG33" in url


def test_ampersand_inside_numserie_is_percent_encoded():
    url = build_aeat_validation_url(
        nif="89890001K", numserie="12345678&G33",
        fecha="01-01-2026", importe=Decimal("100"),
    )
    assert "numserie=12345678%26G33" in url
    # Nunca debe aparecer un '&' literal fuera de los separadores de query.
    query = url.split("?", 1)[1]
    parts = query.split("&")
    assert len(parts) == 4


def test_importe_is_always_formatted_with_two_decimals():
    url = build_aeat_validation_url(
        nif="B12345678", numserie="APP-000001",
        fecha="05-03-2026", importe=Decimal("1500"),
    )
    assert "importe=1500.00" in url


@pytest.mark.parametrize("missing_field", ["nif", "numserie", "fecha"])
def test_missing_required_field_raises(missing_field):
    kwargs = dict(
        nif="B12345678", numserie="APP-000001",
        fecha="05-03-2026", importe=Decimal("10"),
    )
    kwargs[missing_field] = ""
    with pytest.raises(ValueError):
        build_aeat_validation_url(**kwargs)


def test_pending_reference_is_not_an_aeat_url():
    payload = build_pending_reference_payload(
        organization_code="GESTINEM", series_code="APP", invoice_number=42,
    )
    assert "agenciatributaria" not in payload.lower()
    assert "GESTINEM" in payload
    assert "000042" in payload


def test_legal_phrases_are_distinct_and_never_confused():
    """El texto VERI*FACTU nunca debe imprimirse mientras no haya envio real."""
    assert VERIFACTU_LEGAL_PHRASE != PENDING_LEGAL_PHRASE
    assert "VERI*FACTU" in VERIFACTU_LEGAL_PHRASE
    assert "VERI*FACTU" not in PENDING_LEGAL_PHRASE or "no acogido" in PENDING_LEGAL_PHRASE
