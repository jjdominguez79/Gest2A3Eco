"""Tests de MaestroTercerosService: normalizacion, busqueda, creacion y actualizacion."""
from pathlib import Path
import pytest

from models.gestor_sqlite import GestorSQLite
from services.maestro_terceros_service import (
    MaestroTercerosService,
    normalizar_nif,
    detectar_tipo_identificacion,
    normalizar_nombre,
    TIPO_NIF, TIPO_CIF, TIPO_NIE, TIPO_VAT, TIPO_SIN_NIF,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gestor(tmp_path: Path) -> GestorSQLite:
    g = GestorSQLite(tmp_path / "terceros.db")
    g.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Test SA", "digitos_plan": 8, "activo": 1,
    })
    return g


def _svc() -> MaestroTercerosService:
    return MaestroTercerosService()


# ── normalizar_nif ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("B-12345678", "B12345678"),
    ("b12345678", "B12345678"),
    ("B 12345678", "B12345678"),
    ("12345678A", "12345678A"),
    ("X1234567A", "X1234567A"),
    ("ES-B12345678", "ESB12345678"),
    ("",           ""),
    (None,         ""),
])
def test_normalizar_nif(raw, expected):
    assert normalizar_nif(raw) == expected


# ── detectar_tipo_identificacion ──────────────────────────────────────────────

def test_detectar_tipo_nif():
    assert detectar_tipo_identificacion("12345678A") == TIPO_NIF


def test_detectar_tipo_cif():
    assert detectar_tipo_identificacion("B12345678") == TIPO_CIF


def test_detectar_tipo_nie():
    assert detectar_tipo_identificacion("X1234567A") == TIPO_NIE


def test_detectar_tipo_vat():
    assert detectar_tipo_identificacion("DE123456789") == TIPO_VAT


def test_detectar_tipo_sin_nif():
    assert detectar_tipo_identificacion("") == TIPO_SIN_NIF


# ── normalizar_nombre ─────────────────────────────────────────────────────────

def test_normalizar_nombre_elimina_sufijo_juridico():
    assert "demo" == normalizar_nombre("Demo SL")


def test_normalizar_nombre_elimina_acentos():
    result = normalizar_nombre("Informatica Avanzada SA")
    assert "informatica" in result


def test_normalizar_nombre_colapsa_espacios():
    result = normalizar_nombre("  Empresa   Demo  ")
    assert "  " not in result


def test_normalizar_nombre_vacio():
    assert normalizar_nombre("") == ""
    assert normalizar_nombre(None) == ""


# ── buscar_tercero_por_nif ────────────────────────────────────────────────────

def test_buscar_por_nif_campo_nuevo(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Proveedor Demo SL"})
    t = svc.buscar_tercero_por_nif(g, "B12345678")
    assert t is not None
    assert t["nif_normalizado"] == "B12345678"


def test_buscar_por_nif_normaliza_entrada(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Demo SL"})
    assert svc.buscar_tercero_por_nif(g, "b-12345678") is not None


def test_buscar_por_nif_fallback_campo_legacy(tmp_path):
    """Tercero creado solo con el campo legacy 'nif' debe encontrarse."""
    g = _make_gestor(tmp_path)
    g.upsert_tercero({
        "id": None, "nif": "B99999999", "nombre": "Legacy SA",
        "direccion": "", "cp": "", "poblacion": "", "provincia": "",
        "telefono": "", "email": "", "contacto": "", "tipo": None,
    })
    svc = _svc()
    t = svc.buscar_tercero_por_nif(g, "B99999999")
    assert t is not None
    assert t["nif"] == "B99999999"


def test_buscar_por_nif_no_encontrado(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().buscar_tercero_por_nif(g, "B00000000") is None


def test_buscar_por_nif_vacio_devuelve_none(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().buscar_tercero_por_nif(g, "") is None


# ── buscar_tercero_por_nombre ─────────────────────────────────────────────────

def test_buscar_por_nombre_exacto(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Servicios Globales SA"})
    results = svc.buscar_tercero_por_nombre(g, "Servicios Globales SA")
    assert len(results) == 1
    assert results[0]["nombre_legal"] == "Servicios Globales SA"


def test_buscar_por_nombre_parcial_fuzzy(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Servicios Informaticos ABC"})
    results = svc.buscar_tercero_por_nombre(g, "Informaticos ABC")
    assert len(results) >= 1


def test_buscar_por_nombre_parcial_desactivado(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Servicios Informaticos ABC"})
    results = svc.buscar_tercero_por_nombre(g, "Informaticos ABC", fuzzy=False)
    assert len(results) == 0


def test_buscar_por_nombre_vacio_devuelve_lista_vacia(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().buscar_tercero_por_nombre(g, "") == []


# ── crear_tercero_global ──────────────────────────────────────────────────────

def test_crear_tercero_persiste_campos_nuevos(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    t = svc.crear_tercero_global(g, {
        "nif": "B12345678",
        "nombre": "Demo SL",
        "nombre_comercial": "Demo",
        "pais": "ES",
        "cp": "28001",
        "origen": "ocr",
    })
    assert t["nif_normalizado"] == "B12345678"
    assert t["nombre_legal"] == "Demo SL"
    assert t["nombre_comercial"] == "Demo"
    assert t["pais"] == "ES"
    assert t["codigo_postal"] == "28001"
    assert t["origen"] == "ocr"
    assert t["tipo_identificacion"] == TIPO_CIF


def test_crear_tercero_idempotente_por_nif(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    t1 = svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Primera SA"})
    t2 = svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Segunda SA"})
    assert t1["id"] == t2["id"]
    # Solo un tercero con ese NIF
    rows = g.conn.execute(
        "SELECT COUNT(*) FROM terceros WHERE nif_normalizado='B12345678'"
    ).fetchone()[0]
    assert rows == 1


def test_crear_tercero_sin_nif_permitido(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    t = svc.crear_tercero_global(g, {"nombre": "Entidad sin NIF", "tipo_identificacion": "sin_nif"})
    assert t["id"] is not None
    assert t.get("tipo_identificacion") == "sin_nif"


def test_crear_tercero_activo_por_defecto(tmp_path):
    g = _make_gestor(tmp_path)
    t = _svc().crear_tercero_global(g, {"nif": "B12345678", "nombre": "Demo SL"})
    assert t["activo"] == 1


def test_crear_tercero_pais_espana_por_defecto(tmp_path):
    g = _make_gestor(tmp_path)
    t = _svc().crear_tercero_global(g, {"nif": "B12345678", "nombre": "Demo SL"})
    assert t["pais"] == "ES"


# ── actualizar_tercero ────────────────────────────────────────────────────────

def test_actualizar_tercero_modifica_campos(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    t = svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Antigua SA"})
    svc.actualizar_tercero(g, t["id"], {"nombre": "Nueva SA", "telefono": "912345678"})
    actualizado = svc.buscar_tercero_por_nif(g, "B12345678")
    assert actualizado["nombre_legal"] == "Nueva SA"
    assert actualizado["telefono"] == "912345678"


def test_actualizar_tercero_no_sobreescribe_campo_ausente(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    t = svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Demo SL", "pais": "FR"})
    svc.actualizar_tercero(g, t["id"], {"nombre": "Demo SL actualizado"})
    actualizado = svc.buscar_tercero_por_nif(g, "B12345678")
    assert actualizado["pais"] == "FR"


# ── nif_ya_existe ─────────────────────────────────────────────────────────────

def test_nif_ya_existe_true(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    svc.crear_tercero_global(g, {"nif": "B12345678", "nombre": "Existe SA"})
    assert svc.nif_ya_existe(g, "B12345678") is True
    assert svc.nif_ya_existe(g, "b-12345678") is True


def test_nif_ya_existe_false(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().nif_ya_existe(g, "B99999999") is False


def test_nif_ya_existe_vacio(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().nif_ya_existe(g, "") is False
