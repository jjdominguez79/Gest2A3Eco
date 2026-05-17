"""Tests de MaestroContableEmpresaService: clasificacion, busqueda, propuesta y creacion."""
from pathlib import Path

import pandas as pd
import pytest

from models.gestor_sqlite import GestorSQLite
from services.maestro_contable_empresa_service import (
    MaestroContableEmpresaService,
    clasificar_tipo_subcuenta,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gestor(tmp_path: Path) -> GestorSQLite:
    g = GestorSQLite(tmp_path / "contable.db")
    g.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Test SA", "digitos_plan": 8, "activo": 1,
    })
    return g


def _svc() -> MaestroContableEmpresaService:
    return MaestroContableEmpresaService()


def _add_subcuenta(g, subcuenta, tipo=None, nif=None, tercero_id=None):
    g.upsert_maestro_subcuenta({
        "codigo_empresa": "E00570",
        "subcuenta": subcuenta,
        "tipo_subcuenta": tipo or clasificar_tipo_subcuenta(subcuenta),
        "nif_snapshot": nif,
        "tercero_id": tercero_id,
        "activo": 1,
        "origen": "test",
    })


# ── clasificar_tipo_subcuenta ─────────────────────────────────────────────────

@pytest.mark.parametrize("codigo,tipo_esperado", [
    ("43000001", "cliente"),
    ("40000001", "proveedor"),
    ("41000001", "acreedor"),
    ("44000001", "deudor"),
    ("60000001", "gasto"),
    ("62900001", "gasto"),
    ("70000001", "ingreso"),
    ("75900001", "ingreso"),
    ("47200001", "iva_soportado"),
    ("47700001", "iva_repercutido"),
    ("47500001", "hacienda"),
    ("47600001", "seguridad_social"),
    ("46500001", "personal"),
    ("57200001", "banco"),
    ("57000001", "caja"),
    ("10000001", "otra"),
    ("999",      "otra"),
    ("",         "otra"),
])
def test_clasificar_tipo_subcuenta(codigo, tipo_esperado):
    assert clasificar_tipo_subcuenta(codigo) == tipo_esperado, \
        f"clasificar_tipo_subcuenta({codigo!r}) deberia ser {tipo_esperado!r}"


# ── buscar_subcuenta ──────────────────────────────────────────────────────────

def test_buscar_subcuenta_existente(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001", nif="B12345678")
    rec = _svc().buscar_subcuenta(g, "E00570", "40000001")
    assert rec is not None
    assert rec["tipo_subcuenta"] == "proveedor"


def test_buscar_subcuenta_inexistente(tmp_path):
    g = _make_gestor(tmp_path)
    assert _svc().buscar_subcuenta(g, "E00570", "99999999") is None


# ── buscar_subcuentas_por_tipo ────────────────────────────────────────────────

def test_buscar_subcuentas_por_tipo_proveedor(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001")
    _add_subcuenta(g, "40000002")
    _add_subcuenta(g, "43000001")
    rows = _svc().buscar_subcuentas_por_tipo(g, "E00570", "proveedor")
    assert all(r["tipo_subcuenta"] == "proveedor" for r in rows)
    assert len(rows) == 2


# ── buscar_subcuentas_por_nif ─────────────────────────────────────────────────

def test_buscar_subcuentas_por_nif(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001", nif="B12345678")
    _add_subcuenta(g, "41000001", nif="B12345678")
    _add_subcuenta(g, "43000001", nif="A99999999")
    rows = _svc().buscar_subcuentas_por_nif(g, "E00570", "B12345678")
    assert len(rows) == 2
    assert all(r["nif_snapshot"] == "B12345678" for r in rows)


def test_buscar_subcuentas_por_nif_normaliza(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001", nif="B12345678")
    rows = _svc().buscar_subcuentas_por_nif(g, "E00570", "b-12345678")
    assert len(rows) == 1


# ── proponer_siguiente_subcuenta ──────────────────────────────────────────────

def test_proponer_proveedor_sin_subcuentas(tmp_path):
    g = _make_gestor(tmp_path)
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "proveedor", digitos_plan=8)
    assert sub == "40000001"


def test_proponer_cliente_prefijo_430(tmp_path):
    g = _make_gestor(tmp_path)
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "cliente", digitos_plan=8)
    assert sub == "43000001"


def test_proponer_acreedor_prefijo_410(tmp_path):
    g = _make_gestor(tmp_path)
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "acreedor", digitos_plan=8)
    assert sub == "41000001"


def test_proponer_evita_ocupadas_en_maestro(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001")
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "proveedor", digitos_plan=8)
    assert sub == "40000002"


def test_proponer_evita_colision_con_plan_cuentas(tmp_path):
    g = _make_gestor(tmp_path)
    g.conn.execute(
        "INSERT OR IGNORE INTO plan_cuentas (codigo_empresa, ejercicio, cuenta, descripcion)"
        " VALUES (?,?,?,?)",
        ("E00570", 2026, "40000001", "Proveedor plan"),
    )
    g.conn.commit()
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "proveedor", digitos_plan=8)
    assert sub == "40000002"


def test_proponer_respeta_digitos_plan(tmp_path):
    g = _make_gestor(tmp_path)
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "proveedor", digitos_plan=10)
    assert len(sub) == 10
    assert sub.startswith("400")


def test_proponer_no_cruza_empresa(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_empresa({"codigo": "E00999", "ejercicio": 2026,
                      "nombre": "Otra", "digitos_plan": 8, "activo": 1})
    g.upsert_maestro_subcuenta({
        "codigo_empresa": "E00999", "subcuenta": "40000001",
        "tipo_subcuenta": "proveedor", "activo": 1, "origen": "test",
    })
    sub = _svc().proponer_siguiente_subcuenta(g, "E00570", "proveedor", digitos_plan=8)
    assert sub == "40000001"


# ── crear_subcuenta_empresa ───────────────────────────────────────────────────

def test_crear_subcuenta_clasifica_tipo_automaticamente(tmp_path):
    g = _make_gestor(tmp_path)
    rec = _svc().crear_subcuenta_empresa(g, {
        "codigo_empresa": "E00570",
        "subcuenta": "40000001",
        "nombre_subcuenta": "Demo Proveedor SL",
    })
    assert rec["tipo_subcuenta"] == "proveedor"
    assert rec["creado_en_gest2a3eco"] == 1
    assert rec["pendiente_alta_a3"] == 1


def test_crear_subcuenta_tipo_explicito(tmp_path):
    g = _make_gestor(tmp_path)
    rec = _svc().crear_subcuenta_empresa(g, {
        "codigo_empresa": "E00570",
        "subcuenta": "62900001",
        "tipo_subcuenta": "gasto",
        "nombre_subcuenta": "Servicios externos",
    })
    assert rec["tipo_subcuenta"] == "gasto"


def test_crear_subcuenta_importacion_no_marca_pendiente(tmp_path):
    g = _make_gestor(tmp_path)
    rec = _svc().crear_subcuenta_empresa(g, {
        "codigo_empresa": "E00570",
        "subcuenta": "40000001",
        "creado_en_gest2a3eco": 0,
        "origen": "importacion_a3",
    })
    assert rec["pendiente_alta_a3"] == 0


def test_crear_subcuenta_falta_empresa_lanza_error(tmp_path):
    g = _make_gestor(tmp_path)
    with pytest.raises(ValueError, match="obligatorios"):
        _svc().crear_subcuenta_empresa(g, {"subcuenta": "40000001"})


def test_crear_subcuenta_falta_subcuenta_lanza_error(tmp_path):
    g = _make_gestor(tmp_path)
    with pytest.raises(ValueError, match="obligatorios"):
        _svc().crear_subcuenta_empresa(g, {"codigo_empresa": "E00570"})


# ── importar_subcuentas_desde_dataframe ───────────────────────────────────────

def test_importar_desde_dataframe_basico(tmp_path):
    g = _make_gestor(tmp_path)
    df = pd.DataFrame([
        {"subcuenta": "40000001", "descripcion": "Proveedor Uno SL"},
        {"subcuenta": "40000002", "descripcion": "Proveedor Dos SL"},
        {"subcuenta": "43000001", "descripcion": "Cliente Principal SL"},
    ])
    resultado = _svc().importar_subcuentas_desde_dataframe(g, "E00570", df)
    assert resultado["importadas"] == 3
    assert resultado["actualizadas"] == 0
    assert resultado["errores"] == 0
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec is not None
    assert rec["tipo_subcuenta"] == "proveedor"
    assert rec["creado_en_gest2a3eco"] == 0
    assert rec["pendiente_alta_a3"] == 0


def test_importar_desde_dataframe_actualiza_existente(tmp_path):
    g = _make_gestor(tmp_path)
    _add_subcuenta(g, "40000001", "proveedor")
    df = pd.DataFrame([{"subcuenta": "40000001", "descripcion": "Proveedor Actualizado SL"}])
    resultado = _svc().importar_subcuentas_desde_dataframe(g, "E00570", df)
    assert resultado["importadas"] == 0
    assert resultado["actualizadas"] == 1


def test_importar_desde_dataframe_columna_cuenta(tmp_path):
    g = _make_gestor(tmp_path)
    df = pd.DataFrame([{"cuenta": "40000001", "descripcion": "Proveedor"}])
    resultado = _svc().importar_subcuentas_desde_dataframe(g, "E00570", df)
    assert resultado["importadas"] == 1


def test_importar_desde_dataframe_sin_columna_lanza_error(tmp_path):
    g = _make_gestor(tmp_path)
    df = pd.DataFrame([{"otro": "valor"}])
    with pytest.raises(ValueError, match="subcuenta"):
        _svc().importar_subcuentas_desde_dataframe(g, "E00570", df)


def test_importar_desde_dataframe_ignora_filas_vacias(tmp_path):
    g = _make_gestor(tmp_path)
    df = pd.DataFrame([
        {"subcuenta": "40000001", "descripcion": "Proveedor"},
        {"subcuenta": "",         "descripcion": "Vacia"},
        {"subcuenta": None,       "descripcion": "Nula"},
    ])
    resultado = _svc().importar_subcuentas_desde_dataframe(g, "E00570", df)
    assert resultado["importadas"] == 1


# ── marcar_subcuenta_alta_a3_realizada ────────────────────────────────────────

def test_marcar_alta_a3_realizada(tmp_path):
    g = _make_gestor(tmp_path)
    svc = _svc()
    rec = svc.crear_subcuenta_empresa(g, {
        "codigo_empresa": "E00570",
        "subcuenta": "40000001",
        "creado_en_gest2a3eco": 1,
    })
    assert rec["pendiente_alta_a3"] == 1
    svc.marcar_subcuenta_alta_a3_realizada(g, rec["id"], lote="LOTE-001")
    rec_actualizado = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec_actualizado["pendiente_alta_a3"] == 0
    assert rec_actualizado["lote_alta_a3"] == "LOTE-001"
