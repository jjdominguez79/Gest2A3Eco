"""
Actualiza datos de empresas desde un CSV aplicando los cambios a todos los ejercicios.
Usa las columnas presentes en el CSV (minimo 'codigo'; 'ejercicio' opcional).

Ejecutar:
    python actualizar_empresas_todos_ejercicios.py ruta/al/empresas.csv
"""

import sys
from pathlib import Path

from import_empresas_csv import actualizar_empresas_csv_todos_ejercicios


def main():
    if len(sys.argv) < 2:
        print("Uso: python actualizar_empresas_todos_ejercicios.py ruta/al/empresas.csv")
        sys.exit(1)

    csv_path = Path(sys.argv[1]).expanduser()
    db_path = Path(__file__).resolve().parent / "plantillas" / "gest2a3eco.db"

    n = actualizar_empresas_csv_todos_ejercicios(db_path, csv_path)
    print(f"Filas actualizadas: {n}")


if __name__ == "__main__":
    main()
