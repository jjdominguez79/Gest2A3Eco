from facturas_common import Linea, d2

def generar_asiento_recibida(row, conf) -> list[Linea]:
    fecha = row["Fecha"]
    desc = str(row.get("Descripcion",""))
    base = d2(row.get("Base", 0))
    cuota_iva = d2(row.get("CuotaIVA", 0))
    ret = d2(row.get("CuotaRetencion", 0))
    total = d2(row.get("Total", base + cuota_iva - ret))
    nd = conf.get('digitos_plan',8)
    c_prov = (row.get('_cuenta_tercero_override') or (conf.get('cuenta_proveedor_por_defecto') if row.get('_usar_cuenta_generica') else conf.get('cuenta_proveedor_prefijo','400') + (row.get('NIF') or '0000'))).ljust(nd, '0')[:nd]
    c_gasto = (row.get('_cuenta_py_gv_override') or conf.get('cuenta_gasto_por_defecto','62900000'))
    c_iva = (row.get('_cuenta_iva_override') or conf.get('cuenta_iva_soportado_defecto','47200000'))
    c_ret = conf.get("cuenta_retenciones_irpf","47510000")
    lineas = []
    if base != d2(0): lineas.append(Linea(fecha, c_gasto, "D", base, desc))
    if cuota_iva != d2(0): lineas.append(Linea(fecha, c_iva, "D", cuota_iva, desc))
    lineas.append(Linea(fecha, c_prov, "H", total - ret, desc))
    if ret != d2(0) and conf.get("soporta_retencion", True): lineas.append(Linea(fecha, c_ret, "H", ret, desc))
    return lineas
