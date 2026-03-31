from __future__ import annotations

import re
from datetime import date
from pathlib import Path
import unicodedata

try:
    import xlrd
except Exception:  # pragma: no cover
    xlrd = None

# ─── Constantes para lectura binaria de ficheros ISAM de A3Eco ───────────────
# Descubiertas por ingeniería inversa de los DAT de A3Eco (Wolters Kluwer).
# Todos los ficheros tienen cabecera de 128 bytes y registros de tamaño fijo.
# El byte 0 de cada registro es el marcador:  0x40/0x41=activo, otro=borrado.

_ISAM_HEADER = 128
_ISAM_ACTIVE = {0x40, 0x41}

# Fichero EM (empresa master): tamaño de registro 248 bytes
#   bytes  5-13 : NIF/CIF (9 chars, cp850)
#   bytes 54-73 : Razón Social (20 chars, cp850)
_EM_REC_SIZE = 248
_EM_NIF_SLICE = slice(5, 14)
_EM_NAME_SLICE = slice(54, 74)

# Fichero CU (cuentas / plan contable): tamaño de registro 260 bytes
#   bytes 5-7  : número de cuenta (entero big-endian 3 bytes)
#   bytes 8-37 : descripción (30 chars, cp850)
_CU_REC_SIZE = 260
_CU_CODE_SLICE = slice(5, 8)
_CU_DESC_SLICE = slice(8, 38)

_A3_ENCODING = "cp850"


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
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_WEB_RE = re.compile(r"\b(?:https?://|www\.)[A-Z0-9./_-]+\b", re.IGNORECASE)
_ADDRESS_START_RE = re.compile(
    r"\b(?:CL|C/|CALLE|AV|AVDA|AVENIDA|PZ|PL|PLAZA|PS|PASEO|CTRA|CARRETERA|BARRIO|POL|URB|TR|RONDA)\b",
    re.IGNORECASE,
)


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


def _candidate_em_paths(codigo: str) -> list[Path]:
    """Localiza el fichero EM (empresa master) dentro de la carpeta E{codigo}."""
    out = []
    for folder in _candidate_dirs(codigo):
        out.append(folder / f"{codigo}0EM.DAT")
        out.append(folder / f"{codigo}0EM.dat")
    return out


def _candidate_cu_paths(codigo: str) -> list[Path]:
    """Localiza el fichero CU (plan de cuentas) dentro de la carpeta E{codigo}."""
    out = []
    for folder in _candidate_dirs(codigo):
        out.append(folder / f"{codigo}0CU.DAT")
        out.append(folder / f"{codigo}0CU.dat")
    return out


def _candidate_dashboard_paths(codigo: str) -> list[Path]:
    out = []
    for folder in _candidate_dirs(codigo):
        out.append(folder / f"INF{codigo}" / "CUADRO DE MANDO.XLS")
        out.append(folder / f"inf{codigo}" / "CUADRO DE MANDO.XLS")
    return out


def _read_header_text(path: Path) -> str:
    data = path.read_bytes()[:512]
    return data.decode("latin-1", errors="ignore").replace("\x00", " ")


def _to_printable_text(data: bytes) -> str:
    return "".join(chr(b) if b >= 32 else " " for b in data)


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
        blocks.append({"tag": tag, "text": text, "printable": printable, "raw": block})
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


def _block_by_tag(blocks: list[dict], tag: str) -> dict:
    for block in blocks:
        if block.get("tag") == tag:
            return block
    return {}


def _block_by_prefix(blocks: list[dict], prefix: str) -> dict:
    for block in blocks:
        if str(block.get("tag") or "").startswith(prefix):
            return block
    return {}


def _clean_visible_text(text: str) -> str:
    raw = str(text or "").replace("\x00", " ")
    cleaned = []
    for ch in raw:
        if ch in "\r\n\t":
            cleaned.append(" ")
        elif ch.isalnum() or ch in " .,:;/@_()-[]":
            cleaned.append(ch)
        elif ch.isalpha():
            cleaned.append(ch)
        else:
            cat = unicodedata.category(ch)
            cleaned.append(ch if cat.startswith(("L", "N")) else " ")
    return " ".join("".join(cleaned).split())


def _extract_email(text: str) -> str:
    match = _EMAIL_RE.search(text or "")
    return match.group(0).strip() if match else ""


def _extract_web(text: str) -> str:
    match = _WEB_RE.search(text or "")
    return match.group(0).strip() if match else ""


def _extract_postal_code(text: str) -> str:
    for match in re.findall(r"\b\d{5}\b", text or ""):
        if match.startswith(("01", "02", "03", "04", "05", "06", "07", "08", "09")) or match.startswith(
            tuple(f"{n:02d}" for n in range(10, 53))
        ):
            return match
    return ""


def _extract_city_province(dom_text: str) -> tuple[str, str]:
    poblacion = " ".join(dom_text[116:146].split()).title()
    provincia = " ".join(dom_text[146:176].split()).title()
    if poblacion and provincia and poblacion != "Nn":
        return poblacion, provincia
    dom_tokens = [
        token.strip().title()
        for token in re.findall(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,}", dom_text.upper())
        if token.strip() and token.strip() not in {"DOM", "NN"}
    ]
    poblacion = dom_tokens[0] if dom_tokens else ""
    provincia = dom_tokens[1] if len(dom_tokens) > 1 else poblacion
    return poblacion, provincia


def _extract_address_from_ban(block: dict) -> tuple[str, str]:
    printable = str(block.get("printable") or "")
    start = _ADDRESS_START_RE.search(printable)
    if not start:
        return "", ""
    tail = printable[start.start() :]
    parts = [part.strip(" ,.-") for part in re.split(r"\s{2,}", tail) if part.strip(" ,.-")]
    if not parts:
        return "", ""
    direccion = parts[0]
    poblacion = parts[1].title() if len(parts) > 1 else ""
    return direccion.title(), poblacion


def _extract_phone(text: str) -> str:
    for match in _PHONE_RE.findall(text or ""):
        if len(match) == 9:
            return match
    return ""


def _decode_field(raw: bytes) -> str:
    """Decodifica un campo de texto A3 (cp850) y elimina espacios."""
    try:
        text = raw.decode(_A3_ENCODING, errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return text.strip()


def _leer_em_binario(em_path: Path) -> dict:
    """
    Lee el fichero EM.DAT (empresa master) en formato ISAM binario.
    Devuelve {'nif': ..., 'nombre': ...} con los datos del primer registro activo.
    Layout: cabecera 128 bytes, registros de 248 bytes cada uno.
      bytes  5-13  NIF/CIF (9 chars cp850)
      bytes 54-73  Razón Social (20 chars cp850)
    """
    try:
        data = em_path.read_bytes()
    except OSError:
        return {}
    offset = _ISAM_HEADER
    nif = ""
    nombre = ""
    while offset + _EM_REC_SIZE <= len(data):
        rec = data[offset: offset + _EM_REC_SIZE]
        if rec[0] in _ISAM_ACTIVE:
            if not nif:
                candidate = _decode_field(rec[_EM_NIF_SLICE])
                # Filtrar: NIF válido tiene al menos 7 caracteres alfanuméricos
                candidate_clean = re.sub(r"[^A-Za-z0-9]", "", candidate).upper()
                if len(candidate_clean) >= 7:
                    nif = candidate_clean[:9]
            if not nombre:
                candidate = _decode_field(rec[_EM_NAME_SLICE])
                if len(candidate) >= 3:
                    nombre = candidate
            if nif and nombre:
                break
        offset += _EM_REC_SIZE
    return {"nif": nif, "nombre": nombre}


def _leer_plan_cuentas_binario(cu_path: Path) -> list[dict]:
    """
    Lee el fichero CU.DAT (plan de cuentas) en formato ISAM binario.
    Devuelve lista de {'cuenta': '100', 'descripcion': 'CAPITAL SOCIAL'}.
    Layout: cabecera 128 bytes, registros de 260 bytes.
      bytes 5-7  número de cuenta (big-endian 3 bytes)
      bytes 8-37 descripción (30 chars cp850)
    """
    try:
        data = cu_path.read_bytes()
    except OSError:
        return []
    cuentas = []
    offset = _ISAM_HEADER
    while offset + _CU_REC_SIZE <= len(data):
        rec = data[offset: offset + _CU_REC_SIZE]
        if rec[0] in _ISAM_ACTIVE:
            code_bytes = rec[_CU_CODE_SLICE]
            num = (code_bytes[0] << 16) | (code_bytes[1] << 8) | code_bytes[2]
            if num > 0:
                desc = _decode_field(rec[_CU_DESC_SLICE])
                if desc:
                    cuentas.append({"cuenta": str(num), "descripcion": desc})
        offset += _CU_REC_SIZE
    return cuentas


def _parse_var_company_data(var_path: Path) -> dict:
    blocks = _read_var_blocks(var_path)
    emp = _block_by_tag(blocks, "EMP")
    dom = _block_by_tag(blocks, "DOM")
    ban = _block_by_prefix(blocks, "BAN")
    full_text = "\n".join(str(block.get("text") or "") for block in blocks)
    emp_text = str(emp.get("text") or "")
    dom_text = str(dom.get("text") or "")
    ban_text = str(ban.get("text") or "")

    cif = _extract_cif(full_text)
    telefono = _extract_phone(full_text)
    email = _extract_email(full_text)
    web = _extract_web(full_text)
    nombre = _extract_name_from_var(full_text)
    poblacion, provincia = _extract_city_province(dom_text)
    direccion, poblacion_ban = _extract_address_from_ban(ban)
    cp = _extract_postal_code(" ".join([emp_text, dom_text, ban_text]))
    if not poblacion and poblacion_ban:
        poblacion = poblacion_ban

    raw_preview_parts = []
    for key in ("EMP", "DOM", "IVA"):
        block = _block_by_tag(blocks, key)
        if block:
            raw_preview_parts.append(f"[{key}] {_clean_visible_text(block['printable'])}")
    if ban:
        raw_preview_parts.append(f"[{ban.get('tag')}] {_clean_visible_text(ban.get('printable'))}")

    return {
        "nombre": nombre,
        "cif": cif,
        "direccion": direccion,
        "cp": cp,
        "poblacion": poblacion,
        "provincia": provincia,
        "telefono": telefono,
        "email": email,
        "web": web,
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


def _to_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _parse_dashboard_company_data(path: Path, codigo_norm: str) -> dict:
    if xlrd is None:
        return {}
    try:
        book = xlrd.open_workbook(str(path), on_demand=True)
    except Exception:
        return {}

    def _sheet(name: str):
        try:
            return book.sheet_by_name(name)
        except Exception:
            return None

    idx_sheet = _sheet("Índice") or _sheet("Indice")
    if idx_sheet is not None and idx_sheet.nrows:
        headers = [str(idx_sheet.cell_value(0, col)).strip().lower() for col in range(idx_sheet.ncols)]
        try:
            col_empresa = headers.index("empresa")
            col_ejercicio = headers.index("ejercicio")
            col_nombre = headers.index("nombre empresa")
        except ValueError:
            col_empresa = col_ejercicio = col_nombre = -1
        if min(col_empresa, col_ejercicio, col_nombre) >= 0:
            selected = None
            for row in range(1, idx_sheet.nrows):
                empresa = _to_int(idx_sheet.cell_value(row, col_empresa))
                ejercicio = _to_int(idx_sheet.cell_value(row, col_ejercicio))
                nombre = str(idx_sheet.cell_value(row, col_nombre) or "").strip()
                if not nombre:
                    continue
                if empresa is not None and str(empresa).zfill(5) == codigo_norm:
                    if selected is None or (ejercicio or 0) > (selected.get("ejercicio") or 0):
                        selected = {"nombre": nombre, "ejercicio": ejercicio}
            if selected:
                return selected

    menu_sheet = _sheet("Menu")
    if menu_sheet is not None:
        for row in range(min(menu_sheet.nrows, 12)):
            for col in range(min(menu_sheet.ncols, 8)):
                val = str(menu_sheet.cell_value(row, col) or "").strip()
                if len(val) >= 6 and sum(ch.isalpha() for ch in val) >= 6:
                    return {"nombre": val}
    return {}


def importar_empresa_desde_a3(codigo: str) -> dict:
    codigo_norm = _clean_code(codigo)
    codigo_a3 = f"E{codigo_norm}"
    company_dirs = [path for path in _candidate_dirs(codigo_norm) if path.exists()]
    var_path = next((path for path in _candidate_var_paths(codigo_norm) if path.exists()), None)
    em_path = next((path for path in _candidate_em_paths(codigo_norm) if path.exists()), None)
    cu_path = next((path for path in _candidate_cu_paths(codigo_norm) if path.exists()), None)
    dashboard_path = next((path for path in _candidate_dashboard_paths(codigo_norm) if path.exists()), None)
    data_path = next((path for path in _candidate_paths(codigo_norm) if path.exists()), None)

    if em_path is None and data_path is None and not company_dirs and var_path is None and dashboard_path is None:
        raise ValueError(f"No se ha encontrado la empresa {codigo_a3} en A3.")

    # 1. Lectura binaria del fichero EM (más fiable para NIF y nombre)
    em_data = _leer_em_binario(em_path) if em_path else {}

    # 2. Plan de cuentas desde fichero CU binario
    plan_cuentas = _leer_plan_cuentas_binario(cu_path) if cu_path else []

    # 3. Variables empresa (VAR): web, email, domicilio, teléfono
    text = _read_header_text(data_path) if data_path else ""
    raw_preview = " ".join(text.split())
    detalle_origen = {}
    if var_path:
        try:
            detalle_origen = _parse_var_company_data(var_path)
        except Exception:
            detalle_origen = {}
    dashboard_data = {}
    if dashboard_path:
        dashboard_data = _parse_dashboard_company_data(dashboard_path, codigo_norm)

    # Prioridad: binario EM > dashboard > VAR regex > texto cabecera
    nombre = str(
        dashboard_data.get("nombre")
        or em_data.get("nombre")
        or _extract_name(text)
        or ""
    )
    cif = str(
        em_data.get("nif")
        or detalle_origen.get("cif")
        or _extract_cif(text)
        or ""
    )
    direccion = str(detalle_origen.get("direccion") or "")
    cp = str(detalle_origen.get("cp") or "")
    poblacion = str(detalle_origen.get("poblacion") or "")
    provincia = str(detalle_origen.get("provincia") or "")
    telefono = str(detalle_origen.get("telefono") or "")
    email = str(detalle_origen.get("email") or "")
    ejercicio = (
        _to_int(dashboard_data.get("ejercicio"))
        or _extract_year(text, company_dirs)
        or date.today().year
    )

    detalle = []
    if dashboard_path:
        detalle.append(f"Cuadro de mando A3: {dashboard_path}")
    if em_path:
        detalle.append(f"Fichero EM (empresa master): {em_path}")
    if var_path:
        detalle.append(f"Ficha empresa VAR: {var_path}")
    if cu_path:
        detalle.append(f"Plan de cuentas CU ({len(plan_cuentas)} cuentas): {cu_path}")
    if data_path:
        detalle.append(f"Ficha A3: {data_path}")
    if company_dirs:
        detalle.append(f"Carpeta A3ECO: {company_dirs[0]}")
    detalle.append(f"Ejercicio detectado: {ejercicio}")
    if detalle_origen.get("web"):
        detalle.append(f"Web detectada: {detalle_origen.get('web')}")

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
        "plan_cuentas": plan_cuentas,
        "_a3_info": "\n".join(detalle),
        "_a3_raw_header": str(detalle_origen.get("_a3_raw_header") or raw_preview[:1200]),
    }
