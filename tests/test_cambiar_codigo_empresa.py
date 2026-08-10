from models.gestor_base import GestorBase


class _Resultado:
    def __init__(self, filas=None):
        self._filas = filas or []

    def fetchall(self):
        return self._filas


class _Conexion:
    def __init__(self):
        self.sentencias = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=()):
        self.sentencias.append((" ".join(sql.split()), params))
        if "information_schema.columns" in sql:
            columna = params[0]
            tablas = {
                "codigo_empresa": [{"table_name": "facturas_emitidas"}],
                "empresa_codigo": [{"table_name": "usuarios_empresas"}],
                "empresa_id": [{"table_name": "documentos_ocr"}],
            }
            return _Resultado(tablas.get(columna, []))
        return _Resultado()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _gestor(empresas):
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = _Conexion()
    gestor.get_empresa = lambda codigo, ejercicio=None: empresas.get(codigo)
    return gestor


def test_cambiar_codigo_empresa_traslada_referencias_y_empresa():
    gestor = _gestor({"E00304": {"codigo": "E00304"}})

    assert gestor.cambiar_codigo_empresa("E00304", "E01071") is True

    sql = [sentencia for sentencia, _params in gestor.conn.sentencias]
    assert "UPDATE facturas_emitidas SET codigo_empresa=? WHERE codigo_empresa=?" in sql
    assert "UPDATE usuarios_empresas SET empresa_codigo=? WHERE empresa_codigo=?" in sql
    assert "UPDATE documentos_ocr SET empresa_id=? WHERE empresa_id=?" in sql
    assert "UPDATE empresas SET codigo=? WHERE codigo=?" in sql
    assert gestor.conn.commits == 1


def test_cambiar_codigo_empresa_rechaza_un_codigo_existente():
    gestor = _gestor({
        "E00304": {"codigo": "E00304"},
        "E01071": {"codigo": "E01071"},
    })

    try:
        gestor.cambiar_codigo_empresa("E00304", "E01071")
    except ValueError as exc:
        assert "Ya existe una empresa" in str(exc)
    else:
        raise AssertionError("Debia rechazar el codigo duplicado")

    assert gestor.conn.commits == 0
