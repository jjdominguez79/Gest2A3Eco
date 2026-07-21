from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.tramites_dgt_service import TramitesDgtService


def _tables(gestor: GestorSQLite) -> set[str]:
    rows = gestor.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _columns(gestor: GestorSQLite, table: str) -> set[str]:
    rows = gestor.conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_tramites_dgt_schema(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt.db")
    tables = _tables(gestor)
    assert "dgt_expedientes" in tables
    assert "dgt_documentos_generados" in tables
    assert "usuarios_permisos_globales" in tables
    for col in ("referencia", "estado", "vendedor_token_hash", "comprador_token_hash", "firma_provider"):
        assert col in _columns(gestor, "dgt_expedientes")


def test_crear_validar_y_generar_documentos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.tramites_dgt_service.get_app_data_dir", lambda: tmp_path)
    gestor = GestorSQLite(tmp_path / "dgt_service.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo(
        {
            "vendedor_nombre": "Vendedor Demo",
            "comprador_nombre": "Comprador Demo",
            "vehiculo_matricula": "1234 ABC",
            "precio_venta": "1200,50",
        }
    )
    expediente = service.get_expediente(expediente_id)
    assert expediente["referencia"].startswith("DGT-")
    assert expediente["vehiculo_matricula"] == "1234ABC"
    assert expediente["vendedor_token_hash"]
    assert expediente["comprador_token_hash"]

    service.validar_expediente(expediente_id)
    docs = service.generar_documentos(expediente_id)
    assert {doc["tipo_documento"] for doc in docs} == {
        "contrato_compraventa",
        "mandato_dgt_comprador",
        "mandato_dgt_vendedor",
    }
    for doc in docs:
        assert Path(doc["ruta_txt"]).exists()
