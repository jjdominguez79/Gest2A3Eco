"""
Limpieza: elimina de la base de datos los certificados que NO tienen fichero.

Se considera "sin fichero" un certificado cuya ruta_archivo esta vacia o cuyo
fichero no existe en disco. Se hace una COPIA DE SEGURIDAD de la base de datos
antes de borrar.

Uso (desde la raiz del proyecto):
    python Helpers/limpiar_certificados_sin_fichero.py            # aplica (con backup)
    python Helpers/limpiar_certificados_sin_fichero.py --dry-run  # solo muestra
    python Helpers/limpiar_certificados_sin_fichero.py --db "ruta\\a\\gest2a3eco.db"

La ruta de la base de datos se toma de --db, o de config.local.json / config.json
(claves db_path / last_db_path).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_desde_config() -> str | None:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Elimina certificados sin fichero de la BD")
    ap.add_argument("--db", help="Ruta al fichero gest2a3eco.db")
    ap.add_argument("--dry-run", action="store_true", help="Solo mostrar, no borrar")
    args = ap.parse_args()

    db = args.db or _db_desde_config()
    if not db:
        print("ERROR: no se pudo determinar la ruta de la base de datos.")
        print("Usa --db o revisa config.local.json (db_path / last_db_path).")
        return 2
    if not os.path.isfile(db):
        print(f"ERROR: no se encuentra la base de datos:\n  {db}")
        return 2

    print(f"Base de datos: {db}")
    con = sqlite3.connect(db, timeout=10)
    con.execute("PRAGMA busy_timeout = 10000")
    try:
        cur = con.execute(
            "SELECT id, codigo_empresa, nombre, ruta_archivo FROM notif_certificados"
        )
    except sqlite3.OperationalError:
        print("La tabla notif_certificados no existe todavia en esta base de datos. Nada que limpiar.")
        return 0
    rows = cur.fetchall()
    print(f"Certificados totales: {len(rows)}")

    a_borrar = []
    for cid, emp, nombre, ruta in rows:
        ruta = (ruta or "").strip()
        if not ruta:
            motivo = "sin ruta"
        elif not os.path.isfile(ruta):
            motivo = f"fichero no existe: {ruta}"
        else:
            continue
        a_borrar.append((cid, emp, nombre, motivo))

    if not a_borrar:
        print("No hay certificados sin fichero. Nada que borrar.")
        return 0

    print(f"\nCertificados a eliminar ({len(a_borrar)}):")
    for cid, emp, nombre, motivo in a_borrar:
        print(f"  - [{emp}] {nombre!r}  ({motivo})")

    if args.dry_run:
        print("\n--dry-run: no se ha borrado nada.")
        return 0

    # Backup antes de borrar
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{db}.bak_{ts}"
    try:
        shutil.copy2(db, backup)
        print(f"\nCopia de seguridad creada:\n  {backup}")
    except Exception as exc:
        print(f"AVISO: no se pudo crear copia de seguridad ({exc}). Abortando por seguridad.")
        return 3

    ids = [c[0] for c in a_borrar]
    con.executemany("DELETE FROM notif_certificados WHERE id=?", [(i,) for i in ids])
    # Desvincular buzones que apuntaban a esos certificados (quedan sin certificado
    # explicito; usaran el certificado unico del cliente si lo hay).
    con.executemany("UPDATE notif_buzones SET certificado_id=NULL WHERE certificado_id=?",
                    [(i,) for i in ids])
    con.commit()
    con.close()
    print(f"\nEliminados {len(ids)} certificado(s) sin fichero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
