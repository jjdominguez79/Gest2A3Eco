from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "backend" / "api" / "web"


def test_portal_equipo_usa_navegacion_directa_simplificada():
    template = (ROOT / "templates" / "staff_messages.html").read_text(encoding="utf-8")
    assert 'id="team-shortcuts"' in template
    assert 'id="people-shortcuts"' in template
    assert 'id="thread-avatar"' in template
    assert 'id="space-clients"' not in template
    assert 'id="space-team"' not in template
    assert 'id="internal-direct-dialog"' not in template


def test_portal_equipo_crea_privado_desde_la_lista_de_personas():
    script = (ROOT / "static" / "staff-messaging.js").read_text(encoding="utf-8")
    assert "function renderNavigation()" in script
    assert "function openPerson(memberId,threadId)" in script
    assert "counterpart_avatar_url" in script
    assert "data-permission" not in script  # Los permisos se leen desde el DOM y /staff/me.
