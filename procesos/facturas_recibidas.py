# procesos/facturas_recibidas.py
#
# Generación de líneas lógicas (Linea) para facturas recibidas.
# Estas líneas luego se transforman en registros suenlace
# según el formato que ya tienes implementado en el proyecto.

from typing import List, Dict, Any

from collections import defaultdict
from facturas_common import Linea, render_a3_tipo12_cabecera, render_a3_tipo9_detalle
from utilidades import d2


def _ajustar_cuenta(raw: Any, ndig: int) -> str:
    """
    Normaliza una cuenta a 'ndig' dígitos:
    - deja solo dígitos
    - si excede, recorta por la IZQUIERDA (dígitos más significativos)
    - si falta, rellena con ceros a la DERECHA
    """
    s = "" if raw is None else str(raw)
    dig = "".join(ch for ch in s if ch.isdigit())
    if not dig:
        dig = "0"
    if len(dig) > ndig:
        return dig[:ndig]
    return dig.ljust(ndig, "0")


def _resolver_cuenta_proveedor(row: Dict[str, Any], conf: Dict[str, Any]) -> str:
    """
    Determina la subcuenta del proveedor con la siguiente prioridad:

    1) Override explícito en la fila: '_cuenta_tercero_override'
    2) Si '_usar_cuenta_generica' es True -> 'cuenta_proveedor_por_defecto'
    3) Columna mapeada en el Excel: 'Cuenta Cliente Proveedor'
    4) Construir a partir de:
       prefijo 'cuenta_proveedor_prefijo' + dígitos del NIF del proveedor

    En todos los casos, la cuenta resultante se normaliza al número de
    dígitos del plan ('digitos_plan') para que A3 la acepte y, si no existe,
    la cree automáticamente al importar el fichero.
    """
    ndig = int(conf.get("digitos_plan", 8))

    # 1) Override explícito en la fila
    override = row.get("_cuenta_tercero_override")
    if override:
        return _ajustar_cuenta(override, ndig)

    # 2) Cuenta genérica si así se indica en la fila
    if row.get("_usar_cuenta_generica"):
        c_gen = conf.get("cuenta_proveedor_por_defecto")
        if c_gen:
            return _ajustar_cuenta(c_gen, ndig)

    # 3) Columna mapeada de subcuenta en el Excel
    c_excel = (
        row.get("Cuenta Cliente Proveedor")
        or row.get("Cuenta Cliente/Proveedor")
        or row.get("Cuenta Proveedor")
    )
    if c_excel:
        return _ajustar_cuenta(c_excel, ndig)

    # 4) Prefijo + NIF
    pref = str(conf.get("cuenta_proveedor_prefijo", "400"))
    nif = (
        row.get("NIF Cliente Proveedor")
        or row.get("NIF")
        or ""
    )
    nif_dig = "".join(ch for ch in str(nif) if ch.isdigit()) or "0"
    base = "".join(ch for ch in pref if ch.isdigit()) + nif_dig
    return _ajustar_cuenta(base, ndig)


def generar_asiento_recibida(row: Dict[str, Any], conf: Dict[str, Any]) -> List[Linea]:
    """
    A partir de una fila 'row' (dict con los campos ya mapeados desde el Excel)
    y la configuración de la plantilla 'conf', devuelve la lista de Linea
    que compondrán el asiento de la factura recibida.
    """
    # Fecha y descripción
    fecha = (
        row.get("Fecha Asiento")
        or row.get("Fecha Expedicion")
        or row.get("Fecha Operacion")
        or row.get("Fecha")
        or ""
    )
    desc = str(
        row.get("Descripcion Factura")
        or row.get("Descripcion")
        or row.get("Concepto")
        or ""
    )

    # Importes
    base = d2(row.get("Base", 0))
    cuota_iva = d2(row.get("Cuota IVA", 0))
    cuota_re = d2(row.get("Cuota Recargo Equivalencia", 0))
    ret = d2(row.get("Cuota Retencion IRPF", 0))

    # Total = base + iva + recargo - retención (si no viene)
    total = d2(
        row.get("Total", base + cuota_iva + cuota_re - ret)
    )
    signo = -1 if total < 0 else 1

    # Configuración de cuentas
    nd = int(conf.get("digitos_plan", 8))

    c_prov = _resolver_cuenta_proveedor(row, conf)

    c_gasto = (
        row.get("_cuenta_py_gv_override")
        or conf.get("cuenta_gasto_por_defecto", "62900000")
    )
    c_gasto = _ajustar_cuenta(c_gasto, nd)

    c_iva = (
        row.get("_cuenta_iva_override")
        or conf.get("cuenta_iva_soportado_defecto", "47200000")
    )
    c_iva = _ajustar_cuenta(c_iva, nd)

    c_re = conf.get("cuenta_recargo_equivalencia")
    if c_re:
        c_re = _ajustar_cuenta(c_re, nd)

    c_ret = conf.get("cuenta_retenciones_irpf", "47510000")
    c_ret = _ajustar_cuenta(c_ret, nd)

    lineas: List[Linea] = []

    # Debe: gasto
    if base != d2(0):
        dh_base = "D" if signo > 0 else "H"
        lineas.append(Linea(fecha, c_gasto, dh_base, abs(base), desc))

    # Debe: IVA soportado
    if cuota_iva != d2(0):
        dh_iva = "D" if signo > 0 else "H"
        lineas.append(Linea(fecha, c_iva, dh_iva, abs(cuota_iva), desc))

    # Debe: recargo de equivalencia (si hay y hay cuenta configurada)
    if cuota_re != d2(0) and c_re:
        dh_re = "D" if signo > 0 else "H"
        lineas.append(Linea(fecha, c_re, dh_re, abs(cuota_re), desc))

    # Haber: proveedor (por el total menos retención)
    if total != d2(0):
        dh_prov = "H" if signo > 0 else "D"
        lineas.append(Linea(fecha, c_prov, dh_prov, abs(total - ret), desc))

    # Haber: retención IRPF (si aplica y la plantilla soporta retenciones)
    if ret != d2(0) and conf.get("soporta_retencion", True):
        dh_ret = "H" if signo > 0 else "D"
        lineas.append(Linea(fecha, c_ret, dh_ret, abs(ret), desc))

    # Ajuste por descuadre (tolerancia centesimal): forzamos que Debe == Haber
    debe = sum(ln.importe for ln in lineas if ln.dh.upper() == "D")
    haber = sum(ln.importe for ln in lineas if ln.dh.upper() == "H")
    diff = debe - haber
    if diff != d2(0):
        # Si diff > 0 falta haber; si diff < 0 falta debe
        target_dh = "H" if diff > 0 else "D"
        target_line = None
        # Preferimos ajustar la línea del proveedor
        for ln in lineas:
            if ln.subcuenta == c_prov and ln.dh.upper() == target_dh:
                target_line = ln
                break
        if target_line is None and lineas:
            target_line = lineas[-1]
        if target_line:
            target_line.importe = (target_line.importe or d2(0)) + abs(diff)

    return lineas


def generar_recibidas(
    rows: List[Dict[str, Any]],
    conf: Dict[str, Any],
    codigo_empresa: str | None = None,
    ndig_plan: int | None = None,
) -> List[Linea]:
    """
    Función de alto nivel que algunas partes de la aplicación importan:

        from procesos.facturas_recibidas import generar_recibidas

    En muchas llamadas antiguas se le pasan 4 parámetros:
      (rows, conf, codigo_empresa, ndig_plan)

    Aquí aceptamos también esos dos últimos, aunque no los necesitamos
    para construir las Linea, para mantener compatibilidad.
    """
    todas: List[Linea] = []
    for row in rows:
        lineas = generar_asiento_recibida(row, conf)
        if lineas:
            todas.extend(lineas)
    return todas


def _fv(x) -> float:
    """
    Convierte un valor a float, soportando formatos 1234,56 y 1.234,56.
    Devuelve 0.0 si no es convertible.
    """
    if x is None or x == "":
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)

    s = str(x).strip()
    if not s:
        return 0.0

    s = s.replace("\xa0", " ")

    # Caso 1: tiene punto y coma -> '.' miles, ',' decimales
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    # Caso 2: solo coma -> decimal
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return 0.0


def _key_factura(rec: Dict[str, Any]):
    """
    Agrupa l¡neas del Excel por factura.
    Preferimos 'Numero Factura Largo SII' si existe, si no, Serie+N§mero.
    """
    nfl = rec.get("Numero Factura Largo SII") or rec.get("N§mero Factura Largo SII")
    if nfl:
        return ("NFL", str(nfl).strip())

    serie = str(rec.get("Serie") or "").strip()
    num = str(
        rec.get("Numero Factura")
        or rec.get("N§mero Factura")
        or ""
    ).strip()
    return ("SERIE_NUM", f"{serie}|{num}")


def generar_recibidas_suenlace(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig: int,
) -> List[str]:
    """
    Genera registros SUENLACE (cabecera tipo 1/2 + detalle tipo 9, formato 254)
    para FACTURAS RECIBIDAS a partir de las filas ya mapeadas del Excel.
    """
    cta_gasto_def  = str(plantilla.get("cuenta_gasto_por_defecto", "62900000"))
    subtipo_def    = str(plantilla.get("subtipo_recibidas", "01"))

    grupos: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for rec in rows:
        grupos[_key_factura(rec)].append(rec)

    registros: List[str] = []

    for (_, _id), grecs in grupos.items():
        if not grecs:
            continue

        r0 = grecs[0]

        fecha = (
            r0.get("Fecha Asiento")
            or r0.get("Fecha Expedicion")
            or r0.get("Fecha Operacion")
        )
        desc = r0.get("Descripcion Factura") or r0.get("Descripcion") or ""

        num_fact = (
            r0.get("Numero Factura")
            or r0.get("N§mero Factura")
            or r0.get("Numero Factura Largo SII")
            or ""
        )

        # Subcuenta proveedor
        conf_ctas = dict(plantilla)
        conf_ctas["digitos_plan"] = ndig
        c_prov = _resolver_cuenta_proveedor(r0, conf_ctas)

        nif = str(r0.get("NIF Cliente Proveedor") or "").strip()
        nombre = str(r0.get("Nombre Cliente Proveedor") or "").strip()

        total = 0.0
        for rr in grecs:
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))
            total += base + cuota + re_c - ret_c
        signo = -1 if total < 0 else 1
        total_abs = abs(total)
        tipo_registro = "2" if signo < 0 else "1"  # 2=rectificativa (abono)

        # CABECERA tipo 1 (factura normal) con tipo_factura = 2 (compras)
        registros.append(
            render_a3_tipo12_cabecera(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro=tipo_registro,
                cuenta_tercero=c_prov,
                ndig_plan=ndig,
                tipo_factura="2",
                num_factura=num_fact,
                desc_apunte=desc,
                importe_total=total_abs,
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=r0.get("Fecha Expedicion") or "",
            )
        )

        # DETALLES tipo 9 (una por cada l¡nea de IVA de la factura)
        n_lineas = len(grecs)
        for i, rr in enumerate(grecs):
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))

            # Si no hay base ni IVA ni recargo ni retenci¢n, se omite
            re_pct= _fv(rr.get("Porcentaje Recargo Equivalencia"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_pct= _fv(rr.get("Porcentaje Retencion IRPF"))
            ret_c  = _fv(rr.get("Cuota Retencion IRPF"))

            if base == 0 and cuota == 0 and re_c == 0 and ret_c == 0:
                continue

            pct   = _fv(rr.get("Porcentaje IVA"))
            if base != 0 and pct == 0 and cuota != 0:
                pct = round(abs(cuota / base * 100.0), 2)

            registros.append(
                render_a3_tipo9_detalle(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_gasto_def,
                    ndig_plan=ndig,
                    num_factura=num_fact,
                    desc_apunte=desc,
                    subtipo=subtipo_def,
                    base=(base if signo > 0 else -abs(base)),
                    pct_iva=abs(pct),
                    cuota_iva=(cuota if signo > 0 else -abs(cuota)),
                    pct_re=abs(re_pct),
                    cuota_re=(re_c if signo > 0 else -abs(re_c)),
                    pct_ret=abs(ret_pct),
                    cuota_ret=(ret_c if signo > 0 else -abs(ret_c)),
                    es_ultimo=(i == n_lineas - 1),
                    dh=("A" if signo < 0 else "C"),
                    keep_sign=True,
                )
            )

    return registros
