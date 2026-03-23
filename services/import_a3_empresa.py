from __future__ import annotations

import re
from datetime import date
from pathlib import Path


_ID_RE = re.compile(
    r"\b(?:[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]|\d{8}[A-Z]|[XYZ]\d{7}[A-Z])\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_NAME_RE = re.compile(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .,&'/()-]{5,}")
_SKIP_NAME_TOKENS = {
    "TELE",
    "TEL",
    "MOVIL",
    "FACTURAS",
    "CONTABILIDAD",
    "DOCUMENTOS",
    "EMPRESA",
}

_PHONE_RE = re.compile(r"\b\d{9,12}\b")


def _clean_code(codigo: str) -> str:
    raw = str(codigo or "").strip().upper()
    if raw.startswith("E"):
        raw = raw[1:]
    txt = "".join(ch for ch in raw if ch.isdigit())
    if not txt:
        raise ValueError("Introduce un codigo de empresa A3 valido, por ejemplo E00193 o 00193.")
    return txt.zfill(5)


def _candidate_paths(codigo: str) -> list[Path]:
    bases = [Path(r"Z:\A3"), Path(r"Z:\A3\A3ECO"), Path(r"C:\A3")]
    out = []
    for base in bases:
        out.append(base / f"E{codigo}.DAT")
        out.append(base / f"e{codigo}.DAT")
        out.append(base / "A3ECO" / f"E{codigo}.DAT")
    return out


def _candidate_dirs(codigo: str) -> list[Path]:
    bases = [Path(r"Z:\A3\A3ECO"), Path(r"C:\A3\A3ECO"), Path(r"Z:\A3")]
    out = []
    for base in bases:
        out.append(base / f"E{codigo}")
    return out


def _candidate_var_paths(codigo: str) -> list[Path]:
    out = []
    for folder in _candidate_dirs(codigo):
        out.append(folder / f"{codigo}VAR.DAT")
        out.append(folder / f"{codigo}VAR.dat")
    return out


def _read_header_text(path: Path) -> str:
    data = path.read_bytes()[:512]
    return data.decode("latin-1", errors="ignore").replace("\x00", " ")


def _to_printable_text(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else " " for b in data)


def _read_var_blocks(path: Path) -> list[dict]:
    data = path.read_bytes()
    if len(data) <= 128:
        return []
    blocks = []
    for start in range(128, len(data), 268):
        block = data[start : start + 268]
        if len(block) < 16 or block[:2] != b"A\x08":
            continue
        tag = block[2:14].decode("latin-1", errors="ignore").rstrip("\x00 ").strip()
        text = block.decode("latin-1", errors="ignore")
        printable = _to_printable_text(block)
        blocks.append({"tag": tag, "text": text, "printable": printable})
    return blocks


def _extract_name_from_var(text: str) -> str:
    candidates = []
    for match in _NAME_RE.findall(text.upper()):
        value = " ".join(match.split()).strip(" .,-/")
        if len(value) < 6:
            continue
        if any(token in value for token in _SKIP_NAME_TOKENS):
            continue
        if sum(ch.isalpha() for ch in value) < 6:
            continue
        candidates.append(value.title())
    return candidates[-1] if candidates else ""


def _parse_var_company_data(var_path: Path) -> dict:
    blocks = _read_var_blocks(var_path)
    by_tag = {}
    for block in blocks:
        by_tag.setdefault(block["tag"], []).append(block)

    emo = (by_tag.get("EMO") or [{}])[0]
    dom = (by_tag.get("DOM") or [{}])[0]
    emo_text = str(emo.get("text") or "")
    dom_text = str(dom.get("text") or "")

    cif = _extract_cif(emo_text)
    telefono_match = _PHONE_RE.search(emo_text)
    telefono = telefono_match.group(0) if telefono_match else ""
    nombre = _extract_name_from_var(emo_text)

    sigla = emo_text[79:81].strip()
    via = " ".join(emo_text[81:111].split()).strip()
    numero = emo_text[111:116].strip()
    resto = " ".join(emo_text[116:122].split()).strip()
    direccion = " ".join(part for part in (sigla, via, numero, resto) if part).strip()

    poblacion = " ".join(dom_text[116:146].split()).title()
    provincia = " ".join(dom_text[146:176].split()).title()
    if not poblacion or poblacion == "Nn":
        dom_tokens = [
            token.strip().title()
            for token in re.findall(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,}", dom_text.upper())
            if token.strip() and token.strip() not in {"DOM", "NN"}
        ]
        poblacion = dom_tokens[0] if dom_tokens else ""
        provincia = dom_tokens[1] if len(dom_tokens) > 1 else poblacion

    raw_preview_parts = []
    for key in ("EMP", "DOM", "EMO", "IVA"):
        for block in by_tag.get(key, [])[:1]:
            raw_preview_parts.append(f"[{key}] {' '.join(block['printable'].split())}")

    return {
        "nombre": nombre,
        "cif": cif,
        "direccion": direccion,
        "cp": "",
        "poblacion": poblacion,
        "provincia": provincia,
        "telefono": telefono,
        "email": "",
        "_a3_raw_header": "\n".join(raw_preview_parts).strip(),
    }


def _extract_name(text: str) -> str:
    best = ""
    for raw in _NAME_RE.findall(text.upper()):
        name = " ".join(raw.split()).strip(" .,-/")
        while name and len(name.split()[-1]) == 1:
            name = " ".join(name.split()[:-1]).strip()
        if len(name) < 6:
            continue
        if any(token in name for token in _SKIP_NAME_TOKENS):
            continue
        if sum(ch.isalpha() for ch in name) < 6:
            continue
        if len(name) > len(best):
            best = name
    return best.title()


def _extract_cif(text: str) -> str:
    match = _ID_RE.search(text.upper())
    return match.group(0).upper() if match else ""


def _extract_year(text: str, fallback_dirs: list[Path]) -> int:
    years = []
    for match in _YEAR_RE.findall(text):
        try:
            year = int(match)
        except Exception:
            continue
        if 2000 <= year <= 2099:
            years.append(year)
    for folder in fallback_dirs:
        facturas_dir = folder / "FACTURAS"
        if not facturas_dir.exists():
            continue
        for child in facturas_dir.iterdir():
            if child.is_dir() and child.name.isdigit() and len(child.name) == 4:
                years.append(int(child.name))
    return max(years) if years else 2025


def importar_empresa_desde_a3(codigo: str) -> dict:
    codigo_norm = _clean_code(codigo)
    codigo_a3 = f"E{codigo_norm}"
    data_path = next((path for path in _candidate_paths(codigo_norm) if path.exists()), None)
    company_dirs = [path for path in _candidate_dirs(codigo_norm) if path.exists()]
    var_path = next((path for path in _candidate_var_paths(codigo_norm) if path.exists()), None)

    if data_path is None and not company_dirs and var_path is None:
        raise ValueError(f"No se ha encontrado la empresa {codigo_a3} en A3.")

    text = _read_header_text(data_path) if data_path else ""
    raw_preview = " ".join(text.split())
    detalle_origen = {}
    if var_path:
        try:
            detalle_origen = _parse_var_company_data(var_path)
        except Exception:
            detalle_origen = {}
    nombre = str(detalle_origen.get("nombre") or _extract_name(text) or "")
    cif = str(detalle_origen.get("cif") or _extract_cif(text) or "")
    direccion = str(detalle_origen.get("direccion") or "")
    cp = str(detalle_origen.get("cp") or "")
    poblacion = str(detalle_origen.get("poblacion") or "")
    provincia = str(detalle_origen.get("provincia") or "")
    telefono = str(detalle_origen.get("telefono") or "")
    email = str(detalle_origen.get("email") or "")
    ejercicio = date.today().year

    detalle = []
    if var_path:
        detalle.append(f"Ficha empresa VAR: {var_path}")
    if data_path:
        detalle.append(f"Ficha A3: {data_path}")
    if company_dirs:
        detalle.append(f"Carpeta A3ECO: {company_dirs[0]}")
    detalle.append(f"Ejercicio asignado por defecto: {ejercicio} (no importado desde A3)")

    return {
        "codigo": codigo_a3,
        "nombre": nombre,
        "digitos_plan": 8,
        "ejercicio": ejercicio,
        "serie_emitidas": "A",
        "siguiente_num_emitidas": 1,
        "serie_emitidas_rect": "R",
        "siguiente_num_emitidas_rect": 1,
        "cuenta_bancaria": "",
        "cuentas_bancarias": "",
        "cif": cif,
        "direccion": direccion,
        "cp": cp,
        "poblacion": poblacion,
        "provincia": provincia,
        "telefono": telefono,
        "email": email,
        "logo_path": "",
        "logo_max_width_mm": None,
        "logo_max_height_mm": None,
        "activo": True,
        "_a3_info": "\n".join(detalle),
        "_a3_raw_header": str(detalle_origen.get("_a3_raw_header") or raw_preview[:1200]),
    }
