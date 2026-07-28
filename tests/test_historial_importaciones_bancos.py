from models.gestor_sqlite import GestorSQLite
from services.historial_importaciones_bancos import resumir_importacion_banco


def test_resumen_calcula_periodo_saldos_y_movimientos():
    rows = [
        {"Fecha Asiento": "03/02/2026", "Importe": "-25,50", "Saldo": "974,50"},
        {"Fecha Asiento": "01/02/2026", "Importe": "100,00", "Saldo": "1.000,00"},
        {"Fecha Asiento": "fecha mala", "Importe": "9", "Saldo": "983,50"},
        {"Fecha Asiento": "04/02/2026", "Importe": "0", "Saldo": "974,50"},
    ]

    resumen = resumir_importacion_banco(rows, ["Una fecha invalida"])

    assert resumen["filas_leidas"] == 4
    assert resumen["movimientos_generados"] == 2
    assert resumen["movimientos_omitidos"] == 2
    assert resumen["fecha_primer_asiento"] == "20260201"
    assert resumen["fecha_ultimo_asiento"] == "20260203"
    assert resumen["saldo_primer_asiento"] == 1000
    assert resumen["saldo_final"] == 974.5
    assert resumen["importe_entradas"] == 100
    assert resumen["importe_salidas"] == 25.5
    assert resumen["variacion_neta"] == 74.5


def test_gestor_persiste_y_lista_historial(tmp_path):
    gestor = GestorSQLite(tmp_path / "historial.db")
    registro_id = gestor.crear_importacion_banco({
        "codigo_empresa": "E00001",
        "ejercicio": 2026,
        "banco": "Banco prueba",
        "numero_cuenta": "ES9121000418450200051332",
        "subcuenta_banco": "57200000",
        "usuario": "maria",
        "estado": "CON_AVISOS",
        "filas_leidas": 3,
        "movimientos_generados": 2,
        "movimientos_omitidos": 1,
        "avisos": ["Fila 3 omitida"],
    })

    registros = gestor.listar_importaciones_bancos("E00001", 2026)

    assert registros[0]["id"] == registro_id
    assert registros[0]["usuario"] == "maria"
    assert registros[0]["numero_cuenta"] == "ES9121000418450200051332"
    assert registros[0]["avisos"] == ["Fila 3 omitida"]
    assert gestor.listar_importaciones_bancos("E00002", 2026) == []


def test_saldo_final_es_cierre_del_ultimo_dia_con_extracto_invertido():
    rows = [
        # El banco entrega primero el movimiento mas reciente del mismo dia.
        {"Fecha Asiento": "03/02/2026", "Importe": "-20", "Saldo": "130"},
        {"Fecha Asiento": "03/02/2026", "Importe": "50", "Saldo": "150"},
        {"Fecha Asiento": "02/02/2026", "Importe": "100", "Saldo": "100"},
    ]

    resumen = resumir_importacion_banco(rows, [])

    assert resumen["fecha_ultimo_asiento"] == "20260203"
    assert resumen["saldo_final"] == 130
