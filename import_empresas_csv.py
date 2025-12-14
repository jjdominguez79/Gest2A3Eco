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


def import_empresas_csv(db_path: str, csv_path: str) -> int:
    db_path = str(Path(db_path).resolve())
    csv_path = str(Path(csv_path).resolve())

    with sqlite3.connect(db_path) as conn:
        cols_db = set(table_columns(conn, TABLE))

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)

            if rdr.fieldnames is None:
                raise ValueError("El CSV no tiene cabecera (header).")

            # CSV -> solo columnas que existen en la tabla
            csv_cols = [c for c in rdr.fieldnames if c in cols_db]

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
                values = []
                for c in csv_cols:
                    if c == "codigo":
                        values.append(normalize_codigo(row.get(c)))
                    elif c in INT_COLS:
                        values.append(to_int_or_none(row.get(c)))
                    else:
                        values.append(normalize(row.get(c)))

                cur.execute(sql, values)
                n += 1

            conn.commit()
            return n


if __name__ == "__main__":
    n = import_empresas_csv(DB_PATH, CSV_PATH)
    print(f"Importadas/actualizadas {n} filas en '{TABLE}'.")
