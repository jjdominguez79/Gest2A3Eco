"""
Tests de la interfaz web del despacho.

NOTA: Los tests de los templates de la PWA heredada (staff_messages.html,
staff-messaging.js) han sido eliminados junto con la propia PWA.
Flutter es el unico cliente de interfaz de mensajeria.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "backend" / "api" / "web"


def test_portal_equipo_pwa_eliminada():
    """Los templates de la PWA del despacho deben haber sido eliminados."""
    assert not (ROOT / "templates" / "staff_messages.html").exists()
    assert not (ROOT / "static" / "staff-messaging.js").exists()
    assert not (ROOT / "static" / "staff-messaging.webmanifest").exists()
    assert not (ROOT / "static" / "staff-messaging-sw.js").exists()
