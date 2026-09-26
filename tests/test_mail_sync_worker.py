from __future__ import annotations

import json

import pytest

from sync_worker.config import _mail_sources
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


def test_normaliza_etiqueta_funcional_del_buzon():
    result = ComunicacionesRepository._normalize(
        {"id": "3"}, "jjdominguez@gestinem.es", label="Documentacion",
    )

    assert result["mailbox"] == "jjdominguez@gestinem.es"
    assert result["mailbox_label"] == "Documentacion"


def test_configura_varios_origenes_y_filtro_por_alias(monkeypatch):
    monkeypatch.setenv(
        "GRAPH_MAIL_SOURCES",
        json.dumps([
            {"mailbox": "oficina@gestinem.es", "label": "Oficina"},
            {
                "mailbox": "jjdominguez@gestinem.es",
                "recipient_filter": "documentacion@gestinem.es",
                "label": "Documentacion",
            },
        ]),
    )

    sources = _mail_sources()

    assert [item.mailbox for item in sources] == [
        "oficina@gestinem.es", "jjdominguez@gestinem.es",
    ]
    assert sources[1].recipient_filter == "documentacion@gestinem.es"


def test_rechaza_buzones_repetidos(monkeypatch):
    monkeypatch.setenv(
        "GRAPH_MAIL_SOURCES",
        '[{"mailbox":"oficina@gestinem.es"},{"mailbox":"OFICINA@gestinem.es"}]',
    )

    with pytest.raises(ValueError, match="repetido"):
        _mail_sources()
