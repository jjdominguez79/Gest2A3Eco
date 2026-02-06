
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import math

SEP = "\t"

def d2(x):
    """
    Convierte a Decimal con 2 decimales de forma tolerante:
    - None, cadenas vac¡as o NaN -> 0.00
    - Acepta formatos "1.234,56" y "1234,56"
    - Si no es convertible, devuelve 0.00 en vez de disparar conversionSyntax
    """
    if x is None:
        return Decimal("0.00")

    # N£meros (int/float) directos
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        # Protege NaN/inf
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return Decimal("0.00")
        try:
            return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    s = str(x).strip()
    if not s:
        return Decimal("0.00")

    s = s.replace("\xa0", " ").replace(" ", "")
    # Formatos con coma/punto
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")

def fmt_fecha(dt):
    if isinstance(dt, str):
        for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%d/%m/%y","%Y/%m/%d"):
            try:
                return datetime.strptime(dt.strip(), fmt).strftime("%Y%m%d")
            except Exception:
                pass
        raise ValueError(f"Fecha inválida: {dt}")
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    return dt.strftime("%Y%m%d")

def fmt_importe_pos(x):
    return f"{abs(float(x)):.2f}"

def pad_subcuenta(sc: str, ndig: int):
    sc = (sc or "").strip()
    if len(sc) != ndig:
        raise ValueError(f"Subcuenta '{sc}' no cumple longitud {ndig}.")
    return sc

def construir_nombre_salida(ruta_elegida: str, codigo_empresa: str):
    from pathlib import Path
    destino = Path(ruta_elegida)
    carpeta = destino if destino.is_dir() else destino.parent
    return carpeta / f"{codigo_empresa}.dat"

def col_letter_to_index(letter: str) -> int:
    letter = (letter or "").strip().upper()
    if not letter:
        return -1
    idx = 0
    for ch in letter:
        if not ('A' <= ch <= 'Z'):
            raise ValueError(f"Columna inválida: {letter}")
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1

# utilidades.py (añade esto si no lo tienes)
def validar_subcuenta_longitud(sc: str, ndig: int, campo: str = "subcuenta"):
    sc = (sc or "").strip()
    if not sc:
        return
    if len(sc) != ndig:
        raise ValueError(f"La {campo} '{sc}' debe tener {ndig} dígitos (configurado a nivel de empresa).")

def aplicar_descuento_total_lineas(lineas, tipo, valor):
    """
    Aplica un descuento total proporcional sobre las lineas (base e impuestos).
    tipo: "pct" o "imp". valor: porcentaje o importe absoluto.
    """
    if not lineas:
        return []
    t = (tipo or "").strip().lower()
    if t not in ("pct", "imp"):
        return [dict(ln) for ln in lineas]
    try:
        v = float(valor or 0)
    except Exception:
        v = 0.0
    if v <= 0:
        return [dict(ln) for ln in lineas]

    total_base = 0.0
    for ln in lineas:
        try:
            total_base += float(ln.get("base", 0) or 0)
        except Exception:
            pass
    if total_base <= 0:
        return [dict(ln) for ln in lineas]

    if t == "pct":
        desc_total = total_base * min(max(v, 0.0), 100.0) / 100.0
    else:
        desc_total = min(abs(v), total_base)

    out = []
    for ln in lineas:
        base = float(ln.get("base", 0) or 0)
        if base <= 0:
            out.append(dict(ln))
            continue
        ratio = desc_total * (base / total_base)
        factor = max(0.0, 1.0 - (ratio / base))
        nl = dict(ln)
        nl["base"] = round(base * factor, 2)
        try:
            nl["cuota_iva"] = round(float(ln.get("cuota_iva", 0) or 0) * factor, 2)
        except Exception:
            nl["cuota_iva"] = 0.0
        try:
            nl["cuota_re"] = round(float(ln.get("cuota_re", 0) or 0) * factor, 2)
        except Exception:
            nl["cuota_re"] = 0.0
        try:
            nl["cuota_irpf"] = round(float(ln.get("cuota_irpf", 0) or 0) * factor, 2)
        except Exception:
            nl["cuota_irpf"] = 0.0
        out.append(nl)
    return out
