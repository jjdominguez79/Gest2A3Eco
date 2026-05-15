from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.ocr_recibidas_service import mark_docs_as_generated


def _make_gestor(tmp_path: Path) -> GestorSQLite:
    db_path = tmp_path / "ocr-flow.db"
    gestor = GestorSQLite(db_path)
    gestor.upsert_empresa(
        {
            "codigo": "E00570",
            "ejercicio": 2026,
            "nombre": "Empresa Demo",
            "digitos_plan": 8,
            "activo": 1,
        }
    )
    return gestor


def test_mark_docs_as_generated_updates_states(tmp_path):
    gestor = _make_gestor(tmp_path)
    doc = {
        "id": "doc-1",
        "codigo_empresa": "E00570",
        "ejercicio": 2026,
        "estado_ocr": "procesado",
        "estado_validacion": "validada",
        "estado_contable": "pendiente_contabilizar",
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
    gestor.upsert_factura_recibida_doc(doc)

    persisted = gestor.get_factura_recibida_doc("doc-1")
    assert persisted["estado_contable"] == "pendiente_contabilizar"
    assert persisted["generada"] is False

    mark_docs_as_generated(gestor, [persisted], fecha_generacion="2026-05-15 12:30")

    updated = gestor.get_factura_recibida_doc("doc-1")
    assert updated["estado_contable"] == "contabilizada"
    assert updated["generada"] is True
    assert updated["fecha_generacion"] == "2026-05-15 12:30"
