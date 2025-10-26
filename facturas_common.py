from dataclasses import dataclass
from datetime import datetime
from typing import List
from decimal import Decimal
from utilidades import d2, fmt_fecha, fmt_importe_pos, SEP, pad_subcuenta

@dataclass
class Linea:
    fecha: datetime
    subcuenta: str
    dh: str
    importe: Decimal
    concepto: str

def cuenta_por_porcentaje(tipos_iva: list, pct: float, defecto: str) -> str:
    for t in tipos_iva or []:
        try:
            if float(t.get("porcentaje", -1)) == float(pct):
                return t.get("cuenta_iva", defecto)
        except Exception:
            continue
    return defecto

def formar_tercero(prefijo: str, codigo: str, ndig: int) -> str:
    codigo = (codigo or "").upper().replace(" ", "").replace("-", "")
    subcta = (prefijo + codigo).ljust(ndig, "0")[:ndig]
    return subcta

def render_tabular(lineas: List[Linea], ndig: int) -> List[str]:
    out = []
    for ln in lineas:
        out.append(SEP.join(["T", fmt_fecha(ln.fecha), pad_subcuenta(ln.subcuenta, ndig), ln.dh, fmt_importe_pos(ln.importe), (ln.concepto or "").strip()]))
    return out
