from services.empresa_service import EmpresaService


class GestorDashboard:
    def get_empresa(self, codigo, ejercicio):
        return {"codigo": codigo, "ejercicio": ejercicio, "nombre": "Alfa", "cif": "A12345678"}

    def listar_ejercicios_empresa(self, codigo):
        return [2026]

    def listar_facturas_emitidas(self, codigo, ejercicio):
        return [
            {
                "id": "F1", "fecha_expedicion": "2026-01-15", "generada": True,
                "enviado": True, "borrador": False,
                "lineas": [{"base": 100, "cuota_iva": 21, "cuota_re": 0}],
            },
            {
                "id": "F2", "fecha_expedicion": "2026-02-15", "generada": False,
                "enviado": False, "borrador": True,
                "lineas": [{"base": 500, "cuota_iva": 105, "cuota_re": 0}],
            },
        ]

    def listar_comunicaciones(self, codigo):
        return [{"id": "C1", "estado": "abierta", "asunto": "Documentacion"}]

    def listar_mensajes_comunicacion(self, comunicacion_id):
        return [
            {"fecha": "2026-01-21T10:00:00+01:00", "direccion": "saliente", "asunto": "Respuesta"},
            {"fecha": "2026-01-20T10:00:00+01:00", "direccion": "entrante", "asunto": "Documentacion", "remitente": "cliente@example.com"},
        ]

    def listar_bancos(self, *args): return []
    def listar_emitidas(self, *args): return []
    def listar_recibidas(self, *args): return []
    def listar_facturas_recibidas_docs(self, *args): return [{"estado_validacion": "pendiente"}]
    def listar_terceros_por_empresa(self, *args): return []
    def listar_maestro_subcuentas_empresa(self, *args, **kwargs): return []
    def listar_cuentas_bancarias(self, *args): return []


def test_dashboard_resume_facturacion_correos_y_pendientes():
    context = EmpresaService(GestorDashboard()).get_dashboard_context("E00001", 2026)

    assert context["resumen_facturacion"]["importe_total"] == 121.0
    assert context["resumen_facturacion"]["mensual"][:2] == [121.0, 0.0]
    assert context["resumen_comunicaciones"] == {"recibidos": 1, "enviados": 1, "pendientes": 1}
    assert context["pendientes"] == {"total": 3, "correos": 1, "ocr": 1, "facturacion": 1}
    assert context["actividad_comunicaciones"][0]["asunto"] == "Respuesta"
