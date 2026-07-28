import json
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
        return Response(202)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(200, {"value": [], "@odata.deltaLink": "delta-final"})


def test_shared_mailbox_sends_without_mailbox_read_permission(monkeypatch):
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
    assert result.message_id == ""
    assert session.calls[0][0].endswith("/users/Oficina%40gestinem.es/sendMail")
    assert len(session.calls) == 1
    assert '"saveToSentItems": true' in session.calls[0][1]["data"]


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


def test_inline_attachment_uses_content_id(monkeypatch, tmp_path: Path):
    session = Session()
    service = GraphMailService(
        {"tenant_id": "t", "client_id": "c"}, session=session,
    )
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"logo")

    service.send(
        sender="me", to=["a@b.es"], subject="x",
        body='<img src="cid:gestinem-logo">',
        inline_attachments=[
            {"path": str(logo), "content_id": "gestinem-logo"},
        ],
    )

    payload = json.loads(session.calls[0][1]["data"])
    attachment = payload["message"]["attachments"][0]
    assert attachment["isInline"] is True
    assert attachment["contentId"] == "gestinem-logo"


def test_sync_inbox_uses_delta_and_returns_cursor(monkeypatch):
    service = GraphMailService(
        {"tenant_id": "t", "client_id": "c"}, session=Session(),
    )
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))

    result = service.sync_inbox(mailbox="Oficina@gestinem.es")

    assert result.mailbox == "Oficina@gestinem.es"
    assert result.delta_link == "delta-final"
    assert "/users/Oficina%40gestinem.es/mailFolders/inbox/messages/delta" in service.session.calls[0][0]
