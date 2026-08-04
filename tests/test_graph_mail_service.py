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


def test_token_uses_cached_account_username_when_claim_is_absent(monkeypatch):
    class Cache:
        has_state_changed = False

    class App:
        def get_accounts(self):
            return [{"username": "usuario@gestinem.es"}]

        def acquire_token_silent(self, _scopes, account):
            assert account["username"] == "usuario@gestinem.es"
            return {"access_token": "token", "id_token_claims": {}}

    service = GraphMailService({"tenant_id": "t", "client_id": "c"}, session=Session())
    service._cache = Cache()
    monkeypatch.setattr(
        "services.graph_mail_service.msal.PublicClientApplication",
        lambda *_args, **_kwargs: App(),
    )

    assert service._token() == ("token", "usuario@gestinem.es")


def test_send_includes_blind_copy_recipients(monkeypatch):
    session = Session()
    service = GraphMailService({"tenant_id": "t", "client_id": "c"}, session=session)
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))

    service.send(
        sender="me", to=["cliente@example.com"], cc=["copia@example.com"],
        bcc=["oculta@example.com"], subject="Factura", body="<p>Adjunto</p>",
    )

    payload = json.loads(session.calls[0][1]["data"])
    assert payload["message"]["bccRecipients"] == [
        {"emailAddress": {"address": "oculta@example.com"}}
    ]


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


def test_lists_and_downloads_file_attachments(monkeypatch):
    class AttachmentSession(Session):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url.endswith("/attachments") or "/attachments?$select=" in url:
                return Response(200, {"value": [
                    {"id": "file-1", "name": "factura.pdf", "@odata.type": "#microsoft.graph.fileAttachment"},
                    {"id": "inline", "name": "logo.png", "isInline": True, "@odata.type": "#microsoft.graph.fileAttachment"},
                ]})
            return Response(200, {"id": "file-1", "name": "factura.pdf", "contentBytes": "eA==", "@odata.type": "#microsoft.graph.fileAttachment"})

    session = AttachmentSession()
    service = GraphMailService({"tenant_id": "t", "client_id": "c"}, session=session)
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))
    attachments = service.list_attachments(mailbox="me", message_id="message-1")
    item = service.download_attachment(mailbox="me", message_id="message-1", attachment_id="file-1")

    assert [x["name"] for x in attachments] == ["factura.pdf"]
    assert item["contentBytes"] == "eA=="


def test_reply_creates_threaded_draft_attaches_and_sends(monkeypatch, tmp_path: Path):
    class ReplySession(Session):
        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url.endswith("/createReply"):
                return Response(201, {"id": "draft-1"})
            if url.endswith("/attachments"):
                return Response(201)
            return Response(202)

        def patch(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response(200)

    attachment = tmp_path / "respuesta.pdf"
    attachment.write_bytes(b"pdf")
    session = ReplySession()
    service = GraphMailService({"tenant_id": "t", "client_id": "c"}, session=session)
    monkeypatch.setattr(service, "_token", lambda: ("token", "yo@gestinem.es"))

    result = service.reply(
        mailbox="Oficina@gestinem.es", message_id="original-1",
        body="<p>Respuesta</p>", attachments=[str(attachment)],
    )

    urls = [item[0] for item in session.calls]
    assert any(url.endswith("/messages/original-1/createReply") for url in urls)
    assert any(url.endswith("/messages/draft-1/attachments") for url in urls)
    assert urls[-1].endswith("/messages/draft-1/send")
    assert result.message_id == "draft-1"
