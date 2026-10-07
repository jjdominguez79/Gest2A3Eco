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
