"""Tests de migracion de esquema Fase 2: verifica tablas y columnas esperadas."""
from pathlib import Path
import pytest
from models.gestor_sqlite import GestorSQLite


def _gestor(tmp_path: Path) -> GestorSQLite:
    return GestorSQLite(tmp_path / "schema_test.db")


def _columns(gestor: GestorSQLite, table: str) -> set:
    rows = gestor.conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _tables(gestor: GestorSQLite) -> set:
    rows = gestor.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


# ── Tablas originales siguen existiendo ──────────────────────────────────────

def test_tablas_originales_existen(tmp_path):
    g = _gestor(tmp_path)
    t = _tables(g)
    for tabla in ("empresas", "bancos", "terceros", "terceros_empresas",
                  "plan_cuentas", "facturas_recibidas_docs", "ocr_lineas_fiscales",
                  "facturas_emitidas_docs", "series_emitidas", "usuarios",
                  "usuarios_empresas", "cuentas_bancarias"):
        assert tabla in t, f"Tabla '{tabla}' no existe tras migracion"


# ── Tablas nuevas de Fase 2 ───────────────────────────────────────────────────

def test_tabla_maestro_subcuentas_empresa_existe(tmp_path):
    g = _gestor(tmp_path)
    assert "maestro_subcuentas_empresa" in _tables(g)


def test_tabla_captura_documental_retenciones_existe(tmp_path):
    g = _gestor(tmp_path)
    assert "captura_documental_retenciones" in _tables(g)


# ── Columnas nuevas en terceros ───────────────────────────────────────────────

def test_terceros_columnas_fase2(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "terceros")
    for col in ("nif_normalizado", "nombre_legal", "nombre_comercial",
                "tipo_identificacion", "pais", "codigo_postal", "observaciones",
                "origen", "activo", "fecha_creacion", "fecha_actualizacion"):
        assert col in cols, f"Columna 'terceros.{col}' no existe"


# ── Columnas nuevas en ocr_lineas_fiscales ────────────────────────────────────

def test_ocr_lineas_fiscales_columnas_fase2(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "ocr_lineas_fiscales")
    for col in ("cuota_iva_manual", "cuota_recargo_manual",
                "subcuenta_base_id", "subcuenta_iva_id",
                "subcuenta_recargo_id", "observaciones"):
        assert col in cols, f"Columna 'ocr_lineas_fiscales.{col}' no existe"


def test_terceros_empresas_columnas_configuracion_fiscal(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "terceros_empresas")
    for col in (
        "cliente_tipo_operacion_iva",
        "cliente_intracomunitaria_clase",
        "cliente_iva_deducible",
        "cliente_porcentaje_deduccion_iva",
        "proveedor_tipo_operacion_iva",
        "proveedor_intracomunitaria_clase",
        "proveedor_iva_deducible",
        "proveedor_porcentaje_deduccion_iva",
    ):
        assert col in cols, f"Columna 'terceros_empresas.{col}' no existe"


def test_facturas_recibidas_docs_columnas_configuracion_fiscal(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "facturas_recibidas_docs")
    for col in (
        "proveedor_tipo_operacion_iva",
        "proveedor_iva_deducible",
        "proveedor_porcentaje_deduccion_iva",
    ):
        assert col in cols, f"Columna 'facturas_recibidas_docs.{col}' no existe"


# ── Columnas nuevas en plan_cuentas ──────────────────────────────────────────

def test_plan_cuentas_columnas_fase2(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "plan_cuentas")
    for col in ("tipo_cuenta", "tercero_id", "pendiente_alta_a3",
                "origen_cuenta", "activo"):
        assert col in cols, f"Columna 'plan_cuentas.{col}' no existe"


# ── Columnas maestro_subcuentas_empresa ───────────────────────────────────────

def test_maestro_subcuentas_empresa_columnas(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "maestro_subcuentas_empresa")
    for col in ("id", "codigo_empresa", "tercero_id", "subcuenta",
                "nombre_subcuenta", "tipo_subcuenta",
                "tipo_operacion_predeterminada",
                "cuenta_gasto_predeterminada_id",
                "cuenta_ingreso_predeterminada_id",
                "cuenta_iva_predeterminada_id",
                "cuenta_retencion_predeterminada_id",
                "nif_snapshot", "activo", "origen", "fecha_importacion",
                "creado_en_gest2a3eco", "pendiente_alta_a3",
                "fecha_alta_a3", "lote_alta_a3", "observaciones",
                "created_at", "updated_at"):
        assert col in cols, f"Columna 'maestro_subcuentas_empresa.{col}' no existe"


# ── Columnas captura_documental_retenciones ───────────────────────────────────

def test_captura_retenciones_columnas(tmp_path):
    g = _gestor(tmp_path)
    cols = _columns(g, "captura_documental_retenciones")
    for col in ("id", "documento_id", "base_retencion", "tipo_retencion",
                "cuota_retencion", "cuota_retencion_manual",
                "tipo_retencion_fiscal", "subcuenta_retencion_id", "observaciones"):
        assert col in cols, f"Columna 'captura_documental_retenciones.{col}' no existe"


# ── Idempotencia: segunda instancia no falla ─────────────────────────────────

def test_doble_instancia_no_falla(tmp_path):
    db = tmp_path / "idem.db"
    g1 = GestorSQLite(db)
    g1.conn.close()
    g2 = GestorSQLite(db)
    assert "maestro_subcuentas_empresa" in _tables(g2)
