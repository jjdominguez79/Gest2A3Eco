from models.gestor_postgres import (
    CursorPostgres,
    FilaPostgres,
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
