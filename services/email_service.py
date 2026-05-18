import os
import smtplib
import ssl
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from utils.utilidades import load_app_config, save_app_config

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


def _base_dir() -> Path:
    """Directorio raiz de la aplicacion (junto al .exe o al proyecto en desarrollo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def get_template_html_path() -> Path:
    """Ruta del fichero de plantilla HTML editable por el usuario."""
    return _base_dir() / "plantillas" / "email_factura.html"


def ensure_template_file() -> Path:
    """Crea el fichero de plantilla si no existe. Devuelve su ruta."""
    path = get_template_html_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_HTML_TEMPLATE, encoding="utf-8")
    return path


def load_smtp_config() -> dict:
    return load_app_config().get("smtp") or {}


def save_smtp_config(cfg: dict) -> None:
    app_cfg = load_app_config()
    app_cfg["smtp"] = cfg
    save_app_config(app_cfg)


def load_email_html_template() -> str:
    """Carga la plantilla HTML desde el fichero externo (plantillas/email_factura.html).
    Si no existe lo crea con el contenido por defecto."""
    path = ensure_template_file()
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return DEFAULT_HTML_TEMPLATE


def save_email_html_template(template: str) -> None:
    """Guarda la plantilla en el fichero externo (y por compatibilidad en config.json)."""
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


def send_email_smtp(
    smtp_cfg: dict,
    to_addrs: list,
    subject: str,
    body: str,
    attachment_path: str = None,
    attachment_paths: list[str] | None = None,
    html_body: str = None,
) -> None:
    host      = str(smtp_cfg.get("host") or "").strip()
    port      = int(smtp_cfg.get("port") or 587)
    user      = str(smtp_cfg.get("user") or "").strip()
    password  = str(smtp_cfg.get("password") or "")
    from_addr = str(smtp_cfg.get("from_addr") or user).strip()
    use_tls   = bool(smtp_cfg.get("use_tls", True))
    use_ssl   = bool(smtp_cfg.get("use_ssl", False))

    if not host:
        raise ValueError("Servidor SMTP no configurado.")
    if not to_addrs:
        raise ValueError("No hay destinatarios.")

    msg = MIMEMultipart("mixed")
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(to_addrs)
    msg["Subject"] = subject

    # Parte de texto: plain + HTML (multipart/alternative)
    if html_body:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    all_attachments = []
    if attachment_path:
        all_attachments.append(attachment_path)
    for extra_path in attachment_paths or []:
        if extra_path and extra_path not in all_attachments:
            all_attachments.append(extra_path)

    for file_path in all_attachments:
        if not os.path.exists(file_path):
            continue
        with open(file_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'
        msg.attach(part)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, to_addrs, msg.as_bytes())
    else:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, to_addrs, msg.as_bytes())
