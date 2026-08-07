import sqlite3

from models.gestor_sqlite import GestorSQLite


def test_migra_fecha_registro_en_tabla_de_cuotas_existente(tmp_path):
    db_path = tmp_path / "cuotas_legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE cuotas_periodicas_generadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuota_id TEXT NOT NULL,
            periodo TEXT NOT NULL,
            factura_id TEXT,
            UNIQUE(cuota_id, periodo)
        )
        """
    )
    conn.execute(
        "INSERT INTO cuotas_periodicas_generadas (cuota_id, periodo, factura_id) "
        "VALUES ('cuota-1', '2026-06', 'factura-1')"
    )
    conn.commit()
    conn.close()

    gestor = GestorSQLite(db_path)
    gestor.registrar_periodo_generado("cuota-1", "2026-07", "factura-2", "07/08/2026")

    columns = {
        row[1]
        for row in gestor.conn.execute(
            "PRAGMA table_info(cuotas_periodicas_generadas)"
        )
    }
    assert "fecha_registro" in columns
    row = gestor.conn.execute(
        "SELECT factura_id, fecha_registro "
        "FROM cuotas_periodicas_generadas WHERE cuota_id=? AND periodo=?",
        ("cuota-1", "2026-07"),
    ).fetchone()
    assert tuple(row) == ("factura-2", "07/08/2026")
