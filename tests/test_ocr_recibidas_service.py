"""Tests de ocr_recibidas_service: mapeo de filas y generacion de suenlace."""
from pathlib import Path

import pytest

from models.gestor_sqlite import GestorSQLite
from services.ocr_recibidas_service import doc_to_row, doc_to_rows, generate_suenlace_for_docs


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_doc(**overrides) -> dict:
    doc = {
        "id": "doc-1",
        "codigo_empresa": "E00570",
        "ejercicio": 2026,
        "fecha_asiento": "2026-05-15",
        "fecha_factura": "2026-05-14",
        "fecha_operacion": "2026-05-14",
        "descripcion": "Factura de prueba",
        "numero_factura": "F-100",
        "proveedor_nif": "B12345678",
        "proveedor_nombre": "Proveedor Demo SL",
        "base_imponible": 100.0,
        "cuota_iva": 21.0,
        "cuota_recargo": 0.0,
        "cuota_retencion": 0.0,
        "total": 121.0,
        "cuenta_proveedor": "40000001",
        "cuenta_gasto": "62900000",
        "cuenta_iva": "47200000",
    }
    doc.update(overrides)
    return doc


def _make_gestor(tmp_path: Path) -> GestorSQLite:
    g = GestorSQLite(tmp_path / "recibidas.db")
    g.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Empresa Demo", "digitos_plan": 8, "activo": 1,
    })
    return g


# ── doc_to_row ────────────────────────────────────────────────────────────────

def test_doc_to_row_mapea_campos_esperados():
    row = doc_to_row(_base_doc())
    assert row["Fecha Asiento"] == "2026-05-15"
    assert row["Numero Factura"] == "F-100"
    assert row["NIF Cliente Proveedor"] == "B12345678"
    assert row["Base"] == 100.0
    assert row["Cuota IVA"] == 21.0
    assert row["_cuenta_tercero_override"] == "40000001"
    assert row["_pdf_ref"] == "doc-1"


# ── doc_to_rows: fallback single-row ─────────────────────────────────────────

def test_doc_to_rows_sin_lineas_devuelve_una_fila():
    rows = doc_to_rows(_base_doc(), [])
    assert len(rows) == 1
    assert rows[0]["Base"] == 100.0


def test_doc_to_rows_lineas_todo_cero_devuelve_fallback():
    lineas_vacias = [
        {"base_imponible": 0.0, "cuota_iva": 0.0, "cuota_recargo": 0.0, "cuota_retencion": 0.0}
    ]
    rows = doc_to_rows(_base_doc(), lineas_vacias)
    assert len(rows) == 1
    assert rows[0]["Base"] == 100.0  # valor del doc, no de la linea


def test_doc_to_rows_none_lineas_devuelve_fallback():
    rows = doc_to_rows(_base_doc(), None)
    assert len(rows) == 1


# ── doc_to_rows: multi-base expansion ────────────────────────────────────────

def test_doc_to_rows_dos_tramos_produce_dos_filas():
    lineas = [
        {"base_imponible": 600.0, "tipo_iva": 21.0, "cuota_iva": 126.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
        {"base_imponible": 400.0, "tipo_iva": 10.0, "cuota_iva":  40.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
    ]
    rows = doc_to_rows(_base_doc(), lineas)
    assert len(rows) == 2
    assert rows[0]["Base"] == 600.0
    assert rows[0]["Porcentaje IVA"] == 21.0
    assert rows[0]["Cuota IVA"] == 126.0
    assert rows[1]["Base"] == 400.0
    assert rows[1]["Porcentaje IVA"] == 10.0
    assert rows[1]["Cuota IVA"] == 40.0


def test_doc_to_rows_campos_comunes_replicados_en_cada_fila():
    lineas = [
        {"base_imponible": 600.0, "tipo_iva": 21.0, "cuota_iva": 126.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
        {"base_imponible": 400.0, "tipo_iva": 10.0, "cuota_iva":  40.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
    ]
    rows = doc_to_rows(_base_doc(), lineas)
    for row in rows:
        assert row["Numero Factura"] == "F-100"
        assert row["NIF Cliente Proveedor"] == "B12345678"
        assert row["_pdf_ref"] == "doc-1"
        assert row["_cuenta_tercero_override"] == "40000001"


def test_doc_to_rows_cuenta_base_por_linea_sobreescribe_global():
    lineas = [
        {"base_imponible": 1000.0, "tipo_iva": 21.0, "cuota_iva": 210.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": "62100000", "cuenta_iva": "47201000"},
    ]
    rows = doc_to_rows(_base_doc(), lineas)
    assert rows[0].get("Cuenta Compras Ventas") == "62100000"
    assert rows[0].get("_cuenta_iva_override") == "47201000"


def test_doc_to_rows_recargo_y_retencion_por_linea():
    lineas = [
        {"base_imponible": 1000.0, "tipo_iva": 21.0, "cuota_iva": 210.0,
         "tipo_recargo": 5.2, "cuota_recargo": 52.0,
         "tipo_retencion": 15.0, "cuota_retencion": 150.0},
    ]
    rows = doc_to_rows(_base_doc(), lineas)
    assert rows[0]["Porcentaje Recargo Equivalencia"] == 5.2
    assert rows[0]["Cuota Recargo Equivalencia"] == 52.0
    assert rows[0]["Porcentaje Retencion IRPF"] == 15.0
    assert rows[0]["Cuota Retencion IRPF"] == 150.0


# ── generate_suenlace_for_docs ────────────────────────────────────────────────

def test_generate_suenlace_devuelve_registros(tmp_path):
    g = _make_gestor(tmp_path)
    doc = _base_doc(estado_ocr="procesado", estado_validacion="validada",
                    estado_contable="pendiente_contabilizar",
                    generada=0, lineas=[], datos_extra={})
    regs = generate_suenlace_for_docs(g, "E00570", 2026, [doc])
    # Cabecera + 1 tipo9 + tipo6 de trazabilidad
    assert len(regs) >= 2
    assert any("G2A" in line for line in regs)


def test_generate_suenlace_multibase_produce_dos_tipo9(tmp_path):
    """Dos tramos de IVA deben generar 2 registros tipo-9 (+ 1 cabecera + 1 tipo-6)."""
    g = _make_gestor(tmp_path)
    lineas = [
        {"base_imponible": 600.0, "tipo_iva": 21.0, "cuota_iva": 126.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
        {"base_imponible": 400.0, "tipo_iva": 10.0, "cuota_iva":  40.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0},
    ]
    doc_multi = _base_doc(
        estado_ocr="procesado", estado_validacion="validada",
        estado_contable="pendiente_contabilizar",
        base_imponible=1000.0, cuota_iva=166.0, total=1166.0,
        generada=0, lineas=lineas, datos_extra={},
    )
    doc_single = _base_doc(
        id="doc-2", numero_factura="F-200",
        estado_ocr="procesado", estado_validacion="validada",
        estado_contable="pendiente_contabilizar",
        generada=0, lineas=[], datos_extra={},
    )
    regs_multi  = generate_suenlace_for_docs(g, "E00570", 2026, [doc_multi])
    regs_single = generate_suenlace_for_docs(g, "E00570", 2026, [doc_single])
    # Multi-base debe tener mas registros que single-base por los dos tipo-9
    assert len(regs_multi) > len(regs_single)


def test_generate_suenlace_lista_vacia(tmp_path):
    g = _make_gestor(tmp_path)
    assert generate_suenlace_for_docs(g, "E00570", 2026, []) == []
