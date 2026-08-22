from __future__ import annotations

import smtplib
import ssl
import base64
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

import requests

from backend.api.config import get_settings


def configured() -> bool:
    cfg = get_settings()
    return _graph_configured(cfg) or _smtp_configured(cfg)


def default_sender() -> str:
    cfg = get_settings()
    return str(cfg.messaging_graph_from or cfg.messaging_smtp_from or "").strip()


def _graph_configured(cfg) -> bool:
    return bool(
        cfg.messaging_graph_tenant_id
        and cfg.messaging_graph_client_id
        and cfg.messaging_graph_client_secret
        and cfg.messaging_graph_from
    )


def _smtp_configured(cfg) -> bool:
    return bool(cfg.messaging_smtp_host and cfg.messaging_smtp_from)


def send_mail(
    to: str | list[str], subject: str, html: str, *, sender: str = "",
    cc: list[str] | None = None, bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
    text: str = "",
) -> bool:
    cfg = get_settings()
    if _graph_configured(cfg):
        return _send_mail_graph(
            cfg, to, subject, html, sender=sender, cc=cc, bcc=bcc,
            attachments=attachments,
        )
    if not _smtp_configured(cfg):
        return False
    return _send_mail_smtp(
        cfg, to, subject, html, cc=cc, bcc=bcc, attachments=attachments,
        text=text,
    )


def _recipients(values: str | list[str] | None) -> list[dict]:
    if isinstance(values, str):
        values = [values]
    return [
        {"emailAddress": {"address": str(value).strip()}}
        for value in (values or []) if str(value).strip()
    ]


def _send_mail_graph(
    cfg, to: str | list[str], subject: str, html: str, *, sender: str = "",
    cc: list[str] | None = None, bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
) -> bool:
    token_response = requests.post(
        "https://login.microsoftonline.com/"
        f"{quote(cfg.messaging_graph_tenant_id, safe='')}/oauth2/v2.0/token",
        data={
            "client_id": cfg.messaging_graph_client_id,
            "client_secret": cfg.messaging_graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if token_response.status_code != 200:
        raise RuntimeError(_graph_error(token_response, "autenticacion"))
    access_token = str(token_response.json().get("access_token") or "")
    if not access_token:
        raise RuntimeError("Microsoft Graph no devolvio un token de acceso")

    sent = requests.post(
        "https://graph.microsoft.com/v1.0/users/"
        f"{quote(sender or cfg.messaging_graph_from, safe='')}/sendMail",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html},
                "toRecipients": _recipients(to),
                "ccRecipients": _recipients(cc),
                "bccRecipients": _recipients(bcc),
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": item["name"],
                        "contentType": item.get("content_type") or "application/octet-stream",
                        "contentBytes": base64.b64encode(item["content"]).decode("ascii"),
                        "isInline": bool(item.get("content_id")),
                        **({"contentId": item["content_id"]} if item.get("content_id") else {}),
                    }
                    for item in (attachments or [])
                ],
            },
            "saveToSentItems": True,
        },
        timeout=30,
    )
    if sent.status_code != 202:
        raise RuntimeError(_graph_error(sent, "envio"))
    return True


def _graph_error(response, operation: str) -> str:
    try:
        payload = response.json()
        detail = payload.get("error", {})
        message = (
            detail.get("message") if isinstance(detail, dict) else ""
        ) or payload.get("error_description")
    except Exception:
        message = ""
    return message or f"Error de {operation} de Microsoft Graph (HTTP {response.status_code})"


def _send_mail_smtp(
    cfg, to: str | list[str], subject: str, html: str, *,
    cc: list[str] | None = None, bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
    text: str = "",
) -> bool:
    to_values = [to] if isinstance(to, str) else list(to)
    message = EmailMessage()
    message["From"] = cfg.messaging_smtp_from
    message["To"] = ", ".join(to_values)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message.set_content(
        text or "Abre la aplicacion Gestinem para consultar este aviso seguro."
    )
    message.add_alternative(html, subtype="html")
    for item in attachments or []:
        content_type = str(item.get("content_type") or "application/octet-stream")
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(
            item["content"], maintype=maintype or "application",
            subtype=subtype or "octet-stream", filename=item["name"],
        )
    with smtplib.SMTP(cfg.messaging_smtp_host, cfg.messaging_smtp_port, timeout=30) as smtp:
        if cfg.messaging_smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if cfg.messaging_smtp_user:
            smtp.login(cfg.messaging_smtp_user, cfg.messaging_smtp_password)
        smtp.send_message(message, to_addrs=to_values + list(cc or []) + list(bcc or []))
    return True


def send_invitation(to: str, name: str, url: str) -> bool:
    cfg = get_settings()
    return send_mail(
        to, "Invitacion a la mensajeria de Gestinem",
        f"<p>Hola {escape(name)},</p><p>Gestinem te invita a utilizar su canal seguro de mensajeria.</p>"
        f"<p><a href=\"{escape(url)}\">Activar mi cuenta</a></p>"
        f"<p>Si el boton no funciona, abre este enlace:<br>{escape(url)}</p>"
        "<p>El enlace es personal y caduca en 72 horas.</p>",
        sender=cfg.messaging_graph_invitation_from,
        text=(
            f"Hola {name},\n\nGestinem te invita a utilizar su canal seguro de mensajeria.\n"
            f"Activa tu cuenta desde este enlace:\n{url}\n\n"
            "El enlace es personal y caduca en 72 horas."
        ),
    )


def send_message_notice(to: str, name: str, portal_url: str = "") -> bool:
    """Aviso de nuevo mensaje. portal_url ignorado (mensajeria web retirada)."""
    return send_mail(
        to, "Nuevo mensaje de Gestinem",
        f"<p>Hola {escape(name)},</p><p>Tienes un nuevo mensaje en el canal seguro de Gestinem.</p>"
        "<p>Abre la aplicacion Gestinem para leer y responder tu mensaje.</p>"
        "<p>Por seguridad, el contenido no se incluye en este email.</p>",
    )


def send_password_reset(to: str, name: str, url: str) -> bool:
    return send_mail(
        to, "Recuperar contraseña de Mensajes Gestinem",
        f"<p>Hola {escape(name)},</p><p>Hemos recibido una solicitud para cambiar tu contraseña.</p>"
        f"<p><a href=\"{escape(url)}\">Crear una nueva contraseña</a></p>"
        "<p>El enlace caduca en una hora. Si no lo has solicitado, ignora este email.</p>",
    )
