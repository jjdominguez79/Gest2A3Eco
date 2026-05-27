
import json
import math
import os
import sqlite3
import sys
import traceback
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

SEP = "\t"
APP_VENDOR = "Gestinem"
APP_NAME = "Gest2A3Eco"

DEFAULT_MONEDAS = [
    {"codigo": "EUR", "simbolo": "€", "nombre": "Euro"},
    {"codigo": "USD", "simbolo": "$", "nombre": "Dolar"},
]

def _base_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def get_install_dir() -> Path:
    return _base_dir()


def get_app_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        path = root / APP_VENDOR / APP_NAME
    else:
        path = _base_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    path = get_app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path(filename: str = "app.log") -> Path:
    return get_logs_dir() / filename


def get_user_config_path() -> Path:
    return get_app_data_dir() / "config.local.json"


def get_user_preferences_path() -> Path:
    return get_app_data_dir() / "user.config.json"


def get_default_templates_dir() -> Path:
    path = get_app_data_dir() / "plantillas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_output_dir() -> Path:
    path = get_app_data_dir() / "pdfs_emitidas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_db_path() -> Path:
    return get_app_data_dir() / "gest2a3eco.db"


def get_packaged_templates_dir() -> Path:
    return get_install_dir() / "plantillas"


def get_packaged_email_template_path() -> Path | None:
    path = get_packaged_templates_dir() / "email_factura.html"
    return path if path.exists() else None


def get_seed_json_path() -> Path | None:
    path = get_packaged_templates_dir() / "plantillas.json"
    return path if path.exists() else None


def _config_example_path() -> Path:
    return _base_dir() / "config.example.json"


def _legacy_config_path() -> Path:
    return _base_dir() / "config.json"


def _legacy_local_config_path() -> Path:
    return _base_dir() / "config.local.json"


def _config_local_path() -> Path:
    return get_user_config_path()


def _load_json_file(path: Path) -> dict:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _merge_dicts(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dicts(out[key], value)
        else:
            out[key] = value
    return out


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _ensure_local_config_migrated() -> None:
    cfg_path = get_user_config_path()
    if cfg_path.exists():
        return
    legacy_data = {}
    for path in (_legacy_config_path(), _legacy_local_config_path()):
        legacy_data = _merge_dicts(legacy_data, _load_json_file(path))
    if legacy_data:
        _write_json_file(cfg_path, legacy_data)


def _apply_env_overrides(data: dict) -> dict:
    out = dict(data)

    direct_map = {
        "GEST2A3ECO_A3_BASE_PATH": "a3_base_path",
        "GEST2A3ECO_LAST_DB_PATH": "last_db_path",
        "GEST2A3ECO_WORD_TEMPLATES_DIR": "word_templates_dir",
        "GEST2A3ECO_OCR_ENDPOINT": "ocr_endpoint",
        "GEST2A3ECO_ADMIN_PASSWORD": "admin_password",
        "GEST2A3ECO_INITIAL_ADMIN_PASSWORD": "initial_admin_password",
        "GEST2A3ECO_DESMARCAR_GENERADAS_PASSWORD": "desmarcar_generadas_password",
    }
    for env_name, config_key in direct_map.items():
        value = os.getenv(env_name)
        if value is not None:
            out[config_key] = value

    smtp_cfg = dict(out.get("smtp") or {})
    smtp_map = {
        "GEST2A3ECO_SMTP_HOST": "host",
        "GEST2A3ECO_SMTP_PORT": "port",
        "GEST2A3ECO_SMTP_USER": "user",
        "GEST2A3ECO_SMTP_PASSWORD": "password",
        "GEST2A3ECO_SMTP_FROM_ADDR": "from_addr",
        "GEST2A3ECO_SMTP_USE_TLS": "use_tls",
        "GEST2A3ECO_SMTP_USE_SSL": "use_ssl",
    }
    for env_name, config_key in smtp_map.items():
        value = os.getenv(env_name)
        if value is None:
            continue
        if config_key == "port":
            try:
                smtp_cfg[config_key] = int(value)
            except Exception:
                continue
        elif config_key in {"use_tls", "use_ssl"}:
            smtp_cfg[config_key] = str(value).strip().lower() in {"1", "true", "yes", "si"}
        else:
            smtp_cfg[config_key] = value
    if smtp_cfg:
        out["smtp"] = smtp_cfg

    return out


def _normalize_config(data: dict) -> dict:
    out = dict(data or {})
    out.setdefault("templates_path", "")
    out.setdefault("word_templates_dir", "")
    out.setdefault("a3_base_path", "")
    out.setdefault("db_path", "")
    out.setdefault("last_db_path", "")
    out.setdefault("ocr_endpoint", "")
    out.setdefault("documentos_output_dir", "")

    if not str(out.get("db_path") or "").strip():
        out["db_path"] = str(out.get("last_db_path") or "").strip()
    if not str(out.get("last_db_path") or "").strip():
        out["last_db_path"] = str(out.get("db_path") or "").strip()
    if not str(out.get("documentos_output_dir") or "").strip():
        out["documentos_output_dir"] = str(get_default_output_dir())

    smtp = out.get("smtp")
    if not isinstance(smtp, dict):
        smtp = {}
    smtp.setdefault("host", "")
    smtp.setdefault("port", 587)
    smtp.setdefault("user", "")
    smtp.setdefault("password", "")
    smtp.setdefault("from_addr", "")
    smtp.setdefault("use_tls", True)
    smtp.setdefault("use_ssl", False)
    out["smtp"] = smtp

    monedas = out.get("monedas")
    if not isinstance(monedas, list) or not monedas:
        out["monedas"] = list(DEFAULT_MONEDAS)
    else:
        norm = []
        for m in monedas:
            if not isinstance(m, dict):
                continue
            codigo = str(m.get("codigo") or "").strip().upper()
            simbolo = str(m.get("simbolo") or "").strip()
            nombre = str(m.get("nombre") or "").strip()
            if not codigo:
                continue
            norm.append({"codigo": codigo, "simbolo": simbolo, "nombre": nombre})
        out["monedas"] = norm or list(DEFAULT_MONEDAS)
    return out


def _normalize_user_config(data: dict) -> dict:
    out = dict(data or {})
    out.setdefault("email_mode", "outlook")
    out.setdefault("default_cc", "")
    out.setdefault("default_bcc", "")
    out.setdefault("email_signature", "")
    out.setdefault("open_outlook_before_send", True)
    return out


def load_app_config() -> dict:
    _ensure_local_config_migrated()
    data = {}
    for path in (_config_example_path(), _legacy_config_path(), _config_local_path()):
        data = _merge_dicts(data, _load_json_file(path))
    data = _apply_env_overrides(data)
    return _normalize_config(data)


def load_user_config() -> dict:
    cfg_path = get_user_preferences_path()
    data = _normalize_user_config(_load_json_file(cfg_path))
    if not cfg_path.exists():
        save_user_config(data)
    return data

def get_word_templates_dir(default_dir: str | None = None) -> str:
    cfg = load_app_config()
    raw = str(cfg.get("word_templates_dir") or "").strip()
    if raw:
        path = Path(raw)
        if path.exists() and path.is_dir():
            return str(path)
    fallback = Path(default_dir) if default_dir else get_default_templates_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)

def set_word_templates_dir(path: str) -> None:
    cfg = load_app_config()
    cfg["word_templates_dir"] = path
    save_app_config(cfg)


def get_configured_db_path() -> str:
    cfg = load_app_config()
    raw = str(cfg.get("db_path") or cfg.get("last_db_path") or "").strip()
    return raw or str(get_default_db_path())


def set_configured_db_path(path: str) -> None:
    cfg = load_app_config()
    cfg["db_path"] = path
    cfg["last_db_path"] = path
    save_app_config(cfg)


def validate_sqlite_db_path(path: str, *, allow_create: bool = True) -> str:
    raw = str(path or "").strip().strip('"')
    if not raw:
        raise ValueError("Debes indicar una ruta para la base de datos SQLite.")

    db_path = Path(raw).expanduser()
    parent = db_path.parent
    if not str(parent):
        raise ValueError(f"Ruta de base de datos no válida: {raw}")
    if not parent.exists():
        if allow_create:
            raise FileNotFoundError(f"No existe la carpeta de la base de datos:\n{parent}")
        raise FileNotFoundError(f"No existe la base de datos:\n{db_path}")
    if not parent.is_dir():
        raise NotADirectoryError(f"La carpeta de la base de datos no es válida:\n{parent}")
    if db_path.exists() and db_path.is_dir():
        raise IsADirectoryError(f"La ruta seleccionada es una carpeta, no un fichero SQLite:\n{db_path}")
    if not db_path.exists() and not allow_create:
        raise FileNotFoundError(f"No existe la base de datos seleccionada:\n{db_path}")

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS __gest2a3eco_access_check__ (id INTEGER PRIMARY KEY)")
        conn.execute("DROP TABLE IF EXISTS __gest2a3eco_access_check__")
        conn.commit()
    except Exception as exc:
        raise PermissionError(
            f"No se puede abrir la base de datos con permisos de lectura y escritura:\n{db_path}\n\nDetalle: {exc}"
        ) from exc
    finally:
        if conn is not None:
            conn.close()
    return str(db_path)


def save_app_config(data: dict) -> None:
    cfg_path = _config_local_path()
    current = _load_json_file(cfg_path)
    payload = _normalize_config(_merge_dicts(current, dict(data or {})))
    _write_json_file(cfg_path, payload)


def save_user_config(data: dict) -> None:
    cfg_path = get_user_preferences_path()
    current = _load_json_file(cfg_path)
    payload = _normalize_user_config(_merge_dicts(current, dict(data or {})))
    _write_json_file(cfg_path, payload)


def log_exception(message: str, exc: Exception | None = None, *, log_name: str = "app.log", extra: dict | None = None) -> None:
    try:
        path = get_log_path(log_name)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n---- ERROR ----\n")
            f.write(f"Message: {message}\n")
            if extra:
                for key, value in extra.items():
                    f.write(f"{key}: {value}\n")
            if exc is not None:
                f.write("Exception:\n")
                f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass

def load_monedas() -> list:
    return load_app_config().get("monedas") or list(DEFAULT_MONEDAS)

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

def format_num_es(x, dec: int = 2, empty_if_none: bool = False) -> str:
    """
    Formatea numeros con miles en punto y decimales en coma.
    """
    if x is None and empty_if_none:
        return ""
    try:
        s = f"{float(x):,.{dec}f}"
    except Exception:
        if empty_if_none:
            return ""
        s = f"{0.0:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

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
        if str(ln.get("tipo") or "").strip().lower() == "obs":
            continue
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
        if str(ln.get("tipo") or "").strip().lower() == "obs":
            out.append(dict(ln))
            continue
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
