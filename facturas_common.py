from dataclasses import dataclass
from typing import List
from decimal import Decimal

@dataclass
class Linea:
    fecha: str        # 'AAAAMMDD' o variante convertible
    subcuenta: str    # cuenta nivel 6-12 (12 chars en A3; nosotros la normalizamos)
    dh: str           # 'D' o 'H'
    importe: Decimal  # positivo; el signo se coloca en el campo del importe
    concepto: str     # 30 chars en tipo 0

# ---------------- utilidades de posicionado A3 (512) ----------------

def _s(x): return "" if x is None else str(x)

def _digits(s: str) -> str:
    return "".join(ch for ch in _s(s) if ch.isdigit())

def _empresa5(cod) -> str:
    # 5 dígitos, con ceros a la izquierda
    return str(int(_digits(cod) or "0")).zfill(5)[:5]

def _fecha_yyyymmdd(fecha: str) -> str:
    f = _s(fecha).strip()
    if not f:
        return "00000000"
    f = f.replace("-", "").replace("/", "")
    if len(f) >= 8 and f[:8].isdigit():      # AAAAMMDD
        return f[:8]
    if len(f) >= 8 and f[-8:].isdigit():     # DDMMAAAA -> AAAAMMDD
        dd, mm, yyyy = f[-8:-6], f[-6:-4], f[-4:]
        return f"{yyyy}{mm}{dd}"
    return "00000000"

def _cuenta_12(c: str, ndig_plan: int = 8) -> str:
    """
    Campo 16..27 (12 chars) para A3:
    - Si el plan es de 'ndig_plan' (p.ej. 8), la subcuenta se
      ALINEA A LA IZQUIERDA y se RELLENA CON CEROS A LA DERECHA hasta 12.
    - Si la subcuenta trae más dígitos que el plan, se toman los primeros 'ndig_plan'.
    - Si trae menos, se completa a la derecha con ceros hasta 'ndig_plan', y luego
      de nuevo hasta 12 con ceros.
    Ejemplos (ndig_plan=8):
      '57200001'   -> '57200001' + '0000' = '572000010000'
      '40012345'   -> '40012345' + '0000' = '400123450000'
    """
    base = _digits(c)  # solo dígitos
    if not base:
        base = ""
    if ndig_plan:
        if len(base) > ndig_plan:
            base = base[:ndig_plan]             # recorta si excede
        else:
            base = base.ljust(ndig_plan, "0")   # completa a la derecha si falta
    # ahora expándelo a 12 rellenando a la derecha con ceros
    return base.ljust(12, "0")

def _importe_14(amt) -> str:
    
    """
    Devuelve: signo (always '+') + 10 enteros + '.' + 2 decimales  => 14 chars.
    Si la parte entera supera 10 dígitos, se toman los 10 últimos.
    """
    try:
        v = float(_s(amt).replace(",", "."))
    except Exception:
        v = 0.0
    v = abs(v)  # el sentido contable lo marca D/H; aquí siempre positivo
    s = f"{v:.2f}"   # ej: '123456.78'
    int_part, dec_part = s.split(".")
    int_part = int_part.zfill(10)[-10:]  # 10 enteros exactos
    return f"+{int_part}.{dec_part}"     # 1 + 10 + 1 + 2 = 14

def _s(x):
    return "" if x is None else str(x)

def _fix_len(s: str, n: int) -> str:
    s = _s(s)
    return s[:n].ljust(n)

def _set_slice(buf: list, start: int, end: int, value: str):
    """Escribe value en buf[start:end] (1-based en comentario, 0-based aquí)."""
    val = _fix_len(value, end - start)
    buf[start:end] = list(val)

# ---------------- RENDER: Tipo 0 (Apuntes sin IVA) 512 bytes ----------------

def render_a3_tipo0_bancos(lineas: List[Linea], codigo_empresa: str, ndig_plan: int = 8) -> List[str]:
    """
    Genera registros tipo 0 (apuntes sin IVA) de 512 bytes para bancos.
    - Agrupa en asientos: el primer movimiento 'I', intermedios 'M', último 'U'.
    - Cada Linea debe tener: fecha, subcuenta (se normaliza), D/H, importe positivo, concepto.
    - Si falta subcuenta en contrapartida, usa la subcuenta por defecto ANTES de llamar a este render.
    Campos (según manual):
      1         : '5' (tipo de formato)
      2..6      : código empresa (00001..99999)
      7..14     : fecha AAAAMMDD
      15        : '0' (tipo de registro)
      16..27    : cuenta (nivel 6..12) -> 12 chars
      28..57    : descripción cuenta -> 30 (puedes dejar espacios)
      58        : D/H
      59..68    : ref doc -> 10
      69        : I/M/U
      70..99    : descripción apunte -> 30
      100..113  : importe (signo + 10 + '.' + 2) -> 14
      114..250  : reserva -> 137
      251       : 'S' si asiento nómina (normal: espacio)
      252       : 'S' si hay distribución analítica (normal: espacio)
      253..508  : reserva -> 256
      509       : moneda 'E'
      510       : indicador generado 'N'
      511..512  : CRLF
    """
    if not lineas:
        return []

    emp = _empresa5(codigo_empresa)

    # agrupamos por fecha + concepto para formar asientos
    def k_asiento(ln: Linea):
        return (_fecha_yyyymmdd(ln.fecha), _s(ln.concepto).strip())

    grupos = []
    cur_key = k_asiento(lineas[0])
    cur = []
    for ln in lineas:
        k = k_asiento(ln)
        if k != cur_key and cur:
            grupos.append((cur_key, cur))
            cur = []
            cur_key = k
        cur.append(ln)
    if cur:
        grupos.append((cur_key, cur))

    out = []
    for (fecha8, concepto), movs in grupos:
        n = len(movs)
        for i, ln in enumerate(movs):
            buf = [" "] * 512

            # 1: '5'
            _set_slice(buf, 0, 1, "5")
            # 2..6: empresa
            _set_slice(buf, 1, 6, emp)
            # 7..14: fecha
            _set_slice(buf, 6, 14, fecha8)
            # 15: tipo registro 0
            _set_slice(buf, 14, 15, "0")
            # 16..27: cuenta (12)
            _set_slice(buf, 15, 27, _cuenta_12(ln.subcuenta, ndig_plan))
            # 28..57: desc cuenta (opcional, dejamos espacios)
            _set_slice(buf, 27, 57, "")
            # 58: D/H
            _set_slice(buf, 57, 58, "D" if _s(ln.dh).upper() == "D" else "H")
            # 59..68: referencia (vacío)
            _set_slice(buf, 58, 68, "")
            # 69: I/M/U
            ind = "I" if i == 0 else ("U" if i == n - 1 else "M")
            _set_slice(buf, 68, 69, ind)
            # 70..99: descripción apunte (30)
            _set_slice(buf, 69, 99, _s(concepto))
            # 100..113: importe 14 (con punto)
            _set_slice(buf, 99, 113, _importe_14(ln.importe))
            # 114..250: reserva
            _set_slice(buf, 113, 250, "")
            # 251 nómina (en blanco)
            _set_slice(buf, 250, 251, " ")
            # 252 analítica (en blanco)
            _set_slice(buf, 251, 252, " ")
            # 253..508 reserva
            _set_slice(buf, 252, 508, "")
            # 509 moneda
            _set_slice(buf, 508, 509, "E")
            # 510 generado
            _set_slice(buf, 509, 510, "N")
            # 511..512 CRLF
            buf[510] = "\r"
            buf[511] = "\n"

            out.append("".join(buf))

    return out
