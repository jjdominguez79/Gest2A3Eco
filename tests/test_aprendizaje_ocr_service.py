import json
import sqlite3

from services.ocr.aprendizaje_service import AprendizajeOcrService


class GestorPrueba:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE ocr_aprendizaje_ejemplos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_id TEXT NOT NULL,
                documento_id TEXT NOT NULL, factura_id TEXT NOT NULL UNIQUE,
                proveedor_nif TEXT, origen_path TEXT, datos_validados_json TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente', modelo_destino TEXT,
                fecha_validacion TEXT NOT NULL, fecha_exportacion TEXT, notas TEXT,
                marcas_json TEXT NOT NULL DEFAULT '{}'
            );
        """)

    def listar_lineas_iva_ocr(self, factura_id):
        assert factura_id == "fac-1"
        return [{"tipo_iva": 21, "base": 100, "cuota_iva": 21}]

    def upsert_ejemplo_aprendizaje_ocr(self, ejemplo):
        cur = self.conn.execute(
            "INSERT INTO ocr_aprendizaje_ejemplos "
            "(empresa_id, documento_id, factura_id, proveedor_nif, origen_path, datos_validados_json, estado, fecha_validacion, notas, marcas_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(factura_id) DO UPDATE SET datos_validados_json=excluded.datos_validados_json, estado='pendiente', marcas_json=excluded.marcas_json",
            (ejemplo["empresa_id"], ejemplo["documento_id"], ejemplo["factura_id"],
             ejemplo["proveedor_nif"], ejemplo["origen_path"], ejemplo["datos_validados_json"],
             ejemplo["estado"], ejemplo["fecha_validacion"], ejemplo["notas"], ejemplo.get("marcas_json", "{}")),
        )
        self.conn.commit()
        return cur.lastrowid

    def resumen_aprendizaje_ocr(self, empresa_id):
        rows = self.conn.execute(
            "SELECT proveedor_nif, COUNT(*) total FROM ocr_aprendizaje_ejemplos "
            "WHERE empresa_id=? AND estado='pendiente' GROUP BY proveedor_nif", (empresa_id,)
        ).fetchall()
        return {"pendientes": sum(row["total"] for row in rows),
                "por_proveedor": {row["proveedor_nif"]: row["total"] for row in rows}}


def test_registrar_factura_validada_crea_ejemplo_privado_y_estructurado():
    gestor = GestorPrueba()
    service = AprendizajeOcrService(gestor, "E00001")
    service.registrar_factura_validada(
        {"id": "doc-1", "ruta_original": "C:/factura.pdf"},
        {"id": "fac-1", "nif_proveedor": "A123", "nombre_proveedor": "Proveedor",
         "numero_factura": "F-1", "fecha_factura": "2026-08-05", "base_total": 100,
         "iva_total": 21, "total_factura": 121},
    )
    row = gestor.conn.execute("SELECT * FROM ocr_aprendizaje_ejemplos").fetchone()
    data = json.loads(row["datos_validados_json"])
    assert row["empresa_id"] == "E00001"
    assert data["NumeroFactura"] == "F-1"
    assert data["LineasIva"] == [{"Base": 100.0, "CuotaIva": 21.0, "TipoIva": 21.0}]
    assert service.resumen() == {"pendientes": 1, "por_proveedor": {"A123": 1}}
