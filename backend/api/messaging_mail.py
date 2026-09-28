from __future__ import annotations

import smtplib
import ssl
import base64
import re
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from pathlib import Path
from urllib.parse import quote

import requests

from backend.api.config import get_settings


INVITATION_MANUAL_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "Manual_Mensajeria_Gestinem.pdf"
)
INVITATION_EMAIL_VERSION = 1
INVITATION_EMAIL_SUBJECT = (
    "Nueva aplicación Gestinem y canales de comunicación desde el 1 de octubre"
)
INVITATION_EMAIL_INTRO = """Hola {{nombre_cliente}},

Gestinem pone a tu disposición una nueva aplicación para facilitar y mejorar la comunicación con el despacho.

Su objetivo principal es reforzar la privacidad de las comunicaciones y permitir el envío de documentos que contengan información personal o confidencial dentro de un entorno privado y seguro.

Además, las consultas y solicitudes generales enviadas mediante la aplicación podrán ser atendidas por el personal autorizado del despacho, independientemente del día o la hora en que se reciban. De esta forma evitaremos que un mensaje o una petición quede pendiente porque la persona que revisa habitualmente el teléfono de WhatsApp no se encuentre disponible en ese momento.

La aplicación se mejorará progresivamente para ofrecer a nuestros clientes una plataforma de facturación ágil y gratuita. También permitirá solicitar certificados de la Seguridad Social y de la Agencia Tributaria, consultar y obtener copias de sus impuestos y acceder a otros documentos y servicios del despacho en cualquier momento.

Las aplicaciones para Android y Apple se encuentran actualmente en fase de publicación y todavía no están disponibles en sus respectivas tiendas. Mientras finaliza este proceso, puedes acceder a Gestinem directamente desde el navegador de tu móvil, tableta u ordenador, sin necesidad de instalar ninguna aplicación."""
INVITATION_EMAIL_CLOSING = """El enlace de activación es personal y estará disponible durante {{horas_caducidad}} horas.

Te informamos también de que, a partir del 1 de octubre de 2026, la cuenta de WhatsApp del despacho quedará desactivada. Desde esa fecha no se atenderán comunicaciones enviadas por WhatsApp.

Las comunicaciones deberán realizarse mediante la aplicación Gestinem o a través de las siguientes direcciones:

- oficina@gestinem.es: consultas y comunicaciones con el departamento contable y fiscal.
- laboral@gestinem.es: consultas y comunicaciones relacionadas con el ámbito laboral.
- documentacion@gestinem.es: envío de la documentación correspondiente a los trimestres, como se viene haciendo hasta ahora.

También tendrás siempre la posibilidad de contactar directamente conmigo, como responsable del despacho, mediante mi correo electrónico personal o enviándome un mensaje privado desde la aplicación. Los mensajes privados únicamente serán accesibles para su destinatario.

En el enlace al manual encontrarás los pasos necesarios para activar tu cuenta y comenzar a utilizar Gestinem desde el navegador.

Gracias por tu colaboración.

Un saludo,
Gestinem
Gestión Fiscal, Contable y Laboral"""


@dataclass(frozen=True)
class InvitationEmailContent:
    subject: str = INVITATION_EMAIL_SUBJECT
    intro_text: str = INVITATION_EMAIL_INTRO
    closing_text: str = INVITATION_EMAIL_CLOSING
    version: int = INVITATION_EMAIL_VERSION


DEFAULT_INVITATION_EMAIL_CONTENT = InvitationEmailContent()


def configured() -> bool:
    cfg = get_settings()
    return _graph_configured(cfg) or _smtp_configured(cfg)


def default_sender() -> str:
    cfg = get_settings()
    return str(cfg.messaging_graph_from or cfg.messaging_smtp_from or "").strip()


def personal_sender() -> str:
    """Buzon personal autorizado para envios iniciados desde el escritorio."""
    cfg = get_settings()
    return str(cfg.messaging_graph_invitation_from or "").strip()


def personal_sender_configured() -> bool:
    cfg = get_settings()
    return bool(_graph_configured(cfg) and cfg.messaging_graph_invitation_from.strip())


def _graph_configured(cfg) -> bool:
    return bool(
        cfg.messaging_graph_tenant_id
        and cfg.messaging_graph_client_id
        and cfg.messaging_graph_client_secret
        and cfg.messaging_graph_from
    )


def _smtp_configured(cfg) -> bool:
    return bool(cfg.messaging_smtp_host and cfg.messaging_smtp_from)


def _graph_access_token(cfg) -> str:
    """Obtiene un token de aplicacion; las credenciales nunca salen del backend."""
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
    return access_token


def graph_headers(cfg) -> dict[str, str]:
    if not _graph_configured(cfg):
        raise RuntimeError("Microsoft Graph no esta configurado en el backend")
    return {
        "Authorization": f"Bearer {_graph_access_token(cfg)}",
        "Prefer": 'IdType="ImmutableId"',
    }


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
    access_token = _graph_access_token(cfg)

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


def invitation_manual_url() -> str:
    base = get_settings().messaging_public_base_url.rstrip("/")
    return f"{base}/api/v1/messaging/public/client-manual"


def _invitation_values(value: str, name: str) -> str:
    return (
        value.replace("{{nombre_cliente}}", name)
        .replace("{{horas_caducidad}}", "72")
    )


def _editable_text_html(value: str) -> str:
    """Convierte texto administrable a HTML seguro con listas sencillas."""
    blocks: list[str] = []
    for raw_block in re.split(r"\n\s*\n", value.strip()):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("- ") for line in lines):
            blocks.append(
                "<ul>" + "".join(
                    f"<li>{escape(line[2:].strip())}</li>" for line in lines
                ) + "</ul>"
            )
        else:
            blocks.append("<p>" + "<br>".join(escape(line) for line in lines) + "</p>")
    return "".join(blocks)


def render_invitation(
    name: str,
    url: str,
    *,
    content: InvitationEmailContent | None = None,
    manual_url: str = "",
) -> tuple[str, str, str]:
    selected = content or DEFAULT_INVITATION_EMAIL_CONTENT
    manual_url = manual_url or invitation_manual_url()
    subject = _invitation_values(selected.subject, name).strip()
    intro = _invitation_values(selected.intro_text, name)
    closing = _invitation_values(selected.closing_text, name)
    safe_url = escape(url, quote=True)
    safe_manual_url = escape(manual_url, quote=True)
    html = (
        _editable_text_html(intro)
        + f'<p><a href="{safe_url}" style="display:inline-block;padding:12px 20px;'
        "background:#0759af;color:#ffffff;text-decoration:none;border-radius:6px;"
        'font-weight:bold">Activar mi cuenta y acceder a Gestinem</a></p>'
        + f"<p>Si el botón no funciona, copia y pega este enlace en tu navegador:<br>"
        f"{escape(url)}</p>"
        + f'<p><a href="{safe_manual_url}" style="display:inline-block;padding:10px 18px;'
        "border:1px solid #0759af;color:#0759af;text-decoration:none;border-radius:6px;"
        'font-weight:bold">Consultar el manual de Gestinem</a></p>'
        + _editable_text_html(closing)
    )
    text = (
        f"{intro.strip()}\n\n"
        f"Activa tu cuenta y accede a Gestinem desde este enlace:\n{url}\n\n"
        f"Consulta el manual actualizado de Gestinem:\n{manual_url}\n\n"
        f"{closing.strip()}"
    )
    return subject, html, text


def send_invitation(
    to: str,
    name: str,
    url: str,
    *,
    content: InvitationEmailContent | None = None,
    manual_url: str = "",
) -> bool:
    cfg = get_settings()
    subject, html, text = render_invitation(
        name, url, content=content, manual_url=manual_url,
    )
    return send_mail(
        to,
        subject,
        html,
        sender=cfg.messaging_graph_invitation_from,
        text=text,
    )


def send_message_notice(to: str, name: str) -> bool:
    """Envia un aviso sin incluir el contenido confidencial del mensaje."""
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
