from models.gestor_sqlite import GestorSQLite
from views.ui_comunicaciones import construir_cuerpo_html, html_a_texto


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


def test_construir_cuerpo_html_incluye_firma_html_usuario_y_escapa_mensaje():
    cuerpo = construir_cuerpo_html(
        "Hola <cliente>\nGracias",
        "<strong>Gestinem</strong>",
        "Ana & Equipo",
    )

    assert "Hola &lt;cliente&gt;<br>Gracias" in cuerpo
    assert "Ana &amp; Equipo" in cuerpo
    assert "<strong>Gestinem</strong>" in cuerpo


def test_html_a_texto_muestra_cuerpo_y_firma_sin_etiquetas():
    cuerpo = construir_cuerpo_html(
        "Hola\nGracias", "<strong>Gestinem</strong>", "Juan",
    )

    texto = html_a_texto(cuerpo)

    assert "Hola\nGracias" in texto
    assert "Juan" in texto
    assert "Gestinem" in texto
    assert "<br>" not in texto
