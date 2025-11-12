# facturas_common.py
from dataclasses import dataclass
from typing import List
from decimal import Decimal

# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE LÍNEA (entrada lógica)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Linea:
    fecha: str         # 'AAAAMMDD' u otra convertible
    subcuenta: str     # cuenta (banco/contrapartida) del movimiento
    dh: str            # 'D' o 'H'
    importe: Decimal   # importe positivo (el sentido lo marca D/H)
    concepto: str      # texto del apunte (cabecera o narrativa)

# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES COMUNES
# ─────────────────────────────────────────────────────────────────────────────
def _s(x) -> str:
    return "" if x is None else str(x)

def _digits(s: str) -> str:
    return "".join(ch for ch in _s(s) if ch.isdigit())

def _fix_len(s: str, n: int) -> str:
    s = _s(s)
    return s[:n].ljust(n)

def _set_slice(buf: list, start: int, end: int, value: str):
    """Escribe value en buf[start:end] (0-based)."""
    val = _fix_len(value, end - start)
    buf[start:end] = list(val)

def _empresa5(cod) -> str:
    # 5 dígitos con ceros a la izquierda
    d = _digits(cod)
    if d == "": d = "0"
    return str(int(d)).zfill(5)[:5]

def _fecha_yyyymmdd(fecha: str) -> str:
    f = _s(fecha).strip()
    if not f:
        return "00000000"
    # quita separadores
    f = f.replace("-", "").replace("/", "").replace(".", "")
    # si trae 8 dígitos
    if len(f) >= 8 and f[:8].isdigit():
        s = f[:8]
        yyyy = s[:4]
        mm = s[4:6]
        dd = s[6:8]
        # si los 4 primeros no parecen un año (p.ej. 1011), interpretamos DDMMAAAA
        try:
            y = int(yyyy)
        except:
            y = 0
        if y < 1900 or y > 2100:
            # tratar como DDMMAAAA
            dd, mm, yyyy = s[0:2], s[2:4], s[4:8]
        # normaliza componentes a 2/4 dígitos
        return f"{yyyy}{mm}{dd}"
    # si los 8 últimos son dígitos (caso raro), intenta DDMMAAAA al final
    if len(f) >= 8 and f[-8:].isdigit():
        s = f[-8:]
        dd, mm, yyyy = s[0:2], s[2:4], s[4:8]
        return f"{yyyy}{mm}{dd}"
    return "00000000"

def _cuenta_12(c: str, ndig_plan: int = 8) -> str:
    """
    Cuenta para campo 16..27 (12 chars):
    - Para planes de 8 dígitos, A3 suele esperar la cuenta A LA IZQUIERDA
      y rellenada con CEROS A LA DERECHA hasta 12.
    - Si el valor excede ndig_plan, se toman los primeros ndig_plan.
    """
    base = _digits(c)
    if ndig_plan:
        if len(base) > ndig_plan:
            base = base[:ndig_plan]
        else:
            base = base.ljust(ndig_plan, "0")
    return base.ljust(12, "0")

def _importe_14(amt) -> str:
    """
    Devuelve: + 10 enteros + '.' + 2 decimales  => 14 chars exactos.
    (Siempre positivo; el sentido lo decide D/H o el propio tipo de registro).
    """
    try:
        v = float(_s(amt).replace(",", "."))
    except Exception:
        v = 0.0
    v = abs(v)
    s = f"{v:.2f}"          # '123456.78'
    ent, dec = s.split(".")
    ent = ent.zfill(10)[-10:]
    return f"+{ent}.{dec}"

# ─────────────────────────────────────────────────────────────────────────────
# RENDER 512 BYTES: BANCOS (TIPO 0)
# ─────────────────────────────────────────────────────────────────────────────
def render_a3_tipo0_bancos(lineas: List[Linea], codigo_empresa: str, ndig_plan: int = 8) -> List[str]:
    """
    Registros tipo 0 (apuntes sin IVA) de 512 bytes.
    Agrupación por (fecha + concepto) para marcar I/M/U.
    Campos según manual A3, con CRLF al final de cada registro.
    """
    if not lineas:
        return []

    emp5 = _empresa5(codigo_empresa)

    def key_asiento(ln: Linea):
        return (_fecha_yyyymmdd(ln.fecha), _s(ln.concepto).strip())

    grupos = []
    cur_key = key_asiento(lineas[0])
    cur = []
    for ln in lineas:
        k = key_asiento(ln)
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
            # 1           : '5'
            _set_slice(buf, 0, 1, "5")
            # 2..6        : empresa
            _set_slice(buf, 1, 6, emp5)
            # 7..14       : fecha AAAAMMDD
            _set_slice(buf, 6, 14, fecha8)
            # 15          : tipo 0
            _set_slice(buf, 14, 15, "0")
            # 16..27      : cuenta (12 chars, izq + ceros dcha)
            _set_slice(buf, 15, 27, _cuenta_12(ln.subcuenta, ndig_plan))
            # 28..57      : desc cuenta (en blanco)
            _set_slice(buf, 27, 57, "")
            # 58          : D/H
            _set_slice(buf, 57, 58, ("D" if _s(ln.dh).upper()=="D" else "H"))
            # 59..68      : referencia doc. (vacío)
            _set_slice(buf, 58, 68, "")
            # 69          : I/M/U
            ind = "I" if i==0 else ("U" if i==n-1 else "M")
            _set_slice(buf, 68, 69, ind)
            # 70..99      : descripción apunte (30)
            _set_slice(buf, 69, 99, concepto)
            # 100..113    : importe 14 (signo + 10 enteros + '.' + 2 dec)
            _set_slice(buf, 99, 113, _importe_14(ln.importe))
            # 114..508    : reserva
            _set_slice(buf, 113, 508, "")
            # 509         : Moneda 'E'
            _set_slice(buf, 508, 509, "E")
            # 510         : Indicador generado 'N'
            _set_slice(buf, 509, 510, "N")
            # 511..512    : CRLF
            buf[510] = "\r"; buf[511] = "\n"
            out.append("".join(buf))
    return out

# ─────────────────────────────────────────────────────────────────────────────
# RENDER 512 BYTES: FACTURAS (CABECERA TIPO 1/2) + DETALLE TIPO 9
# ─────────────────────────────────────────────────────────────────────────────
def _porc_5(xx) -> str:
    # “xx.xx” → exactamente 5 posiciones
    try:
        v = float(str(xx).replace(",", "."))
    except Exception:
        v = 0.0
    return f"{v:05.2f}"[-5:]

def _importe_14_pos(amt) -> str:
    # Igual que _importe_14 pero explícito por semántica
    return _importe_14(amt)

def render_a3_tipo12_cabecera(*, codigo_empresa: str, fecha: str, tipo_registro: str,
                              cuenta_tercero: str, ndig_plan: int,
                              tipo_factura: str,  # '1' ventas, '2' compras, '3' bienes inversión
                              num_factura: str, desc_apunte: str,
                              importe_total: float,
                              nif: str = "", nombre: str = "",
                              fecha_operacion: str = "", fecha_factura: str = "",
                              num_factura_largo_sii: str = "") -> str:
    """
    Registro TIPO 1 (facturas) o 2 (rectificativas). Longitud 512.
    Posiciones principales:
      1:'5' 2-6:empresa 7-14:fecha 15:'1'/'2' 16-27:cuenta
      58:tipo factura(1/2/3) 59-68:num doc 69:'I'
      70-99:desc apunte 100-113:importe total (+0000000000.00)
      176-189:NIF 190-229:Nombre
      237-244:Fecha operación 245-252:Fecha factura
      253-312:Núm. factura largo SII
      509:'E' 510:'N' 511-512:CRLF
    """
    buf = [" "] * 512
    emp5 = _empresa5(codigo_empresa)
    f8 = _fecha_yyyymmdd(fecha)
    cuenta12 = _cuenta_12(cuenta_tercero, ndig_plan)

    _set_slice(buf, 0, 1, "5")
    _set_slice(buf, 1, 6, emp5)
    _set_slice(buf, 6, 14, f8)
    _set_slice(buf, 14, 15, tipo_registro)          # '1' o '2'
    _set_slice(buf, 15, 27, cuenta12)               # 16..27
    _set_slice(buf, 27, 57, "")                     # 28..57 desc cuenta (opcional)
    _set_slice(buf, 57, 58, tipo_factura)           # 58: 1 ventas / 2 compras
    _set_slice(buf, 58, 68, _s(num_factura)[:10])   # 59..68 nº doc
    _set_slice(buf, 68, 69, "I")                    # 69
    _set_slice(buf, 69, 99, desc_apunte)            # 70..99
    _set_slice(buf, 99, 113, _importe_14_pos(importe_total))  # 100..113
    _set_slice(buf, 113, 175, "")                   # 114..175 reserva
    _set_slice(buf, 175, 189, _s(nif)[:14])         # 176..189 NIF
    _set_slice(buf, 189, 229, _s(nombre)[:40])      # 190..229 Nombre
    _set_slice(buf, 229, 235, "")                   # 230..234 reserva
    _set_slice(buf, 235, 237, "")                   # 235..236 reserva
    _set_slice(buf, 237, 244, _fecha_yyyymmdd(fecha_operacion))  # 237..244
    _set_slice(buf, 244, 252, _fecha_yyyymmdd(fecha_factura))    # 245..252
    _set_slice(buf, 252, 312, _s(num_factura_largo_sii)[:60])    # 253..312
    _set_slice(buf, 312, 508, "")                   # resto reserva
    _set_slice(buf, 508, 509, "E")
    _set_slice(buf, 509, 510, "N")
    buf[510] = "\r"; buf[511] = "\n"
    return "".join(buf)

def render_a3_tipo9_detalle(*, codigo_empresa: str, fecha: str,
                            cuenta_base_iva: str, ndig_plan: int,
                            num_factura: str, desc_apunte: str,
                            subtipo: str,  # '01' operaciones interiores (por defecto)
                            base: float, pct_iva: float, cuota_iva: float,
                            pct_re: float = 0.0, cuota_re: float = 0.0,
                            pct_ret: float = 0.0, cuota_ret: float = 0.0,
                            es_ultimo: bool = False) -> str:
    """
    Registro TIPO 9 (detalle por línea de IVA). Longitud 512.
    Posiciones principales:
      1:'5' 2-6:empresa 7-14:fecha 15:'9' 16-27:cuenta (ventas/compras)
      58:'C' (cargo) 59-68:num doc 69:'M'/'U'
      70-99:desc 100-101:subtipo '01'..
      102-115:Base 116-120:%IVA 121-134:Cuota IVA
      135-139:%RE 140-153:Cuota RE 154-158:%RET 159-172:Cuota RET
      509:'E' 510:'N' 511-512:CRLF
    """
    buf = [" "] * 512
    emp5 = _empresa5(codigo_empresa)
    f8 = _fecha_yyyymmdd(fecha)
    cuenta12 = _cuenta_12(cuenta_base_iva, ndig_plan)

    _set_slice(buf, 0, 1, "5")
    _set_slice(buf, 1, 6, emp5)
    _set_slice(buf, 6, 14, f8)
    _set_slice(buf, 14, 15, "9")
    _set_slice(buf, 15, 27, cuenta12)
    _set_slice(buf, 27, 57, "")
    _set_slice(buf, 57, 58, "C")                      # normal: 'C'
    _set_slice(buf, 58, 68, _s(num_factura)[:10])     # nº doc
    _set_slice(buf, 68, 69, ("U" if es_ultimo else "M"))
    _set_slice(buf, 69, 99, desc_apunte)
    _set_slice(buf, 99, 101, _s(subtipo).rjust(2, "0")[-2:])  # 100..101

    _set_slice(buf, 101, 115, _importe_14_pos(base))       # 102..115 base
    _set_slice(buf, 115, 120, _porc_5(pct_iva))            # 116..120 %IVA
    _set_slice(buf, 120, 134, _importe_14_pos(cuota_iva))  # 121..134 cuota
    _set_slice(buf, 134, 139, _porc_5(pct_re))             # 135..139 %RE
    _set_slice(buf, 139, 153, _importe_14_pos(cuota_re))   # 140..153 cuota RE
    _set_slice(buf, 153, 158, _porc_5(pct_ret))            # 154..158 %RET
    _set_slice(buf, 158, 172, _importe_14_pos(cuota_ret))  # 159..172 cuota RET

    _set_slice(buf, 172, 508, "")
    _set_slice(buf, 508, 509, "E")
    _set_slice(buf, 509, 510, "N")
    buf[510] = "\r"; buf[511] = "\n"
    return "".join(buf)
