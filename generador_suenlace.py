from utilidades import SEP, fmt_fecha, fmt_importe_pos, pad_subcuenta

def linea_I(fecha, subcta_banco, importe, concepto, ndig):
    dh = "D" if float(importe) < 0 else "H"
    return SEP.join(["I", fmt_fecha(fecha), pad_subcuenta(subcta_banco, ndig), dh, fmt_importe_pos(importe), (concepto or "").strip()])

def linea_U(fecha, subcta_contra, importe, concepto, ndig):
    dh = "H" if float(importe) < 0 else "D"
    return SEP.join(["U", fmt_fecha(fecha), pad_subcuenta(subcta_contra, ndig), dh, fmt_importe_pos(importe), (concepto or "").strip()])

def apuntes_extracto(fecha, concepto, importe, subcta_banco, subcta_contra, ndigitos):
    return [linea_I(fecha, subcta_banco, importe, concepto, ndigitos),
            linea_U(fecha, subcta_contra, importe, concepto, ndigitos)]
