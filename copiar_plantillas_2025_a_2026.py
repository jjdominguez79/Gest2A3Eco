"""
Script para copiar plantillas del ejercicio 2025 al 2026 para todas las empresas.
Ejecuta: python copiar_plantillas_2025_a_2026.py
"""

from pathlib import Path

from gestor_sqlite import GestorSQLite


# Ruta a la base de datos SQLite
DB_PATH = Path(__file__).resolve().parent / "plantillas" / "gest2a3eco.db"

SRC_EJ = 2025
DST_EJ = 2026


def main():
    gestor = GestorSQLite(DB_PATH)
    empresas = gestor.listar_empresas()

    # Empresas que tienen datos en el ejercicio origen
    empresas_src = [e for e in empresas if e.get("ejercicio") == SRC_EJ]

    emp_copiadas = 0
    pls_copiadas = 0

    for emp in empresas_src:
        codigo = emp.get("codigo")
        if not codigo:
            continue

        # Asegura la empresa destino (misma info, nuevo ejercicio)
        nueva = dict(emp)
        nueva["ejercicio"] = DST_EJ
        # opcional: reiniciar numeracion de emitidas
        nueva["siguiente_num_emitidas"] = 1
        gestor.upsert_empresa(nueva)

        # Copiar plantillas de bancos
        for b in gestor.listar_bancos(codigo, SRC_EJ):
            nb = dict(b, ejercicio=DST_EJ)
            gestor.upsert_banco(nb)
            pls_copiadas += 1

        # Copiar plantillas de facturas emitidas
        for p in gestor.listar_emitidas(codigo, SRC_EJ):
            np = dict(p, ejercicio=DST_EJ)
            gestor.upsert_emitida(np)
            pls_copiadas += 1

        # Copiar plantillas de facturas recibidas
        for p in gestor.listar_recibidas(codigo, SRC_EJ):
            np = dict(p, ejercicio=DST_EJ)
            gestor.upsert_recibida(np)
            pls_copiadas += 1

        emp_copiadas += 1

    print(f"Empresas procesadas: {emp_copiadas}")
    print(f"Plantillas copiadas: {pls_copiadas}")


if __name__ == "__main__":
    main()
