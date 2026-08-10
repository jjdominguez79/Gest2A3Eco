from __future__ import annotations

import base64
import sys
from types import ModuleType, SimpleNamespace

from backend.dgt_api import messaging_push


class FakeWebPushException(Exception):
    pass


def _install_fake_pywebpush(monkeypatch, webpush, private_key="private"):
    module = ModuleType("pywebpush")
    module.WebPushException = FakeWebPushException
    module.webpush = webpush
    monkeypatch.setitem(sys.modules, "pywebpush", module)
    monkeypatch.setattr(
        messaging_push,
        "get_settings",
        lambda: SimpleNamespace(
            messaging_vapid_public_key="public",
            messaging_vapid_private_key=private_key,
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


def test_send_push_converts_raw_vapid_private_key_to_der(monkeypatch):
    from cryptography.hazmat.primitives.serialization import load_der_private_key

    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)

    raw_key = bytes(range(1, 33))
    encoded_raw_key = base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode("ascii")
    _install_fake_pywebpush(monkeypatch, fake_webpush, private_key=encoded_raw_key)

    delivered = messaging_push.send_push(
        {
            "endpoint": "https://db5p.notify.windows.com/w/?token=test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        {"title": "Prueba"},
    )

    encoded_der_key = captured["vapid_private_key"]
    padding = "=" * (-len(encoded_der_key) % 4)
    private_key = load_der_private_key(
        base64.urlsafe_b64decode(encoded_der_key + padding),
        password=None,
    )
    assert delivered is True
    assert private_key.private_numbers().private_value == int.from_bytes(raw_key, "big")


def test_send_push_converts_pem_vapid_private_key_to_der(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)

    scalar = int.from_bytes(bytes(range(1, 33)), "big")
    private_key = ec.derive_private_key(scalar, ec.SECP256R1())
    pem_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    _install_fake_pywebpush(monkeypatch, fake_webpush, private_key=pem_key)

    delivered = messaging_push.send_push(
        {
            "endpoint": "https://db5p.notify.windows.com/w/?token=test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        {"title": "Prueba"},
    )

    encoded_der_key = captured["vapid_private_key"]
    padding = "=" * (-len(encoded_der_key) % 4)
    normalized_key = serialization.load_der_private_key(
        base64.urlsafe_b64decode(encoded_der_key + padding),
        password=None,
    )
    assert delivered is True
    assert normalized_key.private_numbers().private_value == scalar


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
