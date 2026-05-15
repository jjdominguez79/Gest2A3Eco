from __future__ import annotations

from datetime import date, datetime

from utils.utilidades import format_num_es


def to_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0


def parse_date_ui(val: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except Exception:
            continue
    return date.today()


def to_fecha_ui(val: str) -> str:
    if not val:
        return date.today().strftime("%d/%m/%Y")
    try:
        d = parse_date_ui(str(val))
        return d.strftime("%d/%m/%Y")
    except Exception:
        return date.today().strftime("%d/%m/%Y")


def to_fecha_ui_or_blank(val: str) -> str:
    if not val:
        return ""
    return to_fecha_ui(val)


def round2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def round4(x) -> float:
    try:
        return round(float(x), 4)
    except Exception:
        return 0.0


def fmt2(x) -> str:
    return format_num_es(x, 2)


def fmt4(x) -> str:
    return format_num_es(x, 4)


def fmt2s(x, simbolo: str = "") -> str:
    txt = format_num_es(x, 2)
    return f"{txt} {simbolo}".strip() if simbolo else txt


def normalizar_telefono(tel: str) -> str:
    import re

    return re.sub(r"[\s\-\+\(\)]", "", str(tel or "").strip())
