from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

SEP = "\t"

def d2(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

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
