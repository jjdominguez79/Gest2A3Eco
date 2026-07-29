from models.gestor_sqlite import GestorSQLite


def test_actualizar_numero_asiento_factura_emitida_actualiza_solo_la_factura(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_factura_emitida(
        {
            "id": "fac-1",
            "codigo_empresa": "E00001",
            "ejercicio": 2026,
            "numero": "1",
            "fecha_asiento": "2026-01-01",
            "lineas": [],
        }
    )

    assert gestor.actualizar_numero_asiento_factura_emitida("E00001", "fac-1", "42")
    factura = gestor.listar_facturas_emitidas("E00001", 2026)[0]
    assert factura["numero_asiento"] == "42"
