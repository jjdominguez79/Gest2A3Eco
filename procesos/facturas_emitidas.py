# procesos/facturas_emitidas.py
#
# Generacion de registros SUENLACE para facturas emitidas (ventas).
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

from models.facturas_common import (
    render_emitidas_cabecera_256,
    render_emitidas_detalle_256,
    render_a3_tipoC_alta_cuenta,
)


def _fv(x) -> float:
    """Convierte a float tolerando formatos 1.234,56 / 1234,56 y devuelve 0.0 si no es convertible."""
    if x is None or x == "":
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip().replace("\xa0", " ")
    if not s:
        return 0.0
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _r2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0

def _d2(x) -> Decimal:
    try:
        return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def _d0(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def _norm_subtipo(val: Any) -> str:
    s = "" if val is None else str(val).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return "01"
    return digits.zfill(2)[-2:]

def _subcuenta_generica(plantilla: Dict[str, Any], ndig: int) -> str:
    pref_cli_raw = str(plantilla.get("cuenta_cliente_prefijo", "430") or "430")
    pref_digits = "".join(ch for ch in pref_cli_raw if ch.isdigit()) or "0"
    if len(pref_digits) >= ndig:
        return pref_digits[:ndig]
    return pref_digits.ljust(ndig, "0")


def _key_factura(rec: Dict[str, Any]):
    """
    Agrupa las lineas del Excel por factura.
    Prefiere 'Numero Factura Largo SII' si existe, si no, Serie + Numero.
    """
    nfl = rec.get("Numero Factura Largo SII")
    if nfl:
        return ("NFL", str(nfl).strip())
    serie = str(rec.get("Serie") or "").strip()
    num = str(rec.get("Numero Factura") or "").strip()
    return ("SERIE_NUM", f"{serie}|{num}")

def _ajustar_cuenta(raw: Any, ndig: int) -> str:
    s = "" if raw is None else str(raw)
    dig = "".join(ch for ch in s if ch.isdigit())
    if not dig:
        dig = "0"
    if len(dig) > ndig:
        return dig[:ndig]
    return dig.ljust(ndig, "0")

def _norm_nif(nif: Any) -> str:
    return str(nif or "").strip().upper()

def _datos_tercero(row: Dict[str, Any], terceros_by_nif: Dict[str, Dict[str, Any]] | None):
    nif = _norm_nif(row.get("NIF Cliente Proveedor") or row.get("NIF"))
    nombre = str(row.get("Nombre Cliente Proveedor") or "").strip()
    tercero = (terceros_by_nif or {}).get(nif) if nif else None
    if tercero:
        nombre = str(tercero.get("nombre") or nombre).strip()
    return {
        "nif": nif,
        "nombre": nombre,
        "direccion": str((tercero or {}).get("direccion") or "").strip(),
        "cp": str((tercero or {}).get("cp") or "").strip(),
        "poblacion": str((tercero or {}).get("poblacion") or "").strip(),
        "provincia": str((tercero or {}).get("provincia") or "").strip(),
        "telefono": str((tercero or {}).get("telefono") or "").strip(),
        "email": str((tercero or {}).get("email") or "").strip(),
    }

def _cuenta_ingreso_tercero(terceros_by_nif: Dict[str, Dict[str, Any]] | None, nif: str, ndig: int) -> str:
    if not terceros_by_nif or not nif:
        return ""
    raw = (terceros_by_nif.get(nif) or {}).get("subcuenta_ingreso")
    if not raw:
        return ""
    return _ajustar_cuenta(raw, ndig)


def generar_emitidas(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig: int,
    ejercicio: int | None = None,
    terceros_by_nif: Dict[str, Dict[str, Any]] | None = None,
) -> List[str]:
    """
    Genera registros de SUENLACE para FACTURAS EMITIDAS
    en formato 4 / 256 bytes (tipos 1 y 9), a partir de las filas
    ya mapeadas del Excel o del editor interno.
    """

    cta_ventas_def  = str(plantilla.get("cuenta_ingreso_por_defecto", "70000000"))
    cta_iva_def     = str(plantilla.get("cuenta_iva_repercutido_defecto", "47700000"))
    cta_ret_def     = str(plantilla.get("cuenta_retenciones_irpf", ""))  # normalmente vacio
    subtipo_def     = _norm_subtipo(plantilla.get("subtipo_emitidas", "01"))

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
        desc = (
            r0.get("Descripcion Factura")
            or r0.get("Descripcion Linea")
            or r0.get("Descripcion")
            or ""
        )

        num_fact = (
            r0.get("Numero Factura")
            or r0.get("Numero Factura Largo SII")
            or ""
        )

        # Datos tercero
        datos_ter = _datos_tercero(r0, terceros_by_nif)
        nif = datos_ter.get("nif", "")
        nombre = datos_ter.get("nombre", "")
        c_ing_ter = _cuenta_ingreso_tercero(terceros_by_nif, nif, ndig)
        ref_doc = str(r0.get("_pdf_ref") or r0.get("Referencia Doc") or "").strip()
        desc_cab = f"Nª Fra. {num_fact}".strip()
        desc_det = f"Ventas a {nombre}".strip() if nombre else "Ventas"

        # Subcuenta: si no hay mapeo o no viene informada, usa generica
        cta_excel = str(r0.get("Cuenta Cliente Proveedor") or "").strip()
        if cta_excel and not r0.get("_usar_cuenta_generica"):
            dig_cta = "".join(ch for ch in cta_excel if ch.isdigit()) or "0"
            subcliente = (dig_cta + "0" * ndig)[:ndig]
        else:
            subcliente = _subcuenta_generica(plantilla, ndig)

        # Total factura: suma de bases + IVA + recargo + retenciones (retenciones negativas)
        total = Decimal("0.00")
        for rr in grecs:
            base  = _d2(_fv(rr.get("Base")))
            pct   = _d0(_fv(rr.get("Porcentaje IVA")))
            cuota = _d2(_fv(rr.get("Cuota IVA")))
            if base != 0 and pct != 0:
                cuota = (base * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            re_pct = _d0(_fv(rr.get("Porcentaje Recargo Equivalencia")))
            re_c   = _d2(_fv(rr.get("Cuota Recargo Equivalencia")))
            if base != 0 and re_pct != 0:
                re_c = (base * re_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ret_pct = _d0(_fv(rr.get("Porcentaje Retencion IRPF")))
            ret_c   = _d2(_fv(rr.get("Cuota Retencion IRPF")))
            if base != 0 and ret_pct != 0:
                ret_c = -(abs(base * ret_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                ret_c = -abs(ret_c)
            total += base + cuota + re_c + ret_c
        total = _d2(total)
        signo = -1 if total < 0 else 1
        total_abs = abs(float(total))
        tipo_registro = "2" if signo < 0 else "1"  # 2 = rectificativa (abono)

        registros.append(
            render_emitidas_cabecera_256(
                codigo_empresa=codigo_empresa,
                fecha=fecha,
                tipo_registro=tipo_registro,
                cuenta_tercero=subcliente,
                ndig_plan=ndig,
                tipo_factura="1",            # 1 = ventas
                num_factura=num_fact,
                desc_apunte=desc_cab,
                ref_doc=ref_doc,
                importe_total=total_abs,
                nif=nif,
                nombre=nombre,
                fecha_operacion=r0.get("Fecha Operacion") or "",
                fecha_factura=r0.get("Fecha Expedicion") or "",
            )
        )

        # Detalle tipo 9 por cada linea de IVA
        cta_ventas = r0.get("Cuenta Compras Ventas") or c_ing_ter or cta_ventas_def
        cta_ventas = _ajustar_cuenta(cta_ventas, ndig)
        detalle_rows = []
        for rr in grecs:
            base  = _d2(_fv(rr.get("Base")))
            pct   = _d0(_fv(rr.get("Porcentaje IVA")))
            cuota = _d2(_fv(rr.get("Cuota IVA")))
            if base != 0 and pct != 0:
                cuota = (base * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            re_pct = _d0(_fv(rr.get("Porcentaje Recargo Equivalencia")))
            re_c   = _d2(_fv(rr.get("Cuota Recargo Equivalencia")))
            if base != 0 and re_pct != 0:
                re_c = (base * re_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            ret_pct = _d0(_fv(rr.get("Porcentaje Retencion IRPF")))
            ret_c   = _d2(_fv(rr.get("Cuota Retencion IRPF")))
            if base != 0 and ret_pct != 0:
                ret_c = -(abs(base * ret_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                ret_c = -abs(ret_c)

            # Si no hay base, IVA, recargo ni retención, se omite
            if base == 0 and cuota == 0 and re_c == 0 and ret_c == 0:
                continue

            if base != 0 and pct == 0 and cuota != 0:
                pct = _d0((abs(cuota / base) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            detalle_rows.append(
                {
                    "base": float(base),
                    "pct": float(pct),
                    "cuota": float(cuota),
                    "re_pct": float(re_pct),
                    "re_c": float(re_c),
                    "ret_pct": float(ret_pct),
                    "ret_c": float(ret_c),
                }
            )

        n_lineas = len(detalle_rows)
        for i, rr in enumerate(detalle_rows):
            base = rr["base"]
            cuota = rr["cuota"]
            re_c = rr["re_c"]
            ret_c = rr["ret_c"]
            re_pct = rr["re_pct"]
            ret_pct = rr["ret_pct"]
            pct = rr["pct"]

            registros.append(
                render_emitidas_detalle_256(
                    codigo_empresa=codigo_empresa,
                    fecha=fecha,
                    cuenta_base_iva=cta_ventas,
                    ndig_plan=ndig,
                    num_factura=num_fact,
                    desc_apunte=desc_det,
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
                    cuenta_iva=cta_iva_def,
                    cuenta_recargo="",
                    cuenta_retencion=cta_ret_def or "",
                    impreso="",
                    operacion_sujeta_iva=True,
                    keep_sign=True,
                )
            )

    return registros
