"""Tests de flujo de estados OCR: transiciones, bandejas y lineas fiscales."""
from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.ocr_recibidas_service import mark_docs_as_generated


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gestor(tmp_path: Path) -> GestorSQLite:
    db_path = tmp_path / "ocr-flow.db"
    gestor = GestorSQLite(db_path)
    gestor.upsert_empresa({
        "codigo": "E00570", "ejercicio": 2026,
        "nombre": "Empresa Demo", "digitos_plan": 8, "activo": 1,
    })
    return gestor


def _base_doc(doc_id: str = "doc-1", **overrides) -> dict:
    doc = {
        "id": doc_id,
        "codigo_empresa": "E00570",
        "ejercicio": 2026,
        "estado_ocr": "procesado",
        "estado_validacion": "pendiente",
        "estado_contable": "",
        "proveedor_nif": "B12345678",
        "proveedor_nombre": "Proveedor Demo SL",
        "numero_factura": "F-1",
        "fecha_factura": "2026-05-15",
        "fecha_operacion": "2026-05-15",
        "fecha_asiento": "2026-05-15",
        "descripcion": "Factura Demo",
        "base_imponible": 100.0,
        "cuota_iva": 21.0,
        "cuota_recargo": 0.0,
        "cuota_retencion": 0.0,
        "total": 121.0,
        "cuenta_gasto": "62900000",
        "cuenta_iva": "47200000",
        "cuenta_proveedor": "40000001",
        "generada": 0,
        "lineas": [],
        "datos_extra": {},
    }
    doc.update(overrides)
    return doc


# ── mark_docs_as_generated ────────────────────────────────────────────────────

def test_mark_docs_as_generated_updates_states(tmp_path):
    gestor = _make_gestor(tmp_path)
    doc = _base_doc(estado_contable="pendiente_contabilizar")
    gestor.upsert_factura_recibida_doc(doc)

    persisted = gestor.get_factura_recibida_doc("doc-1")
    assert persisted["estado_contable"] == "pendiente_contabilizar"
    assert persisted["generada"] is False

    mark_docs_as_generated(gestor, [persisted], fecha_generacion="2026-05-15 12:30")

    updated = gestor.get_factura_recibida_doc("doc-1")
    assert updated["estado_contable"] == "contabilizada"
    assert updated["generada"] is True
    assert updated["fecha_generacion"] == "2026-05-15 12:30"


# ── Filtrado por bandeja ──────────────────────────────────────────────────────

def test_bandeja_pendiente_revision_filtra_correctamente(tmp_path):
    gestor = _make_gestor(tmp_path)
    # Este debe aparecer en pendiente_revision
    gestor.upsert_factura_recibida_doc(
        _base_doc("d1", estado_ocr="procesado", estado_validacion="pendiente")
    )
    # Este no (estado_ocr=error)
    gestor.upsert_factura_recibida_doc(
        _base_doc("d2", estado_ocr="error", estado_validacion="pendiente")
    )

    docs = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "pendiente_revision")
    ids = [d["id"] for d in docs]
    assert "d1" in ids
    assert "d2" not in ids


def test_bandeja_error_filtra_correctamente(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(
        _base_doc("d1", estado_ocr="error", error_mensaje="Fallo OCR")
    )
    gestor.upsert_factura_recibida_doc(
        _base_doc("d2", estado_ocr="procesado")
    )

    docs = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "error")
    ids = [d["id"] for d in docs]
    assert "d1" in ids
    assert "d2" not in ids


def test_bandeja_pendiente_contabilizar_filtra_correctamente(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(
        _base_doc("d1", estado_validacion="validada", estado_contable="pendiente_contabilizar")
    )
    gestor.upsert_factura_recibida_doc(
        _base_doc("d2", estado_validacion="pendiente", estado_contable="")
    )

    docs = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "pendiente_contabilizar")
    ids = [d["id"] for d in docs]
    assert "d1" in ids
    assert "d2" not in ids


def test_bandeja_contabilizada_filtra_correctamente(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(
        _base_doc("d1", estado_contable="contabilizada")
    )
    gestor.upsert_factura_recibida_doc(
        _base_doc("d2", estado_contable="pendiente_contabilizar")
    )

    docs = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "contabilizada")
    ids = [d["id"] for d in docs]
    assert "d1" in ids
    assert "d2" not in ids


def test_bandeja_sin_filtro_devuelve_todos(tmp_path):
    gestor = _make_gestor(tmp_path)
    for i in range(3):
        gestor.upsert_factura_recibida_doc(_base_doc(f"d{i}"))

    docs = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, None)
    assert len(docs) >= 3


# ── Lineas fiscales CRUD ──────────────────────────────────────────────────────

def test_reemplazar_ocr_lineas_doc_round_trip(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(_base_doc())

    lineas = [
        {"orden": 0, "tipo_iva": 21.0, "base_imponible": 600.0, "cuota_iva": 126.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
        {"orden": 1, "tipo_iva": 10.0, "base_imponible": 400.0, "cuota_iva":  40.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
    ]
    gestor.reemplazar_ocr_lineas_doc("doc-1", lineas)

    recovered = gestor.listar_ocr_lineas_doc("doc-1")
    assert len(recovered) == 2
    assert recovered[0]["tipo_iva"] == 21.0
    assert recovered[0]["base_imponible"] == 600.0
    assert recovered[1]["tipo_iva"] == 10.0
    assert recovered[1]["base_imponible"] == 400.0


def test_reemplazar_ocr_lineas_borra_anteriores(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(_base_doc())

    lineas_v1 = [
        {"orden": 0, "tipo_iva": 21.0, "base_imponible": 1000.0, "cuota_iva": 210.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
    ]
    gestor.reemplazar_ocr_lineas_doc("doc-1", lineas_v1)
    assert len(gestor.listar_ocr_lineas_doc("doc-1")) == 1

    # Reemplazar con lineas completamente distintas
    lineas_v2 = [
        {"orden": 0, "tipo_iva": 10.0, "base_imponible": 500.0, "cuota_iva": 50.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
        {"orden": 1, "tipo_iva": 4.0, "base_imponible": 200.0, "cuota_iva": 8.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
    ]
    gestor.reemplazar_ocr_lineas_doc("doc-1", lineas_v2)
    recovered = gestor.listar_ocr_lineas_doc("doc-1")
    assert len(recovered) == 2
    assert recovered[0]["tipo_iva"] == 10.0


def test_reemplazar_ocr_lineas_vacia_elimina_todas(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(_base_doc())

    gestor.reemplazar_ocr_lineas_doc("doc-1", [
        {"orden": 0, "tipo_iva": 21.0, "base_imponible": 100.0, "cuota_iva": 21.0,
         "tipo_recargo": 0.0, "cuota_recargo": 0.0, "tipo_retencion": 0.0, "cuota_retencion": 0.0,
         "cuenta_base": None, "cuenta_iva": None, "cuenta_retencion": None, "tipo_operacion_linea": None},
    ])
    gestor.reemplazar_ocr_lineas_doc("doc-1", [])
    assert gestor.listar_ocr_lineas_doc("doc-1") == []


# ── Transicion de estado ──────────────────────────────────────────────────────

def test_estado_transicion_procesando_a_error(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(
        _base_doc(estado_ocr="procesando")
    )
    doc = gestor.get_factura_recibida_doc("doc-1")
    doc["estado_ocr"] = "error"
    doc["error_mensaje"] = "Fallo al leer el PDF."
    gestor.upsert_factura_recibida_doc(doc)

    updated = gestor.get_factura_recibida_doc("doc-1")
    assert updated["estado_ocr"] == "error"
    assert updated["error_mensaje"] == "Fallo al leer el PDF."

    en_error = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "error")
    assert any(d["id"] == "doc-1" for d in en_error)


def test_estado_transicion_revision_a_pendiente_contabilizar(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_factura_recibida_doc(
        _base_doc(estado_ocr="procesado", estado_validacion="pendiente", estado_contable="")
    )

    doc = gestor.get_factura_recibida_doc("doc-1")
    doc["estado_validacion"] = "validada"
    doc["estado_contable"] = "pendiente_contabilizar"
    gestor.upsert_factura_recibida_doc(doc)

    en_revision = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "pendiente_revision")
    en_pte_cont = gestor.listar_facturas_recibidas_docs_filtrado("E00570", 2026, "pendiente_contabilizar")

    assert not any(d["id"] == "doc-1" for d in en_revision)
    assert any(d["id"] == "doc-1" for d in en_pte_cont)
