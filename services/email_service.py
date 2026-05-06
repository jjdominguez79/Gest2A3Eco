import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.utilidades import load_app_config, save_app_config


def load_smtp_config() -> dict:
    return load_app_config().get("smtp") or {}


def save_smtp_config(cfg: dict) -> None:
    app_cfg = load_app_config()
    app_cfg["smtp"] = cfg
    save_app_config(app_cfg)


def send_email_smtp(
    smtp_cfg: dict,
    to_addrs: list,
    subject: str,
    body: str,
    attachment_path: str = None,
) -> None:
    host = str(smtp_cfg.get("host") or "").strip()
    port = int(smtp_cfg.get("port") or 587)
    user = str(smtp_cfg.get("user") or "").strip()
    password = str(smtp_cfg.get("password") or "")
    from_addr = str(smtp_cfg.get("from_addr") or user).strip()
    use_tls = bool(smtp_cfg.get("use_tls", True))
    use_ssl = bool(smtp_cfg.get("use_ssl", False))

    if not host:
        raise ValueError("Servidor SMTP no configurado.")
    if not to_addrs:
        raise ValueError("No hay destinatarios.")

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
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
