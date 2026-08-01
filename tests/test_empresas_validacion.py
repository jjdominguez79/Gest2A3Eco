import pytest

from models.gestor_sqlite import GestorSQLite
from utils.validaciones import normalizar_codigo_empresa_a3


def test_codigo_empresa_a3_exige_una_e_y_cinco_digitos():
    assert normalizar_codigo_empresa_a3("E01006") == "E01006"
    for invalido in ("E001006", "EE01006", "01006", "E1006", "E0100A"):
        with pytest.raises(ValueError):
            normalizar_codigo_empresa_a3(invalido)


def test_no_permite_otra_empresa_con_mismo_nif(tmp_path):
    gestor = GestorSQLite(tmp_path / "empresas.sqlite")
    gestor.upsert_empresa({"codigo": "E01006", "ejercicio": 2026, "cif": "B-12345678"})

    # Un nuevo ejercicio de la misma empresa es valido.
    gestor.upsert_empresa({"codigo": "E01006", "ejercicio": 2027, "cif": "B12345678"})

    with pytest.raises(ValueError, match="Ya existe una empresa"):
        gestor.upsert_empresa({"codigo": "E01007", "ejercicio": 2026, "cif": "B12345678"})


def test_modelo_rechaza_codigo_con_seis_digitos(tmp_path):
    gestor = GestorSQLite(tmp_path / "empresas.sqlite")
    with pytest.raises(ValueError, match="exactamente cinco"):
        gestor.upsert_empresa({"codigo": "E001006", "ejercicio": 2026})


def test_eliminar_empresa_completa_elimina_todos_los_ejercicios(tmp_path):
    gestor = GestorSQLite(tmp_path / "empresas.sqlite")
    gestor.upsert_empresa({"codigo": "E01006", "ejercicio": 2026, "cif": "B12345678"})
    gestor.upsert_empresa({"codigo": "E01006", "ejercicio": 2027, "cif": "B12345678"})
    gestor.upsert_banco({"codigo_empresa": "E01006", "ejercicio": 2026, "banco": "Banco"})

    assert gestor.eliminar_empresa_completa("E01006") >= 2
    assert gestor.listar_ejercicios_empresa("E01006") == []
    assert gestor.listar_bancos("E01006", 2026) == []
