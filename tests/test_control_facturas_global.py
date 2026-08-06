from models.gestor_sqlite import GestorSQLite


def test_listar_control_facturas_global_unifica_y_limita_empresas(tmp_path):
    gestor = GestorSQLite(tmp_path / "control.db")
    gestor.conn.execute(
        """INSERT INTO facturas_emitidas_docs
           (id, codigo_empresa, ejercicio, serie, numero, nombre, generada, estado_contable, lineas_json)
           VALUES ('e1', 'E00001', 2026, 'A', '1', 'Cliente', 1, 'generado', '[]')"""
    )
    gestor.conn.execute(
        """INSERT INTO facturas_recibidas_docs
           (id, codigo_empresa, ejercicio, proveedor_nombre, numero_factura, total, generada,
            estado_contable, created_at, updated_at)
           VALUES ('r1', 'E00001', 2026, 'Proveedor', 'R-1', 121.0, 0,
                   'pendiente_contabilizar', '2026-01-01', '2026-01-01')"""
    )
    gestor.conn.execute(
        """INSERT INTO facturas_emitidas_docs
           (id, codigo_empresa, ejercicio, serie, numero, nombre, generada, lineas_json)
           VALUES ('privada', 'E99999', 2026, 'A', '2', 'No visible', 0, '[]')"""
    )
    gestor.conn.commit()

    rows = gestor.listar_control_facturas_global(['E00001'])

    assert {row['id'] for row in rows} == {'e1', 'r1'}
    assert {row['tipo'] for row in rows} == {'emitida', 'recibida'}
    recibida = next(row for row in rows if row['id'] == 'r1')
    assert recibida['total'] == 121.0
