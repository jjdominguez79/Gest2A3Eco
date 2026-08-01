from __future__ import annotations

import json

from sync_worker.repository import ComunicacionesRepository


def test_normaliza_mensaje_graph():
    raw = {
        "id": "immutable-1",
        "conversationId": "conversation-1",
        "internetMessageId": "<message@example.com>",
        "subject": "Consulta",
        "body": {"content": "<p>Hola</p>"},
        "from": {"emailAddress": {"address": "cliente@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "oficina@gestinem.es"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-08-01T10:00:00Z",
        "hasAttachments": True,
        "isRead": False,
    }

    result = ComunicacionesRepository._normalize(raw, "oficina@gestinem.es")

    assert result["graph_message_id"] == "immutable-1"
    assert result["remitente"] == "cliente@example.com"
    assert result["destinatarios"] == ["oficina@gestinem.es"]
    assert result["cuerpo_html"] == "<p>Hola</p>"
    assert result["tiene_adjuntos"] is True
    json.dumps(result)


def test_normaliza_asunto_y_listas_vacias():
    result = ComunicacionesRepository._normalize(
        {"id": "2", "body": None}, "oficina@gestinem.es"
    )

    assert result["asunto"] == "(Sin asunto)"
    assert result["destinatarios"] == []
    assert result["cc"] == []
    assert result["cuerpo_html"] == ""
