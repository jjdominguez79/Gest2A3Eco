from __future__ import annotations

import re
from datetime import date
from pathlib import Path
import unicodedata

try:
    import xlrd
except Exception:  # pragma: no cover
    xlrd = None

try:
    from utils.utilidades import load_app_config as _load_app_config
except Exception:  # pragma: no cover
    def _load_app_config() -> dict:  # type: ignore[misc]
        return {}

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
#   bytes 5-7  : número de cuenta (entero big-endian 3 bytes, max 16.777.215)
#   bytes 8-37 : descripción (30 chars, cp850)
# El campo de cuenta ocupa exactamente 3 bytes. Para planes de hasta 7 dígitos
# (max 9.999.999) esto es suficiente. Los 6 primeros bytes del registro son:
#   [0]=marcador activo/borrado, [1-4]=cero (padding ISAM), [5-7]=código.
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


def _get_a3_eco_bases() -> list[Path]:
    """
    Devuelve las rutas base candidatas donde puede estar instalado A3ECO.
    Prioridad: 1) ruta configurada en config.json (a3_base_path),
               2) rutas por defecto conocidas.
    """
    bases: list[Path] = []
    try:
        cfg = _load_app_config()
        configured = str(cfg.get("a3_base_path") or "").strip()
        if configured:
            p = Path(configured)
            # La ruta configurada puede ser la carpeta A3 o directamente A3ECO
            if (p / "A3ECO").exists():
                bases.append(p / "A3ECO")
            bases.append(p)
    except Exception:
        pass
    # Rutas por defecto: unidad de red primero, luego instalacion local
    defaults = [
        Path(r"Z:\A3\A3ECO"),
        Path(r"Z:\A3"),
        Path(r"C:\Users\GestinemFiscal\Documents\A3\A3ECO"),
        Path(r"C:\A3\A3ECO"),
    ]
    seen = {str(b).lower() for b in bases}
    for d in defaults:
        if str(d).lower() not in seen:
            bases.append(d)
            seen.add(str(d).lower())
    return bases


def _get_a3_gesw_bases() -> list[Path]:
    """Rutas candidatas del modulo A3GESW (para TECODIR y datos de gestion)."""
    bases: list[Path] = []
    try:
        cfg = _load_app_config()
        configured = str(cfg.get("a3_base_path") or "").strip()
        if configured:
            p = Path(configured)
            if (p / "A3GESW").exists():
                bases.append(p / "A3GESW")
    except Exception:
        pass
    defaults = [
        Path(r"Z:\A3\A3GESW"),
        Path(r"C:\Users\GestinemFiscal\Documents\A3\A3GESW"),
        Path(r"C:\A3\A3GESW"),
    ]
    seen = {str(b).lower() for b in bases}
    for d in defaults:
        if str(d).lower() not in seen:
            bases.append(d)
            seen.add(str(d).lower())
    return bases


def _candidate_paths(codigo: str) -> list[Path]:
    out = []
    for base in _get_a3_eco_bases():
        out.append(base / f"E{codigo}.DAT")
        out.append(base / f"e{codigo}.DAT")
        # tambien en subcarpeta A3ECO si la base es la raiz A3
        out.append(base / "A3ECO" / f"E{codigo}.DAT")
    return out


def _candidate_dirs(codigo: str) -> list[Path]:
    out = []
    for base in _get_a3_eco_bases():
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


def _find_latest_cu_path(codigo_norm: str) -> "Path | None":
    """
    Devuelve el fichero CU del último ejercicio abierto en A3.
    A3 genera un fichero por ejercicio: {codigo}{digit}CU.DAT.
    Se ordena por fecha de modificación (mtime) para obtener el más reciente.
    """
    for folder in _candidate_dirs(codigo_norm):
        if not folder.exists():
            continue
        candidates = list(folder.glob(f"{codigo_norm}?CU.DAT"))
        if not candidates:
            candidates = list(folder.glob(f"{codigo_norm}?CU.dat"))
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def _count_active_cu_records(cu_path: Path) -> int:
    try:
        data = cu_path.read_bytes()
    except OSError:
        return 0
    total = 0
    offset = _ISAM_HEADER
    while offset + _CU_REC_SIZE <= len(data):
        rec = data[offset: offset + _CU_REC_SIZE]
        if rec and rec[0] in _ISAM_ACTIVE:
            total += 1
        offset += _CU_REC_SIZE
    return total


def _find_best_cu_path(codigo_norm: str) -> "Path | None":
    candidates = []
    for folder in _candidate_dirs(codigo_norm):
        if not folder.exists():
            continue
        candidates.extend(folder.glob(f"{codigo_norm}?CU.DAT"))
        candidates.extend(folder.glob(f"{codigo_norm}?CU.dat"))
        candidates.extend(folder.glob(f"{codigo_norm}0CU.DAT"))
        candidates.extend(folder.glob(f"{codigo_norm}0CU.dat"))
    if not candidates:
        return None
    ranked = []
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(( _count_active_cu_records(path), path.stat().st_mtime, path))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2] if ranked else None


def _candidate_tecodir_paths() -> list[Path]:
    """Devuelve las rutas candidatas del fichero TECODIR.DAT (directorio central de empresas)."""
    out = []
    for base in _get_a3_eco_bases():
        out.append(base / "TECODIR.DAT")
        out.append(base / "tecodir.dat")
    return out


def _candidate_tecodir_gesw_paths() -> list[Path]:
    """Rutas candidatas de TECODIR.DAT del modulo A3GESW."""
    out = []
    for base in _get_a3_gesw_bases():
        out.append(base / "TECODIR.DAT")
        out.append(base / "tecodir.dat")
    return out


# ─── Constantes para lectura de TECODIR.DAT ──────────────────────────────────
# TECODIR.DAT es el directorio central de empresas de A3ECO.
# Registros de 516 bytes a partir del byte 128 de cabecera.
# Byte 0 del registro = 0x42 → activo.
_TECODIR_HEADER = 128
_TECODIR_REC_SIZE = 516
_TECODIR_ACTIVE = 0x42

# Offsets dentro del registro (0-indexado):
_TD_NOMBRE = slice(5, 45)         # Razón Social (40 bytes, cp850)
_TD_CIF = slice(49, 58)           # NIF/CIF (9 bytes, cp850)
_TD_PATH = slice(103, 140)        # Ruta A3ECO (p.ej. \A3\A3ECO\E00193\)
_TD_TIPO_VIA = slice(165, 170)    # Tipo de vía (CL, AV, PS…)
_TD_CALLE = slice(175, 195)       # Nombre de la calle (20 bytes)
_TD_NUMERO = slice(231, 238)      # Número de la vía (7 bytes)
_TD_CP_START = 257                # Código postal: 3 bytes little-endian
_TD_CIUDAD = slice(263, 278)      # Población (15 bytes)
_TD_PROVINCIA = slice(283, 298)   # Provincia (15 bytes)
_TD_TELEFONO = slice(337, 346)    # Teléfono 1 (9 bytes)
_TD_TELEFONO2 = slice(361, 370)   # Teléfono 2 (9 bytes)
_TD_EMAIL = slice(437, 477)       # Email (40 bytes)

_TIPO_VIA_EXPAND = {
    "CL": "C/", "C/": "C/", "AV": "Av.", "AVDA": "Avda.",
    "PS": "Paseo", "PZ": "Plaza", "PL": "Plaza", "TR": "Travesía",
    "RD": "Ronda", "BRR": "Barrio", "POL": "Pol.", "URB": "Urb.",
    "CR": "Ctra.", "CTRA": "Ctra.", "VIA": "Vía",
}


def _td_decode(rec: bytes, slc: slice) -> str:
    return rec[slc].decode(_A3_ENCODING, errors="replace").strip()


def _parse_tecodir(tecodir_path: Path, codigo_norm: str) -> dict:
    """
    Lee TECODIR.DAT y extrae los datos de la empresa con código E{codigo_norm}.
    Devuelve un dict con: nombre, cif, direccion, cp, poblacion, provincia,
    telefono, email. Devuelve {} si no se encuentra la empresa.
    """
    try:
        data = tecodir_path.read_bytes()
    except OSError:
        return {}

    target_path = f"E{codigo_norm}".upper()
    offset = _TECODIR_HEADER
    while offset + _TECODIR_REC_SIZE <= len(data):
        rec = data[offset: offset + _TECODIR_REC_SIZE]
        if rec[0] == _TECODIR_ACTIVE:
            path_raw = _td_decode(rec, _TD_PATH).upper()
            if target_path in path_raw:
                nombre = _td_decode(rec, _TD_NOMBRE)
                cif = _td_decode(rec, _TD_CIF)
                tipo_via_raw = _td_decode(rec, _TD_TIPO_VIA)
                tipo_via = _TIPO_VIA_EXPAND.get(tipo_via_raw, tipo_via_raw)
                calle = _td_decode(rec, _TD_CALLE).title()
                numero = _td_decode(rec, _TD_NUMERO)
                cp_bytes = rec[_TD_CP_START: _TD_CP_START + 3]
                cp_int = cp_bytes[0] + cp_bytes[1] * 256 + cp_bytes[2] * 65536
                cp = str(cp_int) if cp_int else ""
                ciudad = _td_decode(rec, _TD_CIUDAD).title()
                provincia = _td_decode(rec, _TD_PROVINCIA).title()
                tel1 = _td_decode(rec, _TD_TELEFONO)
                tel2 = _td_decode(rec, _TD_TELEFONO2)
                telefono = tel1 or tel2
                email = _td_decode(rec, _TD_EMAIL).lower()

                partes_dir = [p for p in (tipo_via, calle, numero) if p]
                direccion = " ".join(partes_dir)

                return {
                    "nombre": nombre,
                    "cif": cif,
                    "direccion": direccion,
                    "cp": cp,
                    "poblacion": ciudad,
                    "provincia": provincia,
                    "telefono": telefono,
                    "email": email,
                    "_tecodir_path": str(tecodir_path),
                }
        offset += _TECODIR_REC_SIZE
    return {}


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


def _extract_ban_labels(blocks: list[dict]) -> list[str]:
    """
    Extrae las etiquetas descriptivas de las cuentas bancarias de los bloques BAN.
    Estructura del bloque VAR (268 bytes):
      bytes  0-1  : cabecera "A\\x08"
      bytes  2-13 : tag (p.ej. "BAN001")
      bytes 14+   : datos binarios del banco (IBAN codificado propietariamente,
                    numero de cuenta CCC, subcuenta contable, etc.)
    Se busca el primer fragmento de texto imprimible de longitud razonable
    probando varios offsets candidatos dentro de los datos binarios.
    """
    # Offset 30 en bloques BAN contiene el byte de longitud del campo (0x4E=78).
    # El texto descriptivo real empieza en offset 31.
    _CANDIDATE_OFFSETS = (14, 16, 20, 24, 31, 30, 34, 40)
    labels = []
    for block in blocks:
        if not str(block.get("tag") or "").startswith("BAN"):
            continue
        raw = block.get("raw") or b""
        if len(raw) < 20:
            continue
        found = ""
        for off in _CANDIDATE_OFFSETS:
            if off >= len(raw):
                continue
            # Leer hasta 60 bytes desde el offset, limpiar nulos y no-imprimibles
            chunk = raw[off: off + 60]
            text = "".join(
                chr(b) if 32 <= b < 127 or b >= 160 else "\x00"
                for b in chunk
            )
            # Tomar el primer segmento antes del primer nulo
            segment = text.split("\x00")[0].strip()
            if len(segment) >= 4:
                found = segment
                break
        if found:
            labels.append(found)
    return labels


def dump_ban_blocks(var_path: Path) -> str:
    """
    Utilidad de diagnostico: vuelca los bloques BAN del fichero VAR.DAT en
    formato hexadecimal + texto para identificar el offset correcto del label.
    Uso: from services.import_a3_empresa import dump_ban_blocks; from pathlib import Path
         print(dump_ban_blocks(Path(r'Z:\\A3\\A3ECO\\E00193\\000193VAR.DAT')))
    """
    try:
        data = var_path.read_bytes()
    except OSError as exc:
        return f"Error leyendo {var_path}: {exc}"
    blocks = _read_var_blocks(var_path)
    ban_blocks = [b for b in blocks if str(b.get("tag") or "").startswith("BAN")]
    if not ban_blocks:
        return f"No se encontraron bloques BAN en {var_path}"
    lines = [f"Fichero: {var_path}  ({len(ban_blocks)} bloque(s) BAN)"]
    for block in ban_blocks:
        raw = block.get("raw") or b""
        tag = block.get("tag", "?")
        hex_all = " ".join(f"{b:02X}" for b in raw[:80])
        lines.append(f"\n[{tag}] hex[0:80]:\n  {hex_all}")
        for off in range(10, min(60, len(raw))):
            chunk = raw[off: off + 40]
            segment = "".join(chr(b) if 32 <= b < 127 or b >= 160 else "." for b in chunk)
            if any(c.isalpha() for c in segment[:10]):
                lines.append(f"  @{off}: {segment!r}")
    return "\n".join(lines)


def _build_bank_records_from_labels(labels: list[str]) -> list[dict]:
    out = []
    for idx, label in enumerate(labels or []):
        value = str(label or "").strip()
        if not value:
            continue
        out.append(
            {
                "descripcion": value,
                "iban": "",
                "subcuenta_contable": "",
                "origen": "a3",
                "principal": idx == 0,
            }
        )
    return out


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
    Devuelve lista de {'cuenta': '43000000', 'descripcion': 'CLIENTES NACIONALES'}.
    Layout: cabecera 128 bytes, registros de 260 bytes.
      bytes 5-8  número de cuenta (big-endian 4 bytes)
      bytes 9-38 descripción (30 chars cp850)
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
            num = int.from_bytes(code_bytes, "big")
            if num > 0:
                desc = _decode_field(rec[_CU_DESC_SLICE])
                if desc:
                    cuentas.append({"cuenta": str(num), "descripcion": desc})
        offset += _CU_REC_SIZE
    return cuentas


def _isam_rec_size_from_header(data: bytes) -> int:
    """
    Lee el tamaño maximo de registro del header ISAM (bytes 54-57, big-endian)
    y le suma 4 bytes de overhead ISAM que preceden a cada registro en el fichero.
    Devuelve 0 si el header no es legible.
    """
    if len(data) < 58:
        return 0
    max_len = int.from_bytes(data[54:58], "big")
    return (max_len + 4) if max_len > 0 else 0


def _candidate_asiento_paths(codigo_norm: str, ejercicio: int) -> list[Path]:
    """
    Localiza los ficheros de asientos {codigo}{ej_digit}{mes}A.DAT
    de un ejercicio dado. A3ECO genera un fichero por mes:
      1..9 = enero..septiembre, O=octubre, N=noviembre, D=diciembre, I=cierre.
    """
    ej_digit = str(ejercicio % 10)
    meses = list("123456789") + ["O", "N", "D", "I"]
    seen: set[str] = set()
    out: list[Path] = []
    for folder in _candidate_dirs(codigo_norm):
        for mes in meses:
            for variant in (mes.upper(), mes.lower()):
                path = folder / f"{codigo_norm}{ej_digit}{variant}A.DAT"
                key = str(path).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(path)
    return out


def dump_asiento_records(codigo: str, ejercicio: int, max_records: int = 3) -> str:
    """
    Utilidad de diagnostico: vuelca los primeros registros activos de los
    ficheros de asientos *A.DAT de A3ECO en formato hexadecimal + texto,
    anotando las posiciones de byte candidatas a contener campos de interes
    (concepto, numero de factura, numero de asiento, subcuenta, importe).

    Uso:
        from services.import_a3_empresa import dump_asiento_records
        print(dump_asiento_records('E00193', 2025))

    La salida permite identificar los offsets exactos necesarios para implementar
    la captura automatica del numero de asiento tras el enlace con A3ECO.
    """
    codigo_norm = _clean_code(codigo)
    ficheros_encontrados = 0
    out: list[str] = []

    for path in _candidate_asiento_paths(codigo_norm, ejercicio):
        if not path.exists():
            continue
        ficheros_encontrados += 1
        try:
            data = path.read_bytes()
        except OSError as exc:
            out.append(f"\nError leyendo {path}: {exc}")
            continue

        if len(data) <= _ISAM_HEADER:
            out.append(f"\n{path}: fichero vacio o solo cabecera ({len(data)} bytes)")
            continue

        rec_size = _isam_rec_size_from_header(data)
        if rec_size <= 4:
            out.append(
                f"\n{path}: tamaño de registro no determinado "
                f"(header[54:58]={data[54:58].hex()})"
            )
            continue

        max_len = rec_size - 4
        total_recs = (len(data) - _ISAM_HEADER) // rec_size
        active_count = sum(
            1 for i in range(total_recs)
            if len(data) >= _ISAM_HEADER + (i + 1) * rec_size
            and data[_ISAM_HEADER + i * rec_size] in _ISAM_ACTIVE
        )

        org  = data[39] if len(data) > 39 else "?"
        comp = data[41] if len(data) > 41 else "?"
        mode = data[48] if len(data) > 48 else "?"

        out.append(
            f"\n{'=' * 74}\n"
            f"Fichero   : {path}\n"
            f"Bytes     : {len(data)}  |  rec_size={rec_size} bytes "
            f"(max_len={max_len} + 4 overhead ISAM)\n"
            f"Registros : {total_recs} totales, {active_count} activos\n"
            f"Header    : organización={org}  comprimido={comp}  modo={mode}\n"
            f"{'=' * 74}"
        )

        count = 0
        offset = _ISAM_HEADER
        while offset + rec_size <= len(data) and count < max_records:
            rec = data[offset: offset + rec_size]
            marker = rec[0]
            if marker not in _ISAM_ACTIVE:
                offset += rec_size
                continue

            # ── Hex + texto del registro completo en bloques de 16 bytes ──────
            out.append(f"\n  Registro #{count + 1}  @  offset_fichero={offset}  marker=0x{marker:02X}")
            out.append(f"  {'byte':>5}  {'hex (16 bytes)':49}  texto")
            out.append(f"  {'─' * 5}  {'─' * 48}  {'─' * 20}")
            for row_start in range(0, min(rec_size, 256), 16):
                chunk = rec[row_start: row_start + 16]
                hex_col = " ".join(f"{b:02X}" for b in chunk).ljust(47)
                txt_col = "".join(
                    chr(b) if 32 <= b < 127 else ("·" if b == 0 else "?")
                    for b in chunk
                )
                out.append(f"  {row_start:>5}  {hex_col}  {txt_col}")

            # ── Campos de texto candidatos ────────────────────────────────────
            # Busca secuencias de caracteres imprimibles cp850 de longitud >= 4
            # para ayudar a identificar visualmente los campos.
            out.append(f"\n  Campos de texto detectados (byte_inicio → contenido):")
            i = 0
            while i < min(rec_size, 256):
                b = rec[i]
                # cp850: 0x20-0x7E + 0x80-0xFF (Latin extendido)
                if (0x20 <= b <= 0x7E) or (0x80 <= b <= 0xFF):
                    j = i
                    while j < min(rec_size, 256) and ((0x20 <= rec[j] <= 0x7E) or (0x80 <= rec[j] <= 0xFF)):
                        j += 1
                    if j - i >= 4:
                        try:
                            fragment = rec[i:j].decode(_A3_ENCODING, errors="replace").strip()
                        except Exception:
                            fragment = rec[i:j].decode("latin-1", errors="replace").strip()
                        if fragment:
                            out.append(f"    byte {i:3d}-{j - 1:3d} (len={j - i:3d}): {fragment!r}")
                    i = j
                else:
                    i += 1

            # ── Interpretación de posibles enteros ───────────────────────────
            out.append(f"\n  Enteros candidatos a numero de asiento / subcuenta:")
            for start_b in range(0, min(rec_size, 230), 1):
                for nbytes in (2, 3, 4):
                    if start_b + nbytes > rec_size:
                        break
                    val = int.from_bytes(rec[start_b: start_b + nbytes], "big")
                    if 1 <= val <= 999999:
                        out.append(
                            f"    byte {start_b:3d} len={nbytes}: {val:>8d}  "
                            f"(hex {rec[start_b:start_b + nbytes].hex()})"
                        )

            count += 1
            offset += rec_size

        if count == 0:
            out.append("  (no se encontraron registros activos en este fichero)")

    if not ficheros_encontrados:
        rutas = "\n".join(
            f"  {p}" for p in _candidate_asiento_paths(codigo_norm, ejercicio)
        )
        return (
            f"No se encontraron ficheros de asientos para empresa {codigo_norm}, "
            f"ejercicio {ejercicio}.\n"
            f"Rutas buscadas:\n{rutas}"
        )

    return "\n".join(out)


# ── Offsets confirmados por diagnóstico sobre 0042361A.DAT (enero 2026) ───────
_AS_CONCEPTO = slice(15, 45)   # 30 chars cp850 — descripción del apunte
_AS_NUM_FRA  = slice(45, 55)   # 10 chars cp850 — número de factura (campo búsqueda)
_AS_APUNTE   = slice(110, 112) # 2 bytes big-endian — número de asiento ← clave


def leer_numero_asiento_desde_a3(
    codigo: str,
    ejercicio: int,
    num_factura: str,
    descripcion: str = "",
) -> str | None:
    """
    Busca el número de asiento en los ficheros *A.DAT de A3ECO tras procesar
    el suenlace.

    Parámetros
    ----------
    codigo      : Código de empresa tal como aparece en TECODIR (ej. 'E00423').
    ejercicio   : Año del ejercicio (ej. 2026).
    num_factura : Número de factura escrito en el suenlace (máx. 10 chars).
                  Se busca en el campo num_fra de cada registro (bytes 45-54).
    descripcion : Cadena alternativa que se busca en el campo concepto (bytes
                  15-44) si num_factura no produce coincidencia exacta.
                  Se comparan los primeros 10 caracteres.

    Retorna
    -------
    El número de asiento como cadena (ej. '15') o None si no se encuentra.
    El número de asiento es el mismo para todos los apuntes de un mismo asiento,
    por lo que se devuelve el primero que coincida con cualquier apunte del
    asiento buscado.
    """
    codigo_norm = _clean_code(codigo)
    num_fra_limpio = str(num_factura or "").strip()[:10]
    desc_prefix = str(descripcion or "").strip()[:10]

    for path in _candidate_asiento_paths(codigo_norm, ejercicio):
        if not path.exists():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue

        rec_size = _isam_rec_size_from_header(data) or 132
        offset = _ISAM_HEADER

        while offset + rec_size <= len(data):
            rec = data[offset: offset + rec_size]
            if rec[0] in _ISAM_ACTIVE:
                num_fra_rec = rec[_AS_NUM_FRA].decode(_A3_ENCODING, errors="replace").strip()
                match_num_fra = num_fra_limpio and num_fra_rec == num_fra_limpio
                match_concepto = False
                if not match_num_fra and desc_prefix:
                    concepto_rec = rec[_AS_CONCEPTO].decode(_A3_ENCODING, errors="replace").strip()
                    match_concepto = desc_prefix in concepto_rec
                if match_num_fra or match_concepto:
                    apunte = int.from_bytes(rec[_AS_APUNTE], "big")
                    if apunte > 0:
                        return str(apunte)
            offset += rec_size

    return None


def dump_cu_records(cu_path: Path, max_records: int = 20) -> str:
    """
    Utilidad de diagnostico: vuelca los primeros registros activos del fichero
    CU.DAT en formato hexadecimal + texto para verificar el layout real.
    Uso: from services.import_a3_empresa import dump_cu_records; from pathlib import Path
         print(dump_cu_records(Path(r'Z:\\A3\\A3ECO\\E00193\\000193?CU.DAT')))
    """
    try:
        data = cu_path.read_bytes()
    except OSError as exc:
        return f"Error leyendo {cu_path}: {exc}"
    lines = [f"Fichero: {cu_path}  ({len(data)} bytes, {(len(data) - _ISAM_HEADER) // _CU_REC_SIZE} registros aprox.)"]
    offset = _ISAM_HEADER
    count = 0
    while offset + _CU_REC_SIZE <= len(data) and count < max_records:
        rec = data[offset: offset + _CU_REC_SIZE]
        marker = rec[0]
        is_active = marker in _ISAM_ACTIVE
        hex_head = " ".join(f"{b:02X}" for b in rec[:40])
        code3 = int.from_bytes(rec[5:8], "big")
        desc8 = rec[8:38].decode(_A3_ENCODING, errors="replace").strip()
        lines.append(
            f"[{offset}] {'ACTIVO' if is_active else 'borrado'} "
            f"marker=0x{marker:02X}  hex[0:40]={hex_head}\n"
            f"    code={code3}  desc={desc8!r}"
        )
        if is_active:
            count += 1
        offset += _CU_REC_SIZE
    return "\n".join(lines)


_SUFIJOS_ENTIDAD_SVC = re.compile(
    r"\b(S\.?L\.?U?\.?|S\.?A\.?U?\.?|S\.?C\.?|C\.?B\.?|S\.?L\.?P\.?|S\.?R\.?L\.?|"
    r"SL|SA|SLU|SAU|SC|CB|SLP|SRL)\b",
    re.IGNORECASE,
)
_PALABRAS_ENTIDAD_SVC = re.compile(
    r"\b(ASESORIA|ASESORES|GESTORIA|CONSULTORIA|CONTABILIDAD|EMPRESA|GRUPO|SERVICIOS|"
    r"SOLUCIONES|SOCIEDAD|COMUNIDAD|INVERSIONES|INMOBILIARIA|CONSTRUCCIONES|TRANSPORTES|"
    r"DISTRIBUCIONES|COMERCIAL|INDUSTRIAL|TECNOLOGIAS|INFORMATICA)\b",
    re.IGNORECASE,
)

# Descripciones estándar del PGC (Plan General Contable) por prefijo de cuenta.
# Se usan para corregir descripciones que A3ECO rellena con la razón social
# de la empresa (comportamiento habitual en cuentas de capital y reservas).
_PGC_DESCRIPCIONES: list[tuple[str, str]] = [
    # Grupo 1 - Financiación básica
    ("10000", "Capital"),
    ("1000",  "Capital"),
    ("100",   "Capital"),
    ("1010",  "Capital social pendiente de inscripcion"),
    ("101",   "Capital social pendiente de inscripcion"),
    ("1020",  "Capital"),
    ("102",   "Capital"),
    ("1030",  "Socios por desembolsos no exigidos"),
    ("103",   "Socios por desembolsos no exigidos"),
    ("1040",  "Socios por aportaciones no dinerarias pendientes"),
    ("104",   "Socios por aportaciones no dinerarias pendientes"),
    ("110",   "Prima de emision o asuncion"),
    ("111",   "Otros instrumentos de patrimonio neto"),
    ("112",   "Constitucion"),
    ("113",   "Reservas voluntarias"),
    ("114",   "Reservas especiales"),
    ("115",   "Reservas por perdidas y ganancias actuariales"),
    ("116",   "Reservas para acciones o participaciones de la sociedad dominante"),
    ("117",   "Reservas por acciones propias aceptadas en garantia"),
    ("118",   "Aportaciones de socios o propietarios"),
    ("119",   "Diferencias por ajuste del capital a euros"),
    ("120",   "Remanente"),
    ("121",   "Resultados negativos de ejercicios anteriores"),
    ("129",   "Resultado del ejercicio"),
    ("130",   "Subvenciones oficiales de capital"),
    ("131",   "Donaciones y legados de capital"),
    ("132",   "Otras subvenciones"),
    ("133",   "Ajustes por valoracion en activos financieros disponibles para la venta"),
    ("134",   "Operaciones de cobertura"),
    ("135",   "Ajustes por valoracion en activos no corrientes en venta"),
    ("136",   "Diferencia de conversion"),
    ("137",   "Ingresos fiscales a distribuir en varios ejercicios"),
]

def _parece_nombre_entidad_svc(descripcion: str) -> bool:
    """Devuelve True si la descripcion parece una razon social en lugar de un concepto contable."""
    d = (descripcion or "").strip()
    if not d:
        return False
    if _SUFIJOS_ENTIDAD_SVC.search(d):
        return True
    if _PALABRAS_ENTIDAD_SVC.search(d):
        return True
    return False


def _corregir_descripcion_pgc(cuenta: str, descripcion: str) -> str:
    """
    Si la descripcion de una cuenta parece una razon social (A3ECO la rellena
    con el nombre de la empresa en cuentas de capital y reservas), la sustituye
    por la descripcion estandar del PGC correspondiente al prefijo de la cuenta.

    Solo actua cuando la descripcion es sospechosa Y existe un mapeo PGC conocido.
    """
    if not _parece_nombre_entidad_svc(descripcion):
        return descripcion
    codigo = str(cuenta or "").strip()
    # Buscar el prefijo mas largo que coincida
    for prefijo, desc_pgc in _PGC_DESCRIPCIONES:
        if codigo.startswith(prefijo):
            return desc_pgc
    return descripcion


def _deducir_digitos_plan(plan_cuentas: list[dict]) -> int:
    lengths = [len(str(item.get("cuenta") or "").strip()) for item in (plan_cuentas or []) if str(item.get("cuenta") or "").strip()]
    if not lengths:
        return 8
    max_len = max(lengths)
    if max_len < 4:
        return 8
    return max_len


def _filtrar_plan_cuentas_por_digitos(plan_cuentas: list[dict], ndig: int) -> list[dict]:
    """Conserva cuentas hoja y las normaliza al nivel exacto del plan.

    El fichero CU de A3 no siempre guarda las subcuentas con todos los digitos
    del plan. Es habitual encontrar niveles compactos como `4300`, `140000`
    o `1000000`. Para Gest2A3Eco interesan las cuentas hoja del plan y deben
    verse al ancho exacto del plan de la empresa.

    Regla aplicada:
    - se eliminan cuentas vacias/no numericas;
    - se descartan cuentas padre si existe otra mas larga que empiece por ellas;
    - las cuentas hoja resultantes se rellenan con ceros a la derecha hasta
      `ndig`;
    - si alguna excede `ndig`, se ignora por seguridad.
    """
    if ndig <= 0:
        return []

    cleaned: list[dict] = []
    for item in plan_cuentas or []:
        cuenta = "".join(ch for ch in str(item.get("cuenta") or "").strip() if ch.isdigit())
        if not cuenta:
            continue
        cleaned.append({
            "cuenta": cuenta,
            "descripcion": str(item.get("descripcion") or "").strip(),
        })

    raw_codes = sorted({item["cuenta"] for item in cleaned}, key=lambda x: (len(x), x))
    leaf_codes = {
        code for code in raw_codes
        if not any(other != code and other.startswith(code) for other in raw_codes)
    }

    out: list[dict] = []
    seen: set[str] = set()
    for item in cleaned:
        cuenta = item["cuenta"]
        if cuenta not in leaf_codes:
            continue
        if len(cuenta) > ndig:
            continue
        cuenta_norm = cuenta.ljust(ndig, "0")
        if cuenta_norm in seen:
            continue
        seen.add(cuenta_norm)
        desc_corregida = _corregir_descripcion_pgc(cuenta_norm, item["descripcion"])
        out.append({
            "cuenta": cuenta_norm,
            "descripcion": desc_corregida,
        })
    out.sort(key=lambda x: (int(x["cuenta"]), x["cuenta"]))
    return out


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

    # Etiquetas bancarias detectadas (texto legible de los bloques BAN).
    # Nota: los IBANs en A3ECO están en formato binario propietario; solo
    # se puede extraer la etiqueta descriptiva (p.ej. "Urbana 7140").
    ban_labels = _extract_ban_labels(blocks)

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
        "_ban_labels": ban_labels,
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


def listar_empresas_a3() -> list[dict]:
    """
    Devuelve la lista de todas las empresas registradas en A3ECO (TECODIR.DAT).
    Cada entrada: {'codigo': 'E00193', 'nombre': ..., 'cif': ..., ...}
    Util para mostrar un desplegable de seleccion en la UI.
    """
    tecodir_path = next((p for p in _candidate_tecodir_paths() if p.exists()), None)
    if not tecodir_path:
        return []
    try:
        data = tecodir_path.read_bytes()
    except OSError:
        return []
    empresas = []
    offset = _TECODIR_HEADER
    while offset + _TECODIR_REC_SIZE <= len(data):
        rec = data[offset: offset + _TECODIR_REC_SIZE]
        if rec[0] == _TECODIR_ACTIVE:
            path_raw = _td_decode(rec, _TD_PATH).upper()
            # Extraer codigo de empresa del path (p.ej. \A3\A3ECO\E00193\ → E00193)
            m = re.search(r"E(\d{5})", path_raw)
            if m:
                codigo_norm = m.group(1)
                nombre = _td_decode(rec, _TD_NOMBRE)
                cif = _td_decode(rec, _TD_CIF)
                empresas.append({"codigo": f"E{codigo_norm}", "nombre": nombre, "cif": cif})
        offset += _TECODIR_REC_SIZE
    return empresas


def importar_empresa_desde_a3(codigo: str, digitos_plan_objetivo: int | None = None) -> dict:
    codigo_norm = _clean_code(codigo)
    codigo_a3 = f"E{codigo_norm}"

    # 1. Directorio central de empresas (TECODIR.DAT): fuente más fiable
    tecodir_path = next((p for p in _candidate_tecodir_paths() if p.exists()), None)
    tecodir_data = _parse_tecodir(tecodir_path, codigo_norm) if tecodir_path else {}

    # 1b. Comprobar si la empresa tambien existe en A3GESW (para informes cruzados)
    tecodir_gesw_path = next((p for p in _candidate_tecodir_gesw_paths() if p.exists()), None)
    en_gesw = False
    if tecodir_gesw_path:
        try:
            gesw_data = tecodir_gesw_path.read_bytes()
            gesw_offset = _TECODIR_HEADER
            while gesw_offset + _TECODIR_REC_SIZE <= len(gesw_data):
                rec = gesw_data[gesw_offset: gesw_offset + _TECODIR_REC_SIZE]
                if rec[0] == _TECODIR_ACTIVE:
                    path_raw = _td_decode(rec, _TD_PATH).upper()
                    if f"E{codigo_norm}" in path_raw:
                        en_gesw = True
                        break
                gesw_offset += _TECODIR_REC_SIZE
        except Exception:
            pass

    # 2. Ficheros binarios por empresa: CU (plan de cuentas) y datos de respaldo
    company_dirs = [path for path in _candidate_dirs(codigo_norm) if path.exists()]
    # Priorizamos el CU del ultimo ejercicio abierto/modificado en A3.
    cu_path = _find_latest_cu_path(codigo_norm) or _find_best_cu_path(codigo_norm)
    var_path = next((path for path in _candidate_var_paths(codigo_norm) if path.exists()), None)
    em_path = next((path for path in _candidate_em_paths(codigo_norm) if path.exists()), None)
    dashboard_path = next((path for path in _candidate_dashboard_paths(codigo_norm) if path.exists()), None)
    data_path = next((path for path in _candidate_paths(codigo_norm) if path.exists()), None)

    # Verificar que al menos hay algún origen de datos
    if (
        not tecodir_data
        and em_path is None
        and data_path is None
        and not company_dirs
        and var_path is None
        and dashboard_path is None
    ):
        raise ValueError(f"No se ha encontrado la empresa {codigo_a3} en A3.")

    # 3. Plan de cuentas desde fichero CU binario
    plan_cuentas_raw = _leer_plan_cuentas_binario(cu_path) if cu_path else []
    digitos_detectados = _deducir_digitos_plan(plan_cuentas_raw)
    digitos_plan = int(digitos_plan_objetivo or digitos_detectados or 8)
    plan_cuentas = _filtrar_plan_cuentas_por_digitos(plan_cuentas_raw, digitos_plan)

    # 4. Fuentes de respaldo: VAR y cabecera de la ficha DAT
    text = _read_header_text(data_path) if data_path else ""
    raw_preview = " ".join(text.split())
    var_data: dict = {}
    if var_path:
        try:
            var_data = _parse_var_company_data(var_path)
        except Exception:
            var_data = {}
    dashboard_data: dict = {}
    if dashboard_path:
        dashboard_data = _parse_dashboard_company_data(dashboard_path, codigo_norm)

    # 5. Prioridad de datos: TECODIR > dashboard > VAR/EM > texto cabecera
    nombre = str(
        tecodir_data.get("nombre")
        or dashboard_data.get("nombre")
        or var_data.get("nombre")
        or _extract_name(text)
        or ""
    )
    cif = str(
        tecodir_data.get("cif")
        or var_data.get("cif")
        or _extract_cif(text)
        or ""
    )
    direccion = str(tecodir_data.get("direccion") or var_data.get("direccion") or "")
    cp = str(tecodir_data.get("cp") or var_data.get("cp") or "")
    poblacion = str(tecodir_data.get("poblacion") or var_data.get("poblacion") or "")
    provincia = str(tecodir_data.get("provincia") or var_data.get("provincia") or "")
    telefono = str(tecodir_data.get("telefono") or var_data.get("telefono") or "")
    email = str(tecodir_data.get("email") or var_data.get("email") or "")
    ejercicio = (
        _to_int(dashboard_data.get("ejercicio"))
        or _extract_year(text, company_dirs)
        or date.today().year
    )

    # 6. Construir el texto de detalle para la UI
    detalle = []
    if tecodir_data:
        detalle.append(f"Directorio A3 (TECODIR): {tecodir_data.get('_tecodir_path', tecodir_path)}")
    if dashboard_path:
        detalle.append(f"Cuadro de mando A3: {dashboard_path}")
    if cu_path:
        detalle.append(
            f"Plan de cuentas CU ({len(plan_cuentas)} subcuentas de {digitos_plan} digitos"
            f" de {len(plan_cuentas_raw)} cuentas leidas): {cu_path}"
        )
    if var_path:
        detalle.append(f"Ficha empresa VAR: {var_path}")
    if em_path:
        detalle.append(f"Fichero EM: {em_path}")
    if data_path:
        detalle.append(f"Ficha A3: {data_path}")
    if company_dirs:
        detalle.append(f"Carpeta A3ECO: {company_dirs[0]}")
    detalle.append(f"Ejercicio detectado: {ejercicio}")
    if var_data.get("web"):
        detalle.append(f"Web: {var_data.get('web')}")

    ban_labels = var_data.get("_ban_labels") or []
    bank_records = _build_bank_records_from_labels(ban_labels)
    if ban_labels:
        detalle.append(f"Cuentas bancarias detectadas en A3 (sin IBAN): {', '.join(ban_labels)}")
        detalle.append("  → El IBAN/CCC en A3 esta en formato binario propietario. Introducelo manualmente en la pestana Bancos.")
    if en_gesw:
        detalle.append("Empresa presente en A3GESW (disponible para informes de gestion).")

    raw_header = str(var_data.get("_a3_raw_header") or raw_preview[:1200])

    return {
        "codigo": codigo_a3,
        "nombre": nombre,
        "digitos_plan": digitos_plan,
        "ejercicio": ejercicio,
        "serie_emitidas": "A",
        "siguiente_num_emitidas": 1,
        "serie_emitidas_rect": "R",
        "siguiente_num_emitidas_rect": 1,
        "cuenta_bancaria": str(ban_labels[0]) if ban_labels else "",
        "cuentas_bancarias": "\n".join(str(x) for x in ban_labels if str(x).strip()),
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
        "bank_records": bank_records,
        "_ban_labels": ban_labels,
        "_en_gesw": en_gesw,
        "_a3_info": "\n".join(detalle),
        "_a3_raw_header": raw_header,
    }
