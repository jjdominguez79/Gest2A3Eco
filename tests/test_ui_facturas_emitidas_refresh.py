from types import SimpleNamespace

from views.ui_facturas_emitidas import UIFacturasEmitidas


def test_fin_actualizacion_aplica_cambios_preservando_estado_y_reprograma():
    llamadas = []
    view = object.__new__(UIFacturasEmitidas)
    view._facturas_refresh_running = True
    view._facturas_refresh_manual_pending = False
    view._destroying = False
    view.controller = SimpleNamespace(
        aplicar_facturas=lambda facturas, **kwargs: llamadas.append(
            ("aplicar", facturas, kwargs),
        ),
        cerrar_lector_facturas=lambda: llamadas.append(("cerrar",)),
    )
    view._programar_actualizacion_facturas = lambda: llamadas.append(("programar",))

    UIFacturasEmitidas._finalizar_actualizacion_facturas(
        view, [{"id": "fac-2"}], None,
    )

    assert llamadas == [
        ("aplicar", [{"id": "fac-2"}], {
            "solo_si_cambia": True,
            "preservar_estado": True,
        }),
        ("programar",),
    ]
    assert view._facturas_refresh_running is False


def test_fin_actualizacion_destruida_descarta_resultado_y_cierra_lector():
    llamadas = []
    view = object.__new__(UIFacturasEmitidas)
    view._facturas_refresh_running = True
    view._destroying = True
    view.controller = SimpleNamespace(
        aplicar_facturas=lambda *_args, **_kwargs: llamadas.append(("aplicar",)),
        cerrar_lector_facturas=lambda: llamadas.append(("cerrar",)),
    )

    UIFacturasEmitidas._finalizar_actualizacion_facturas(
        view, [{"id": "obsoleta"}], None,
    )

    assert llamadas == [("cerrar",)]


def test_peticion_manual_pendiente_lanza_segunda_consulta_inmediata():
    llamadas = []
    view = object.__new__(UIFacturasEmitidas)
    view._facturas_refresh_running = True
    view._facturas_refresh_manual_pending = True
    view._destroying = False
    view.controller = SimpleNamespace(
        aplicar_facturas=lambda *_args, **_kwargs: None,
        cerrar_lector_facturas=lambda: None,
    )
    view._programar_actualizacion_facturas = lambda: llamadas.append(("programar",))
    view._iniciar_actualizacion_facturas = (
        lambda manual=False: llamadas.append(("iniciar", manual))
    )

    UIFacturasEmitidas._finalizar_actualizacion_facturas(view, [], None)

    assert llamadas == [("iniciar", True)]
    assert view._facturas_refresh_manual_pending is False


def test_restaurar_estado_conserva_seleccion_foco_scroll_y_marcadas_existentes():
    class Tree:
        def __init__(self):
            self.selected = []
            self.focused = ""
            self.scroll = None

        def get_children(self):
            return ("fac-1", "fac-2")

        def selection_set(self, items):
            self.selected = list(items)

        def focus(self, item=None):
            if item is not None:
                self.focused = item
            return self.focused

        def yview_moveto(self, position):
            self.scroll = position

    view = object.__new__(UIFacturasEmitidas)
    view.tv = Tree()
    view._marked_factura_ids = {"fac-1", "eliminada"}

    UIFacturasEmitidas.restaurar_estado_facturas(view, {
        "seleccion": ["fac-1", "eliminada"],
        "foco": "fac-2",
        "yview": 0.45,
    })

    assert view.tv.selected == ["fac-1"]
    assert view.tv.focused == "fac-2"
    assert view.tv.scroll == 0.45
    assert view._marked_factura_ids == {"fac-1"}
