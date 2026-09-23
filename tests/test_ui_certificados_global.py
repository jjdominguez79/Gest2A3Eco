from datetime import date, datetime

from views.ui_certificados_global import (
    _fecha_caducidad_orden,
    _ordenar_por_caducidad,
)


def test_ordena_certificados_por_caducidad_ascendente_y_sin_fecha_al_final():
    certificados = [
        {"id": "sin-fecha", "fecha_caducidad": None},
        {"id": "lejano", "fecha_caducidad": "2028-05-20"},
        {"id": "invalido", "fecha_caducidad": "desconocida"},
        {"id": "proximo", "fecha_caducidad": "2026-10-01"},
    ]

    ordenados = _ordenar_por_caducidad(certificados)

    assert [certificado["id"] for certificado in ordenados] == [
        "proximo",
        "lejano",
        "sin-fecha",
        "invalido",
    ]


def test_invierte_el_orden_sin_adelantar_las_fechas_ausentes():
    certificados = [
        {"id": "proximo", "fecha_caducidad": date(2026, 10, 1)},
        {"id": "sin-fecha", "fecha_caducidad": ""},
        {"id": "lejano", "fecha_caducidad": datetime(2028, 5, 20, 12, 30)},
    ]

    ordenados = _ordenar_por_caducidad(certificados, descendente=True)

    assert [certificado["id"] for certificado in ordenados] == [
        "lejano",
        "proximo",
        "sin-fecha",
    ]


def test_normaliza_el_formato_espanol_de_fecha():
    assert _fecha_caducidad_orden("01/10/2026") == date(2026, 10, 1)
