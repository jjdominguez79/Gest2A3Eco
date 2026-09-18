from types import SimpleNamespace

from views.ui_mensajeria import UIMensajeria


def test_edicion_es_solo_del_autor_y_marca_siempre_visible():
    vista = SimpleNamespace(session=SimpleNamespace(user=SimpleNamespace(id=1)))
    propio = {"author_type": "staff", "author_id": "1", "body": "Actual", "edited_at": "fecha"}
    assert UIMensajeria._puede_editar_mensaje(vista, propio)
    assert not UIMensajeria._puede_editar_mensaje(vista, {**propio, "author_id": "2"})
    assert not UIMensajeria._puede_editar_mensaje(vista, {**propio, "author_type": "client"})
    assert not UIMensajeria._puede_editar_mensaje(vista, {**propio, "deleted": True})
    assert UIMensajeria._texto_mensaje(propio) == "Actual [Editado]"
    assert UIMensajeria._texto_mensaje({**propio, "deleted": True}) == "Mensaje eliminado"


def test_historial_de_escritorio_no_se_consulta_sin_permiso():
    for item in ({"id": "m1", "edited_at": "fecha"},
                 {"id": "m1", "can_view_history": True}):
        vista = SimpleNamespace(_mensaje_seleccionado=lambda: item)
        # No llega a realizar ninguna llamada remota ni abre un dialogo.
        UIMensajeria._ver_versiones_mensaje(vista)


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
