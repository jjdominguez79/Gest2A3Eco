"""
Tests de version y etiqueta de pantalla de acceso - v1.8.0.

Cubre:
1. APP_VERSION == "1.8.0".
2. APP_RELEASE_DATE existe en app_version.
3. APP_RELEASE_DATE tiene formato ISO valido (YYYY-MM-DD).
4. get_version_label() contiene la version y la fecha formateada en espanol.
5. views/ui_auth.py no contiene "1.8.0" hardcodeado directamente.
6. views/ui_auth.py usa get_version_label en lugar de APP_VERSION para la etiqueta de pie.
"""
from __future__ import annotations

import re
from pathlib import Path


# ===========================================================================
# 1. APP_VERSION
# ===========================================================================

def test_app_version_es_1_8_0():
    from app_version import APP_VERSION
    assert APP_VERSION == "1.8.0"


# ===========================================================================
# 2. APP_RELEASE_DATE existe
# ===========================================================================

def test_app_release_date_existe():
    import app_version
    assert hasattr(app_version, "APP_RELEASE_DATE"), (
        "app_version.py debe definir APP_RELEASE_DATE"
    )
    assert app_version.APP_RELEASE_DATE, "APP_RELEASE_DATE no debe estar vacio"


# ===========================================================================
# 3. APP_RELEASE_DATE tiene formato ISO YYYY-MM-DD valido
# ===========================================================================

def test_app_release_date_formato_iso():
    from app_version import APP_RELEASE_DATE
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", APP_RELEASE_DATE), (
        f"APP_RELEASE_DATE debe ser YYYY-MM-DD, obtenido: {APP_RELEASE_DATE!r}"
    )
    y, m, d = APP_RELEASE_DATE.split("-")
    assert 2020 <= int(y) <= 2099
    assert 1 <= int(m) <= 12
    assert 1 <= int(d) <= 31


def test_app_release_date_es_1_8_0():
    from app_version import APP_RELEASE_DATE
    assert APP_RELEASE_DATE == "2026-08-18", (
        f"La fecha de publicacion de v1.8.0 debe ser 2026-08-18, obtenido {APP_RELEASE_DATE!r}"
    )


# ===========================================================================
# 4. get_version_label() contiene version y fecha en espanol
# ===========================================================================

def test_get_version_label_contiene_version():
    from app_version import APP_VERSION, get_version_label
    label = get_version_label()
    assert APP_VERSION in label, f"La etiqueta no contiene la version: {label!r}"


def test_get_version_label_contiene_fecha_es():
    from app_version import APP_RELEASE_DATE, get_version_label
    y, m, d = APP_RELEASE_DATE.split("-")
    fecha_es = f"{d}/{m}/{y}"
    label = get_version_label()
    assert fecha_es in label, (
        f"La etiqueta debe contener la fecha en formato ES ({fecha_es!r}): {label!r}"
    )


def test_get_version_label_formato_completo():
    from app_version import get_version_label
    label = get_version_label()
    # Debe incluir "Gest2A3Eco", la version precedida de "v" y "Publicada"
    assert "Gest2A3Eco" in label
    assert "v1.8.0" in label
    assert "Publicada" in label


# ===========================================================================
# 5. ui_auth.py no contiene la version hardcodeada
# ===========================================================================

def test_ui_auth_no_tiene_version_hardcodeada():
    ui_auth_path = Path(__file__).parent.parent / "views" / "ui_auth.py"
    contenido = ui_auth_path.read_text(encoding="utf-8")
    assert "1.8.0" not in contenido, (
        "views/ui_auth.py no debe contener la version '1.8.0' hardcodeada"
    )


# ===========================================================================
# 6. ui_auth.py usa get_version_label y no APP_VERSION para la etiqueta de pie
# ===========================================================================

def test_ui_auth_importa_get_version_label():
    ui_auth_path = Path(__file__).parent.parent / "views" / "ui_auth.py"
    contenido = ui_auth_path.read_text(encoding="utf-8")
    assert "get_version_label" in contenido, (
        "views/ui_auth.py debe importar y usar get_version_label"
    )


def test_ui_auth_no_usa_app_version_directamente_en_etiqueta():
    """APP_VERSION no debe aparecer en el texto del label de pie de pagina."""
    ui_auth_path = Path(__file__).parent.parent / "views" / "ui_auth.py"
    contenido = ui_auth_path.read_text(encoding="utf-8")
    # El import de APP_VERSION fue reemplazado por get_version_label
    assert "from app_version import APP_VERSION" not in contenido, (
        "views/ui_auth.py no debe importar APP_VERSION directamente; "
        "debe usar get_version_label()"
    )
