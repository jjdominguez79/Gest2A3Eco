import os
import shutil
import traceback
from html import escape
from pathlib import Path

from utils.utilidades import (
    get_default_templates_dir,
    get_log_path,
    get_packaged_email_template_path,
    load_user_config,
    save_user_config,
)

# ── Plantilla HTML por defecto ───────────────────────────────────────────────
DEFAULT_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:6px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">

        <!-- Cabecera -->
        <tr>
          <td style="background:#002C57;padding:24px 32px;">
            <p style="margin:0;color:#ffffff;font-size:20px;font-weight:bold;">{nombre_empresa}</p>
            <p style="margin:4px 0 0;color:#a8c4e0;font-size:12px;">{cif_empresa}</p>
          </td>
        </tr>

        <!-- Cuerpo -->
        <tr>
          <td style="padding:32px;">
            <p style="margin:0 0 16px;color:#333;font-size:14px;">Estimado/a <strong>{nombre_cliente}</strong>,</p>
            <p style="margin:0 0 16px;color:#555;font-size:14px;line-height:1.6;">
              Le adjuntamos la factura <strong>{numero}</strong> con fecha <strong>{fecha}</strong>
              por un importe de <strong>{total}</strong>.
            </p>
            <p style="margin:0 0 16px;color:#555;font-size:14px;line-height:1.6;">
              Quedo a su disposición para cualquier consulta.
            </p>
          </td>
        </tr>

        <!-- Separador -->
        <tr><td style="border-top:1px solid #e2e8f0;"></td></tr>

        <!-- Pie -->
        <tr>
          <td style="padding:20px 32px;background:#f8fafc;">
            <p style="margin:0;color:#002C57;font-size:13px;font-weight:bold;">{nombre_empresa}</p>
            <p style="margin:4px 0 0;color:#64748b;font-size:12px;">
              {direccion_empresa}<br>
              {telefono_empresa} &nbsp;|&nbsp; {email_empresa}
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

def get_template_html_path() -> Path:
    """Ruta del fichero de plantilla HTML editable por el usuario."""
    return get_default_templates_dir() / "email_factura.html"


def ensure_template_file() -> Path:
    """Crea el fichero de plantilla si no existe. Devuelve su ruta."""
    path = get_template_html_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        packaged = get_packaged_email_template_path()
        if packaged and packaged.exists():
            shutil.copy2(packaged, path)
        else:
            path.write_text(DEFAULT_HTML_TEMPLATE, encoding="utf-8")
    return path


def load_email_preferences() -> dict:
    return load_user_config()


def save_email_preferences(cfg: dict) -> None:
    save_user_config(cfg)


def load_email_html_template() -> str:
    """Carga la plantilla HTML editable desde AppData y la crea si no existe."""
    path = ensure_template_file()
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return DEFAULT_HTML_TEMPLATE


def save_email_html_template(template: str) -> None:
    """Guarda la plantilla HTML editable en AppData."""
    path = ensure_template_file()
    path.write_text(template, encoding="utf-8")


def build_html_body(empresa_conf: dict, fac: dict, cliente: dict, totales: dict) -> str:
    """Rellena la plantilla HTML con los datos de la factura."""
    template = load_email_html_template()

    def _v(d, *keys, default=""):
        for k in keys:
            v = d.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return default

    placeholders = {
        "nombre_empresa":   _v(empresa_conf, "nombre"),
        "cif_empresa":      _v(empresa_conf, "cif"),
        "direccion_empresa": ", ".join(filter(None, [
            _v(empresa_conf, "direccion"),
            _v(empresa_conf, "cp"),
            _v(empresa_conf, "poblacion"),
            _v(empresa_conf, "provincia"),
        ])),
        "telefono_empresa": _v(empresa_conf, "telefono"),
        "email_empresa":    _v(empresa_conf, "email"),
        "nombre_cliente":   _v(cliente, "nombre"),
        "nif_cliente":      _v(cliente, "nif"),
        "numero":           _v(fac, "numero"),
        "fecha":            _v(fac, "fecha_expedicion", "fecha_asiento"),
        "total":            _fmt_total(totales, fac),
    }
    try:
        return template.format(**placeholders)
    except KeyError:
        # Si la plantilla tiene llaves desconocidas, devolver sin sustituir
        return template


def build_invoice_email_text(fac: dict, cliente: dict, totales: dict) -> str:
    """Cuerpo breve y uniforme para el envio de facturas emitidas."""
    nombre_cliente = str(cliente.get("nombre") or "").strip()
    numero = str(fac.get("numero") or "").strip()
    fecha = str(fac.get("fecha_expedicion") or fac.get("fecha_asiento") or "").strip()
    total = _fmt_total(totales, fac)
    return (
        f"Estimado/a {nombre_cliente},\n\n"
        f"Le adjuntamos la factura {numero} con fecha {fecha} por un importe de {total}.\n\n"
        "Quedo a su disposición para cualquier consulta."
    )


def build_outlook_bodies(
    plain_body: str,
    *,
    html_body: str = "",
    signature: str = "",
) -> tuple[str, str]:
    plain = str(plain_body or "").strip()
    sign = str(signature or "").strip()
    if sign:
        plain = f"{plain}\n\n{sign}".strip() if plain else sign

    html = str(html_body or "").strip()
    extra_blocks = []
    if plain_body:
        escaped = escape(str(plain_body or "").strip()).replace("\n", "<br>")
        extra_blocks.append(f"<p style=\"margin:16px 0 0;color:#555;font-size:14px;line-height:1.6;\">{escaped}</p>")
    if sign:
        escaped_sign = escape(sign).replace("\n", "<br>")
        extra_blocks.append(f"<p style=\"margin:16px 0 0;color:#333;font-size:13px;line-height:1.5;\">{escaped_sign}</p>")

    if html:
        insert_html = "".join(extra_blocks)
        if insert_html:
            if "</body>" in html:
                html = html.replace("</body>", f"{insert_html}</body>", 1)
            else:
                html = f"{html}{insert_html}"
    elif plain:
        html = f"<html><body>{escape(plain).replace(chr(10), '<br>')}</body></html>"

    return plain, html


def open_outlook_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
    cc: str = "",
    bcc: str = "",
    html_body: str = "",
) -> None:
    attachments = attachments or []
    resolved_attachments = []
    for attachment in attachments:
        if not attachment:
            continue
        path = Path(attachment).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo adjunto: {path}")
        resolved_attachments.append(str(path.resolve()))

    try:
        import win32com.client  # type: ignore[import-untyped]
    except Exception as exc:
        _log_email_error("Outlook no disponible", exc)
        raise RuntimeError(
            "No se ha podido abrir Microsoft Outlook. Revise que Outlook este instalado y configurado en este equipo."
        ) from exc

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = to or ""
        mail.CC = cc or ""
        mail.BCC = bcc or ""
        mail.Subject = subject or ""
        if html_body:
            mail.HTMLBody = html_body
        else:
            mail.Body = body or ""
        for attachment in resolved_attachments:
            mail.Attachments.Add(attachment)
        mail.Display()
    except FileNotFoundError:
        raise
    except Exception as exc:
        _log_email_error("Error al abrir correo en Outlook", exc)
        raise RuntimeError(
            "No se ha podido abrir Microsoft Outlook. Revise que Outlook este instalado y configurado en este equipo."
        ) from exc


def _fmt_total(totales: dict, fac: dict | None = None) -> str:
    try:
        val = float(totales.get("total") or 0)
        s = f"{val:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        simbolo = str(
            (fac or {}).get("moneda_simbolo") or totales.get("moneda_simbolo") or "€"
        ).strip()
        return f"{s} {simbolo}".strip()
    except Exception:
        return str(totales.get("total", ""))


def _log_email_error(message: str, exc: Exception) -> None:
    try:
        log_path = get_log_path("email_error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n---- EMAIL ERROR ----\n")
            f.write(f"Message: {message}\n")
            f.write("Exception:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass
