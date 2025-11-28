# procesos/facturas_emitidas.py
from typing import List, Dict, Any
from collections import defaultdict
from facturas_common import render_a3_tipo12_cabecera, render_a3_tipo9_detalle


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


def _solo_digitos(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())


def _cta_cliente(
    rec_cab: Dict[str, Any],
    plantilla: Dict[str, Any],
    nif: str,
    ndig_plan: int
) -> str:
    """
    Calcula la subcuenta del cliente con esta prioridad:

      1) Si en el Excel viene una columna 'Cuenta Cliente Proveedor' mapeada,
         usamos esa cuenta (ajustada a ndig_plan).

      2) Si la plantilla tiene 'cuenta_cliente_por_defecto' (ej. 43000000),
         usamos esa cuenta fija para todas las facturas.

      3) Si no, usamos 'cuenta_cliente_prefijo' (ej. 430) + dígitos del NIF,
         recortando POR LA IZQUIERDA y rellenando por la derecha, para
         mantener el grupo 430 al principio.
    """
    # 1) Cuenta desde Excel
    cta_excel = str(rec_cab.get("Cuenta Cliente Proveedor") or "").strip()
    if cta_excel:
        dig = _solo_digitos(cta_excel) or "0"
        return dig[:ndig_plan].ljust(ndig_plan, "0")

    # 2) Cuenta por defecto en la plantilla (ej. 43000000)
    cta_def = str(plantilla.get("cuenta_cliente_por_defecto") or "").strip()
    if cta_def:
        dig = _solo_digitos(cta_def) or "0"
        return dig[:ndig_plan].ljust(ndig_plan, "0")

    # 3) Prefijo + NIF (manteniendo el prefijo a la izquierda)
    pref_cli = str(plantilla.get("cuenta_cliente_prefijo", "430"))
    dig_nif = _solo_digitos(nif)
    base = (pref_cli + dig_nif) or pref_cli
    dig = _solo_digitos(base) or "0"
    return dig[:ndig_plan].ljust(ndig_plan, "0")


def generar_emitidas(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig_plan: int
) -> List[str]:
    """
    Genera registros tipo 1 (cabecera) + 9 (detalle) para FACTURAS EMITIDAS
    en el formato estándar de A3 (suenlace.dat).
    """
    cta_ventas_def = str(plantilla.get("cuenta_ingreso_por_defecto", "70000000"))
    subtipo_def = plantilla.get("subtipo_emitidas", "01")

    grupos = defaultdict(list)
    for rec in rows:
        grupos[_key_factura(rec)].append(rec)

    registros: List[str] = []

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

        # Subcuenta del cliente, con la prioridad descrita arriba
        cli_cta = _cta_cliente(r0, plantilla, nif, ndig_plan)

        total = 0.0
        for rr in grecs:
            base = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))
            total += base + cuota + re_c - ret_c

        # ─ Cabecera TIPO 1 (ventas) ─
        registros.append(
            render_a3_tipo12_cabecera(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro="1",         # facturas normales
                cuenta_tercero=cli_cta,    # cuenta de cliente
                ndig_plan=ndig_plan,
                tipo_factura="1",          # '1' = ventas
                num_factura=num_fact,
                desc_apunte=desc,
                importe_total=total,
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=r0.get("Fecha Expedicion") or "",
                num_factura_largo_sii="",
            )
        )

        # ─ Detalles TIPO 9 (líneas de IVA) ─
        for i, rr in enumerate(grecs):
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))

            pct_iva = _fv(rr.get("Porcentaje IVA"))
            if pct_iva == 0 and base != 0:
                pct_iva = round(abs(cuota / base * 100.0), 2)

            pct_re  = _fv(rr.get("Porcentaje Recargo Equivalencia"))
            pct_ret = _fv(rr.get("Porcentaje Retencion IRPF"))

            registros.append(
                render_a3_tipo9_detalle(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_ventas_def,  # cuenta de ingresos
                    ndig_plan=ndig_plan,
                    num_factura=num_fact,
                    desc_apunte=desc,
                    subtipo=str(subtipo_def),
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

    return registros
