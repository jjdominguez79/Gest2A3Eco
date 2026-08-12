
import json
import math
import os
import sys
import traceback
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

SEP = "\t"
APP_VENDOR = "Gestinem"
APP_NAME = "Gest2A3Eco"

WORD_TEMPLATE_SUBDIRS = {
    "facturas": "facturas",
    "albaranes": "albaranes",
    "firmas": "firmas",
    "tramites_dgt": "tramites_dgt",
}

DEFAULT_MONEDAS = [
    {"codigo": "EUR", "simbolo": "€", "nombre": "Euro"},
    {"codigo": "USD", "simbolo": "$", "nombre": "Dolar"},
]

def _base_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def get_install_dir() -> Path:
    return _base_dir()


def get_packaged_resource_path(relative_path: str | Path) -> Path:
    """Devuelve la ruta real de un recurso incluido por PyInstaller.

    En una distribucion ``onedir`` el ejecutable queda en la carpeta principal,
    pero los ``datas`` se alojan bajo ``sys._MEIPASS`` (normalmente
    ``_internal``). En desarrollo, los recursos siguen resolviendose desde la
    raiz del proyecto.
    """
    packaged_dir = Path(
        getattr(sys, "_MEIPASS", _base_dir())
        if getattr(sys, "frozen", False)
        else _base_dir()
    )
    return packaged_dir / Path(relative_path)


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
    path = get_document_repository_dir() / "Empresas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_received_documents_dir() -> Path:
    """Raiz compartida de documentos de empresa que pasan por captura/OCR."""
    path = get_document_repository_dir() / "Empresas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_document_repository_dir() -> Path:
    """Repositorio documental definitivo, comun para todos los puestos."""
    path = Path(
        os.getenv("GEST2A3ECO_DOCUMENT_REPOSITORY_DIR")
        or r"\\GestinemMain\Doc_Compartidos\Gest2A3Eco"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        "GEST2A3ECO_POSTGRES_DSN": "postgres_dsn",
        "GEST2A3ECO_WORD_TEMPLATES_DIR": "word_templates_dir",
        "GEST2A3ECO_OCR_MOTOR_ACTIVO": "ocr_motor_activo",
        "GEST2A3ECO_AZURE_DOC_INTELLIGENCE_ENDPOINT": "azure_doc_intelligence_endpoint",
        "GEST2A3ECO_AZURE_DOC_INTELLIGENCE_KEY": "azure_doc_intelligence_key",
        "GEST2A3ECO_DGT_API_URL": "dgt_api_url",
        "GEST2A3ECO_DGT_API_KEY": "dgt_api_key",
        "GEST2A3ECO_INTEGRATIONS_API_URL": "integrations_api_url",
        "GEST2A3ECO_INTEGRATIONS_API_KEY": "integrations_api_key",
        "GEST2A3ECO_MESSAGING_API_URL": "messaging_api_url",
        "GEST2A3ECO_MESSAGING_API_KEY": "messaging_api_key",
        "GEST2A3ECO_MESSAGING_WORKSTATION_ID": "messaging_workstation_id",
        "GEST2A3ECO_MESSAGING_DEVICE_TOKEN": "messaging_device_token",
        "GEST2A3ECO_FIRMA_HABILITADA": "firma_habilitada",
        "GEST2A3ECO_FIRMA_CATEGORIA_FIRMADOS": "firma_categoria_firmados",
        "GEST2A3ECO_FIRMA_MAX_MB": "firma_max_mb",
        "GEST2A3ECO_FIRMA_WEBHOOK_SECRET": "firma_webhook_secret",
        "GEST2A3ECO_ADMIN_PASSWORD": "admin_password",
        "GEST2A3ECO_INITIAL_ADMIN_PASSWORD": "initial_admin_password",
        "GEST2A3ECO_DESMARCAR_GENERADAS_PASSWORD": "desmarcar_generadas_password",
    }
    for env_name, config_key in direct_map.items():
        value = os.getenv(env_name)
        if value is not None:
            out[config_key] = value

    return out


def _normalize_config(data: dict) -> dict:
    out = dict(data or {})
    # SMTP pertenecia a un flujo local retirado. Si queda en una configuracion
    # antigua, no se expone ni se vuelve a guardar desde la aplicacion.
    out.pop("smtp", None)
    out.setdefault("templates_path", "")
    out.setdefault("word_templates_dir", "")
    out.setdefault("a3_base_path", "")
    out.setdefault("postgres_dsn", "")
    out.setdefault("ocr_motor_activo", "")
    out.setdefault("azure_doc_intelligence_endpoint", "")
    out.setdefault("azure_doc_intelligence_key", "")
    out.setdefault("documentos_output_dir", "")
    out.setdefault("dgt_api_url", "")
    out.setdefault("dgt_api_key", "")
    out.setdefault("integrations_api_url", "")
    out.setdefault("integrations_api_key", "")
    if not out["integrations_api_url"]:
        out["integrations_api_url"] = out["dgt_api_url"]
    if not out["integrations_api_key"]:
        out["integrations_api_key"] = out["dgt_api_key"]
    if not out["dgt_api_url"]:
        out["dgt_api_url"] = out["integrations_api_url"]
    if not out["dgt_api_key"]:
        out["dgt_api_key"] = out["integrations_api_key"]
    out.setdefault("messaging_api_url", "")
    out.setdefault("messaging_api_key", "")
    out.setdefault("messaging_workstation_id", "")
    out.setdefault("messaging_device_token", "")
    out.setdefault("signrequest_base_url", "https://signrequest.com/api/v1")
    out.setdefault("signrequest_use_sms", False)
    out.setdefault("firma_habilitada", True)
    out.setdefault("firma_categoria_firmados", "FIRMAS")
    out.setdefault("firma_max_mb", 15)
    out.setdefault("firma_webhook_secret", "")
    out.setdefault("dataprius_base_url", "https://api.v2.dataprius.com")
    out.setdefault("dataprius_base_path", "FOLDERS/Gest2A3Eco/Tramites DGT")
    # Secretos Dataprius y SignRequest: migrados al backend. Si aun aparecen
    # en la config local (instalacion antigua), se ignoran silenciosamente.
    import logging as _logging
    _log = _logging.getLogger(__name__)
    for _clave in ("dataprius_api_key", "dataprius_api_secret", "signrequest_token",
                   "signrequest_from_email", "signrequest_gestor_email",
                   "signrequest_gestor_telefono", "firma_permitir_cliente_local"):
        if out.pop(_clave, None):
            _log.warning(
                "Clave de configuracion obsoleta '%s' ignorada. "
                "Las credenciales de Dataprius y SignRequest residen ahora en el backend.", _clave
            )

    if not str(out.get("documentos_output_dir") or "").strip():
        repository = Path(
            os.getenv("GEST2A3ECO_DOCUMENT_REPOSITORY_DIR")
            or r"\\GestinemMain\Doc_Compartidos\Gest2A3Eco"
        )
        out["documentos_output_dir"] = str(repository / "Empresas")

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


def get_word_templates_subdir(tipo: str, *, crear: bool = True) -> Path:
    """Devuelve una subcarpeta funcional de la raiz Word compartida."""
    clave = str(tipo or "").strip().lower()
    nombre = WORD_TEMPLATE_SUBDIRS.get(clave)
    if not nombre:
        raise ValueError(f"Tipo de plantillas Word no valido: {tipo}")
    path = Path(get_word_templates_dir()) / nombre
    if crear:
        path.mkdir(parents=True, exist_ok=True)
    return path

def set_word_templates_dir(path: str) -> None:
    cfg = load_app_config()
    cfg["word_templates_dir"] = path
    save_app_config(cfg)


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

def validar_subcuenta_longitud(sc: str, ndig: int, campo: str = "subcuenta"):
    """Valida que la subcuenta tenga exactamente ndig digitos.

    Acepta cuentas con menos digitos solo si son todos numericos (se normalizarian
    rellenando con ceros a la derecha). Lanza ValueError si la longitud es erronea
    y no es normalizable, o si contiene caracteres no numericos.
    """
    sc = (sc or "").strip()
    if not sc:
        return
    # Extraer solo digitos para comprobar si es un codigo numerico
    digits_only = "".join(ch for ch in sc if ch.isdigit())
    if not digits_only or digits_only != sc:
        raise ValueError(
            f"La {campo} '{sc}' debe contener solo digitos numericos."
        )
    if len(sc) == ndig:
        return
    if len(sc) < ndig:
        raise ValueError(
            f"La {campo} '{sc}' tiene {len(sc)} digito(s) pero la empresa usa {ndig}.\n"
            f"Rellena con ceros a la derecha: '{sc.ljust(ndig, chr(48))}'."
        )
    # Mayor que ndig
    raise ValueError(
        f"La {campo} '{sc}' tiene {len(sc)} digitos pero la empresa usa {ndig}.\n"
        f"Acorta a los primeros {ndig} digitos: '{sc[:ndig]}'."
    )


def normalizar_subcuenta_a_plan(sc: str, ndig: int) -> str:
    """Normaliza un codigo de subcuenta al numero de digitos del plan de la empresa.

    - Si es mas corta: rellena con ceros a la derecha.
    - Si es mas larga: toma los primeros ndig digitos.
    - Solo extrae digitos (compatible con Excel que puede dar floats).
    """
    if not sc:
        return ""
    s = str(sc).strip()
    # Eliminar decimal de Excel: "43000001.0" -> "43000001"
    if "." in s:
        try:
            s = str(int(float(s)))
        except (ValueError, OverflowError):
            pass
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""
    if len(digits) > ndig:
        return digits[:ndig]
    return digits.ljust(ndig, "0")

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
        if str(ln.get("tipo") or "").strip().lower() in {"obs", "suplido"}:
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
        if str(ln.get("tipo") or "").strip().lower() in {"obs", "suplido"}:
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
