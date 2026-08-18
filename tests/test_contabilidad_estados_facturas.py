from models.gestor_base import GestorBase


class _Cursor:
    def __init__(self, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)


class _Conexion:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.sentencias = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=()):
        sql_normalizada = " ".join(sql.split())
        self.sentencias.append((sql_normalizada, tuple(params)))
        if sql_normalizada.startswith("SELECT id, origen_factura"):
            return _Cursor(self.rows)
        if sql_normalizada.startswith("SELECT id, numero_asiento"):
            return _Cursor(self.rows)
        return _Cursor(rowcount=1)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _gestor_con_conexion(conexion):
    gestor = object.__new__(GestorBase)
    gestor.conn = conexion
    return gestor


def test_generar_suenlace_contabiliza_sin_modificar_estado_face():
    conexion = _Conexion()
    gestor = _gestor_con_conexion(conexion)

    gestor.marcar_facturas_emitidas_generadas(
        "E00001", ["fac-1"], "2026-08-18", 2026,
    )

    sql = " ".join(sentencia for sentencia, _params in conexion.sentencias)
    assert "estado_contable='contabilizada'" in sql
    assert "facturae_" not in sql
    assert conexion.commits == 1


def test_devolver_emitidas_respeta_origen_y_bloquea_las_con_asiento():
    conexion = _Conexion([
        {
            "id": "fac-1", "origen_factura": "facturacion",
            "ocr_documento_id": None, "numero_asiento": "",
        },
        {
            "id": "ocr-1", "origen_factura": "ocr",
            "ocr_documento_id": "doc-1", "numero_asiento": "",
        },
        {
            "id": "fac-2", "origen_factura": "facturacion",
            "ocr_documento_id": None, "numero_asiento": "08/00042",
        },
    ])
    gestor = _gestor_con_conexion(conexion)

    resultado = gestor.devolver_facturas_emitidas_desde_contabilidad(
        "E00001", 2026, ["fac-1", "ocr-1", "fac-2"], "Importes incorrectos",
    )

    assert resultado == {
        "facturacion": 1, "ocr": 1, "bloqueadas": ["fac-2"],
    }
    sql = "\n".join(sentencia for sentencia, _params in conexion.sentencias)
    assert "UPDATE documentos_ocr SET estado='error'" in sql
    assert "UPDATE facturas_emitidas_ocr SET estado_validacion='pendiente'" in sql
    assert conexion.commits == 1


def test_devolver_recibida_a_ocr_reabre_revision_y_anula_suenlace():
    conexion = _Conexion([
        {"id": "doc-1", "numero_asiento": ""},
        {"id": "doc-2", "numero_asiento": "08/00043"},
    ])
    gestor = _gestor_con_conexion(conexion)

    resultado = gestor.devolver_facturas_recibidas_a_ocr(
        "E00001", ["doc-1", "doc-2"], "Falta la cuenta de gasto",
    )

    assert resultado == {"ocr": 1, "bloqueadas": ["doc-2"]}
    sql = "\n".join(sentencia for sentencia, _params in conexion.sentencias)
    assert "estado_contable='devuelta_ocr'" in sql
    assert "generada=0" in sql
    assert "UPDATE documentos_ocr SET estado='error'" in sql
    assert conexion.commits == 1
