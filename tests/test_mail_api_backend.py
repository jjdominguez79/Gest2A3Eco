from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import mail_api


class Response:
    status_code = 200

    @staticmethod
    def json():
        return {
            "value": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "id": "att-1",
                    "name": "factura.pdf",
                    "isInline": False,
                },
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "id": "inline-1",
                    "name": "firma.png",
                    "isInline": True,
                },
            ],
        }


def test_endpoint_adjuntos_usa_graph_del_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_api, "default_sender", lambda: "oficina@gestinem.es")
    monkeypatch.setattr(mail_api, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(mail_api, "graph_headers", lambda _cfg: {"Authorization": "Bearer backend"})
    monkeypatch.setattr(
        mail_api.requests, "get",
        lambda url, **kwargs: calls.append((url, kwargs)) or Response(),
    )

    result = mail_api.list_backend_attachments(
        mailbox="Oficina@gestinem.es", message_id="id/con/barra",
    )

    assert [item["id"] for item in result] == ["att-1"]
    assert "id%2Fcon%2Fbarra/attachments" in calls[0][0]
    assert calls[0][1]["headers"] == {"Authorization": "Bearer backend"}


def test_endpoint_adjuntos_rechaza_otro_buzon(monkeypatch):
    monkeypatch.setattr(mail_api, "default_sender", lambda: "oficina@gestinem.es")

    with pytest.raises(HTTPException) as exc:
        mail_api.list_backend_attachments(
            mailbox="otra-cuenta@gestinem.es", message_id="message-1",
        )

    assert exc.value.status_code == 403

