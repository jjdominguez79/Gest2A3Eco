from models.gestor_sqlite import GestorSQLite
from services.historial_importaciones_bancos import (
    analizar_duplicados_banco,
    normalizar_movimientos_banco,
    resumir_importacion_banco,
)


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


def test_detecta_solapamiento_y_deja_movimiento_tardio_como_nuevo():
    anteriores = normalizar_movimientos_banco([
        {"Fecha Asiento": "25/02/2026", "Importe": "100", "Concepto": "Cobro A"},
        {"Fecha Asiento": "25/02/2026", "Importe": "-20", "Concepto": "Pago B"},
    ])
    actuales = [
        {"Fecha Asiento": "25/02/2026", "Importe": "100", "Concepto": "Cobro A"},
        {"Fecha Asiento": "25/02/2026", "Importe": "-20", "Concepto": "Pago B"},
        {"Fecha Asiento": "25/02/2026", "Importe": "75", "Concepto": "Cobro tardio"},
    ]

    analisis = analizar_duplicados_banco(actuales, anteriores, [{"id": 1}])

    assert len(analisis["duplicados"]) == 2
    assert len(analisis["nuevos"]) == 1
    assert analisis["nuevos"][0]["concepto"] == "Cobro tardio"
    assert analisis["hay_conflicto"] is True


def test_movimientos_identicos_se_controlan_por_numero_de_apariciones():
    fila = {"Fecha Asiento": "10/03/2026", "Importe": "-9,99", "Concepto": "Comision"}
    anteriores = normalizar_movimientos_banco([fila, fila])

    analisis = analizar_duplicados_banco([fila, fila, fila], anteriores)

    assert len(analisis["duplicados"]) == 2
    assert len(analisis["nuevos"]) == 1
    assert analisis["nuevos"][0]["ocurrencia"] == 3


def test_referencia_existente_con_importe_distinto_se_marca_modificada():
    anteriores = normalizar_movimientos_banco([{
        "Fecha Asiento": "10/03/2026", "Importe": "100",
        "Concepto": "Ingreso", "Referencia": "REF-1",
    }])
    actuales = [{
        "Fecha Asiento": "10/03/2026", "Importe": "120",
        "Concepto": "Ingreso corregido", "Referencia": "REF-1",
    }]

    analisis = analizar_duplicados_banco(actuales, anteriores)

    assert len(analisis["modificados"]) == 1
    assert analisis["nuevos"] == []


def test_gestor_guarda_movimientos_y_busca_solapamientos(tmp_path):
    gestor = GestorSQLite(tmp_path / "movimientos.db")
    plantilla = {
        "banco": "Banco prueba", "numero_cuenta": "ES01",
        "subcuenta_banco": "57200001",
    }
    importacion_id = gestor.crear_importacion_banco({
        "codigo_empresa": "E00001", "ejercicio": 2026,
        **plantilla, "usuario": "maria", "estado": "CORRECTA",
        "fecha_primer_asiento": "20260101",
        "fecha_ultimo_asiento": "20260225",
    })
    movimientos = normalizar_movimientos_banco([{
        "Fecha Asiento": "25/02/2026", "Importe": "10",
        "Concepto": "Movimiento", "Referencia": "R1",
    }])
    gestor.guardar_movimientos_importacion_banco(
        importacion_id,
        {"codigo_empresa": "E00001", "ejercicio": 2026, **plantilla},
        movimientos,
    )

    guardados = gestor.listar_movimientos_importados_banco(
        "E00001", 2026, plantilla
    )
    solapadas = gestor.listar_importaciones_banco_solapadas(
        "E00001", 2026, plantilla, "20260201", "20260301"
    )

    assert len(guardados) == 1
    assert guardados[0]["referencia"] == "R1"
    assert [item["id"] for item in solapadas] == [importacion_id]
