from pathlib import Path

from services.graph_mail_service import GraphMailService


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/messages"):
            return Response(201, {"id": "immutable-1", "internetMessageId": "<x@gestinem.es>"})
        return Response(202)


def test_shared_mailbox_creates_then_sends(monkeypatch):
    session = Session()
    service = GraphMailService(
        {"tenant_id": "tenant", "client_id": "client", "shared_mailbox": "Oficina@gestinem.es"},
        session=session,
    )
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))
    result = service.send(
        sender="Oficina@gestinem.es", to=["cliente@example.com"],
        subject="Prueba", body="<p>Hola</p>",
    )
    assert result.sender == "Oficina@gestinem.es"
    assert result.message_id == "immutable-1"
    assert "/users/Oficina%40gestinem.es/messages" in session.calls[0][0]
    assert session.calls[1][0].endswith("/messages/immutable-1/send")


def test_missing_attachment_is_rejected(monkeypatch, tmp_path: Path):
    service = GraphMailService({"tenant_id": "t", "client_id": "c"}, session=Session())
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))
    missing = tmp_path / "no-existe.pdf"
    try:
        service.send(sender="me", to=["a@b.es"], subject="x", body="x", attachments=[str(missing)])
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Debia rechazar el adjunto inexistente")
