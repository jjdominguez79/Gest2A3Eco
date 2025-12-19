from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Tuple

from docxtpl import DocxTemplate
from docx2pdf import convert


def build_context_emitida(empresa_conf: dict, fac: dict, cliente: dict, totales: dict) -> Dict[str, Any]:
    # Normalice aquí: strings ya formateados, números con 2 decimales, fechas dd/mm/yyyy
    def f2(x):
        try:
            return f"{float(x):.2f}"
        except Exception:
            return "0.00"

    lineas = []
    for ln in fac.get("lineas", []):
        base = float(ln.get("base") or 0)
        cuota_iva = float(ln.get("cuota_iva") or 0)
        cuota_irpf = float(ln.get("cuota_irpf") or 0)
        total_linea = base + cuota_iva + cuota_irpf

        lineas.append({
            "concepto": str(ln.get("concepto", "")),
            "unidades": f2(ln.get("unidades") or 0),
            "precio": f2(ln.get("precio") or 0),
            "base": f2(ln.get("base") or 0),
            "pct_iva": f2(ln.get("pct_iva") or 0),
            "cuota_iva": f2(ln.get("cuota_iva") or 0),
            "pct_irpf": f2(ln.get("pct_irpf") or 0),
            "cuota_irpf": f2(ln.get("cuota_irpf") or 0),
            "total_linea": f2(total_linea),
        })

    return {
        "empresa": {
            "nombre": empresa_conf.get("nombre", ""),
            "cif": empresa_conf.get("cif", ""),
            "direccion": empresa_conf.get("direccion", ""),
            "cp": empresa_conf.get("cp", ""),
            "poblacion": empresa_conf.get("poblacion", ""),
            "provincia": empresa_conf.get("provincia", ""),
            "telefono": empresa_conf.get("telefono", ""),
            "email": empresa_conf.get("email", ""),
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
            "observaciones": fac.get("descripcion", ""),
        },
        "lineas": lineas,
        "totales": {
            "base": f2(totales.get("base", 0)),
            "iva": f2(totales.get("iva", 0)),
            "irpf": f2(totales.get("ret", 0)),
            "total": f2(totales.get("total", 0)),
        },
        "pago": {
            "metodo": "",
            "banco": "",
            "iban": "",
            "vencimiento": "",
        }
    }

def render_docx(template_path: str, context: Dict[str, Any], out_docx_path: str) -> None:
    doc = DocxTemplate(template_path)
    doc.render(context)
    doc.save(out_docx_path)

def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> None:
    # Usa Word instalado
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
