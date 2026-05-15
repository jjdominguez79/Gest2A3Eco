from pathlib import Path

from models.gestor_sqlite import GestorSQLite


def _crear_gestor(tmp_path: Path) -> GestorSQLite:
    db_path = tmp_path / "test_gestor.sqlite"
    return GestorSQLite(db_path)


def test_series_emitidas_se_crean_desde_empresa(tmp_path):
    gestor = _crear_gestor(tmp_path)
    gestor.upsert_empresa(
        {
            "codigo": "E00001",
            "ejercicio": 2026,
            "nombre": "Empresa test",
            "digitos_plan": 8,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 7,
            "serie_emitidas_rect": "R",
            "siguiente_num_emitidas_rect": 3,
        }
    )

    gestor.ensure_series_emitidas("E00001", 2026)
    series = gestor.listar_series_emitidas("E00001", 2026)

    assert len(series) == 2
    assert gestor.get_siguiente_serie_num("E00001", 2026, "A") == 7
    assert gestor.get_siguiente_serie_num("E00001", 2026, "R") == 3


def test_incrementar_serie_num_respeta_serie_y_ejercicio(tmp_path):
    gestor = _crear_gestor(tmp_path)
    gestor.upsert_empresa(
        {
            "codigo": "E00001",
            "ejercicio": 2026,
            "nombre": "Empresa test",
            "digitos_plan": 8,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 1,
            "serie_emitidas_rect": "R",
            "siguiente_num_emitidas_rect": 1,
        }
    )
    gestor.upsert_empresa(
        {
            "codigo": "E00001",
            "ejercicio": 2027,
            "nombre": "Empresa test",
            "digitos_plan": 8,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 10,
            "serie_emitidas_rect": "R",
            "siguiente_num_emitidas_rect": 2,
        }
    )

    gestor.ensure_series_emitidas("E00001", 2026)
    gestor.ensure_series_emitidas("E00001", 2027)
    gestor.upsert_serie_emitida("E00001", 2026, "B", siguiente_num=20, es_rectificativa=0)

    nuevo_a_2026 = gestor.incrementar_serie_num("E00001", 2026, "A")
    nuevo_b_2026 = gestor.incrementar_serie_num("E00001", 2026, "B")

    assert nuevo_a_2026 == 2
    assert nuevo_b_2026 == 21
    assert gestor.get_siguiente_serie_num("E00001", 2027, "A") == 10

