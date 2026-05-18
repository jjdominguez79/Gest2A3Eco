from procesos.facturas_recibidas import generar_asiento_recibida


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
