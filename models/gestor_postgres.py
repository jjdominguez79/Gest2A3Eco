"""Adaptador PostgreSQL para la API publica de :mod:`gestor_sqlite`.

La migracion se realiza previamente con ``procesos.migrar_sqlite_postgres``.
Este gestor no crea tablas automaticamente: asi se evita que un puesto cliente
pueda inicializar por error una base de produccion vacia.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from models.gestor_sqlite import GestorSQLite


class DatabasePostgresError(RuntimeError):
    pass


def crear_dsn_postgres(host: str, port: int | str, database: str, user: str, password: str) -> str:
    """Crea una cadena de conexion escapando credenciales de forma segura."""
    try:
        from psycopg.conninfo import make_conninfo
    except ImportError as exc:
        raise DatabasePostgresError(
            "Falta la dependencia psycopg para conectar con PostgreSQL."
        ) from exc
    return make_conninfo(
        host=str(host or "").strip(),
        port=int(port),
        dbname=str(database or "").strip(),
        user=str(user or "").strip(),
        password=str(password or ""),
        connect_timeout=5,
    )


class FilaPostgres(dict):
    """Fila compatible con sqlite3.Row: admite clave de texto e indice."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _adaptar_fila(row):
    return None if row is None else FilaPostgres(row)


def _traducir_insert_replace(sql: str) -> str:
    patron = re.compile(
        r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([\w\"]+)\s*\(([^)]+)\)\s*(VALUES\s*\(.+\))\s*;?\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    match = patron.match(sql)
    if not match:
        return sql
    tabla, columnas, valores = match.groups()
    nombres = [columna.strip() for columna in columnas.split(",")]
    tabla_normalizada = tabla.strip('"').lower()
    claves_por_tabla = {
        "plan_cuentas": ("codigo_empresa", "ejercicio", "cuenta"),
    }
    claves = claves_por_tabla.get(tabla_normalizada)
    if not claves:
        # No se debe inventar una restriccion: mantener la instruccion para que
        # el error identifique cualquier caso SQLite nuevo que deba adaptarse.
        return sql
    claves_norm = {clave.lower() for clave in claves}
    actualizables = [nombre for nombre in nombres if nombre.strip('"').lower() not in claves_norm]
    actualizaciones = ", ".join(
        f"{nombre}=EXCLUDED.{nombre}" for nombre in actualizables
    )
    conflicto = ", ".join(claves)
    return (
        f"INSERT INTO {tabla} ({columnas}) {valores} "
        f"ON CONFLICT ({conflicto}) DO UPDATE SET {actualizaciones}"
    )


def traducir_sqlite_a_postgres(sql: str) -> str:
    """Traduce el subconjunto SQLite usado por GestorSQLite."""
    traducido = str(sql)
    traducido = _traducir_insert_replace(traducido)
    if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", traducido, re.IGNORECASE):
        traducido = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", traducido, count=1, flags=re.IGNORECASE)
        traducido = traducido.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return traducido.replace("?", "%s")


class CursorPostgres:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, sql: str, params=None):
        traducido = traducir_sqlite_a_postgres(sql)
        self._cursor.execute(traducido, params)
        if re.match(r"^\s*INSERT\b", traducido, re.IGNORECASE):
            try:
                row = self._cursor.connection.execute("SELECT LASTVAL()").fetchone()
                self.lastrowid = next(iter(row.values())) if isinstance(row, dict) else row[0]
            except Exception:
                self.lastrowid = None
        return self

    def executemany(self, sql: str, params_seq: Iterable):
        self._cursor.executemany(traducir_sqlite_a_postgres(sql), params_seq)
        return self

    def fetchone(self):
        return _adaptar_fila(self._cursor.fetchone())

    def fetchall(self):
        return [_adaptar_fila(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [_adaptar_fila(row) for row in rows]

    @property
    def description(self):
        """Metadatos con la forma de sqlite3.Cursor.description.

        Hay metodos historicos que obtienen los nombres mediante ``c[0]``.
        Psycopg expone objetos Column, por lo que se normalizan a tuplas.
        """
        descripcion = self._cursor.description or []
        return [(col.name, None, None, None, None, None, None) for col in descripcion]

    @property
    def rowcount(self):
        """Numero de filas afectadas, compatible con sqlite3.Cursor."""
        return self._cursor.rowcount

    def __iter__(self):
        return (_adaptar_fila(row) for row in self._cursor)

    def close(self):
        self._cursor.close()


class ConexionPostgres:
    def __init__(self, conexion):
        self._conexion = conexion

    def execute(self, sql: str, params=None):
        cursor = CursorPostgres(self._conexion.cursor())
        return cursor.execute(sql, params)

    def executemany(self, sql: str, params_seq: Iterable):
        cursor = CursorPostgres(self._conexion.cursor())
        return cursor.executemany(sql, params_seq)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()


class GestorPostgres(GestorSQLite):
    """Implementacion PostgreSQL de la API de GestorSQLite.

    Hereda los metodos de negocio ya existentes. La capa de conexion adapta
    marcadores, filas y las dos variantes ``INSERT OR ...`` utilizadas por la
    aplicacion.
    """

    def __init__(self, dsn: str):
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise DatabasePostgresError("No se ha configurado la conexion PostgreSQL.")
        try:
            import psycopg
            from psycopg.rows import dict_row

            conexion = psycopg.connect(self.dsn, row_factory=dict_row)
            self.conn = ConexionPostgres(conexion)
            existe = self.conn.execute("SELECT to_regclass('public.empresas')").fetchone()[0]
            if not existe:
                self.conn.close()
                raise DatabasePostgresError(
                    "La base PostgreSQL no contiene el esquema de Gest2A3Eco. "
                    "Ejecuta primero la migracion SQLite a PostgreSQL."
                )
            self._aplicar_migraciones_esenciales_postgres()
        except DatabasePostgresError:
            raise
        except Exception as exc:
            raise DatabasePostgresError(f"No se pudo abrir PostgreSQL: {exc}") from exc

    def _aplicar_migraciones_esenciales_postgres(self) -> None:
        """Crea elementos de seguridad que eran migraciones tardias de SQLite.

        Algunas instalaciones SQLite antiguas no las tienen hasta abrirse con
        una version reciente de la aplicacion. PostgreSQL debe quedar listo
        para autenticar desde el primer arranque posterior a la importacion.
        """
        columnas = (
            ("empresas", "cuenta_bancaria", "TEXT"),
            ("empresas", "cuentas_bancarias", "TEXT"),
            ("empresas", "pdf_ref_seq", "INTEGER"),
            ("empresas", "serie_emitidas_rect", "TEXT"),
            ("empresas", "siguiente_num_emitidas_rect", "INTEGER"),
            ("empresas", "logo_max_width_mm", "DOUBLE PRECISION"),
            ("empresas", "logo_max_height_mm", "DOUBLE PRECISION"),
            ("empresas", "pais", "TEXT"),
            ("empresas", "naf", "TEXT"),
            ("empresas", "responsable", "TEXT"),
            ("empresas", "activo", "INTEGER"),
            ("usuarios", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
        )
        for tabla, columna, tipo in columnas:
            self.conn.execute(
                f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}"
            )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios_permisos_globales (
              id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              usuario_id INTEGER NOT NULL,
              permiso TEXT NOT NULL,
              activo INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(usuario_id, permiso)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usuarios_permisos_globales_usuario "
            "ON usuarios_permisos_globales(usuario_id)"
        )
        self.conn.commit()
