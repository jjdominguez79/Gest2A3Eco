from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from utils.utilidades import d2


CLIENTE_TIPOS_IVA = (
    "INTERIOR_IVA",
    "INTERIOR_EXENTO",
    "INTRACOMUNITARIA",
    "EXPORTACION",
    "ISP",
    "RECARGO_EQUIVALENCIA",
    "NO_SUJETA",
    "OTROS",
)

PROVEEDOR_TIPOS_IVA = (
    "INTERIOR_DEDUCIBLE",
    "INTERIOR_NO_DEDUCIBLE",
    "INTRACOMUNITARIA",
    "IMPORTACION",
    "ISP",
    "BIEN_INVERSION",
    "GASTO_PRORRATA",
    "NO_SUJETA",
    "OTROS",
)

CLASES_INTRACOMUNITARIA = (
    "BIENES",
    "SERVICIOS",
)

DEDUCCION_TOTAL = "total"
DEDUCCION_NO = "no"
DEDUCCION_PARCIAL = "parcial"
DEDUCCION_MODOS = (DEDUCCION_TOTAL, DEDUCCION_NO, DEDUCCION_PARCIAL)
DEDUCCION_LABELS = {
    DEDUCCION_TOTAL: "Si",
    DEDUCCION_NO: "No",
    DEDUCCION_PARCIAL: "Parcial",
}
DEDUCCION_LABELS_INV = {label: key for key, label in DEDUCCION_LABELS.items()}

DEFAULT_REL_CONFIG = {
    "cliente_tipo_operacion_iva": "INTERIOR_IVA",
    "cliente_intracomunitaria_clase": "",
    "cliente_iva_deducible": 0,
    "cliente_porcentaje_deduccion_iva": None,
    "proveedor_tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
    "proveedor_intracomunitaria_clase": "",
    "proveedor_iva_deducible": 1,
    "proveedor_porcentaje_deduccion_iva": 100.0,
}

TIPOS_OPERACION_OCR_MAP = {
    "interior": "INTERIOR_DEDUCIBLE",
    "intracomunitaria": "INTRACOMUNITARIA",
    "importacion": "IMPORTACION",
    "exterior": "OTROS",
}

TIPOS_OPERACION_OCR_REVERSE_MAP = {
    "INTERIOR_DEDUCIBLE": "interior",
    "INTERIOR_NO_DEDUCIBLE": "interior",
    "INTRACOMUNITARIA": "intracomunitaria",
    "IMPORTACION": "importacion",
    "EXPORTACION": "exterior",
    "NO_SUJETA": "exterior",
    "OTROS": "exterior",
}

TIPO_IVA_TOOLTIPS = {
    "INTERIOR_IVA": "Operacion interior sujeta a IVA repercutido.",
    "INTERIOR_EXENTO": "Venta interior exenta, util para futuras obligaciones fiscales.",
    "INTRACOMUNITARIA": "Operacion con contraparte intracomunitaria.",
    "EXPORTACION": "Entrega fuera del territorio de aplicacion del IVA.",
    "ISP": "Operacion con inversion del sujeto pasivo.",
    "RECARGO_EQUIVALENCIA": "Venta con recargo de equivalencia.",
    "NO_SUJETA": "Operacion no sujeta a IVA.",
    "OTROS": "Reserva para casuisticas especiales.",
    "INTERIOR_DEDUCIBLE": "Compra interior con IVA soportado deducible.",
    "INTERIOR_NO_DEDUCIBLE": "Compra interior con IVA no deducible.",
    "IMPORTACION": "Compra de importacion, preparada para evolucion futura.",
    "BIEN_INVERSION": "Compra de bien de inversion.",
    "GASTO_PRORRATA": "Compra sometida a prorrata o deduccion parcial.",
}

CLIENTE_FACTURA_DEFAULTS = {
    "INTERIOR_IVA": {"tipo_operacion": "01", "modelo_fiscal": ""},
    "INTERIOR_EXENTO": {"tipo_operacion": "02", "modelo_fiscal": ""},
    "EXPORTACION": {"tipo_operacion": "06", "modelo_fiscal": ""},
    "ISP": {"tipo_operacion": "08", "modelo_fiscal": ""},
    "RECARGO_EQUIVALENCIA": {"tipo_operacion": "01", "modelo_fiscal": ""},
    "NO_SUJETA": {"tipo_operacion": "07", "modelo_fiscal": ""},
    "OTROS": {"tipo_operacion": "09", "modelo_fiscal": ""},
}


def normalize_percentage(value: Any, *, default: float = 100.0) -> float:
    if value in (None, ""):
        return float(default)
    try:
        pct = float(str(value).replace(",", "."))
    except Exception as exc:
        raise ValueError("El porcentaje de deduccion IVA debe ser numerico.") from exc
    if pct < 0 or pct > 100:
        raise ValueError("El porcentaje de deduccion IVA debe estar entre 0 y 100.")
    return round(pct, 2)


def get_proveedor_deduction_mode(rel: dict | None) -> str:
    rel = rel or {}
    ded = bool(rel.get("proveedor_iva_deducible"))
    pct = normalize_percentage(rel.get("proveedor_porcentaje_deduccion_iva"), default=100.0)
    if not ded or pct <= 0:
        return DEDUCCION_NO
    if pct >= 100:
        return DEDUCCION_TOTAL
    return DEDUCCION_PARCIAL


def apply_proveedor_deduction_mode(rel: dict, mode: str, percentage: Any = None) -> dict:
    if mode not in DEDUCCION_MODOS:
        raise ValueError("Modo de deduccion IVA proveedor no valido.")
    rel = dict(rel or {})
    if mode == DEDUCCION_NO:
        rel["proveedor_iva_deducible"] = 0
        rel["proveedor_porcentaje_deduccion_iva"] = 0.0
        return rel
    if mode == DEDUCCION_TOTAL:
        rel["proveedor_iva_deducible"] = 1
        rel["proveedor_porcentaje_deduccion_iva"] = 100.0
        return rel
    rel["proveedor_iva_deducible"] = 1
    rel["proveedor_porcentaje_deduccion_iva"] = normalize_percentage(percentage, default=100.0)
    return rel


def normalize_tercero_empresa_rel(rel: dict | None) -> dict:
    out = dict(DEFAULT_REL_CONFIG)
    if rel:
        out.update(rel)
    raw = dict(rel or {})
    cliente_tipo = str(out.get("cliente_tipo_operacion_iva") or DEFAULT_REL_CONFIG["cliente_tipo_operacion_iva"]).strip().upper()
    proveedor_tipo = str(out.get("proveedor_tipo_operacion_iva") or DEFAULT_REL_CONFIG["proveedor_tipo_operacion_iva"]).strip().upper()
    if cliente_tipo not in CLIENTE_TIPOS_IVA:
        cliente_tipo = DEFAULT_REL_CONFIG["cliente_tipo_operacion_iva"]
    if proveedor_tipo not in PROVEEDOR_TIPOS_IVA:
        proveedor_tipo = DEFAULT_REL_CONFIG["proveedor_tipo_operacion_iva"]
    out["cliente_tipo_operacion_iva"] = cliente_tipo
    out["proveedor_tipo_operacion_iva"] = proveedor_tipo
    cliente_clase = str(out.get("cliente_intracomunitaria_clase") or "").strip().upper()
    proveedor_clase = str(out.get("proveedor_intracomunitaria_clase") or "").strip().upper()
    out["cliente_intracomunitaria_clase"] = cliente_clase if cliente_clase in CLASES_INTRACOMUNITARIA else ""
    out["proveedor_intracomunitaria_clase"] = proveedor_clase if proveedor_clase in CLASES_INTRACOMUNITARIA else ""
    out["cliente_iva_deducible"] = 0
    out["cliente_porcentaje_deduccion_iva"] = None
    if proveedor_tipo == "INTERIOR_NO_DEDUCIBLE" and raw.get("proveedor_iva_deducible") is None:
        out["proveedor_iva_deducible"] = 0
        out["proveedor_porcentaje_deduccion_iva"] = 0.0
    mode = get_proveedor_deduction_mode(out)
    pct = out.get("proveedor_porcentaje_deduccion_iva")
    return apply_proveedor_deduction_mode(out, mode, pct)


def validate_tercero_empresa_rel(rel: dict | None) -> dict:
    out = normalize_tercero_empresa_rel(rel)
    if out["cliente_tipo_operacion_iva"] not in CLIENTE_TIPOS_IVA:
        raise ValueError("Tipo operacion IVA cliente no valido.")
    if out["proveedor_tipo_operacion_iva"] not in PROVEEDOR_TIPOS_IVA:
        raise ValueError("Tipo operacion IVA proveedor no valido.")
    if out["cliente_tipo_operacion_iva"] == "INTRACOMUNITARIA" and out["cliente_intracomunitaria_clase"] not in CLASES_INTRACOMUNITARIA:
        raise ValueError("Debes indicar si la operacion intracomunitaria de cliente es de bienes o servicios.")
    if out["proveedor_tipo_operacion_iva"] == "INTRACOMUNITARIA" and out["proveedor_intracomunitaria_clase"] not in CLASES_INTRACOMUNITARIA:
        raise ValueError("Debes indicar si la operacion intracomunitaria de proveedor es de bienes o servicios.")
    normalize_percentage(out.get("proveedor_porcentaje_deduccion_iva"), default=100.0)
    return out


def build_cliente_factura_defaults(rel: dict | None) -> dict:
    rel_norm = normalize_tercero_empresa_rel(rel)
    tipo_iva = rel_norm["cliente_tipo_operacion_iva"]
    if tipo_iva == "INTRACOMUNITARIA":
        clase = rel_norm.get("cliente_intracomunitaria_clase") or "BIENES"
        return {
            "tipo_operacion": "03",
            "modelo_fiscal": "02" if clase == "BIENES" else "11",
        }
    defaults = CLIENTE_FACTURA_DEFAULTS.get(tipo_iva) or CLIENTE_FACTURA_DEFAULTS["INTERIOR_IVA"]
    return dict(defaults)


def split_iva_deducible(cuota_iva: Any, porcentaje_deduccion: Any) -> tuple[Decimal, Decimal]:
    cuota = d2(cuota_iva)
    pct = Decimal(str(normalize_percentage(porcentaje_deduccion, default=100.0)))
    ded = (cuota * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    no_ded = (cuota - ded).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ded, no_ded


def build_doc_proveedor_fiscal_data(rel: dict | None, *, cuenta_gasto: str = "", cuenta_proveedor: str = "") -> dict:
    rel_norm = normalize_tercero_empresa_rel(rel)
    return {
        "cuenta_gasto": str(cuenta_gasto or rel_norm.get("subcuenta_gasto") or "").strip(),
        "cuenta_proveedor": str(cuenta_proveedor or rel_norm.get("subcuenta_proveedor") or rel_norm.get("subcuenta_cliente") or "").strip(),
        "proveedor_tipo_operacion_iva": rel_norm["proveedor_tipo_operacion_iva"],
        "proveedor_iva_deducible": int(bool(rel_norm.get("proveedor_iva_deducible"))),
        "proveedor_porcentaje_deduccion_iva": float(rel_norm.get("proveedor_porcentaje_deduccion_iva") or 0.0),
    }


def proveedor_tipo_to_ocr(tipo_operacion_iva: str | None) -> str:
    key = str(tipo_operacion_iva or "").strip().upper()
    return TIPOS_OPERACION_OCR_REVERSE_MAP.get(key, "interior")


def ocr_tipo_to_proveedor(tipo_operacion: str | None) -> str:
    key = str(tipo_operacion or "").strip().lower()
    return TIPOS_OPERACION_OCR_MAP.get(key, DEFAULT_REL_CONFIG["proveedor_tipo_operacion_iva"])
