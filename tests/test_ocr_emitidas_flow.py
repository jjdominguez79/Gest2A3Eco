from services.ocr.ocr_service import OcrService
from services.ocr.types import OcrInvoiceResult, OcrRetentionLine, OcrVatLine
from services.ocr_emitidas_contabilidad_service import OcrEmitContabilidadService


class GestorOcrFalso:
    def __init__(self):
        self.factura = None
        self.lineas = []
        self.retenciones = []

    def upsert_factura_emitida_ocr(self, payload):
        self.factura = dict(payload)

    def upsert_linea_iva_emitida_ocr(self, payload):
        self.lineas.append(dict(payload))

    def upsert_retencion_emitida_ocr(self, payload):
        self.retenciones.append(dict(payload))


def test_ocr_emitida_se_guarda_en_su_tabla_y_respeta_fecha_contable():
    gestor = GestorOcrFalso()
    servicio = object.__new__(OcrService)
    servicio._gestor = gestor
    servicio._empresa = "E00001"
    servicio._tipo_documento = "factura_emitida"
    servicio._fecha_contable = "2026-08-18"
    resultado = OcrInvoiceResult(
        proveedor_nombre="Empresa emisora",
        proveedor_nif="B11111111",
        cliente_nombre="Cliente Uno",
        cliente_nif="B12345678",
        numero_factura="EXT-42",
        fecha_factura="2026-08-10",
        total=121.0,
        base_total=100.0,
        iva_total=21.0,
        bases_iva=[OcrVatLine(tipo_iva=21.0, base=100.0, cuota_iva=21.0)],
        retenciones=[OcrRetentionLine(base_retencion=100.0, tipo_retencion=0.0)],
    )

    factura_id = servicio._guardar_factura("doc-1", resultado)

    assert gestor.factura["id"] == factura_id
    assert gestor.factura["nif_cliente"] == "B12345678"
    assert gestor.factura["fecha_contable"] == "2026-08-18"
    assert gestor.lineas[0]["cuenta_ingreso"] == ""
    assert gestor.retenciones[0]["factura_id"] == factura_id


class GestorContabilidadFalso:
    def __init__(self):
        self.factura = None
        self.enviados = None

    def listar_lineas_iva_emitida_ocr(self, _factura_id):
        return [{
            "base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0,
            "tipo_recargo": 0.0, "cuota_recargo": 0.0,
            "cuenta_ingreso": "70000000",
        }]

    def listar_terceros_por_empresa(self, _codigo, _ejercicio):
        return []

    def upsert_factura_emitida(self, payload):
        self.factura = dict(payload)

    def enviar_facturas_emitidas_a_contabilidad(self, codigo, ejercicio, ids):
        self.enviados = (codigo, ejercicio, list(ids))


def test_emitida_validada_entra_en_contabilidad_con_formato_existente():
    gestor = GestorContabilidadFalso()
    servicio = OcrEmitContabilidadService(gestor, "E00001", 2026)

    payload = servicio.proyectar_factura_validada(
        {"id": "doc-1", "ruta_original": r"C:\docs\externa.pdf"},
        {
            "id": "ocr-1", "nif_cliente": "B12345678",
            "nombre_cliente": "Cliente Uno", "numero_factura": "EXT-42",
            "fecha_factura": "2026-08-10", "fecha_contable": "2026-08-18",
            "base_total": 100.0, "retencion_total": 0.0,
        },
    )

    assert gestor.factura["id"] == "doc-1"
    assert gestor.factura["numero"] == "EXT-42"
    assert gestor.factura["fecha_asiento"] == "2026-08-18"
    assert gestor.factura["lineas"][0]["pct_iva"] == 21.0
    assert gestor.factura["origen_factura"] == "ocr"
    assert gestor.factura["ocr_documento_id"] == "doc-1"
    assert gestor.enviados == ("E00001", 2026, ["doc-1"])
    assert payload["estado_contable"] == "pendiente"


class ConexionReclasificacionFalsa:
    def __init__(self):
        self.sentencias = []
        self.commits = 0

    def execute(self, sql, params):
        self.sentencias.append((" ".join(sql.split()), params))

    def commit(self):
        self.commits += 1


class GestorReclasificacionFalso:
    def __init__(self, documento):
        self.documento = dict(documento)
        self.conn = ConexionReclasificacionFalsa()
        self.guardados = []

    def buscar_documento_ocr_por_hash(self, _empresa, _hash):
        return dict(self.documento)

    def upsert_documento_ocr(self, documento):
        self.documento = dict(documento)
        self.guardados.append(dict(documento))


def test_duplicado_pendiente_se_reclasifica_como_emitida(tmp_path):
    archivo = tmp_path / "factura.pdf"
    archivo.write_bytes(b"pdf")
    gestor = GestorReclasificacionFalso({
        "id": "doc-1",
        "nombre_archivo": "factura.pdf",
        "ruta_original": str(archivo),
        "tipo_documento": "factura_recibida",
        "estado": "pendiente_revision",
    })
    servicio = object.__new__(OcrService)
    servicio._gestor = gestor
    servicio._empresa = "E00001"
    servicio._ejercicio = 2026
    servicio._tipo_documento = "factura_emitida"
    notificaciones = []
    servicio.reprocesar_documento = lambda documento_id, progress_callback=None: {
        "documento_id": documento_id,
        "estado": "pendiente_revision",
        "errores": [],
    }

    resultado = servicio.procesar_archivo(
        str(archivo), progress_callback=notificaciones.append,
    )

    assert resultado["documento_id"] == "doc-1"
    assert gestor.documento["tipo_documento"] == "factura_emitida"
    assert gestor.documento["estado"] == "procesando"
    assert notificaciones[0]["tipo_documento"] == "factura_emitida"
    assert len(gestor.conn.sentencias) == 2
