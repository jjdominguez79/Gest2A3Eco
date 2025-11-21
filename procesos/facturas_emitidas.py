# procesos/facturas_emitidas.py
from typing import List, Dict, Any
from collections import defaultdict
from facturas_common import render_a3_tipo12_cabecera, render_a3_tipo9_detalle


def _fv(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return 0.0


def _key_factura(rec: Dict[str, Any]):
    nfl = rec.get("Numero Factura Largo SII") or rec.get("Número Factura Largo SII")
    if nfl:
        return ("NFL", str(nfl).strip())
    serie = str(rec.get("Serie") or "").strip()
    num = str(rec.get("Numero Factura") or rec.get("Número Factura") or "").strip()
    return ("SERIE_NUM", f"{serie}|{num}")


def generar_emitidas(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig_plan: int
) -> List[str]:
    """
    Genera registros tipo 1 (cabecera) + 9 (detalle) para FACTURAS EMITIDAS.
    """
    pref_cli = str(plantilla.get("cuenta_cliente_prefijo", "430"))
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

        cli8 = (pref_cli + "".join(ch for ch in nif if ch.isdigit()))[-8:].zfill(8)

        total = 0.0
        for rr in grecs:
            base = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            re_c  = _fv(rr.get("Cuota Recargo Equivalencia"))
            ret_c = _fv(rr.get("Cuota Retencion IRPF"))
            total += base + cuota + re_c - ret_c

        registros.append(
            render_a3_tipo12_cabecera(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro="1",
                cuenta_tercero=cli8,
                ndig_plan=ndig_plan,
                tipo_factura="1",  # ventas
                num_factura=num_fact,
                desc_apunte=desc,
                importe_total=total,
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=r0.get("Fecha Expedicion") or "",
                num_factura_largo_sii=r0.get("Numero Factura Largo SII") or "",
            )
        )

        for i, rr in enumerate(grecs):
            base  = _fv(rr.get("Base"))
            cuota = _fv(rr.get("Cuota IVA"))
            pct   = _fv(rr.get("Porcentaje IVA"))
            if pct == 0 and base != 0:
                pct = round(abs(cuota / base * 100.0), 2)

            cta_ventas = cta_ventas_def

            registros.append(
                render_a3_tipo9_detalle(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_ventas,
                    ndig_plan=ndig_plan,
                    num_factura=num_fact,
                    desc_apunte=desc,
                    subtipo=str(subtipo_def),
                    base=abs(base),
                    pct_iva=abs(pct),
                    cuota_iva=abs(cuota),
                    es_ultimo=( i == len(grecs) - 1 ),
                )
            )

    return registros
