import asyncio
from io import BytesIO

from starlette.datastructures import UploadFile

from backend.api import mail_api


def test_endpoint_prepara_destinatarios_y_adjunto_para_backend(monkeypatch):
    captured = {}
    monkeypatch.setattr(mail_api, "configured", lambda: True)
    monkeypatch.setattr(mail_api, "default_sender", lambda: "oficina@gestinem.es")

    def send_mail(to, subject, html, **kwargs):
        captured.update(to=to, subject=subject, html=html, **kwargs)
        return True

    monkeypatch.setattr(mail_api, "send_mail", send_mail)
    result = asyncio.run(mail_api.send_backend_mail(
        to='["cliente@example.test"]', cc='["copia@example.test"]',
        bcc="[]", subject="Factura 1", html="<p>Adjunta</p>",
        files=[UploadFile(BytesIO(b"%PDF"), filename="factura.pdf")],
        inline_files=[],
    ))

    assert result == {"sent": True, "sender": "oficina@gestinem.es"}
    assert captured["to"] == ["cliente@example.test"]
    assert captured["cc"] == ["copia@example.test"]
    assert captured["attachments"][0]["content"] == b"%PDF"
