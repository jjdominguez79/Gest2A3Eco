from datetime import date, datetime

from models.facturas_common import _cuenta_12, _fecha_yyyymmdd


def test_fecha_yyyymmdd_devuelve_ceros_para_vacio():
    assert _fecha_yyyymmdd(None) == "00000000"
    assert _fecha_yyyymmdd("") == "00000000"


def test_fecha_yyyymmdd_acepta_date_y_datetime():
    assert _fecha_yyyymmdd(date(2026, 5, 15)) == "20260515"
    assert _fecha_yyyymmdd(datetime(2026, 5, 15, 10, 30, 0)) == "20260515"


def test_fecha_yyyymmdd_acepta_formato_espanol():
    assert _fecha_yyyymmdd("15/05/2026") == "20260515"
    assert _fecha_yyyymmdd("15-05-26") == "20260515"


def test_fecha_yyyymmdd_acepta_mes_literal_es():
    assert _fecha_yyyymmdd("10 nov 2025") == "20251110"
    assert _fecha_yyyymmdd("01-ene-25") == "20250101"


def test_fecha_yyyymmdd_acepta_serial_excel():
    assert _fecha_yyyymmdd(45658) == "20250101"


def test_fecha_yyyymmdd_fecha_invalida_devuelve_ceros():
    assert _fecha_yyyymmdd("fecha-no-valida") == "00000000"


def test_cuenta_12_respeta_digitos_plan_y_rellena_a_derecha():
    assert _cuenta_12("430", ndig_plan=8) == "430000000000"
    assert _cuenta_12("43012", ndig_plan=5) == "430120000000"


def test_cuenta_12_recorta_si_supera_digitos_plan():
    assert _cuenta_12("4301234567", ndig_plan=8) == "430123450000"

