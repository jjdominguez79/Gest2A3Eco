# facturas_common.py
from dataclasses import dataclass
from typing import List
from decimal import Decimal
from utilidades import d2, fmt_fecha, fmt_importe_pos, SEP, pad_subcuenta

@dataclass
class Linea:
    fecha: str
    subcuenta: str
    dh: str
    importe: Decimal
    concepto: str

def cuenta_por_porcentaje(tipos_iva: list, pct: float, defecto: str) -> str:
    """
    Devuelve la cuenta de IVA asociada a un % dado. Si no encuentra coincidencia exacta,
    devuelve la cuenta por defecto.
    tipos_iva: lista de dicts tipo {"porcentaje": 21, "cuenta_iva": "47700000"}
    pct: porcentaje buscado (float o str)
    defecto: cuenta por defecto (str)
    """
    try:
        pct = float(str(pct).replace(",", ".")) if pct not in (None, "") else None
    except Exception:
        pct = None
    for t in tipos_iva or []:
        try:
            if pct is not None and float(t.get("porcentaje", -1)) == pct:
                return t.get("cuenta_iva", defecto)
        except Exception:
            continue
    return defecto

def render_tabular(lineas: List[Linea], ndig: int) -> List[str]:
    out = []
    for ln in lineas:
        out.append(
            SEP.join([
                "T",
                fmt_fecha(ln.fecha),
                pad_subcuenta(ln.subcuenta, ndig),
                ln.dh,
                fmt_importe_pos(ln.importe),
                (ln.concepto or "").strip()
            ])
        )
    return out
