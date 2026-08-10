from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from backend.dgt_api import messaging_push


class FakeWebPushException(Exception):
    pass


def _install_fake_pywebpush(monkeypatch, webpush):
    module = ModuleType("pywebpush")
    module.WebPushException = FakeWebPushException
    module.webpush = webpush
    monkeypatch.setitem(sys.modules, "pywebpush", module)
    monkeypatch.setattr(
        messaging_push,
        "get_settings",
        lambda: SimpleNamespace(
            messaging_vapid_public_key="public",
            messaging_vapid_private_key="private",
            messaging_vapid_subject="mailto:oficina@gestinem.es",
        ),
    )


def test_send_push_adds_required_wns_headers(monkeypatch):
    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)

    _install_fake_pywebpush(monkeypatch, fake_webpush)

    delivered = messaging_push.send_push(
        {
            "endpoint": "https://db5p.notify.windows.com/w/?token=test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        {"title": "Prueba"},
    )

    assert delivered is True
    assert captured["headers"] == {
        "X-WNS-Type": "wns/raw",
        "Content-Type": "application/octet-stream",
    }


def test_send_push_does_not_add_wns_headers_to_other_services(monkeypatch):
    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)

    _install_fake_pywebpush(monkeypatch, fake_webpush)

    delivered = messaging_push.send_push(
        {
            "endpoint": "https://fcm.googleapis.com/wp/test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        {"title": "Prueba"},
    )

    assert delivered is True
    assert captured["headers"] == {}


def test_send_push_logs_and_returns_false_for_unexpected_errors(monkeypatch):
    def fake_webpush(**_kwargs):
        raise ValueError("invalid key")

    _install_fake_pywebpush(monkeypatch, fake_webpush)

    delivered = messaging_push.send_push(
        {
            "endpoint": "https://fcm.googleapis.com/wp/test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        {"title": "Prueba"},
    )

    assert delivered is False
