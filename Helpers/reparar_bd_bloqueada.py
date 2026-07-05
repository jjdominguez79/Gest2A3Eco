"""
Diagnostico y reparacion de "database is locked" en la base de datos SQLite.

Que hace (de forma segura):
  - Localiza la BD (--db o config.local.json / config.json).
  - Comprueba si esta bloqueada.
  - Ejecuta un checkpoint del WAL para consolidar y liberar ficheros -wal/-shm.
  - Verifica la integridad (PRAGMA integrity_check).
  - Informa de los ficheros hermanos (-wal/-shm/-journal) y su tamano.

NO borra nada. Ejecuta con la aplicacion CERRADA en todos los equipos.

Uso:
    python Helpers/reparar_bd_bloqueada.py
    python Helpers/reparar_bd_bloqueada.py --db "\\\\GestinemMain\\...\\gest2a3eco.db"
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_desde_config():
    for nombre in ("config.local.json", "config.json"):
        ruta = os.path.join(RAIZ, nombre)
        if os.path.isfile(ruta):
            try:
                cfg = json.load(open(ruta, encoding="utf-8"))
            except Exception:
                continue
            db = (cfg.get("db_path") or cfg.get("last_db_path") or "").strip()
            if db:
                return db
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    args = ap.parse_args()
    db = args.db or _db_desde_config()
    if not db or not os.path.isfile(db):
        print("ERROR: no se encuentra la BD:", db)
        return 2
    print("Base de datos:", db)

    # Ficheros hermanos
    for suf in ("-wal", "-shm", "-journal"):
        f = db + suf
        if os.path.exists(f):
            print(f"  presente {os.path.basename(f)}  ({os.path.getsize(f)} bytes)")

    try:
        con = sqlite3.connect(db, timeout=10)
        con.execute("PRAGMA busy_timeout = 10000")
    except sqlite3.OperationalError as exc:
        print("No se pudo abrir la BD:", exc)
        print("=> Asegurate de que la app esta CERRADA en todos los equipos.")
        return 3

    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("COMMIT")
        print("Estado: la BD NO esta bloqueada (se pudo escribir).")
    except sqlite3.OperationalError as exc:
        print("Estado: BLOQUEADA ->", exc)
        print("=> Cierra la app en todos los equipos y vuelve a ejecutar.")
        con.close()
        return 4

    try:
        r = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        print("Checkpoint WAL:", r)
    except Exception as exc:
        print("Checkpoint no aplicable:", exc)
    try:
        integ = con.execute("PRAGMA integrity_check").fetchone()
        print("Integridad:", integ[0] if integ else "?")
    except Exception as exc:
        print("integrity_check fallo:", exc)

    con.commit()
    con.close()
    print("\nListo. Si seguia bloqueada, revisa que no haya python.exe/Gest2A3Eco.exe abiertos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
