"""Utilidad de consola para cargar una copia SQLite en PostgreSQL.

Uso en PowerShell:
    $env:GEST2A3ECO_POSTGRES_DSN = 'postgresql://usuario:clave@servidor:5432/bd'
    python -m procesos.migrar_sqlite_postgres plantillas/gest2a3eco.db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from models.postgres_migracion import (
    MigracionPostgresError,
    migrar_sqlite_a_postgres,
    validar_sqlite_contra_postgres,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migra una copia SQLite de Gest2A3Eco a una base PostgreSQL vacia."
    )
    parser.add_argument("sqlite_path", type=Path, help="Fichero SQLite de origen (solo lectura).")
    parser.add_argument(
        "--dsn",
        default=os.getenv("GEST2A3ECO_POSTGRES_DSN", ""),
        help="DSN PostgreSQL. Si se omite, usa GEST2A3ECO_POSTGRES_DSN.",
    )
    parser.add_argument(
        "--validar",
        action="store_true",
        help="Solo compara recuentos SQLite/PostgreSQL; no migra datos.",
    )
    args = parser.parse_args(argv)
    dsn = str(args.dsn or "").strip()
    if not dsn:
        parser.error("Indica --dsn o define la variable GEST2A3ECO_POSTGRES_DSN.")

    try:
        if args.validar:
            validacion = validar_sqlite_contra_postgres(args.sqlite_path, dsn)
            if validacion.diferencias:
                print("ERROR: Se detectaron diferencias de filas:", file=sys.stderr)
                for tabla, (origen, destino) in validacion.diferencias.items():
                    print(f"  {tabla}: SQLite={origen}, PostgreSQL={destino}", file=sys.stderr)
                return 2
            print(f"Validacion correcta: {len(validacion.filas_por_tabla)} tablas coinciden.")
            return 0
        resultado = migrar_sqlite_a_postgres(args.sqlite_path, dsn)
    except (MigracionPostgresError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Migracion completada: {resultado.tablas} tablas y {resultado.filas} filas.")
    for tabla, filas in resultado.filas_por_tabla.items():
        print(f"  {tabla}: {filas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
