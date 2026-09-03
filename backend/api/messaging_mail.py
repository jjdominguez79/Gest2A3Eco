from __future__ import annotations

import smtplib
import ssl
import base64
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


def send_invitation(to: str, name: str, url: str) -> bool:
    cfg = get_settings()
    manual = {
        "name": "Manual_Mensajeria_Gestinem.pdf",
        "content_type": "application/pdf",
        "content": INVITATION_MANUAL_PATH.read_bytes(),
    }
    return send_mail(
        to, INVITATION_EMAIL_SUBJECT,
        f"<p>Hola {escape(name)},</p>"
        "<p>Gestinem pone a tu disposición una nueva aplicación para facilitar y "
        "mejorar la comunicación con el despacho.</p>"
        "<p>Su objetivo principal es reforzar la privacidad de las comunicaciones y "
        "permitir el envío de documentos que contengan información personal o "
        "confidencial dentro de un entorno privado y seguro.</p>"
        "<p>Además, las consultas y solicitudes generales enviadas mediante la "
        "aplicación podrán ser atendidas por el personal autorizado del despacho, "
        "independientemente del día o la hora en que se reciban. De esta forma "
        "evitaremos que un mensaje o una petición quede pendiente porque la persona "
        "que revisa habitualmente el teléfono de WhatsApp no se encuentre disponible "
        "en ese momento.</p>"
        "<p>La aplicación se mejorará progresivamente para ofrecer a nuestros clientes "
        "una plataforma de facturación ágil y gratuita. También permitirá solicitar "
        "certificados de la Seguridad Social y de la Agencia Tributaria, consultar y "
        "obtener copias de sus impuestos y acceder a otros documentos y servicios del "
        "despacho en cualquier momento.</p>"
        "<p>Las aplicaciones para Android y Apple se encuentran actualmente en fase "
        "de publicación y todavía no están disponibles en sus respectivas tiendas. "
        "Mientras finaliza este proceso, puedes acceder a Gestinem directamente desde "
        "el navegador de tu móvil, tableta u ordenador, sin necesidad de instalar "
        "ninguna aplicación.</p>"
        f"<p><a href=\"{escape(url)}\" style=\"display:inline-block;padding:12px 20px;"
        "background:#0759af;color:#ffffff;text-decoration:none;border-radius:6px;"
        "font-weight:bold\">Activar mi cuenta y acceder a Gestinem</a></p>"
        f"<p>Si el botón no funciona, copia y pega este enlace en tu navegador:<br>"
        f"{escape(url)}</p>"
        "<p>Este enlace es personal y estará disponible durante 72 horas.</p>"
        "<p>Te informamos también de que, a partir del <strong>1 de octubre de "
        "2026</strong>, la cuenta de WhatsApp del despacho quedará desactivada. Desde "
        "esa fecha no se atenderán comunicaciones enviadas por WhatsApp.</p>"
        "<p>Las comunicaciones deberán realizarse mediante la aplicación Gestinem o a "
        "través de las siguientes direcciones:</p>"
        "<ul>"
        "<li><strong>oficina@gestinem.es:</strong> consultas y comunicaciones con el "
        "departamento contable y fiscal.</li>"
        "<li><strong>laboral@gestinem.es:</strong> consultas y comunicaciones "
        "relacionadas con el ámbito laboral.</li>"
        "<li><strong>documentacion@gestinem.es:</strong> envío de la documentación "
        "correspondiente a los trimestres, como se viene haciendo hasta ahora.</li>"
        "</ul>"
        "<p>También tendrás siempre la posibilidad de contactar directamente conmigo, "
        "como responsable del despacho, mediante mi correo electrónico personal o "
        "enviándome un mensaje privado desde la aplicación. Los mensajes privados "
        "únicamente serán accesibles para su destinatario.</p>"
        "<p>Adjuntamos a este correo el manual de acceso y utilización de Gestinem, "
        "donde encontrarás los pasos necesarios para activar tu cuenta y comenzar a "
        "utilizarla desde el navegador.</p>"
        "<p>Gracias por tu colaboración.</p>"
        "<p>Un saludo,<br><strong>Gestinem</strong><br>Gestión Fiscal, Contable y "
        "Laboral</p>",
        sender=cfg.messaging_graph_invitation_from,
        attachments=[manual],
        text=(
            f"Hola {name},\n\n"
            "Gestinem pone a tu disposición una nueva aplicación para facilitar y "
            "mejorar la comunicación con el despacho.\n\n"
            "Su objetivo principal es reforzar la privacidad de las comunicaciones y "
            "permitir el envío de documentos con información personal o confidencial "
            "dentro de un entorno privado y seguro. Las solicitudes generales podrán "
            "ser atendidas por el personal autorizado del despacho, con independencia "
            "del día o la hora en que se reciban.\n\n"
            "La aplicación se mejorará progresivamente para ofrecer una plataforma de "
            "facturación ágil y gratuita, solicitar certificados de la Seguridad "
            "Social y de la Agencia Tributaria, obtener copias de impuestos y acceder "
            "a otros documentos y servicios en cualquier momento.\n\n"
            "Las aplicaciones para Android y Apple están en fase de publicación y aún "
            "no están disponibles en sus respectivas tiendas. Mientras tanto, puedes "
            "acceder desde el navegador de tu móvil, tableta u ordenador, sin instalar "
            "ninguna aplicación.\n\n"
            f"Activa tu cuenta y accede a Gestinem desde este enlace:\n{url}\n\n"
            "El enlace es personal y estará disponible durante 72 horas.\n\n"
            "A partir del 1 de octubre de 2026, la cuenta de WhatsApp del despacho "
            "quedará desactivada y no se atenderán comunicaciones por esa vía.\n\n"
            "Canales de correo:\n"
            "- oficina@gestinem.es: departamento contable y fiscal.\n"
            "- laboral@gestinem.es: ámbito laboral.\n"
            "- documentacion@gestinem.es: documentación de los trimestres.\n\n"
            "También podrás contactar directamente conmigo mediante mi correo "
            "electrónico personal o un mensaje privado desde la aplicación. Los "
            "mensajes privados únicamente serán accesibles para su destinatario.\n\n"
            "Adjuntamos el manual de acceso y utilización de Gestinem.\n\n"
            "Gracias por tu colaboración.\n\n"
            "Un saludo,\nGestinem\nGestión Fiscal, Contable y Laboral"
        ),
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
