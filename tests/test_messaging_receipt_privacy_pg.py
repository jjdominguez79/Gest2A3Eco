"""Migracion de privacidad sobre PostgreSQL de pruebas en esquema aislado."""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL no definida")
def test_migracion_privacidad_es_aditiva_y_conserva_preferencias():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    esquema = "test_privacidad_" + uuid.uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{esquema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{esquema}"'))
            conn.execute(text(
                "CREATE TABLE msg_staff (external_id TEXT PRIMARY KEY, role TEXT, mostrar_estados_mensajes BOOLEAN);"
                "CREATE TABLE msg_events (id INTEGER);"
                "CREATE TABLE msg_receipts (read_through_at TIMESTAMPTZ);"
                "INSERT INTO msg_staff VALUES ('admin', 'admin', FALSE), ('empleado', 'empleado', FALSE);"
                "INSERT INTO msg_events VALUES (1);"
                "INSERT INTO msg_receipts VALUES (now());"
            ))
            sql = (Path(__file__).resolve().parents[1] / "backend/migrations/025_read_receipt_privacy.sql").read_text(encoding="utf-8")
            conn.execute(text(sql))
            assert conn.execute(text(
                "SELECT external_id, mostrar_estados_mensajes, mostrar_lecturas_clientes, mostrar_lecturas_empleados "
                "FROM msg_staff ORDER BY external_id"
            )).all() == [("admin", True, True, True), ("empleado", False, True, True)]
            conn.execute(text("UPDATE msg_staff SET mostrar_lecturas_clientes=FALSE WHERE external_id='admin'"))
            conn.execute(text(sql))
            assert conn.execute(text("SELECT mostrar_lecturas_clientes FROM msg_staff WHERE external_id='admin'")).scalar() is False
            assert conn.execute(text("SELECT actor_type, actor_id FROM msg_events")).one() == ("", "")
            assert conn.execute(text("SELECT count(*) FROM msg_receipts")).scalar() == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE'))
        engine.dispose()
