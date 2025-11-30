# procesos/facturas_emitidas.py

from collections import defaultdict
from typing import List, Dict, Any

from facturas_common import (
    render_emitidas_cabecera_256,
    render_emitidas_detalle_256,
)


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
    # Caso 3: solo punto -> ya formato anglosajón

    try:
        return float(s)
    except Exception:
        return 0.0


def _key_factura(rec: Dict[str, Any]):
    """
    Agrupa las líneas del Excel por factura.
    Preferimos 'Numero Factura Largo SII' si existe, si no, Serie+Número.
    """
    nfl = rec.get("Numero Factura Largo SII") or rec.get("Número Factura Largo SII")
    if nfl:
        return ("NFL", str(nfl).strip())

    serie = str(rec.get("Serie") or "").strip()
    num = str(
        rec.get("Numero Factura")
        or rec.get("Número Factura")
        or ""
    ).strip()
    return ("SERIE_NUM", f"{serie}|{num}")


def generar_emitidas(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig: int,
) -> List[str]:
    """
    Genera registros de SUENLACE para FACTURAS EMITIDAS
    en formato 4 / 256 bytes (tipos 1 y 9), a partir de las filas
    ya mapeadas del Excel.
    """

    # Configuración de la plantilla
    pref_cli        = str(plantilla.get("cuenta_cliente_prefijo", "430"))
    cta_ventas_def  = str(plantilla.get("cuenta_ingreso_por_defecto", "70000000"))
    cta_iva_def     = str(plantilla.get("cuenta_iva_repercutido_defecto", "47700000"))
    cta_ret_def     = str(plantilla.get("cuenta_retenciones_irpf", ""))  # normalmente vacío
    subtipo_def     = str(plantilla.get("subtipo_emitidas", "01"))

    # Agrupar líneas del Excel por factura
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
            or r0.get("Número Factura")
            or r0.get("Numero Factura Largo SII")
            or ""
        )

        # Configuración Subcuenta Cliente Según la lógica:
        nif = str(r0.get("NIF Cliente Proveedor") or "").strip()
        nombre = str(r0.get("Nombre Cliente Proveedor") or "").strip()

        # 1) Si el Excel trae la subcuenta explícita, la usamos
        cta_excel = str(r0.get("Cuenta Cliente Proveedor") or "").strip()
        if cta_excel:
            # Nos quedamos con los dígitos, recortamos/padeamos a ndig
            dig_cta = "".join(ch for ch in cta_excel if ch.isdigit())
            if not dig_cta:
                dig_cta = "0"
            if len(dig_cta) >= ndig:
                subcliente = dig_cta[:ndig]
            else:
                subcliente = dig_cta.ljust(ndig, "0")

        else:
            # 2) Si NO hay subcuenta en el Excel, usamos la lógica de la plantilla

            pref_cli_raw = str(plantilla.get("cuenta_cliente_prefijo", "430"))
            pref_digits = "".join(ch for ch in pref_cli_raw if ch.isdigit()) or "0"
            nif_digits  = "".join(ch for ch in nif if ch.isdigit()) or "0"

            if len(pref_digits) >= ndig:
                # Caso A: han puesto una cuenta completa (ej: 43000000)
                subcliente = pref_digits[:ndig]
            else:
                # Caso C: prefijo corto (ej: 430) + NIF, recortando por la DERECHA
                base = (pref_digits + nif_digits)
                if len(base) >= ndig:
                    subcliente = base[:ndig]           # mantiene el prefijo al principio
                else:
                    subcliente = base.ljust(ndig, "0")


        # Total factura: suma de bases + IVA + recargo - retenciones
        total = 0.0
        for rr in grecs:
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))
            total += base + cuota + re_c - ret_c

        # CABECERA tipo 1 (formato 4/256)
        registros.append(
            render_emitidas_cabecera_256(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro="1",           # factura normal
                cuenta_tercero=subcliente,
                ndig_plan=ndig,
                tipo_factura="1",            # 1 = ventas
                num_factura=num_fact,
                desc_apunte=desc,
                importe_total=total,
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=r0.get("Fecha Expedicion") or "",
            )
        )

        # DETALLES tipo 9 (una por cada línea de IVA de la factura)
        n_lineas = len(grecs)
        for i, rr in enumerate(grecs):
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))

            # Si no hay IVA en esta línea, la saltamos
            if base == 0 and cuota == 0:
                continue

            pct   = _fv(rr.get("Porcentaje IVA"))
            if base != 0 and pct == 0 and cuota != 0:
                pct = round(abs(cuota / base * 100.0), 2)

            re_pct = _fv(rr.get("Porcentaje Recargo Equivalencia"))
            re_c   = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_pct= _fv(rr.get("Porcentaje Retencion IRPF"))
            ret_c  = _fv(rr.get("Cuota Retencion IRPF"))

            registros.append(
                render_emitidas_detalle_256(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_ventas_def,
                    ndig_plan=ndig,
                    num_factura=num_fact,
                    desc_apunte=desc,
                    subtipo=subtipo_def,
                    base=abs(base),
                    pct_iva=abs(pct),
                    cuota_iva=abs(cuota),
                    pct_re=abs(re_pct),
                    cuota_re=abs(re_c),
                    pct_ret=abs(ret_pct),
                    cuota_ret=abs(ret_c),
                    es_ultimo=(i == n_lineas - 1),
                    cuenta_iva=cta_iva_def,
                    cuenta_recargo="",          # si no hay recargo, lo dejamos vacío
                    cuenta_retencion=cta_ret_def or "",
                    impreso="",                 # campo "Impreso" en blanco
                    operacion_sujeta_iva=True,
                )
            )

    return registros
