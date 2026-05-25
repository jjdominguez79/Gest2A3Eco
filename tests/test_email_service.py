from pathlib import Path

from services.email_service import build_outlook_bodies, open_outlook_email
from utils import utilidades


def test_build_outlook_bodies_append_signature_and_plain_text():
    plain, html = build_outlook_bodies(
        "Adjunto factura F-1.",
        html_body="<html><body><p>Base</p></body></html>",
        signature="Saludos\nEquipo",
    )

    assert plain == "Adjunto factura F-1.\n\nSaludos\nEquipo"
    assert "Adjunto factura F-1." in html
    assert "Saludos<br>Equipo" in html


def test_open_outlook_email_valida_adjuntos_antes_de_outlook(tmp_path):
    missing = tmp_path / "no-existe.pdf"

    try:
        open_outlook_email(
            to="cliente@example.com",
            subject="Factura",
            body="Adjunto factura.",
            attachments=[str(missing)],
        )
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("Se esperaba FileNotFoundError")


def test_load_user_config_crea_archivo_en_roaming(monkeypatch, tmp_path):
    roaming = tmp_path / "Roaming"
    monkeypatch.setenv("APPDATA", str(roaming))

    cfg = utilidades.load_user_config()
    cfg_path = roaming / "Gest2A3Eco" / "config.json"

    assert cfg_path.exists()
    assert cfg["email_mode"] == "outlook"
    assert cfg["open_outlook_before_send"] is True
