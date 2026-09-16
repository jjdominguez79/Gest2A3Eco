"""Verificacion del backfill DEHu sobre PostgreSQL de pruebas, en esquema aislado."""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL no definida")
def test_migracion_dehu_recuerda_anteriores_sin_duplicarlos():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    esquema = "test_dehu_" + uuid.uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{esquema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{esquema}"'))
            conn.execute(text(
                "CREATE TABLE client_dehu_notifications "
                "(holder_tax_id TEXT, external_reference TEXT, first_seen_at TIMESTAMPTZ);"
                "CREATE TABLE client_certificate_requests (parameters_json TEXT, created_at TIMESTAMPTZ);"
                "INSERT INTO client_dehu_notifications VALUES ('b-12345678', 'ANTERIOR', now());"
            ))
            conn.execute(text(
                "INSERT INTO client_certificate_requests VALUES (:params, now())"
            ), {"params": '{"_dehu_audit":[{"holder_tax_id":"B99999999","reference":"OP-ANTERIOR"}]}'})
            migracion = (Path(__file__).resolve().parents[1] / "backend/migrations/023_dehu_new_notifications.sql").read_text(encoding="utf-8")
            conn.execute(text(migracion))
            conn.execute(text(migracion))
            rows = conn.execute(text(
                "SELECT holder_tax_id, external_reference, first_request_id, first_batch_id "
                "FROM client_dehu_seen_references ORDER BY external_reference"
            )).all()
            assert rows == [
                ("B12345678", "ANTERIOR", None, None),
                ("B99999999", "OP-ANTERIOR", None, None),
            ]
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE'))
        engine.dispose()
