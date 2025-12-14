import csv
import sqlite3
from pathlib import Path

DB_PATH  = r"Gest2A3Eco.db"   # ruta a tu .db
CSV_PATH = r"empresas.csv"    # ruta a tu csv

TABLE = "empresas"
PK_COLS = ("codigo", "ejercicio")  # PK compuesta


def table_columns(conn, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def normalize(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    return s


def normalize_codigo(v):
    """
    Devuelve el codigo como texto de 5 dígitos con ceros a la izquierda.
    Si viene vacío o None, devuelve None.
    """
    s = normalize(v)
    if s is None:
        return None
    # Asegura longitud 5 rellenando a la izquierda; si es más largo, se respeta
    return s.zfill(5)


def to_int_or_none(v):
    v = normalize(v)
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", ".")))
    except Exception:
        return None


# Columnas INTEGER de tu tabla (para no insertar texto donde toca int)
INT_COLS = {
    "ejercicio",
    "digitos_plan",
    "siguiente_num_emitidas",
}


def _detect_dialect(f) -> csv.Dialect:
    sample = f.read(4096)
    f.seek(0)
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t")
    except Exception:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","

        class _Dialect(csv.Dialect):
            delimiter = delimiter
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return _Dialect


def import_empresas_csv(db_path: str, csv_path: str) -> int:
    """
    Importa/actualiza empresas desde un CSV.

    - Detecta delimitador (; , o tab) de forma automatica (Excel suele usar ;)
    - Acepta cabeceras con mayusculas/minusculas diferentes (Codigo, CODIGO, etc.)
    """
    db_path = str(Path(db_path).resolve())
    csv_path = str(Path(csv_path).resolve())

    with sqlite3.connect(db_path) as conn:
        cols_db = table_columns(conn, TABLE)
        cols_db_map = {c.lower(): c for c in cols_db}  # normaliza nombres

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            dialect = _detect_dialect(f)
            rdr = csv.DictReader(f, dialect=dialect)

            if rdr.fieldnames is None:
                raise ValueError("El CSV no tiene cabecera (header).")

            # CSV -> solo columnas que existen en la tabla (case-insensitive)
            csv_cols = []
            for name in rdr.fieldnames:
                key = (name or "").strip().lower()
                if key in cols_db_map:
                    csv_cols.append(cols_db_map[key])

            # Debe incluir PK completa
            for c in PK_COLS:
                if c not in csv_cols:
                    raise ValueError(f"El CSV debe incluir la columna obligatoria '{c}' (PK compuesta).")

            col_list = ",".join(csv_cols)
            placeholders = ",".join(["?"] * len(csv_cols))

            # ON CONFLICT(codigo, ejercicio)
            update_cols = [c for c in csv_cols if c not in PK_COLS]
            if update_cols:
                set_clause = ",".join([f"{c}=excluded.{c}" for c in update_cols])
                sql = f"""
                    INSERT INTO {TABLE} ({col_list})
                    VALUES ({placeholders})
                    ON CONFLICT({",".join(PK_COLS)}) DO UPDATE SET
                    {set_clause}
                """
            else:
                # Si solo vinieran PKs (raro), hacemos ignore
                sql = f"""
                    INSERT OR IGNORE INTO {TABLE} ({col_list})
                    VALUES ({placeholders})
                """

            cur = conn.cursor()
            n = 0

            for row in rdr:
                # normaliza claves del CSV a las de BD (case-insensitive)
                norm_row = {}
                for k, v in row.items():
                    nk = (k or "").strip().lower()
                    if nk in cols_db_map:
                        norm_row[cols_db_map[nk]] = v

                values = []
                for c in csv_cols:
                    val = norm_row.get(c)
                    if c == "codigo":
                        values.append(normalize_codigo(val))
                    elif c in INT_COLS:
                        values.append(to_int_or_none(val))
                    else:
                        values.append(normalize(val))

                cur.execute(sql, values)
                n += 1

            conn.commit()
            return n


def actualizar_empresas_csv_todos_ejercicios(db_path: str, csv_path: str) -> int:
    """
    Actualiza datos de empresas para todos sus ejercicios usando el CSV.

    - Solo necesita la columna 'codigo'. 'ejercicio' es opcional.
    - Si el CSV incluye 'ejercicio', solo actualiza ese ejercicio.
    - Si no incluye 'ejercicio', replica los cambios a todos los ejercicios existentes de la empresa.
    - No crea ejercicios nuevos; solo actualiza los que existan.
    """
    db_path = str(Path(db_path).resolve())
    csv_path = str(Path(csv_path).resolve())

    with sqlite3.connect(db_path) as conn:
        cols_db = table_columns(conn, TABLE)
        cols_db_map = {c.lower(): c for c in cols_db}

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            dialect = _detect_dialect(f)
            rdr = csv.DictReader(f, dialect=dialect)
            if rdr.fieldnames is None:
                raise ValueError("El CSV no tiene cabecera (header).")

            # columnas presentes en CSV y en BD
            csv_cols = []
            for name in rdr.fieldnames:
                key = (name or "").strip().lower()
                if key in cols_db_map:
                    csv_cols.append(cols_db_map[key])

            if "codigo" not in csv_cols:
                raise ValueError("El CSV debe incluir la columna obligatoria 'codigo'.")

            tiene_ej = "ejercicio" in csv_cols
            update_cols = [c for c in csv_cols if c not in ("codigo", "ejercicio")]
            if not update_cols:
                return 0  # nada que actualizar

            set_clause = ",".join([f"{c}=?" for c in update_cols])
            sql_update = f"UPDATE {TABLE} SET {set_clause} WHERE codigo=? AND ejercicio=?"

            cur = conn.cursor()
            total_updates = 0

            for row in rdr:
                norm_row = {}
                for k, v in row.items():
                    nk = (k or "").strip().lower()
                    if nk in cols_db_map:
                        norm_row[cols_db_map[nk]] = v

                codigo = normalize_codigo(norm_row.get("codigo"))
                if not codigo:
                    continue

                ejercicios_objetivo = []
                if tiene_ej:
                    ej = to_int_or_none(norm_row.get("ejercicio"))
                    if ej is not None:
                        ejercicios_objetivo.append(ej)
                else:
                    cur_ej = conn.execute(
                        "SELECT ejercicio FROM empresas WHERE codigo=?",
                        (codigo,),
                    )
                    ejercicios_objetivo = [r[0] for r in cur_ej.fetchall()]

                if not ejercicios_objetivo:
                    continue

                values_base = []
                for c in update_cols:
                    val = norm_row.get(c)
                    if c in INT_COLS:
                        values_base.append(to_int_or_none(val))
                    else:
                        values_base.append(normalize(val))

                for ej in ejercicios_objetivo:
                    cur.execute(sql_update, [*values_base, codigo, ej])
                    if cur.rowcount:
                        total_updates += 1

            conn.commit()
            return total_updates


if __name__ == "__main__":
    n = import_empresas_csv(DB_PATH, CSV_PATH)
    print(f"Importadas/actualizadas {n} filas en '{TABLE}'.")
