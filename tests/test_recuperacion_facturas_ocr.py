from models.gestor_sqlite import GestorSQLite


def test_devuelve_facturas_ocr_pendientes_a_documentacion(tmp_path):
    gestor = GestorSQLite(tmp_path / "recuperacion.db")
    gestor.conn.execute(
        """INSERT INTO facturas_recibidas_docs
           (id,codigo_empresa,ejercicio,pdf_path,estado_ocr,estado_validacion,generada,created_at,updated_at)
           VALUES ('pendiente','E00001',2026,'C:/docs/factura.pdf','procesado','pendiente',0,'x','x')"""
    )
    gestor.conn.execute(
        """INSERT INTO facturas_recibidas_docs
           (id,codigo_empresa,ejercicio,pdf_path,estado_contable,generada,created_at,updated_at)
           VALUES ('cerrada','E00001',2026,'C:/docs/cerrada.pdf','contabilizada',1,'x','x')"""
    )
    gestor.conn.commit()

    result = gestor.devolver_facturas_recibidas_a_documentacion('E00001', 2026)

    assert result == {'archivadas': 1, 'omitidas_sin_ruta': 0}
    assert gestor.conn.execute("SELECT COUNT(*) FROM facturas_recibidas_docs").fetchone()[0] == 1
    archived = gestor.conn.execute("SELECT ruta,origen,estado FROM documentos_archivo").fetchone()
    assert tuple(archived) == ('C:/docs/factura.pdf', 'recuperacion_ocr', 'archivado')


def test_puede_recuperar_una_factura_contabilizada_solo_de_forma_explicita(tmp_path):
    gestor = GestorSQLite(tmp_path / "recuperacion-contabilizada.db")
    gestor.conn.execute(
        """INSERT INTO facturas_recibidas_docs
           (id,codigo_empresa,ejercicio,pdf_path,estado_contable,generada,created_at,updated_at)
           VALUES ('prueba','E00001',2026,'C:/docs/prueba.pdf','contabilizada',1,'x','x')"""
    )
    gestor.conn.commit()

    assert gestor.devolver_facturas_recibidas_a_documentacion('E00001', 2026)['archivadas'] == 0
    result = gestor.devolver_facturas_recibidas_a_documentacion(
        'E00001', 2026, incluir_contabilizadas=True,
    )

    assert result['archivadas'] == 1
    assert gestor.conn.execute("SELECT COUNT(*) FROM documentos_archivo").fetchone()[0] == 1
