from models.gestor_sqlite import GestorSQLite


def test_registra_envio_y_lo_lista(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    comunicacion_id, mensaje_id = gestor.registrar_envio_comunicacion({
        "codigo_empresa": "E00001",
        "asunto": "Documentacion pendiente",
        "remitente": "Oficina@gestinem.es",
        "destinatarios": ["cliente@example.com"],
        "cc": [],
        "cuerpo_html": "Hola",
        "estado_envio": "aceptado_graph",
        "graph_message_id": "graph-1",
        "usuario_id": 1,
        "usuario_nombre": "Ana",
    })
    rows = gestor.listar_comunicaciones("E00001")
    assert rows[0]["id"] == comunicacion_id
    assert rows[0]["mensajes"] == 1
    mensajes = gestor.listar_mensajes_comunicacion(comunicacion_id)
    assert mensajes[0]["id"] == mensaje_id
    assert mensajes[0]["graph_message_id"] == "graph-1"
