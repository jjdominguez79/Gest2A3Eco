# facturas_common.py
from dataclasses import dataclass
from typing import List
from decimal import Decimal
from datetime import datetime, date, timedelta
import re

_EXCEL_EPOCH_1900 = date(1899, 12, 30)  # Excel (sistema 1900)
_EXCEL_EPOCH_1904 = date(1904, 1, 1)    # Excel (sistema 1904, frecuente en Mac)

_MONTHS_ES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DIC": 12
}

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

def _yyyy2_to_yyyy(y2: int) -> int:
    # 00-49 => 2000-2049, 50-99 => 1950-1999
    return 2000 + y2 if 0 <= y2 <= 49 else 1900 + y2

def _fecha_yyyymmdd(fecha) -> str:
    """Normaliza cualquier 'fecha' a AAAAMMDD para A3."""
    # 0) None / vacío
    if fecha in (None, ""):
        return "00000000"

    # 1) pandas.Timestamp
    try:
        import pandas as pd
        if isinstance(fecha, pd.Timestamp):
            return fecha.strftime("%Y%m%d")
    except Exception:
        pass

    # 2) datetime.date / datetime
    if isinstance(fecha, (date, datetime)):
        d = fecha.date() if isinstance(fecha, datetime) else fecha
        return d.strftime("%Y%m%d")

    # 3) Serial numérico de Excel (int o float). Acepta enteros y floats con fracción horaria.
    if isinstance(fecha, (int, float)) and not isinstance(fecha, bool):
        try:
            serial = float(fecha)
            days = int(serial)
            d = _EXCEL_EPOCH_1900 + timedelta(days=days)
            # Heurística: si año muy bajo, prueba 1904
            if d.year < 1930:
                d = _EXCEL_EPOCH_1904 + timedelta(days=days)
            return d.strftime("%Y%m%d")
        except Exception:
            pass

    # 4) Cadena: limpiar y probar formatos
    s = _s(fecha)
    s = s.replace("\xa0", " ").strip()   # ya lo tenías
    s = s.strip("'\"")   
    if not s:
        return "00000000"

    # Normaliza separadores a '/'
    ss = s.replace(".", "/").replace("-", "/").replace("\\", "/")

    # Formatos más comunes (incluye año 2 dígitos)
    for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%d/%m/%y", "%Y%m%d", "%d%m%Y"):
        try:
            dt = datetime.strptime(ss, fmt)
            # si el formato fue %d/%m/%y, ajustar ventana de años
            if fmt == "%d/%m/%y":
                y = dt.year % 100
                dt = dt.replace(year=_yyyy2_to_yyyy(y))
            return dt.strftime("%Y%m%d")
        except ValueError:
            continue

    # Mes con nombre en español (ej: "10 nov 2025", "01-ene-25", etc.)
    try:
        parts = [p for p in re.split(r"[ \t/\\\-\.]+", s.strip()) if p]
        if len(parts) >= 3:
            d1, m1, y1 = parts[0], parts[1], parts[2]
            # ¿mes literal?
            mm = None
            m_up = m1.strip().upper()
            m_up = m_up[:4] if len(m_up) >= 4 and m_up.startswith("SEPT") else m_up[:3]
            if m_up in _MONTHS_ES:
                mm = _MONTHS_ES[m_up]
            if mm is not None and d1.isdigit() and y1.isdigit():
                dd = int(d1)
                yy = int(y1)
                if yy < 100:
                    yy = _yyyy2_to_yyyy(yy)
                dt = date(yy, mm, dd)
                return dt.strftime("%Y%m%d")
    except Exception:
        pass

    # Solo dígitos → heurística AAAAMMDD / DDMMAAAA
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        cand = digits[:8]
        yyyy, mm, dd = cand[:4], cand[4:6], cand[6:8]
        # Si el "año" no parece año, interpretar DDMMAAAA
        try:
            y = int(yyyy)
        except:
            y = 0
        if y < 1900 or y > 2100:
            dd, mm, yyyy = cand[0:2], cand[2:4], cand[4:8]
        # Intenta validar; si falla, prueba intercambio dd/mm
        try:
            datetime(int(yyyy), int(mm), int(dd))
        except ValueError:
            dd, mm = mm, dd
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

def _importe_14_signed(amt) -> str:
    """
    Igual que _importe_14 pero preservando el signo (+/-) del valor.
    """
    try:
        v = float(_s(amt).replace(",", "."))
    except Exception:
        v = 0.0
    sign = "-" if v < 0 else "+"
    v = abs(v)
    s = f"{v:.2f}"
    ent, dec = s.split(".")
    ent = ent.zfill(10)[-10:]
    return f"{sign}{ent}.{dec}"

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

def render_a3_tipo12_cabecera(*,
        codigo_empresa: str,
        fecha: str,
        tipo_registro: str,
        cuenta_tercero: str,
        ndig_plan: int,
        tipo_factura: str,  # '1' ventas, '2' compras, '3' bienes inversión
        num_factura: str,
        desc_apunte: str,
        importe_total: float,
        nif: str = "",
        nombre: str = "",
        fecha_operacion: str = "",
        fecha_factura: str = "",
        num_factura_largo_sii: str = ""
    ) -> str:
    
    """
    Registro TIPO 1 (facturas) o 2 (rectificativas). Longitud 254 + CRLF.
    Posiciones principales:
      1:'4'
      2-6:empresa
      7-14:fecha 
      15:'1'/'2'
      16-27:cuenta
      58:tipo factura(1/2/3)
      59-68:num doc
      69:'I'
      70-99:desc apunte
      100-113:importe total (+0000000000.00)
      176-189:NIF
      190-229:Nombre
      237-244:Fecha operación
      245-252:Fecha factura
      253:'E'
      254:'N'
      255-256:CRLF
    """
    buf = [" "] * 254
    emp5 = _empresa5(codigo_empresa)
    f8 = _fecha_yyyymmdd(fecha)
    cuenta12 = _cuenta_12(cuenta_tercero, ndig_plan)

    _set_slice(buf, 0, 1, "4")
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
    _set_slice(buf, 229, 236, "")                   # 230..236 reserva
    _set_slice(buf, 236, 244, _fecha_yyyymmdd(fecha_operacion))  # 237..244
    _set_slice(buf, 244, 252, _fecha_yyyymmdd(fecha_factura))    # 245..252
    _set_slice(buf, 252, 253, "E")
    _set_slice(buf, 253, 254, "N")
    buf.append("\r"); buf.append("\n")
    return "".join(buf)

def render_a3_tipo9_detalle(*, codigo_empresa: str, fecha: str,
                            cuenta_base_iva: str, ndig_plan: int,
                            num_factura: str, desc_apunte: str,
                            subtipo: str,  # '01' operaciones interiores (por defecto)
                            base: float, pct_iva: float, cuota_iva: float,
                            pct_re: float = 0.0, cuota_re: float = 0.0,
                            pct_ret: float = 0.0, cuota_ret: float = 0.0,
                            es_ultimo: bool = False,
                            dh: str = "C",
                            keep_sign: bool = False) -> str:
    """
    Registro TIPO 9 (detalle por línea de IVA). Longitud 254 + CRLF.

    Estructura principal (resumen):
      1:'4'
      2-6 : empresa
      7-14: fecha
      15  : '9'
      16-27: cuenta base/ventas/compras
      58  : 'C'
      59-68: nº doc
      69  : 'M'/'U'
      70-99: descripción
      100-101: subtipo '01'..
      102-115: Base
      116-120: %IVA
      121-134: Cuota IVA
      135-139: %RE
      140-153: Cuota RE
      154-158: %RET
      159-172: Cuota RET
      173-175: Clave subtipo + deducible ('S'/'N') o '00S' para claves especiales
      176-252: reserva
      253: 'E'
      254: 'N'
      255-256: CRLF
    """
    buf = [" "] * 254
    emp5 = _empresa5(codigo_empresa)
    f8 = _fecha_yyyymmdd(fecha)
    cuenta12 = _cuenta_12(cuenta_base_iva, ndig_plan)
    dh_flag = "A" if _s(dh).upper().startswith("A") else "C"

    # Cabecera básica del registro 9
    _set_slice(buf, 0, 1, "4")
    _set_slice(buf, 1, 6, emp5)
    _set_slice(buf, 6, 14, f8)
    _set_slice(buf, 14, 15, "9")
    _set_slice(buf, 15, 27, cuenta12)
    _set_slice(buf, 27, 57, "")
    _set_slice(buf, 57, 58, dh_flag)                  # Cargo/Abono
    _set_slice(buf, 58, 68, _s(num_factura)[:10])     # nº doc
    _set_slice(buf, 68, 69, ("U" if es_ultimo else "M"))
    _set_slice(buf, 69, 99, desc_apunte)

    # Bloque de importes
    _set_slice(buf, 99, 101, _s(subtipo).rjust(2, "0")[-2:])   # 100..101 subtipo

    if keep_sign:
        base_fmt = _importe_14_signed(base)
        iva_fmt  = _importe_14_signed(cuota_iva)
        re_fmt   = _importe_14_signed(cuota_re)
        ret_fmt  = _importe_14_signed(cuota_ret)
    else:
        base_fmt = _importe_14_pos(base)
        iva_fmt  = _importe_14_pos(cuota_iva)
        re_fmt   = _importe_14_pos(cuota_re)
        ret_fmt  = _importe_14_pos(cuota_ret)

    _set_slice(buf, 101, 115, base_fmt)                        # 102..115 base
    _set_slice(buf, 115, 120, _porc_5(pct_iva))                # 116..120 %IVA
    _set_slice(buf, 120, 134, iva_fmt)                         # 121..134 cuota IVA
    _set_slice(buf, 134, 139, _porc_5(pct_re))                 # 135..139 %RE
    _set_slice(buf, 139, 153, re_fmt)                          # 140..153 cuota RE
    _set_slice(buf, 153, 158, _porc_5(pct_ret))                # 154..158 %RET
    _set_slice(buf, 158, 172, ret_fmt)                         # 159..172 cuota RET

    # Clave subtipo + deducibilidad (ej. '01S', '01N', '00S')
    subtipo2 = _s(subtipo).rjust(2, "0")[-2:]
    try:
        iva_val = float(str(pct_iva).replace(",", "."))
    except Exception:
        iva_val = 0.0
    if subtipo2 in ("06", "07"):
        clave_dedu = "00S"
    elif abs(iva_val) < 1e-9:
        clave_dedu = f"{subtipo2}N"
    else:
        clave_dedu = f"{subtipo2}S"
    _set_slice(buf, 172, 175, clave_dedu)

    # Reservas hasta el final
    _set_slice(buf, 175, 252, "")

    # Moneda e indicador al final
    _set_slice(buf, 252, 253, "E")
    _set_slice(buf, 253, 254, "N")
    buf.append("\r")
    buf.append("\n")
    return "".join(buf)

# ─────────────────────────────────────────────────────────────────────────────
# RENDER 256 BYTES: FACTURAS EMITIDAS (CABECERA TIPO 1/2) + DETALLE TIPO 9 - FORMATO 4
# ─────────────────────────────────────────────────────────────────────────────
def render_emitidas_cabecera_256(*,
    codigo_empresa: str,
    fecha: str,
    tipo_registro: str,  # '1' normal, '2' rectif
    cuenta_tercero: str,
    ndig_plan: int,
    tipo_factura: str,  # '1' ventas
    num_factura: str,
    desc_apunte: str,
    importe_total: float,
    nif: str = "",
    nombre: str = "",
    fecha_operacion: str = "",
    fecha_factura: str = ""
) -> str:
    
    buf = [" "] * 256
    emp5 = _empresa5(codigo_empresa)
    f8   = _fecha_yyyymmdd(fecha)
    cta12= _cuenta_12(cuenta_tercero, ndig_plan)
    
    _set_slice(buf, 0, 1, "4")
    _set_slice(buf, 1, 6, emp5)
    _set_slice(buf, 6, 14, f8)
    _set_slice(buf, 14, 15, str(tipo_registro))
    _set_slice(buf, 15, 27, cta12)
    _set_slice(buf, 27, 57, _s(nombre)[:30])
    _set_slice(buf, 57, 58, str(tipo_factura))          # 1=ventas
    _set_slice(buf, 58, 68, _s(num_factura)[:10])
    _set_slice(buf, 68, 69, "I")
    _set_slice(buf, 69, 99, _s(desc_apunte)[:30])
    _set_slice(buf, 99, 113, _importe_14_pos(importe_total))
    _set_slice(buf, 113, 175, "")
    _set_slice(buf, 175, 189, _s(nif)[:14])
    _set_slice(buf, 189, 229, _s(nombre)[:40])
    _set_slice(buf, 229, 234, "")
    _set_slice(buf, 234, 236, "")
    _set_slice(buf, 236, 244, _fecha_yyyymmdd(fecha_operacion))
    _set_slice(buf, 244, 252, _fecha_yyyymmdd(fecha_factura or fecha))
    _set_slice(buf, 252, 253, "E")
    _set_slice(buf, 253, 254, "N")
    buf[254] = "\r"; buf[255] = "\n"
    
    return "".join(buf)

def render_emitidas_detalle_256(*,
    codigo_empresa: str,
    fecha: str,
    cuenta_base_iva: str,
    ndig_plan: int,
    num_factura: str,
    desc_apunte: str,
    subtipo: str,              # '01'.. (operaciones interiores, etc.)
    base: float,
    pct_iva: float,
    cuota_iva: float,
    pct_re: float = 0.0,
    cuota_re: float = 0.0,
    pct_ret: float = 0.0,
    cuota_ret: float = 0.0,
    es_ultimo: bool = False,
    cuenta_iva: str = "",
    cuenta_recargo: str = "",
    cuenta_retencion: str = "",
    cuenta_iva2: str = "",
    cuenta_recargo2: str = "",
    impreso: str = "",
    operacion_sujeta_iva: bool = True
) -> str:
    
    buf = [" "] * 256
    emp5 = _empresa5(codigo_empresa)
    f8   = _fecha_yyyymmdd(fecha)
    cta12= _cuenta_12(cuenta_base_iva, ndig_plan)
    
    _set_slice(buf, 0, 1, "4")
    _set_slice(buf, 1, 6, emp5)
    _set_slice(buf, 6, 14, f8)
    _set_slice(buf, 14, 15, "9")
    _set_slice(buf, 15, 27, cta12)
    _set_slice(buf, 27, 57, "")
    _set_slice(buf, 57, 58, "C")
    _set_slice(buf, 58, 68, _s(num_factura)[:10])
    _set_slice(buf, 68, 69, ("U" if es_ultimo else "M"))
    _set_slice(buf, 69, 99, _s(desc_apunte)[:30])
    _set_slice(buf, 99, 101, _s(subtipo).rjust(2, "0")[-2:])
    _set_slice(buf, 101, 115, _importe_14_pos(base))         # 102-115
    _set_slice(buf, 115, 120, _porc_5(pct_iva))              # 116-120
    _set_slice(buf, 120, 134, _importe_14_pos(cuota_iva))    # 121-134
    _set_slice(buf, 134, 139, _porc_5(pct_re))               # 135-139
    _set_slice(buf, 139, 153, _importe_14_pos(cuota_re))     # 140-153
    _set_slice(buf, 153, 158, _porc_5(pct_ret))              # 154-158
    _set_slice(buf, 158, 172, _importe_14_pos(cuota_ret))    # 159-172
    _set_slice(buf, 172, 174, _s(impreso)[:2])
    _set_slice(buf, 174, 175, "S" if operacion_sujeta_iva else "N")
    _set_slice(buf, 175, 176, "")
    _set_slice(buf, 176, 177, "")
    _set_slice(buf, 177, 191, "")
    _set_slice(buf, 191, 203, _cuenta_12(cuenta_iva, ndig_plan) if cuenta_iva else "")
    _set_slice(buf, 203, 215, _cuenta_12(cuenta_recargo, ndig_plan) if cuenta_recargo else "")
    _set_slice(buf, 215, 227, _cuenta_12(cuenta_retencion, ndig_plan) if cuenta_retencion else "")
    _set_slice(buf, 227, 239, _cuenta_12(cuenta_iva2, ndig_plan) if cuenta_iva2 else "")
    _set_slice(buf, 239, 251, _cuenta_12(cuenta_recargo2, ndig_plan) if cuenta_recargo2 else "")
    _set_slice(buf, 251, 252, "")
    _set_slice(buf, 252, 253, "E")
    _set_slice(buf, 253, 254, "N")
    buf[254] = "\r"; buf[255] = "\n"
    return "".join(buf)
