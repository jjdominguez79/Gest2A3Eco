# facturas_common.py
from dataclasses import dataclass
from typing import List
from decimal import Decimal
from utilidades import d2, fmt_fecha, fmt_importe_pos, SEP, pad_subcuenta

@dataclass
class Linea:
    fecha: str
    subcuenta: str
    dh: str          # 'D' o 'H'
    importe: Decimal
    concepto: str

def cuenta_por_porcentaje(tipos_iva: list, pct: float, defecto: str) -> str:
    """
    Devuelve la cuenta de IVA asociada a un % dado. Si no encuentra coincidencia exacta,
    devuelve la cuenta por defecto.
    tipos_iva: lista de dicts tipo {"porcentaje": 21, "cuenta_iva": "47700000"}
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
    """
    Render antiguo con separador (no lo usa A3). Se mantiene por compatibilidad.
    """
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

# -------------------------
# Render formato fijo A3 (254 chars) patrón E,E,N
# -------------------------

def _fecha_yymmdd(fecha: str) -> str:
    """
    Devuelve YYMMDD. Acepta 'YYYYMMDD', 'YYYY-MM-DD', 'DD/MM/YYYY', etc.
    """
    f = str(fecha or "").strip()
    if not f:
        return "000000"
    f = f.replace("-", "").replace("/", "")
    # si parece AAAAMMDD
    if len(f) >= 8 and f[:8].isdigit():
        yyyy = f[:4]; mm = f[4:6]; dd = f[6:8]
        return f"{yyyy[-2:]}{mm}{dd}"
    # si no, intenta DDMMYYYY
    if len(f) >= 8 and f[-8:].isdigit():
        yyyy = f[-4:]; mm = f[-6:-4]; dd = f[-8:-6]
        return f"{yyyy[-2:]}{mm}{dd}"
    return "000000"

def _fix_len(s: str, width: int) -> str:
    s = (s or "")
    if len(s) > width:
        return s[:width]
    return s.ljust(width)

def _num(amount) -> float:
    try:
        return float(str(amount).replace(",", "."))
    except Exception:
        return 0.0

def _fmt_importe_13(amount: float) -> str:
    # 10 enteros + '.' + 2 decimales = 13 chars, con ceros a la izquierda
    return f"{amount:013.2f}"

def render_a3_een(lineas: List[Linea]) -> List[str]:
    """
    Genera formato fijo (254) para A3 con patrón por 'asiento' E,E,...,N.
    Agrupa por (fecha YYMMDD + concepto). Importes siempre positivos; D/H marca el sentido.
    E-line: termina con 'EN'
    N-line: termina con 'N'
    NOTA: las posiciones exactas pueden variar entre instalaciones; este layout replica
    el patrón usual observado en SUENLACE.DAT de A3.
    """
    out = []

    if not lineas:
        return out

    def key(l: Linea):
        return (_fecha_yymmdd(l.fecha), (l.concepto or "").strip())

    asiento_movs: List[Linea] = []
    asiento_key = key(lineas[0])

    def flush_asiento(movs: List[Linea], k):
        if not movs:
            return
        # ----- E (una por movimiento) -----
        for ln in movs:
            sc = _fix_len((ln.subcuenta or "").strip(), 8)              # 0..7
            fy = _fecha_yymmdd(ln.fecha)                                 # 8..13 (YYMMDD)
            doc = "000000000000"                                         # 14..25
            pre = "0".ljust(24)                                          # 26..49
            base = sc + fy + doc + pre                                   # hasta 49
            # dejamos relleno hasta pos 57 e insertamos D/H
            if len(base) < 58:
                base = base.ljust(58)
            dh = ("D" if str(ln.dh).upper()=="D" else "H")
            base = base[:57] + dh + base[58:]
            # asegurar hasta pos 99 e insertar signo + importe (100..112)
            if len(base) < 100:
                base = base.ljust(100)
            importe = abs(_num(ln.importe))
            base = base[:99] + "+" + _fmt_importe_13(importe) + base[113:]
            # completar a 252 y marcar tipo
            if len(base) < 252:
                base = base.ljust(252)
            base += "EN"  # marca E + sufijo 'N' (observado en ficheros A3)
            out.append(base)

        # ----- N (narrativa) -----
        fecha, concepto = k
        sc0 = _fix_len((movs[0].subcuenta or ""), 8)
        nline = sc0 + fecha
        if len(nline) < 50:
            nline = nline.ljust(50)
        nline = nline[:50] + _fix_len(concepto, 150) + nline[50+150:]
        if len(nline) < 253:
            nline = nline.ljust(253)
        nline += "N"
        out.append(nline)

    for ln in lineas:
        k = key(ln)
        if k != asiento_key and asiento_movs:
            flush_asiento(asiento_movs, asiento_key)
            asiento_movs = []
            asiento_key = k
        asiento_movs.append(ln)
    flush_asiento(asiento_movs, asiento_key)

    return out
