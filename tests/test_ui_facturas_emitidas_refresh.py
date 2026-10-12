from types import SimpleNamespace

from views.ui_facturas_emitidas import (
    UIFacturasEmitidas,
    _codigo_tipo_operacion,
    _texto_estado_area_cliente,
)


def test_area_cliente_sin_publicacion_solicitada_se_muestra_pendiente():
    assert _texto_estado_area_cliente({"area_cliente_estado": ""}) == "Pendiente"
    assert _texto_estado_area_cliente({}) == "Pendiente"
    assert _texto_estado_area_cliente({
        "area_cliente_estado": "error",
        "canal_envio": "email",
    }) == "Pendiente"


def test_area_cliente_conserva_los_estados_de_publicacion():
    assert _texto_estado_area_cliente({"area_cliente_estado": "publicada"}) == "Publicada"
    assert _texto_estado_area_cliente({"area_cliente_estado": "bloqueada"}) == "Bloqueada"
    assert _texto_estado_area_cliente({"area_cliente_estado": "error"}) == "Reintentando"


def test_tipo_operacion_del_listado_normaliza_codigo_y_legacy():
    assert _codigo_tipo_operacion({"tipo_operacion": "02"}) == "02"
    assert _codigo_tipo_operacion({"tipo_operacion": "2"}) == "02"
    assert _codigo_tipo_operacion({"tipo_operacion": ""}) == "01"


def test_listado_muestra_asiento_vacio_para_none_y_numero_real_si_existe():
    class Tree:
        def __init__(self):
            self.rows = []

        def insert(self, _parent, _position, **kwargs):
            self.rows.append(kwargs["values"])

    view = object.__new__(UIFacturasEmitidas)
    view.tv = Tree()
    view._marked_factura_ids = set()
    view._default_moneda_simbolo = "€"
    totales = {"base": 0, "iva": 0, "ret": 0, "total": 0}

    UIFacturasEmitidas.insert_factura_row(
        view, {"id": "fac-1", "numero_asiento": None}, totales,
    )
    UIFacturasEmitidas.insert_factura_row(
        view, {"id": "fac-2", "numero_asiento": "08/00042"}, totales,
    )

    assert view.tv.rows[0][4] == ""
    assert view.tv.rows[1][4] == "08/00042"


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


def test_acciones_bloquean_contabilizada_pero_permiten_verla():
    class Button:
        def __init__(self):
            self.state = None

        def configure(self, **kwargs):
            self.state = kwargs.get("state")

    view = object.__new__(UIFacturasEmitidas)
    view._can_write_facturas = True
    view.btn_fact_ver = Button()
    view.btn_fact_editar = Button()
    view.btn_fact_eliminar = Button()
    view.btn_fact_confirmar = Button()

    UIFacturasEmitidas.actualizar_estado_acciones_factura(view, {
        "id": "fac-1",
        "estado_contable": "contabilizada",
        "numero_asiento": "42",
    })

    assert view.btn_fact_ver.state == "normal"
    assert view.btn_fact_editar.state == "disabled"
    assert view.btn_fact_eliminar.state == "disabled"


def test_factura_generada_fuera_de_contabilidad_conserva_edicion_con_clave():
    class Button:
        def __init__(self):
            self.state = None

        def configure(self, **kwargs):
            self.state = kwargs.get("state")

    view = object.__new__(UIFacturasEmitidas)
    view._can_write_facturas = True
    view.btn_fact_ver = Button()
    view.btn_fact_editar = Button()
    view.btn_fact_eliminar = Button()
    view.btn_fact_confirmar = Button()

    UIFacturasEmitidas.actualizar_estado_acciones_factura(view, {
        "id": "fac-generada", "generada": True,
    })

    assert view.btn_fact_editar.state == "normal"
    assert view.btn_fact_eliminar.state == "disabled"


def test_totales_filtrados_se_presentan_en_filas_por_moneda():
    class Tree:
        def __init__(self):
            self.rows = []
            self.height = None

        def get_children(self):
            return tuple(range(len(self.rows)))

        def delete(self, *_items):
            self.rows.clear()

        def insert(self, _parent, _position, *, values):
            self.rows.append(values)

        def configure(self, **kwargs):
            self.height = kwargs.get("height")

    view = object.__new__(UIFacturasEmitidas)
    view._default_moneda_simbolo = "€"
    view.tv_facturas_totales = Tree()

    UIFacturasEmitidas.set_facturas_totales(view, {
        "EUR": {
            "codigo": "EUR",
            "simbolo": "€",
            "facturas": 9,
            "base": 24493.20,
            "iva": 5143.58,
            "ret": -244.94,
            "total": 29391.84,
        },
    }, 9)

    assert view.tv_facturas_totales.rows == [
        ("EUR", 9, "24.493,20 €", "5.143,58 €", "-244,94 €", "29.391,84 €"),
    ]
    assert view.tv_facturas_totales.height == 1
