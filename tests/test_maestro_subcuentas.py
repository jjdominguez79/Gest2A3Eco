"""Tests de CRUD y migracion del maestro de subcuentas empresa (Fase 2)."""
from pathlib import Path
import pytest
from models.gestor_sqlite import GestorSQLite


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gestor(tmp_path: Path) -> GestorSQLite:
    g = GestorSQLite(tmp_path / "mse.db")
    g.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Empresa Test", "digitos_plan": 8, "activo": 1,
    })
    return g


def _base_subcuenta(**overrides) -> dict:
    d = {
        "codigo_empresa": "E00570",
        "subcuenta": "40000001",
        "nombre_subcuenta": "Proveedor Demo SL",
        "tipo_subcuenta": "proveedor",
        "nif_snapshot": "B12345678",
        "activo": 1,
        "origen": "manual",
        "creado_en_gest2a3eco": 1,
    }
    d.update(overrides)
    return d


# ── upsert_maestro_subcuenta ──────────────────────────────────────────────────

def test_upsert_crea_subcuenta(tmp_path):
    g = _make_gestor(tmp_path)
    sub_id = g.upsert_maestro_subcuenta(_base_subcuenta())
    assert sub_id is not None
    assert int(sub_id) > 0


def test_upsert_idempotente_por_empresa_subcuenta(tmp_path):
    g = _make_gestor(tmp_path)
    id1 = g.upsert_maestro_subcuenta(_base_subcuenta())
    id2 = g.upsert_maestro_subcuenta(_base_subcuenta(nombre_subcuenta="Nombre cambiado"))
    assert id1 == id2
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec["nombre_subcuenta"] == "Nombre cambiado"


def test_upsert_actualiza_por_id(tmp_path):
    g = _make_gestor(tmp_path)
    sub_id = g.upsert_maestro_subcuenta(_base_subcuenta())
    g.upsert_maestro_subcuenta({"id": sub_id, "nombre_subcuenta": "Nuevo nombre",
                                 "activo": 1, "origen": "manual", "pendiente_alta_a3": 0})
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec["nombre_subcuenta"] == "Nuevo nombre"


# ── get_maestro_subcuenta_por_subcuenta ───────────────────────────────────────

def test_get_subcuenta_existente(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta())
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec is not None
    assert rec["tipo_subcuenta"] == "proveedor"
    assert rec["nif_snapshot"] == "B12345678"


def test_get_subcuenta_inexistente_devuelve_none(tmp_path):
    g = _make_gestor(tmp_path)
    assert g.get_maestro_subcuenta_por_subcuenta("E00570", "99999999") is None


# ── listar_maestro_subcuentas_empresa ─────────────────────────────────────────

def test_listar_sin_filtro(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001", tipo_subcuenta="proveedor"))
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="43000001", tipo_subcuenta="cliente",
                                                nif_snapshot="12345678A"))
    rows = g.listar_maestro_subcuentas_empresa("E00570")
    assert len(rows) == 2


def test_listar_filtrado_por_tipo(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001", tipo_subcuenta="proveedor"))
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="43000001", tipo_subcuenta="cliente",
                                                nif_snapshot="12345678A"))
    proveedores = g.listar_maestro_subcuentas_empresa("E00570", tipo="proveedor")
    assert len(proveedores) == 1
    assert proveedores[0]["subcuenta"] == "40000001"


def test_listar_filtrado_activo(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001", activo=1))
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000002", activo=0))
    activos = g.listar_maestro_subcuentas_empresa("E00570", activo=True)
    assert all(r["activo"] == 1 for r in activos)
    inactivos = g.listar_maestro_subcuentas_empresa("E00570", activo=False)
    assert all(r["activo"] == 0 for r in inactivos)


def test_listar_no_cruza_empresa(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_empresa({"codigo": "E00999", "ejercicio": 2026, "nombre": "Otra", "digitos_plan": 8, "activo": 1})
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001"))
    g.upsert_maestro_subcuenta(_base_subcuenta(codigo_empresa="E00999", subcuenta="40000001"))
    rows = g.listar_maestro_subcuentas_empresa("E00570")
    assert all(r["codigo_empresa"] == "E00570" for r in rows)


# ── listar_maestro_subcuentas_por_nif ─────────────────────────────────────────

def test_listar_por_nif_exacto(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001", nif_snapshot="B12345678"))
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000002", nif_snapshot="A99999999"))
    rows = g.listar_maestro_subcuentas_por_nif("E00570", "B12345678")
    assert len(rows) == 1
    assert rows[0]["subcuenta"] == "40000001"


def test_listar_por_nif_normaliza(tmp_path):
    g = _make_gestor(tmp_path)
    g.upsert_maestro_subcuenta(_base_subcuenta(nif_snapshot="B12345678"))
    rows = g.listar_maestro_subcuentas_por_nif("E00570", "b-12345678")
    assert len(rows) == 1


# ── listar_maestro_subcuentas_por_tercero ─────────────────────────────────────

def test_listar_por_tercero(tmp_path):
    g = _make_gestor(tmp_path)
    tid = g.upsert_tercero({"id": None, "nif": "B12345678", "nombre": "Demo SL",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="40000001", tercero_id=str(tid)))
    g.upsert_maestro_subcuenta(_base_subcuenta(subcuenta="41000001", tipo_subcuenta="acreedor",
                                                tercero_id=str(tid)))
    rows = g.listar_maestro_subcuentas_por_tercero("E00570", str(tid))
    assert len(rows) == 2


# ── marcar_maestro_subcuenta_alta_a3 ─────────────────────────────────────────

def test_marcar_alta_a3_limpia_pendiente(tmp_path):
    g = _make_gestor(tmp_path)
    sub_id = g.upsert_maestro_subcuenta(_base_subcuenta(pendiente_alta_a3=1))
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec["pendiente_alta_a3"] == 1
    g.marcar_maestro_subcuenta_alta_a3(sub_id, lote="LOTE-001")
    rec = g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001")
    assert rec["pendiente_alta_a3"] == 0
    assert rec["lote_alta_a3"] == "LOTE-001"
    assert rec["fecha_alta_a3"] is not None


# ── eliminar_maestro_subcuenta ────────────────────────────────────────────────

def test_eliminar_subcuenta(tmp_path):
    g = _make_gestor(tmp_path)
    sub_id = g.upsert_maestro_subcuenta(_base_subcuenta())
    g.eliminar_maestro_subcuenta(sub_id)
    assert g.get_maestro_subcuenta_por_subcuenta("E00570", "40000001") is None


# ── Retencion CRUD ────────────────────────────────────────────────────────────

def test_reemplazar_retenciones_round_trip(tmp_path):
    g = _make_gestor(tmp_path)
    retenciones = [
        {"base_retencion": 1000.0, "tipo_retencion": 15.0, "cuota_retencion": 150.0,
         "cuota_retencion_manual": 0, "tipo_retencion_fiscal": "profesional"},
    ]
    g.reemplazar_captura_retenciones_doc("doc-1", retenciones)
    rows = g.listar_captura_retenciones_doc("doc-1")
    assert len(rows) == 1
    assert rows[0]["cuota_retencion"] == 150.0
    assert rows[0]["tipo_retencion_fiscal"] == "profesional"


def test_reemplazar_retenciones_borra_anteriores(tmp_path):
    g = _make_gestor(tmp_path)
    g.reemplazar_captura_retenciones_doc("doc-1", [
        {"base_retencion": 1000.0, "tipo_retencion": 15.0, "cuota_retencion": 150.0}
    ])
    g.reemplazar_captura_retenciones_doc("doc-1", [
        {"base_retencion": 2000.0, "tipo_retencion": 7.0, "cuota_retencion": 140.0},
        {"base_retencion": 500.0, "tipo_retencion": 19.0, "cuota_retencion": 95.0},
    ])
    rows = g.listar_captura_retenciones_doc("doc-1")
    assert len(rows) == 2


def test_reemplazar_retenciones_vacia_elimina_todas(tmp_path):
    g = _make_gestor(tmp_path)
    g.reemplazar_captura_retenciones_doc("doc-1", [
        {"base_retencion": 1000.0, "tipo_retencion": 15.0, "cuota_retencion": 150.0}
    ])
    g.reemplazar_captura_retenciones_doc("doc-1", [])
    assert g.listar_captura_retenciones_doc("doc-1") == []


# ── Migracion desde terceros_empresas ─────────────────────────────────────────

def test_migracion_puebla_maestro_desde_terceros_empresas(tmp_path):
    """Una DB con terceros_empresas existentes debe migrar al abrir."""
    db_path = tmp_path / "pre-existente.db"
    # Crear DB con datos legacy
    g = GestorSQLite(db_path)
    g.upsert_empresa({"codigo": "E00570", "ejercicio": 2026,
                      "nombre": "Demo", "digitos_plan": 8, "activo": 1})
    tid = g.upsert_tercero({"id": None, "nif": "B12345678", "nombre": "Proveedor SA",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_tercero_empresa({
        "codigo_empresa": "E00570", "ejercicio": 0, "tercero_id": str(tid),
        "subcuenta_proveedor": "40000001",
        "subcuenta_cliente": None, "subcuenta_ingreso": None, "subcuenta_gasto": None,
    })
    g.conn.close()

    # Reabrir: la migración debe haber poblado maestro_subcuentas_empresa
    g2 = GestorSQLite(db_path)
    rows = g2.listar_maestro_subcuentas_empresa("E00570")
    subcuentas = [r["subcuenta"] for r in rows]
    assert "40000001" in subcuentas
    proveedor = next(r for r in rows if r["subcuenta"] == "40000001")
    assert proveedor["tipo_subcuenta"] == "proveedor"
    assert proveedor["nif_snapshot"] == "B12345678"


def test_migracion_no_duplica_en_doble_apertura(tmp_path):
    db_path = tmp_path / "doble.db"
    g = GestorSQLite(db_path)
    g.upsert_empresa({"codigo": "E00570", "ejercicio": 2026,
                      "nombre": "Demo", "digitos_plan": 8, "activo": 1})
    tid = g.upsert_tercero({"id": None, "nif": "B12345678", "nombre": "Demo SA",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_tercero_empresa({
        "codigo_empresa": "E00570", "ejercicio": 0, "tercero_id": str(tid),
        "subcuenta_proveedor": "40000001",
        "subcuenta_cliente": None, "subcuenta_ingreso": None, "subcuenta_gasto": None,
    })
    g.conn.close()

    g2 = GestorSQLite(db_path)
    g2.conn.close()
    g3 = GestorSQLite(db_path)
    rows = g3.listar_maestro_subcuentas_empresa("E00570")
    assert len(rows) == 1


def test_migracion_ignora_subcuentas_nulas(tmp_path):
    g = _make_gestor(tmp_path)
    tid = g.upsert_tercero({"id": None, "nif": "B99999999", "nombre": "Solo cliente",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_tercero_empresa({
        "codigo_empresa": "E00570", "ejercicio": 0, "tercero_id": str(tid),
        "subcuenta_proveedor": None, "subcuenta_cliente": "43000001",
        "subcuenta_ingreso": None, "subcuenta_gasto": None,
    })
    g._migrate_maestro_subcuentas()
    rows = g.listar_maestro_subcuentas_por_nif("E00570", "B99999999")
    assert len(rows) == 1
    assert rows[0]["tipo_subcuenta"] == "cliente"


def test_tercero_empresa_defaults_fiscales(tmp_path):
    g = _make_gestor(tmp_path)
    tid = g.upsert_tercero({"id": None, "nif": "B12345678", "nombre": "Proveedor Fiscal",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_tercero_empresa({
        "codigo_empresa": "E00570", "ejercicio": 0, "tercero_id": str(tid),
        "subcuenta_proveedor": "40000001",
        "subcuenta_cliente": None, "subcuenta_ingreso": None, "subcuenta_gasto": "62900000",
    })
    rel = g.get_tercero_empresa("E00570", str(tid), 2026)
    assert rel["cliente_tipo_operacion_iva"] == "INTERIOR_IVA"
    assert rel["cliente_intracomunitaria_clase"] == ""
    assert rel["proveedor_tipo_operacion_iva"] == "INTERIOR_DEDUCIBLE"
    assert rel["proveedor_intracomunitaria_clase"] == ""
    assert rel["proveedor_porcentaje_deduccion_iva"] == 100


def test_tercero_empresa_guarda_deduccion_parcial(tmp_path):
    g = _make_gestor(tmp_path)
    tid = g.upsert_tercero({"id": None, "nif": "B87654321", "nombre": "Proveedor Mixto",
                             "direccion": "", "cp": "", "poblacion": "", "provincia": "",
                             "telefono": "", "email": "", "contacto": "", "tipo": None})
    g.upsert_tercero_empresa({
        "codigo_empresa": "E00570",
        "ejercicio": 0,
        "tercero_id": str(tid),
        "subcuenta_proveedor": "40000005",
        "subcuenta_gasto": "62100000",
        "proveedor_tipo_operacion_iva": "GASTO_PRORRATA",
        "proveedor_iva_deducible": 1,
        "proveedor_porcentaje_deduccion_iva": 50,
    })
    rel = g.get_tercero_empresa("E00570", str(tid), 2026)
    assert rel["proveedor_tipo_operacion_iva"] == "GASTO_PRORRATA"
    assert rel["proveedor_iva_deducible"] == 1
    assert rel["proveedor_porcentaje_deduccion_iva"] == 50
