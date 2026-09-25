import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
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
        sender_mode="office",
        files=[UploadFile(BytesIO(b"%PDF"), filename="factura.pdf")],
        inline_files=[],
    ))

    assert result == {"sent": True, "sender": "oficina@gestinem.es"}
    assert captured["to"] == ["cliente@example.test"]
    assert captured["cc"] == ["copia@example.test"]
    assert captured["attachments"][0]["content"] == b"%PDF"


def test_endpoint_usa_remitente_personal_configurado_en_backend(monkeypatch):
    captured = {}
    monkeypatch.setattr(mail_api, "configured", lambda: True)
    monkeypatch.setattr(mail_api, "personal_sender_configured", lambda: True)
    monkeypatch.setattr(
        mail_api, "personal_sender", lambda: "jjdominguez@gestinem.es",
    )

    def send_mail(to, subject, html, **kwargs):
        captured.update(to=to, subject=subject, html=html, **kwargs)
        return True

    monkeypatch.setattr(mail_api, "send_mail", send_mail)
    result = asyncio.run(mail_api.send_backend_mail(
        to='["cliente@example.test"]', cc="[]", bcc="[]",
        subject="Factura 2", html="<p>Adjunta</p>", sender_mode="personal",
        files=[], inline_files=[],
    ))

    assert result == {"sent": True, "sender": "jjdominguez@gestinem.es"}
    assert captured["sender"] == "jjdominguez@gestinem.es"


def test_endpoint_rechaza_remitente_personal_no_configurado(monkeypatch):
    monkeypatch.setattr(mail_api, "configured", lambda: True)
    monkeypatch.setattr(mail_api, "personal_sender_configured", lambda: False)

    with pytest.raises(HTTPException) as error:
        asyncio.run(mail_api.send_backend_mail(
            to='["cliente@example.test"]', cc="[]", bcc="[]",
            subject="Factura 3", html="<p>Adjunta</p>", sender_mode="personal",
            files=[], inline_files=[],
        ))

    assert error.value.status_code == 503
    assert "personal" in error.value.detail
