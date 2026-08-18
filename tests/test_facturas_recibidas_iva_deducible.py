from procesos.facturas_recibidas import generar_asiento_recibida, generar_recibidas_suenlace


def _base_row(**overrides):
    row = {
        "Fecha Asiento": "2026-05-15",
        "Descripcion Factura": "Factura proveedor",
        "Base": 100.0,
        "Cuota IVA": 21.0,
        "Cuota Recargo Equivalencia": 0.0,
        "Cuota Retencion IRPF": 0.0,
        "Total": 121.0,
        "_cuenta_tercero_override": "40000001",
        "_cuenta_py_gv_override": "62900000",
        "_cuenta_iva_override": "47200000",
        "_proveedor_porcentaje_deduccion_iva": 100.0,
    }
    row.update(overrides)
    return row


def _base_conf():
    return {
        "digitos_plan": 8,
        "cuenta_gasto_por_defecto": "62900000",
        "cuenta_iva_soportado_defecto": "47200000",
        "cuenta_proveedor_prefijo": "400",
        "soporta_retencion": True,
    }


def test_iva_totalmente_deducible_va_a_472():
    lineas = generar_asiento_recibida(_base_row(), _base_conf())
    gasto = next(l for l in lineas if l.subcuenta == "62900000" and l.dh == "D")
    iva = next(l for l in lineas if l.subcuenta == "47200000" and l.dh == "D")
    assert float(gasto.importe) == 100.0
    assert float(iva.importe) == 21.0


def test_iva_no_deducible_se_integra_en_gasto():
    lineas = generar_asiento_recibida(
        _base_row(_proveedor_porcentaje_deduccion_iva=0.0),
        _base_conf(),
    )
    gasto = next(l for l in lineas if l.subcuenta == "62900000" and l.dh == "D")
    assert float(gasto.importe) == 121.0
    assert not any(l.subcuenta == "47200000" and l.dh == "D" for l in lineas)


def test_iva_parcial_divide_entre_472_y_gasto():
    lineas = generar_asiento_recibida(
        _base_row(_proveedor_porcentaje_deduccion_iva=50.0),
        _base_conf(),
    )
    gasto = next(l for l in lineas if l.subcuenta == "62900000" and l.dh == "D")
    iva = next(l for l in lineas if l.subcuenta == "47200000" and l.dh == "D")
    assert float(gasto.importe) == 110.5
    assert float(iva.importe) == 10.5


def test_suplidos_generan_linea_separada_sin_aumentar_base_iva():
    lineas = generar_asiento_recibida(
        _base_row(Suplidos=15.0, **{"Cuenta Suplidos": "55509999", "Total": 136.0}),
        _base_conf(),
    )
    suplido = next(l for l in lineas if l.subcuenta == "55509999")
    gasto = next(l for l in lineas if l.subcuenta == "62900000")
    assert float(suplido.importe) == 15.0
    assert float(gasto.importe) == 100.0


def test_suenlace_incluye_detalle_separado_para_suplidos(monkeypatch):
    detalles = []
    monkeypatch.setattr(
        "procesos.facturas_recibidas.render_a3_tipo12_cabecera",
        lambda **kwargs: "CABECERA",
    )
    monkeypatch.setattr(
        "procesos.facturas_recibidas.render_a3_tipo9_detalle",
        lambda **kwargs: detalles.append(kwargs) or "DETALLE",
    )
    registros = generar_recibidas_suenlace(
        [_base_row(
            Suplidos=15.0,
            **{
                "Cuenta Suplidos": "55509999", "Numero Factura": "F-1",
                "NIF Cliente Proveedor": "B12345678", "Nombre Cliente Proveedor": "Proveedor",
            },
        )],
        {**_base_conf(), "subtipo_recibidas": "01"},
        "E00001",
        8,
    )
    assert registros == ["CABECERA", "DETALLE", "DETALLE"]
    assert detalles[-1]["cuenta_base_iva"] == "55509999"
    assert detalles[-1]["pct_iva"] == 0.0
    assert detalles[-1]["base"] == 15.0
