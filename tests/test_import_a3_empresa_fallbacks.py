from pathlib import Path

from services.import_a3_empresa import _year_from_cu_path


def test_ejercicio_sin_fichero_cu_devuelve_none():
    assert _year_from_cu_path(None) is None


def test_ejercicio_se_extrae_del_nombre_cu():
    assert _year_from_cu_path(Path("000866CU.DAT")) == 2026
