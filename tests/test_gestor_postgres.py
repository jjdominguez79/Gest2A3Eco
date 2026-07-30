from models.gestor_postgres import (
    ConexionPostgres,
    CursorPostgres,
    FilaPostgres,
    GestorPostgres,
    crear_dsn_postgres,
    traducir_sqlite_a_postgres,
)


def test_traducir_sqlite_a_postgres_convierte_marcadores_e_ignore():
    sql = "INSERT OR IGNORE INTO tabla (id, nombre) VALUES (?, ?)"
    assert traducir_sqlite_a_postgres(sql) == (
        "INSERT INTO tabla (id, nombre) VALUES (%s, %s) ON CONFLICT DO NOTHING"
    )


def test_traducir_insert_replace_plan_cuentas_usa_clave_compuesta():
    sql = (
        "INSERT OR REPLACE INTO plan_cuentas "
        "(codigo_empresa, ejercicio, cuenta, descripcion) VALUES (?, ?, ?, ?)"
    )
    traducido = traducir_sqlite_a_postgres(sql)

    assert "ON CONFLICT (codigo_empresa, ejercicio, cuenta)" in traducido
    assert "descripcion=EXCLUDED.descripcion" in traducido
    assert "codigo_empresa=EXCLUDED.codigo_empresa" not in traducido


def test_fila_postgres_admite_indices_y_claves():
    fila = FilaPostgres({"id": 7, "nombre": "Gestinem"})
    assert fila[0] == 7
    assert fila["nombre"] == "Gestinem"


def test_traducir_sqlite_a_postgres_deja_ddl_postgres_sin_cambios():
    sql = "CREATE TABLE IF NOT EXISTS usuarios_permisos_globales (id INTEGER PRIMARY KEY)"
    assert traducir_sqlite_a_postgres(sql) == sql


def test_cursor_postgres_description_es_compatible_con_sqlite():
    class Columna:
        name = "codigo"

    class Cursor:
        description = [Columna()]
        rowcount = 3

    cursor = CursorPostgres(Cursor())
    assert cursor.description[0][0] == "codigo"
    assert cursor.rowcount == 3


def test_crear_dsn_postgres_escapa_password_especial():
    dsn = crear_dsn_postgres(
        host="192.168.0.19",
        port="5432",
        database="gest2a3eco",
        user="gest2a3eco",
        password="clave con ' comilla",
    )

    assert "host=192.168.0.19" in dsn
    assert "password='clave con \\' comilla'" in dsn


class _Resultado:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _ConexionFalsa:
    def __init__(self, secuencia=None, currval=None):
        self.secuencia = secuencia
        self.currval = currval
        self.rollback_count = 0
        self.commit_count = 0
        self.closed = False
        self.sentencias = []

    def execute(self, sql, params=None):
        if "pg_get_serial_sequence" in sql:
            return _Resultado({"pg_get_serial_sequence": self.secuencia})
        if "currval" in sql:
            return _Resultado({"currval": self.currval})
        raise AssertionError(sql)

    def rollback(self):
        self.rollback_count += 1

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True

    def cursor(self):
        return _CursorFalso(self)


class _CursorFalso:
    description = []

    def __init__(self, conexion, *, error=None):
        self.connection = conexion
        self.rowcount = 1
        self.error = error

    def execute(self, sql, params=None):
        if self.error:
            raise self.error
        self.connection.sentencias.append((sql, params))


def test_cursor_insert_textual_no_aborta_por_lastrowid():
    conexion = _ConexionFalsa(secuencia=None)
    cursor = CursorPostgres(_CursorFalso(conexion))

    cursor.execute("INSERT INTO terceros (id, nombre) VALUES (%s, %s)", ("t1", "Tercero"))

    assert cursor.lastrowid is None
    assert conexion.rollback_count == 0


def test_cursor_insert_identity_recupera_lastrowid():
    conexion = _ConexionFalsa(secuencia="public.usuarios_id_seq", currval=42)
    cursor = CursorPostgres(_CursorFalso(conexion))

    cursor.execute("INSERT INTO usuarios (nombre) VALUES (%s)", ("Usuario",))

    assert cursor.lastrowid == 42


def test_cursor_error_hace_rollback_para_recuperar_conexion():
    conexion = _ConexionFalsa()
    cursor = CursorPostgres(_CursorFalso(conexion, error=RuntimeError("sql incorrecto")))

    try:
        cursor.execute("SELECT columna_inexistente FROM tabla")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Se esperaba RuntimeError")

    assert conexion.rollback_count == 1


def test_conexion_postgres_context_manager_confirma_o_deshace():
    correcta = _ConexionFalsa()
    with ConexionPostgres(correcta):
        pass
    assert correcta.commit_count == 1

    fallida = _ConexionFalsa()
    try:
        with ConexionPostgres(fallida):
            raise ValueError("fallo")
    except ValueError:
        pass
    assert fallida.rollback_count == 1


def test_upsert_banco_confirma_plantilla_sin_columna_id():
    conexion = _ConexionFalsa(secuencia=None)
    gestor = object.__new__(GestorPostgres)
    gestor.conn = ConexionPostgres(conexion)
    plantilla = {
        "codigo_empresa": "E00193",
        "ejercicio": 2026,
        "banco": "Banco prueba",
        "numero_cuenta": "ES00",
        "subcuenta_banco": "57200001",
        "subcuenta_por_defecto": "55500000",
        "conceptos": [{"patron": "RECIBO*", "subcuenta": "41000001"}],
        "excel": {"primera_fila_procesar": 3, "columnas": {"Importe": "F"}},
    }

    gestor.upsert_banco(plantilla)

    assert conexion.rollback_count == 0
    assert conexion.commit_count == 1
    insert_sql, params = conexion.sentencias[0]
    assert "ON CONFLICT(codigo_empresa, ejercicio, banco)" in insert_sql
    assert params[0:6] == (
        "E00193", 2026, "Banco prueba", "ES00", "57200001", "55500000"
    )
    assert '"primera_fila_procesar": 3' in params[7]


def test_upsert_factura_emitida_con_id_textual_confirma_transaccion():
    conexion = _ConexionFalsa(secuencia=None)
    gestor = object.__new__(GestorPostgres)
    gestor.conn = ConexionPostgres(conexion)
    factura = {
        "id": "factura-empleado-809",
        "codigo_empresa": "E00809",
        "ejercicio": 2026,
        "serie": "A",
        "numero": "000009",
        "fecha_asiento": "30/07/2026",
        "nombre": "Cliente prueba",
        "borrador": 0,
        "lineas": [],
    }

    fid = gestor.upsert_factura_emitida(factura)

    assert fid == "factura-empleado-809"
    assert conexion.rollback_count == 0
    assert conexion.commit_count == 1
    insert_sql, params = conexion.sentencias[0]
    assert "INSERT INTO facturas_emitidas_docs" in insert_sql
    assert "ON CONFLICT(id) DO UPDATE" in insert_sql
    assert params[0:3] == ("factura-empleado-809", "E00809", 2026)
