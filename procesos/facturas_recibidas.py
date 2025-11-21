# procesos/facturas_recibidas.py
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from facturas_common import render_a3_tipo12_cabecera, render_a3_tipo9_detalle

TOLERANCIA_DESCUADRE = 0.005


def _fv(x):
    """Convierte cualquier valor a float, usando coma o punto como separador."""
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return 0.0


def _key_factura(rec: Dict[str, Any]):
    """
    Clave de agrupación de filas del Excel en una misma factura:
    - Primero intenta 'Numero Factura Largo SII'
    - Si no, usa Serie + Numero Factura
    """
    nfl = rec.get("Numero Factura Largo SII") or rec.get("Número Factura Largo SII")
    if nfl:
        return ("NFL", str(nfl).strip())
    serie = str(rec.get("Serie") or "").strip()
    num = str(rec.get("Numero Factura") or rec.get("Número Factura") or "").strip()
    return ("SERIE_NUM", f"{serie}|{num}")


def _col_total_posibles(rec: Dict[str, Any]) -> float:
    """
    Intenta localizar una columna de 'total factura' en la fila:
    Probamos varios nombres habituales. Si no existe, devuelve 0.0 (sin control).
    """
    posibles = [
        "Total", "TOTAL", "Importe Total", "Importe total",
        "Total Factura", "Total factura", "Base+IVA",
    ]
    for k in posibles:
        if k in rec and rec.get(k) not in (None, ""):
            return _fv(rec.get(k))
    return 0.0


def generar_recibidas(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig_plan: int
) -> Tuple[List[str], List[str]]:
    """
    Genera registros TIPO 2 (cabecera de compras) + TIPO 9 (detalle IVA)
    para FACTURAS RECIBIDAS en el formato estándar de A3 (suenlace.dat).

    Devuelve:
        (registros, avisos_descuadre)

    - 'avisos_descuadre' contendrá mensajes para aquellas facturas donde
      la diferencia entre el total Excel y el calculado por bases/IVA/ret
      sea > TOLERANCIA_DESCUADRE.
    """
    # Configuración de cuentas desde la plantilla
    pref_prov     = str(plantilla.get("cuenta_proveedor_prefijo", "400"))
    cta_gasto_def = str(plantilla.get("cuenta_gasto_por_defecto", "62900000"))
    cta_iva_def   = str(plantilla.get("cuenta_iva_soportado_defecto", "47200000"))
    cta_ret_def   = str(plantilla.get("cuenta_retenciones_irpf", "47510000"))
    subtipo_def   = str(plantilla.get("subtipo_recibidas", "01"))

    # Agrupamos filas del Excel en facturas
    grupos = defaultdict(list)
    for rec in rows:
        grupos[_key_factura(rec)].append(rec)

    registros: List[str] = []
    avisos: List[str] = []

    for (_, _id), grecs in grupos.items():
        r0 = grecs[0]

        fecha = (
            r0.get("Fecha Asiento")
            or r0.get("Fecha Expedicion")
            or r0.get("Fecha Operacion")
        )
        desc  = r0.get("Descripcion Factura") or ""
        num_fact = r0.get("Numero Factura") or r0.get("Número Factura") or ""
        nif   = str(r0.get("NIF Cliente Proveedor") or "").strip()
        nombre= str(r0.get("Nombre Cliente Proveedor") or "").strip()

        # 1) Cuenta de proveedor (400/410...)
        cta_prov_excel = str(r0.get("Cuenta Cliente Proveedor") or "").strip()
        if cta_prov_excel:
            dig = "".join(ch for ch in cta_prov_excel if ch.isdigit())
            prov8 = dig[-8:].zfill(8)
        else:
            dig = "".join(ch for ch in nif if ch.isdigit())
            prov8 = (pref_prov + dig)[-8:].zfill(8)

        # 2) Total calculado a partir de líneas
        total_calc = 0.0
        total_base = 0.0
        total_iva  = 0.0
        total_re   = 0.0
        total_ret  = 0.0

        for rr in grecs:
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))

            total_base += base
            total_iva  += cuota
            total_re   += re_c
            total_ret  += ret_c

        total_calc = total_base + total_iva + total_re - total_ret

        # 3) Total segun Excel (si existe columna de total)
        total_excel = _col_total_posibles(r0)
        if total_excel != 0.0:
            dif = total_excel - total_calc
            if abs(dif) > TOLERANCIA_DESCUADRE:
                avisos.append(
                    f"Factura {num_fact or '?'}: descuadre Debe/Haber "
                    f"de {dif:.3f} (Total Excel={total_excel:.2f}, calculado={total_calc:.2f})"
                )

        fecha_factura = (
            r0.get("Fecha Expedicion")
            or r0.get("Fecha Factura")
            or fecha
        )

        # ─ CABECERA TIPO 1 (factura normal) con tipo_factura '2' (compras) ─
        registros.append(
            render_a3_tipo12_cabecera(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro="1",         # '1' = factura normal
                cuenta_tercero=prov8,      # proveedor
                ndig_plan=ndig_plan,
                tipo_factura="2",          # '2' = compras
                num_factura=num_fact,
                desc_apunte=desc,
                importe_total=total_calc,  # usamos el calculado coherente con bases/IVA
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=fecha_factura,
                num_factura_largo_sii=r0.get("Numero Factura Largo SII") or "",
            )
        )

        # ─ DETALLES TIPO 9 (líneas de IVA) ─
        for i, rr in enumerate(grecs):
            base   = _fv(rr.get("Base"))
            cuota  = _fv(rr.get("Cuota IVA"))
            re_c   = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c  = _fv(rr.get("Cuota Retencion IRPF"))

            pct_iva = _fv(rr.get("Porcentaje IVA"))
            if pct_iva == 0 and base != 0:
                pct_iva = round(abs(cuota / base * 100.0), 2)

            pct_re  = _fv(rr.get("Porcentaje Recargo Equivalencia"))
            pct_ret = _fv(rr.get("Porcentaje Retencion IRPF"))

            registros.append(
                render_a3_tipo9_detalle(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_gasto_def,  # cuenta de compras/gasto
                    ndig_plan=ndig_plan,
                    num_factura=num_fact,
                    desc_apunte=desc,
                    subtipo=subtipo_def,            # p.ej. '01' operaciones interiores
                    base=abs(base),
                    pct_iva=abs(pct_iva),
                    cuota_iva=abs(cuota),
                    pct_re=abs(pct_re),
                    cuota_re=abs(re_c),
                    pct_ret=abs(pct_ret),
                    cuota_ret=abs(ret_c),
                    es_ultimo=(i == len(grecs) - 1),
                )
            )

    return registros, avisos
