from procesos.bancos import generar_bancos


def test_generar_bancos_omite_fechas_invalidas_y_devuelve_aviso():
    plantilla = {
        "subcuenta_banco": "57200000",
        "subcuenta_por_defecto": "43000000",
        "conceptos": [],
    }
    rows = [
        {"Fecha Asiento": "fecha-mala", "Importe": "10,00", "Concepto": "Cobro"},
    ]

    out_lines, avisos = generar_bancos(rows, plantilla, "E00001", 8)

    assert out_lines == []
    assert len(avisos) == 1
    assert "fecha inválida" in avisos[0].lower()


def test_generar_bancos_genera_registros_para_movimiento_valido():
    plantilla = {
        "subcuenta_banco": "57200000",
        "subcuenta_por_defecto": "43000000",
        "conceptos": [{"patron": "*nomina*", "subcuenta": "64000000"}],
    }
    rows = [
        {"Fecha Asiento": "15/05/2026", "Importe": "-1250,50", "Concepto": "Pago nomina mayo"},
    ]

    out_lines, avisos = generar_bancos(rows, plantilla, "E00001", 8)

    assert avisos == []
    assert len(out_lines) == 2
    assert all(line.endswith("\r\n") for line in out_lines)
