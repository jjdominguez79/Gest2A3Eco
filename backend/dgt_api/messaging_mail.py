from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from backend.dgt_api.config import get_settings


def configured() -> bool:
    cfg = get_settings()
    return bool(cfg.messaging_smtp_host and cfg.messaging_smtp_from)


def send_mail(to: str, subject: str, html: str) -> bool:
    cfg = get_settings()
    if not configured():
        return False
    message = EmailMessage()
    message["From"] = cfg.messaging_smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content("Accede al portal seguro de Gestinem para consultar este aviso.")
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg.messaging_smtp_host, cfg.messaging_smtp_port, timeout=30) as smtp:
        if cfg.messaging_smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if cfg.messaging_smtp_user:
            smtp.login(cfg.messaging_smtp_user, cfg.messaging_smtp_password)
        smtp.send_message(message)
    return True


def send_invitation(to: str, name: str, url: str) -> bool:
    return send_mail(
        to, "Invitacion a la mensajeria de Gestinem",
        f"<p>Hola {escape(name)},</p><p>Gestinem te invita a utilizar su canal seguro de mensajeria.</p>"
        f"<p><a href=\"{escape(url)}\">Activar mi cuenta</a></p>"
        "<p>El enlace es personal y caduca en 72 horas.</p>",
    )


def send_message_notice(to: str, name: str, portal_url: str) -> bool:
    return send_mail(
        to, "Nuevo mensaje de Gestinem",
        f"<p>Hola {escape(name)},</p><p>Tienes un nuevo mensaje en el canal seguro de Gestinem.</p>"
        f"<p><a href=\"{escape(portal_url)}\">Consultar mensaje</a></p>"
        "<p>Por seguridad, el contenido no se incluye en este email.</p>",
    )


def send_password_reset(to: str, name: str, url: str) -> bool:
    return send_mail(
        to, "Recuperar contraseña de Mensajes Gestinem",
        f"<p>Hola {escape(name)},</p><p>Hemos recibido una solicitud para cambiar tu contraseña.</p>"
        f"<p><a href=\"{escape(url)}\">Crear una nueva contraseña</a></p>"
        "<p>El enlace caduca en una hora. Si no lo has solicitado, ignora este email.</p>",
    )
