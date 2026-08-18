import json
from types import SimpleNamespace

from backend.api import messaging_firebase


def _settings(*, path="", raw=""):
    return SimpleNamespace(
        messaging_firebase_credentials=path,
        messaging_firebase_credentials_json=raw,
    )


def test_firebase_admite_cuenta_servicio_desde_variable(monkeypatch):
    raw = json.dumps({
        "type": "service_account",
        "project_id": "gest2a3eco",
        "private_key": "clave-privada-de-prueba",
        "client_email": "firebase@example.test",
    })
    monkeypatch.setattr(
        messaging_firebase, "get_settings", lambda: _settings(raw=raw),
    )

    assert messaging_firebase.configured() is True
    assert messaging_firebase._credential_source()["project_id"] == "gest2a3eco"


def test_firebase_rechaza_json_incompleto(monkeypatch):
    monkeypatch.setattr(
        messaging_firebase,
        "get_settings",
        lambda: _settings(raw='{"project_id":"gest2a3eco"}'),
    )

    assert messaging_firebase.configured() is False


def test_firebase_prioriza_fichero_privado(tmp_path, monkeypatch):
    credentials = tmp_path / "firebase.json"
    credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        messaging_firebase,
        "get_settings",
        lambda: _settings(path=str(credentials), raw="no-es-json"),
    )

    assert messaging_firebase._credential_source() == str(credentials)
