from main import _comprobar_motor_pdf


def test_motor_pdf_crea_y_renderiza_una_pagina():
    assert _comprobar_motor_pdf() == 0
