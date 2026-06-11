"""Tests de TercerosOcrService: busqueda, propuesta de subcuenta y creacion."""
from pathlib import Path

import pytest

from models.gestor_sqlite import GestorSQLite
from services.terceros_ocr_service import TercerosOcrService


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_gestor(tmp_path: Path) -> GestorSQLite:
    g = GestorSQLite(tmp_path / "terceros-test.db")
    g.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Empresa Test", "digitos_plan": 8, "activo": 1,
    })
    return g


def _add_tercero(gestor, nif: str, nombre: str, subcuenta_proveedor: str) -> str:
    """Inserta un tercero en maestro + relacion empresa y devuelve su id."""
    tid = gestor.upsert_tercero({
        "id": None, "nif": nif, "nombre": nombre,
        "direccion": "", "cp": "", "poblacion": "", "provincia": "",
        "telefono": "", "email": "", "contacto": "", "tipo": None,
    })
    gestor.upsert_tercero_empresa({
        "codigo_empresa": "E00570", "ejercicio": 0, "tercero_id": tid,
        "subcuenta_proveedor": subcuenta_proveedor,
        "subcuenta_cliente": None, "subcuenta_ingreso": None, "subcuenta_gasto": None,
    })
    return str(tid)


# ── Propuesta de subcuenta ────────────────────────────────────────────────────

def test_proponer_subcuenta_proveedor_sin_terceros(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    sub = svc.proponer_subcuenta(g, "proveedor", "E00570", 2026)
    assert sub == "40000001"


def test_proponer_subcuenta_evita_ocupadas(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B11111111", "Proveedor Uno SL", "40000001")
    sub = svc.proponer_subcuenta(g, "proveedor", "E00570", 2026)
    assert sub == "40000002"


def test_proponer_subcuenta_evita_colision_con_plan(tmp_path):
    """Si 40000001 ya existe en plan_cuentas, la propuesta salta a 40000002."""
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    # Insertar directamente una cuenta en plan_cuentas
    g.conn.execute(
        "INSERT OR IGNORE INTO plan_cuentas (codigo_empresa, ejercicio, cuenta, descripcion) VALUES (?,?,?,?)",
        ("E00570", 2026, "40000001", "Cuenta test"),
    )
    g.conn.commit()
    sub = svc.proponer_subcuenta(g, "proveedor", "E00570", 2026)
    assert sub == "40000002"


def test_proponer_subcuenta_cliente_prefijo_430(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    sub = svc.proponer_subcuenta(g, "cliente", "E00570", 2026)
    assert sub == "43000001"


def test_proponer_subcuenta_acreedor_prefijo_410(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    sub = svc.proponer_subcuenta(g, "acreedor", "E00570", 2026)
    assert sub == "41000001"


def test_proponer_subcuenta_longitud_respeta_digitos_plan(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    sub = svc.proponer_subcuenta(g, "proveedor", "E00570", 2026)
    assert len(sub) == 8


# ── Resolucion de tercero ─────────────────────────────────────────────────────

def test_resolver_tercero_por_nif_exacto(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B12345678", "Proveedor Demo SL", "40000001")
    t = svc.resolver_tercero(g, "B12345678", "", "E00570", 2026)
    assert t is not None
    assert t["nif"] == "B12345678"


def test_resolver_tercero_nif_normalizado(tmp_path):
    """NIF con guion en la consulta debe coincidir con el del maestro."""
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B12345678", "Proveedor Demo SL", "40000001")
    t = svc.resolver_tercero(g, "B-12345678", "", "E00570", 2026)
    assert t is not None


def test_resolver_tercero_por_nombre_exacto(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B12345678", "Proveedor Demo SL", "40000001")
    t = svc.resolver_tercero(g, "", "Proveedor Demo SL", "E00570", 2026)
    assert t is not None
    assert t["nombre"] == "Proveedor Demo SL"


def test_resolver_tercero_por_nombre_parcial(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B12345678", "Servicios Informaticos ABC SL", "40000001")
    t = svc.resolver_tercero(g, "", "Informaticos ABC", "E00570", 2026)
    assert t is not None


def test_resolver_tercero_no_encontrado_devuelve_none(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    t = svc.resolver_tercero(g, "B99999999", "Inexistente", "E00570", 2026)
    assert t is None


def test_resolver_tercero_incluye_subcuenta(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    _add_tercero(g, "B12345678", "Proveedor Demo SL", "40000007")
    t = svc.resolver_tercero(g, "B12345678", "", "E00570", 2026)
    assert t is not None
    assert t.get("subcuenta_proveedor") == "40000007"


def test_resolver_tercero_desde_maestro_sin_relacion_fiscal(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(
        {
            "codigo_empresa": "E00570",
            "subcuenta": "40000009",
            "nombre_subcuenta": "Proveedor Solo Maestro",
            "tipo_subcuenta": "proveedor",
            "nif_snapshot": "B12345678",
            "activo": 1,
            "origen": "manual",
            "creado_en_gest2a3eco": 1,
        }
    )
    t = svc.resolver_tercero(g, "B12345678", "", "E00570", 2026)
    assert t is not None
    assert t.get("subcuenta_proveedor") == "40000009"
    assert t.get("proveedor_tipo_operacion_iva") is None


# ── Creacion de tercero ───────────────────────────────────────────────────────

def test_crear_tercero_persiste_y_devuelve_subcuenta(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    t = svc.crear_tercero(
        g,
        {"nif": "B12345678", "nombre": "Nuevo Proveedor SL"},
        "40000001",
        "proveedor",
        "E00570",
        2026,
    )
    assert t["subcuenta_proveedor"] == "40000001"
    assert t["id"] is not None

    # El tercero aparece en el maestro
    encontrado = svc.resolver_tercero(g, "B12345678", "", "E00570", 2026)
    assert encontrado is not None
    assert encontrado.get("subcuenta_proveedor") == "40000001"


def test_crear_tercero_idempotente_por_nif(tmp_path):
    """Crear el mismo NIF dos veces reutiliza el id del tercero."""
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    t1 = svc.crear_tercero(
        g, {"nif": "B12345678", "nombre": "Proveedor SA"}, "40000001", "proveedor", "E00570", 2026
    )
    t2 = svc.crear_tercero(
        g, {"nif": "B12345678", "nombre": "Proveedor SA"}, "40000002", "proveedor", "E00570", 2026
    )
    assert str(t1["id"]) == str(t2["id"])
    # Solo un tercero en el maestro global con ese NIF
    todos = g.listar_terceros()
    matching = [t for t in todos if t.get("nif") == "B12345678"]
    assert len(matching) == 1


def test_crear_tercero_tipo_cliente_usa_subcuenta_cliente(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    t = svc.crear_tercero(
        g,
        {"nif": "12345678A", "nombre": "Cliente Persona Fisica"},
        "43000001",
        "cliente",
        "E00570",
        2026,
    )
    assert t["subcuenta_cliente"] == "43000001"
    assert t.get("subcuenta_proveedor") is None


# ── nif_ya_existe ─────────────────────────────────────────────────────────────

def test_nif_ya_existe_true(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    g.upsert_tercero({
        "id": None, "nif": "B12345678", "nombre": "Existe SA",
        "direccion": "", "cp": "", "poblacion": "", "provincia": "",
        "telefono": "", "email": "", "contacto": "", "tipo": None,
    })
    assert svc.nif_ya_existe(g, "B12345678") is True
    assert svc.nif_ya_existe(g, "b12345678") is True  # case-insensitive


def test_nif_ya_existe_false(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    assert svc.nif_ya_existe(g, "B99999999") is False


def test_nif_ya_existe_nif_vacio(tmp_path):
    svc = TercerosOcrService()
    g = _make_gestor(tmp_path)
    assert svc.nif_ya_existe(g, "") is False
