from datetime import date
from types import SimpleNamespace

from controllers.factura_dialog_controller import FacturaDialogController


def _controller(view):
    controller = FacturaDialogController.__new__(FacturaDialogController)
    controller._view = view
    return controller


def test_datos_habituales_no_muestran_confirmacion():
    view = SimpleNamespace(
        get_tipo_operacion=lambda: "01",
        get_moneda=lambda: ("EUR", "€"),
        confirmar_campos_no_habituales=lambda _items: (_ for _ in ()).throw(
            AssertionError("No debe pedir confirmacion para 01/EUR"),
        ),
    )

    assert _controller(view)._confirmar_datos_no_habituales() is True


def test_tipo_y_moneda_no_habituales_se_confirman_en_un_solo_aviso():
    recibidas = []
    view = SimpleNamespace(
        get_tipo_operacion=lambda: "02",
        get_tipo_operacion_label=lambda: "Entregas exentas",
        get_moneda=lambda: ("USD", "$"),
        confirmar_campos_no_habituales=lambda items: recibidas.append(items) or True,
    )

    assert _controller(view)._confirmar_datos_no_habituales() is True
    assert recibidas == [[
        "Tipo de operacion: 02 - Entregas exentas",
        "Moneda: USD",
    ]]


def test_corregir_impide_guardar_factura_definitiva():
    guardadas = []
    view = SimpleNamespace(
        get_retencion_aplica=lambda: False,
        get_lineas=lambda: [{"base": 100.0}],
        get_numero_factura=lambda: "000001",
        get_fecha_exp=lambda: "12/10/2026",
        parse_date=lambda _value: date(2026, 10, 12),
        get_subcuenta=lambda: "",
        set_result_and_close=lambda result: guardadas.append(result),
        show_error=lambda *_args: None,
    )
    controller = _controller(view)
    controller._ejercicio = 2026
    controller._ndig = 8
    controller._allow_fecha_fuera_ejercicio = False
    controller._confirmar_datos_no_habituales = lambda: False

    controller.ok()

    assert guardadas == []


def test_corregir_impide_guardar_borrador():
    guardadas = []
    view = SimpleNamespace(
        get_retencion_aplica=lambda: False,
        get_lineas=lambda: [{"base": 100.0}],
        set_result_and_close=lambda result: guardadas.append(result),
        show_error=lambda *_args: None,
    )
    controller = _controller(view)
    controller._confirmar_datos_no_habituales = lambda: False

    controller.ok_borrador()

    assert guardadas == []
