from __future__ import annotations

from pathlib import Path
import io
import os
import sys
from typing import Dict, Any, Tuple

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx.image.image import Image as DocxImage
from docx2pdf import convert
from xml.sax.saxutils import escape as _xml_escape


def build_context_emitida(empresa_conf: dict, fac: dict, cliente: dict, totales: dict) -> Dict[str, Any]:
    # Normaliza: numeros con miles en punto y decimales con coma (1.000,00)
    def f2(x):
        try:
            s = f"{float(x):,.2f}"
        except Exception:
            s = "0.00"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    def f4(x):
        try:
            s = f"{float(x):,.4f}"
        except Exception:
            s = "0.0000"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    moneda_simbolo = str(fac.get("moneda_simbolo") or "").strip()

    def f2s(x):
        base = f2(x)
        return f"{base} {moneda_simbolo}".strip() if moneda_simbolo else base

    def first_cuenta(raw):
        raw = raw or ""
        if not str(raw).strip():
            return ""
        for sep in ["\n", ";", ","]:
            raw = str(raw).replace(sep, ",")
        for p in str(raw).split(","):
            p = p.strip()
            if p:
                return p
        return ""

    lineas = []
    for ln in fac.get("lineas", []):
        is_obs = str(ln.get("tipo") or "").strip().lower() == "obs"
        base = float(ln.get("base") or 0)
        cuota_iva = float(ln.get("cuota_iva") or 0)
        cuota_irpf = float(ln.get("cuota_irpf") or 0)
        total_linea = base + cuota_irpf
        pct_irpf = ln.get("pct_irpf") or 0

        lineas.append({
            "concepto": str(ln.get("concepto", "")),
            "unidades": "" if is_obs else f2(ln.get("unidades") or 0),
            "precio": "" if is_obs else f4(ln.get("precio") or 0),
            "base": "" if is_obs else f2s(ln.get("base") or 0),
            "pct_iva": "" if is_obs else f2(ln.get("pct_iva") or 0),
            "cuota_iva": "" if is_obs else f2s(ln.get("cuota_iva") or 0),
            "pct_irpf": "" if is_obs else f2(pct_irpf),
            "pct_irpf_pct": "" if is_obs else f"{f2(pct_irpf)}%",
            "cuota_irpf": "" if is_obs else f2s(ln.get("cuota_irpf") or 0),
            "total_linea": "" if is_obs else f2s(total_linea),
        })

    resumen = {}
    for ln in fac.get("lineas", []):
        if str(ln.get("tipo") or "").strip().lower() == "obs":
            continue
        pct = float(ln.get("pct_iva") or 0)
        item = resumen.setdefault(pct, {"base": 0.0, "cuota": 0.0})
        item["base"] += float(ln.get("base") or 0)
        item["cuota"] += float(ln.get("cuota_iva") or 0)
    iva_resumen = []
    for pct in sorted(resumen.keys(), reverse=True):
        item = resumen[pct]
        iva_resumen.append({
            "tipo": f"{pct:.2f}%",
            "base": f2s(item["base"]),
            "cuota": f2s(item["cuota"]),
        })

    if fac.get("retencion_aplica"):
        ret_base = fac.get("retencion_base")
        ret_pct = fac.get("retencion_pct")
        ret_imp = fac.get("retencion_importe")
        if ret_imp is None or ret_imp == "":
            try:
                ret_imp = -abs(float(ret_base or 0) * float(ret_pct or 0) / 100.0) if float(ret_pct or 0) else 0
            except Exception:
                ret_imp = 0
    else:
        ret_base = 0
        ret_pct = 0
        ret_imp = 0

    return {
        "empresa": {
            "nombre": empresa_conf.get("nombre", ""),
            "codigo": empresa_conf.get("codigo") or empresa_conf.get("codigo_empresa") or "",
            "cif": empresa_conf.get("cif", ""),
            "direccion": empresa_conf.get("direccion", ""),
            "cp": empresa_conf.get("cp", ""),
            "poblacion": empresa_conf.get("poblacion", ""),
            "provincia": empresa_conf.get("provincia", ""),
            "telefono": empresa_conf.get("telefono", ""),
            "email": empresa_conf.get("email", ""),
            "logo_path": empresa_conf.get("logo_path", ""),
            "logo_max_width_mm": empresa_conf.get("logo_max_width_mm"),
            "logo_max_height_mm": empresa_conf.get("logo_max_height_mm"),
        },
        "cliente": {
            "nombre": cliente.get("nombre", ""),
            "nif": cliente.get("nif", ""),
            "direccion": cliente.get("direccion", ""),
            "cp": cliente.get("cp", ""),
            "poblacion": cliente.get("poblacion", ""),
            "provincia": cliente.get("provincia", ""),
            "telefono": cliente.get("telefono", ""),
            "email": cliente.get("email", ""),
        },
        "factura": {
            "serie": fac.get("serie", ""),
            "numero": fac.get("numero", ""),
            "fecha": fac.get("fecha_expedicion") or fac.get("fecha_asiento", ""),
            "fecha_operacion": fac.get("fecha_operacion", ""),
            "descripcion": fac.get("descripcion", ""),
            "observaciones": fac.get("observaciones") or fac.get("descripcion", ""),
        },
        "lineas": lineas,
        "iva_resumen": iva_resumen,
        "totales": {
            "base": f2s(totales.get("base", 0)),
            "iva": f2s(totales.get("iva", 0)),
            "irpf": f2s(totales.get("ret", 0)),
            "total": f2s(totales.get("total", 0)),
            "ret_base": f2s(ret_base or 0),
            "ret_pct": f2(ret_pct or 0),
            "ret_importe": f2s(ret_imp or 0),
            "ret_pct_label": f"{f2(ret_pct or 0)}%",
        },
        "retencion": {
            "base": f2s(ret_base or 0),
            "pct": f2(ret_pct or 0),
            "importe": f2s(ret_imp or 0),
            "pct_label": f"{f2(ret_pct or 0)}%",
        },
        "moneda": {
            "codigo": fac.get("moneda_codigo", ""),
            "simbolo": moneda_simbolo,
        },
        "pago": {
            "metodo": fac.get("forma_pago", ""),
            "banco": "",
            "iban": fac.get("cuenta_bancaria")
            or empresa_conf.get("cuenta_bancaria")
            or first_cuenta(empresa_conf.get("cuentas_bancarias", "")),
            "vencimiento": "",
        }
    }

DEFAULT_LOGO_MAX_WIDTH_MM = 20
DEFAULT_LOGO_MAX_HEIGHT_MM = 12


def render_docx(template_path: str, context: Dict[str, Any], out_docx_path: str) -> None:
    doc = DocxTemplate(template_path)
    ctx = dict(context or {})
    empresa_ctx = ctx.get("empresa") or {}
    logo_path = empresa_ctx.get("logo_path") or ""
    logo_path = _resolve_logo_path(logo_path, empresa_ctx.get("codigo") or empresa_ctx.get("codigo_empresa"))
    if logo_path and os.path.exists(logo_path):
        try:
            empresa = ctx.get("empresa") or {}
            max_w = empresa.get("logo_max_width_mm", DEFAULT_LOGO_MAX_WIDTH_MM)
            max_h = empresa.get("logo_max_height_mm", DEFAULT_LOGO_MAX_HEIGHT_MM)
            ctx["logo"] = _inline_logo(doc, logo_path, max_w, max_h)
        except Exception:
            ctx["logo"] = ""
    ctx = _escape_context(ctx)
    doc.render(ctx)
    doc.save(out_docx_path)


def _escape_context(value: Any) -> Any:
    if isinstance(value, InlineImage):
        return value
    if isinstance(value, str):
        return _xml_escape(value)
    if isinstance(value, dict):
        return {k: _escape_context(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_escape_context(v) for v in value]
    return value

def _resolve_logo_path(path: str, codigo: str | None = None) -> str:
    raw = str(path or "").strip()
    code = str(codigo or "").strip()
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    if raw:
        p = Path(raw)
        if p.exists():
            return str(p)
        alt = base_dir / "assets" / "logos" / p.name
        if alt.exists():
            return str(alt)
    if code:
        raw = str(code).strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        candidates = []
        if raw:
            candidates.append(raw)
            if not raw.upper().startswith("E"):
                candidates.append(f"E{raw}")
            # sin ceros a la izquierda
            if digits:
                stripped = digits.lstrip("0") or "0"
                candidates.append(stripped)
                candidates.append(f"E{stripped}")
        if digits:
            for width in (5, 6, 7, 8):
                padded = digits.zfill(width)
                candidates.append(padded)
                candidates.append(f"E{padded}")
        seen = set()
        for name in candidates:
            if name in seen:
                continue
            seen.add(name)
            for ext in [".jpg", ".jpeg", ".png"]:
                candidate = base_dir / "assets" / "logos" / f"{name}{ext}"
                if candidate.exists():
                    return str(candidate)
    return raw


def _inline_logo(doc: DocxTemplate, path: str, max_width_mm: float, max_height_mm: float) -> InlineImage:
    try:
        image = DocxImage.from_file(path)
        max_w = Mm(float(max_width_mm))
        max_h = Mm(float(max_height_mm))
        scale = min(max_w / image.width, max_h / image.height, 1.0)
        width = int(image.width * scale)
        height = int(image.height * scale)
        return InlineImage(doc, path, width=width, height=height)
    except Exception:
        return InlineImage(doc, path, width=Mm(float(max_width_mm)))

def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> None:
    # Usa Word instalado
    # Evita fallo en .exe sin consola (tqdm intenta escribir en None)
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    os.environ.setdefault("TQDM_DISABLE", "1")
    convert(docx_path, pdf_path)

def generar_pdf_desde_plantilla_word(
    template_path: str,
    context: Dict[str, Any],
    out_pdf_path: str,
    out_docx_path: str | None = None,
    guardar_docx: bool = False,
) -> Tuple[str, str | None]:

    out_pdf = str(Path(out_pdf_path))
    if guardar_docx:
        out_docx = str(Path(out_docx_path) if out_docx_path else Path(out_pdf).with_suffix(".docx"))
        render_docx(template_path, context, out_docx)
        convert_docx_to_pdf(out_docx, out_pdf)
        return out_pdf, out_docx

    # si no guarda DOCX, crea uno temporal junto al pdf y lo elimina si quiere (aquí lo dejamos simple)
    tmp_docx = str(Path(out_pdf).with_suffix(".tmp.docx"))
    render_docx(template_path, context, tmp_docx)
    convert_docx_to_pdf(tmp_docx, out_pdf)
    try:
        Path(tmp_docx).unlink(missing_ok=True)
    except Exception:
        pass
    return out_pdf, None
