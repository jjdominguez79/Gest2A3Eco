from types import SimpleNamespace

from views.ui_mensajeria import UIMensajeria


def test_administrador_no_puede_ocultar_sus_indicadores_de_lectura():
    configuracion = {}
    vista = SimpleNamespace(
        session=SimpleNamespace(is_admin=lambda: True),
        mostrar_estados=SimpleNamespace(get=lambda: False),
        msg_tree=SimpleNamespace(configure=lambda **kwargs: configuracion.update(kwargs)),
    )
    UIMensajeria._actualizar_columnas_estados(vista)
    assert "estado_envio" in configuracion["displaycolumns"]
    # Un callback antiguo no puede guardar la preferencia anterior del admin.
    UIMensajeria._guardar_estados(vista)


def test_empleado_conserva_preferencia_visual_personal():
    configuracion = {}
    vista = SimpleNamespace(
        session=SimpleNamespace(is_admin=lambda: False),
        mostrar_estados=SimpleNamespace(get=lambda: False),
        msg_tree=SimpleNamespace(configure=lambda **kwargs: configuracion.update(kwargs)),
    )
    UIMensajeria._actualizar_columnas_estados(vista)
    assert "estado_envio" not in configuracion["displaycolumns"]
