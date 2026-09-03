from types import SimpleNamespace
import base64

from backend.api import messaging_mail


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _settings(**overrides):
    values = {
        "messaging_graph_tenant_id": "tenant-id",
        "messaging_graph_client_id": "client-id",
        "messaging_graph_client_secret": "secret",
        "messaging_graph_from": "oficina@gestinem.es",
        "messaging_graph_invitation_from": "jjdominguez@gestinem.es",
        "messaging_smtp_host": "",
        "messaging_smtp_port": 587,
        "messaging_smtp_user": "",
        "messaging_smtp_password": "",
        "messaging_smtp_from": "",
        "messaging_smtp_use_tls": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_send_mail_usa_graph_como_canal_prioritario(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/oauth2/v2.0/token"):
            return _Response(200, {"access_token": "access-token"})
        return _Response(202)

    monkeypatch.setattr(messaging_mail, "get_settings", _settings)
    monkeypatch.setattr(messaging_mail.requests, "post", post)

    assert messaging_mail.configured()
    assert messaging_mail.send_mail("ana@example.test", "Aviso", "<p>Hola</p>")
    assert len(calls) == 2
    assert calls[0][1]["data"]["grant_type"] == "client_credentials"
    assert calls[1][0].endswith("/users/oficina%40gestinem.es/sendMail")
    assert calls[1][1]["headers"]["Authorization"] == "Bearer access-token"
    assert calls[1][1]["json"]["message"]["toRecipients"] == [
        {"emailAddress": {"address": "ana@example.test"}}
    ]


def test_send_mail_graph_incluye_copias_y_adjuntos(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(200, {"access_token": "token"}) if url.endswith("/token") else _Response(202)

    monkeypatch.setattr(messaging_mail, "get_settings", _settings)
    monkeypatch.setattr(messaging_mail.requests, "post", post)

    assert messaging_mail.send_mail(
        ["cliente@example.test"], "Factura", "<p>Adjunta</p>",
        cc=["copia@example.test"], bcc=["oculta@example.test"],
        attachments=[{
            "name": "factura.pdf", "content_type": "application/pdf",
            "content": b"%PDF",
        }],
    )

    message = calls[1][1]["json"]["message"]
    assert message["ccRecipients"][0]["emailAddress"]["address"] == "copia@example.test"
    assert message["bccRecipients"][0]["emailAddress"]["address"] == "oculta@example.test"
    assert message["attachments"][0]["contentBytes"] == base64.b64encode(b"%PDF").decode("ascii")


def test_send_mail_graph_informa_error_sin_mostrar_secretos(monkeypatch):
    monkeypatch.setattr(messaging_mail, "get_settings", _settings)
    monkeypatch.setattr(
        messaging_mail.requests,
        "post",
        lambda *_args, **_kwargs: _Response(
            401, {
                "error": "unauthorized_client",
                "error_description": "Aplicacion no autorizada",
            },
        ),
    )

    try:
        messaging_mail.send_mail("ana@example.test", "Aviso", "<p>Hola</p>")
    except RuntimeError as exc:
        assert str(exc) == "Aplicacion no autorizada"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("Se esperaba un error de autenticacion de Graph")


def test_invitacion_usa_remitente_personal_configurado(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(200, {"access_token": "token"}) if url.endswith("/token") else _Response(202)

    monkeypatch.setattr(messaging_mail, "get_settings", _settings)
    monkeypatch.setattr(messaging_mail.requests, "post", post)
    assert messaging_mail.send_invitation("ana@example.test", "Ana", "https://example.test/invite")
    assert calls[1][0].endswith("/users/jjdominguez%40gestinem.es/sendMail")
    html = calls[1][1]["json"]["message"]["body"]["content"]
    assert 'href="https://example.test/invite"' in html
    assert "https://example.test/invite" in html
    assert "directamente desde tu navegador" in html
    attachments = calls[1][1]["json"]["message"]["attachments"]
    assert attachments[0]["name"] == "Manual_Mensajeria_Gestinem.pdf"
    assert base64.b64decode(attachments[0]["contentBytes"]).startswith(b"%PDF")


def test_invitacion_incluye_enlace_en_html_y_texto_plano(monkeypatch):
    captured = {}

    def fake_send_mail(to, subject, html, **kwargs):
        captured.update(to=to, subject=subject, html=html, **kwargs)
        return True

    monkeypatch.setattr(messaging_mail, "get_settings", _settings)
    monkeypatch.setattr(messaging_mail, "send_mail", fake_send_mail)
    url = "https://app.example.test/#/accept-invite?token=abc%2B123"

    assert messaging_mail.send_invitation("ana@example.test", "Ana", url)
    assert url in captured["html"]
    assert url in captured["text"]
    assert captured["sender"] == "jjdominguez@gestinem.es"
    assert captured["attachments"][0]["name"] == "Manual_Mensajeria_Gestinem.pdf"
