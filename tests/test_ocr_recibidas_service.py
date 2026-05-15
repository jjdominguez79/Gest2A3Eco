from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.ocr_recibidas_service import doc_to_row, generate_suenlace_for_docs


def test_doc_to_row_maps_expected_fields():
    doc = {
        "id": "doc-1",
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
    row = doc_to_row(doc)
    assert row["Fecha Asiento"] == "2026-05-15"
    assert row["Numero Factura"] == "F-100"
    assert row["NIF Cliente Proveedor"] == "B12345678"
    assert row["Base"] == 100.0
    assert row["_cuenta_tercero_override"] == "40000001"
    assert row["_pdf_ref"] == "doc-1"


def test_generate_suenlace_for_docs_returns_records(tmp_path):
    db_path = Path(tmp_path) / "ocr-recibidas.db"
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
    regs = generate_suenlace_for_docs(gestor, "E00570", 2026, [doc])
    assert regs
    assert any(line.startswith("1") or line.startswith("2") for line in regs)
    assert any("G2A" in line for line in regs)
