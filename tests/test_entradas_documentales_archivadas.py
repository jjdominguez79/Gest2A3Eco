from models.gestor_base import GestorBase


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, archived_rows):
        self.archived_rows = archived_rows
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "FROM documentos_archivo d" in sql:
            return _Result(self.archived_rows)
        return _Result([])


def _gestor(archived_rows, messaging_rows):
    gestor = object.__new__(GestorBase)
    gestor.conn = _Conn(archived_rows)
    gestor.listar_adjuntos_mensajeria = lambda filtro=None: [
        row for row in messaging_rows
        if not filtro.get("estado") or row.get("estado") == filtro["estado"]
    ]
    return gestor


def test_filtro_archivadas_reune_correo_y_mensajeria_archivados():
    gestor = _gestor(
        [{
            "graph_message_id": "graph-1",
            "mailbox": "documentacion@gestinem.es",
            "codigo_empresa": "E00001",
            "remitente": "proveedor@example.com",
            "asunto": "Factura septiembre",
            "fecha": "2026-10-06T15:00:00",
            "tamano": 2048,
        }],
        [{
            "id": "adj-1", "codigo_empresa": "E00001",
            "estado": "archivado", "revisado": True,
            "created_at": "2026-10-06T14:00:00",
        }, {
            "id": "adj-2", "codigo_empresa": "E00001",
            "estado": "pendiente_clasificar", "revisado": False,
            "created_at": "2026-10-06T13:00:00",
        }],
    )

    rows = gestor.listar_entradas_documentales(
        "E00001", solo_pendientes=False, solo_archivadas=True,
    )

    assert [row["id"] for row in rows] == [
        "correo_archivado:documentacion@gestinem.es:graph-1",
        "mensajeria:adj-1",
    ]
    assert rows[0]["estado"] == "archivado"
    assert rows[0]["revisado"] is True
    assert any(
        "d.codigo_empresa=?" in sql and params == ("E00001",)
        for sql, params in gestor.conn.calls
    )


def test_filtro_pendientes_no_consulta_el_archivo_documental():
    gestor = _gestor([], [])

    gestor.listar_entradas_documentales("", solo_pendientes=True)

    assert all("FROM documentos_archivo d" not in sql for sql, _ in gestor.conn.calls)


class _CommunicationsConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _sql, _params=()):
        return _Result(self.rows)


def test_comunicaciones_excluye_correos_identificados_con_adjuntos():
    gestor = object.__new__(GestorBase)
    gestor.conn = _CommunicationsConn([
        {
            "graph_message_id": "documental",
            "sugerencia_codigo_empresa": "E00001",
            "payload_json": '{"tiene_adjuntos": true}',
        },
        {
            "graph_message_id": "sin-cliente",
            "sugerencia_codigo_empresa": "",
            "payload_json": '{"tiene_adjuntos": true}',
        },
        {
            "graph_message_id": "sin-adjuntos",
            "sugerencia_codigo_empresa": "E00002",
            "payload_json": '{"tiene_adjuntos": false}',
        },
    ])

    rows = gestor.listar_comunicaciones_sin_asignar()

    assert [row["graph_message_id"] for row in rows] == [
        "sin-cliente", "sin-adjuntos",
    ]


class _DocumentalConn:
    def execute(self, sql, _params=()):
        if "FROM empresas" in sql:
            return _Result([{
                "codigo": "E00001", "nombre": "Cliente Uno",
                "responsable": "Maria", "ejercicio": 2026,
            }])
        if "FROM comunicaciones_sin_asignar" in sql:
            return _Result([{
                "graph_message_id": "graph-1",
                "mailbox": "documentacion@gestinem.es",
                "sugerencia_codigo_empresa": "E00001",
                "sugerencia_nombre": "",
                "mailbox": "",
                "payload_json": (
                    '{"tiene_adjuntos": true, '
                    '"mailbox": "documentacion@gestinem.es"}'
                ),
                "asunto": "Factura", "fecha": "2026-10-07T10:00:00",
            }])
        return _Result([])


def test_entrada_documental_incluye_nombre_cliente_y_responsable():
    gestor = object.__new__(GestorBase)
    gestor.conn = _DocumentalConn()
    gestor.listar_adjuntos_mensajeria = lambda _filtro=None: []

    rows = gestor.listar_entradas_documentales("", solo_pendientes=True)

    assert rows[0]["empresa_nombre"] == "Cliente Uno"
    assert rows[0]["responsable"] == "Maria"
    assert rows[0]["mailbox"] == "documentacion@gestinem.es"
