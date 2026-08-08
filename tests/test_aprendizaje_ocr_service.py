import json

from services.ocr.aprendizaje_service import AprendizajeOcrService


class GestorPrueba:
    def __init__(self):
        self.ejemplos = []

    def listar_lineas_iva_ocr(self, factura_id):
        assert factura_id == "fac-1"
        return [{"tipo_iva": 21, "base": 100, "cuota_iva": 21}]

    def upsert_ejemplo_aprendizaje_ocr(self, ejemplo):
        existente = next(
            (
                item
                for item in self.ejemplos
                if item["factura_id"] == ejemplo["factura_id"]
            ),
            None,
        )
        if existente:
            existente.update(ejemplo)
            return existente["id"]
        nuevo = dict(ejemplo)
        nuevo["id"] = len(self.ejemplos) + 1
        self.ejemplos.append(nuevo)
        return nuevo["id"]

    def resumen_aprendizaje_ocr(self, empresa_id):
        pendientes = [
            item
            for item in self.ejemplos
            if item["empresa_id"] == empresa_id and item["estado"] == "pendiente"
        ]
        por_proveedor = {}
        for item in pendientes:
            proveedor = item["proveedor_nif"]
            por_proveedor[proveedor] = por_proveedor.get(proveedor, 0) + 1
        return {"pendientes": len(pendientes), "por_proveedor": por_proveedor}


def test_registrar_factura_validada_crea_ejemplo_privado_y_estructurado():
    gestor = GestorPrueba()
    service = AprendizajeOcrService(gestor, "E00001")
    service.registrar_factura_validada(
        {"id": "doc-1", "ruta_original": "C:/factura.pdf"},
        {"id": "fac-1", "nif_proveedor": "A123", "nombre_proveedor": "Proveedor",
         "numero_factura": "F-1", "fecha_factura": "2026-08-05", "base_total": 100,
         "iva_total": 21, "total_factura": 121},
    )
    row = gestor.ejemplos[0]
    data = json.loads(row["datos_validados_json"])
    assert row["empresa_id"] == "E00001"
    assert data["NumeroFactura"] == "F-1"
    assert data["LineasIva"] == [{"Base": 100.0, "CuotaIva": 21.0, "TipoIva": 21.0}]
    assert service.resumen() == {"pendientes": 1, "por_proveedor": {"A123": 1}}
