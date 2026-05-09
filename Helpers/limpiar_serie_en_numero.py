"""
Migracion puntual: elimina el prefijo de serie del campo 'numero' en
facturas_emitidas_docs y albaranes_emitidas_docs.

Ejemplo: si serie='A' y numero='A000123' -> numero='000123'
         si serie='R' y numero='R000005' -> numero='000005'

Ejecutar una sola vez desde la raiz del proyecto:
    python Helpers/limpiar_serie_en_numero.py
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "plantillas" / "gest2a3eco.db"


def _limpiar_tabla(conn: sqlite3.Connection, tabla: str) -> int:
    cur = conn.execute(
        f"SELECT id, serie, numero FROM {tabla} WHERE serie IS NOT NULL AND serie != '' AND numero IS NOT NULL AND numero != ''"
    )
    filas = cur.fetchall()
    actualizadas = 0
    for id_, serie, numero in filas:
        serie = str(serie).strip()
        numero_str = str(numero).strip()
        if not serie:
            continue
        # Si el numero empieza con la serie (case-insensitive), quitar el prefijo
        if numero_str.upper().startswith(serie.upper()):
            nuevo_numero = numero_str[len(serie):]
            # Solo actualizar si lo que queda contiene solo digitos (o esta vacio)
            if nuevo_numero == "" or nuevo_numero.lstrip("0") == "" or nuevo_numero.isdigit():
                conn.execute(
                    f"UPDATE {tabla} SET numero=? WHERE id=?",
                    (nuevo_numero, id_),
                )
                print(f"  [{tabla}] id={id_}  serie={serie!r}  {numero_str!r} -> {nuevo_numero!r}")
                actualizadas += 1
    return actualizadas


def main():
    if not DB_PATH.exists():
        print(f"No se encuentra la base de datos: {DB_PATH}")
        return

    print(f"Base de datos: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        total = 0
        for tabla in ("facturas_emitidas_docs", "albaranes_emitidas_docs"):
            print(f"\nProcesando tabla: {tabla}")
            n = _limpiar_tabla(conn, tabla)
            print(f"  -> {n} fila(s) actualizadas")
            total += n
        conn.commit()
        print(f"\nMigracion completada. Total actualizadas: {total}")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
