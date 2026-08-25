"""Tests para el modulo de validacion de NIF/CIF y calculos fiscales."""

from decimal import Decimal

from backend.api.client_validation import (
    calculate_line_total,
    calculate_vat,
    calculate_withholding,
    normalize_tax_id,
    validate_cif,
    validate_nif,
    validate_tax_id,
)


class TestNormalizeTaxId:
    def test_mayusculas_y_espacios(self):
        assert normalize_tax_id("  12345678z  ") == "12345678Z"

    def test_guiones(self):
        assert normalize_tax_id("12-345-678-Z") == "12345678Z"

    def test_puntos(self):
        assert normalize_tax_id("B.1234.5678") == "B12345678"


class TestValidateNif:
    def test_nif_valido(self):
        assert validate_nif("12345678Z") is True

    def test_nif_valido_minusculas(self):
        assert validate_nif("12345678z") is True

    def test_nif_invalido_letra(self):
        assert validate_nif("12345678A") is False

    def test_nif_corto(self):
        assert validate_nif("1234567") is False

    def test_nie_valido_x(self):
        assert validate_nif("X1234567L") is True

    def test_nie_valido_y(self):
        assert validate_nif("Y1234567X") is True

    def test_nie_invalido(self):
        assert validate_nif("X1234567A") is False


class TestValidateCif:
    def test_cif_formato_valido(self):
        assert validate_cif("B12345678") is True

    def test_cif_con_letra_control(self):
        assert validate_cif("A1234567J") is True

    def test_cif_invalido_prefijo(self):
        assert validate_cif("Z12345678") is False

    def test_cif_corto(self):
        assert validate_cif("B1234") is False


class TestValidateTaxId:
    def test_nif_valido(self):
        assert validate_tax_id("12345678Z") is True

    def test_cif_valido(self):
        assert validate_tax_id("B12345678") is True

    def test_invalido(self):
        assert validate_tax_id("INVALIDO") is False


class TestCalculateLineTotal:
    def test_sin_descuento(self):
        result = calculate_line_total(
            Decimal("2"), Decimal("100.00"), Decimal("0"),
        )
        assert result == Decimal("200.00")

    def test_con_descuento(self):
        result = calculate_line_total(
            Decimal("1"), Decimal("100.00"), Decimal("10"),
        )
        assert result == Decimal("90.00")

    def test_redondeo(self):
        result = calculate_line_total(
            Decimal("3"), Decimal("33.33"), Decimal("0"),
        )
        assert result == Decimal("99.99")


class TestCalculateVat:
    def test_iva_21(self):
        assert calculate_vat(Decimal("100.00"), Decimal("21")) == Decimal("21.00")

    def test_iva_10(self):
        assert calculate_vat(Decimal("100.00"), Decimal("10")) == Decimal("10.00")

    def test_iva_redondeo(self):
        assert calculate_vat(Decimal("33.33"), Decimal("21")) == Decimal("7.00")


class TestCalculateWithholding:
    def test_retencion_15(self):
        result = calculate_withholding(Decimal("1000.00"), Decimal("15"))
        assert result == Decimal("150.00")

    def test_sin_retencion(self):
        result = calculate_withholding(Decimal("1000.00"), Decimal("0"))
        assert result == Decimal("0.00")
