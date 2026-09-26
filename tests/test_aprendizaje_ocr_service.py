import json
from types import SimpleNamespace

from services.ocr.aprendizaje_service import AprendizajeOcrService


class GestorPrueba:
    def __init__(self):
        self.ejemplos = []

    def listar_lineas_iva_ocr(self, factura_id):
        assert factura_id == "fac-1"
        return [{"tipo_iva": 21, "base": 100, "cuota_iva": 21}]

    def listar_lineas_iva_emitida_ocr(self, factura_id):
        assert factura_id == "fac-1"
        return [{"tipo_iva": 21, "base": 200, "cuota_iva": 42}]

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
    assert data["TipoDocumento"] == "factura_recibida"
    assert data["LineasIva"] == [{"Base": 100.0, "CuotaIva": 21.0, "TipoIva": 21.0}]
    assert service.resumen() == {"pendientes": 1, "por_proveedor": {"A123": 1}}


def test_registrar_factura_emitida_separa_emisor_cliente_y_lineas():
    gestor = GestorPrueba()
    service = AprendizajeOcrService(gestor, "E00001")
    service.registrar_factura_validada(
        {
            "id": "doc-2", "ruta_original": "C:/emitida.pdf",
            "tipo_documento": "factura_emitida",
            "json_ocr": json.dumps({
                "proveedor_nif": "B11111111",
                "proveedor_nombre": "Empresa emisora SL",
            }),
        },
        {
            "id": "fac-1", "nif_cliente": "B22222222",
            "nombre_cliente": "Cliente SL", "numero_factura": "E-1",
            "fecha_factura": "2026-08-18", "base_total": 200,
            "iva_total": 42, "total_factura": 242,
        },
    )
    row = gestor.ejemplos[0]
    data = json.loads(row["datos_validados_json"])
    assert data["TipoDocumento"] == "factura_emitida"
    assert data["EmisorNif"] == "B11111111"
    assert data["ClienteNif"] == "B22222222"
    assert "ProveedorNif" not in data
    assert data["LineasIva"] == [
        {"Base": 200.0, "CuotaIva": 42.0, "TipoIva": 21.0}
    ]
    assert row["proveedor_nif"] == "B22222222"


class GestorModelo:
    def __init__(self):
        self.modelos = []

    def listar_ejemplos_aprendizaje_ocr_todos(self, empresa_id):
        assert empresa_id == "E00001"
        return [{
            "id": 1, "empresa_id": empresa_id, "proveedor_nif": "B12345678",
            "origen_path": "factura.pdf",
            "datos_validados_json": json.dumps({"TipoDocumento": "factura_recibida"}),
            "marcas_json": json.dumps({
                "NumeroFactura": {"page": 0, "x": 150, "y": 300, "width": 180, "height": 30},
            }),
        }]

    def upsert_modelo_ocr_local(self, modelo):
        modelo = dict(modelo)
        modelo["version"] = 1
        self.modelos.append(modelo)
        return modelo["id"]

    def listar_modelos_ocr_locales(self, empresa_id, tipo_documento):
        return self.modelos


def test_entrenamiento_local_normaliza_marcas_y_las_aplica(monkeypatch):
    gestor = GestorModelo()
    service = AprendizajeOcrService(gestor, "E00001")
    monkeypatch.setattr(
        service, "_dimensiones_paginas", lambda _path: {0: (900.0, 1200.0)},
    )

    resumen = service.entrenar_modelos_locales()

    assert resumen == {"modelos_entrenados": 1, "ejemplos_revisados": 1}
    campos = json.loads(gestor.modelos[0]["campos_json"])
    assert campos["NumeroFactura"]["x"] == round(150 / 900, 6)

    monkeypatch.setattr(
        service, "_extraer_campos", lambda _path, _campos: {"NumeroFactura": "F-2026-15"},
    )
    resultado = SimpleNamespace(
        proveedor_nif="B12345678", texto="", numero_factura="",
        proveedor_nombre="", cliente_nif="", cliente_nombre="",
        fecha_factura="", fecha_vencimiento="", base_total=0.0,
        iva_total=0.0, total=0.0, raw_json={}, motor="azure_backend",
        confianza=0.6,
    )

    service.aplicar_modelo_local("factura.pdf", resultado)

    assert resultado.numero_factura == "F-2026-15"
    assert resultado.motor == "azure_backend+modelo_local_v1"
    assert resultado.raw_json["modelo_local"]["tercero_nif"] == "B12345678"
