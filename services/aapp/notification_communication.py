"""Publicacion y aviso por email de notificaciones DEHu al cliente."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from requests import ConnectionError, Timeout

from services.aapp.document_publication import PublicadorDocumentosAAPP
from services.backend_mail_service import BackendMailService


DEFAULT_EMAIL_SUBJECT = "Nueva notificacion electronica: {asunto}"
DEFAULT_EMAIL_HTML = """\
<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#334155;">
  <h2 style="color:#002C57;">Notificaciones electronicas</h2>
  <p>Estimado/a <strong>{nombre_cliente}</strong>,</p>
  <p>Le comunicamos que hemos recibido {cantidad} notificacion(es) electronica(s):</p>
  {notificaciones}
  <p>Encontrara los documentos adjuntos y disponibles en su area de cliente.</p>
  <p>Atentamente,<br><strong>Gestinem</strong></p>
</body></html>
"""


@dataclass
class ResultadoComunicacion:
    total: int = 0
    publicadas: int = 0
    emails_enviados: int = 0
    errores: list[str] = field(default_factory=list)


def _direcciones(valor: str) -> list[str]:
    return [parte.strip() for parte in re.split(r"[;,]", str(valor or "")) if parte.strip()]


def _lista_notificaciones(items: list[dict]) -> str:
    filas = []
    for item in items:
        asunto = escape(str(item.get("asunto") or "Notificacion electronica"))
        organismo = escape(str(item.get("organismo_emisor") or item.get("organismo_nombre") or "DEHu"))
        fecha = escape(str(item.get("fecha_puesta_disposicion") or "")[:10])
        filas.append(f"<li><strong>{asunto}</strong> - {organismo} ({fecha or 'sin fecha'})</li>")
    return f"<ul>{''.join(filas)}</ul>"


def render_email_notificaciones(config: dict, empresa: dict, items: list[dict]) -> tuple[str, str]:
    if not items:
        raise ValueError("Selecciona al menos una notificacion.")
    asuntos = ", ".join(str(item.get("asunto") or "Notificacion electronica") for item in items)
    valores = {
        "nombre_cliente": escape(str(empresa.get("nombre") or "cliente")),
        "nif_cliente": escape(str(empresa.get("cif") or "")),
        "cantidad": str(len(items)),
        "asunto": escape(str(items[0].get("asunto") or "Notificacion electronica")) if len(items) == 1 else f"{len(items)} notificaciones electronicas",
        "asuntos": escape(asuntos),
        "notificaciones": _lista_notificaciones(items),
    }
    asunto_tpl = str(config.get("email_asunto") or DEFAULT_EMAIL_SUBJECT)
    html_tpl = str(config.get("email_html") or DEFAULT_EMAIL_HTML)
    try:
        valores_asunto = {
            **valores,
            "nombre_cliente": str(empresa.get("nombre") or "cliente"),
            "nif_cliente": str(empresa.get("cif") or ""),
            "asunto": str(items[0].get("asunto") or "Notificacion electronica") if len(items) == 1 else valores["asunto"],
            "asuntos": asuntos,
        }
        asunto = asunto_tpl.format(**valores_asunto).replace("\r", " ").replace("\n", " ")
        return asunto, html_tpl.format(**valores)
    except KeyError as exc:
        raise ValueError(f"La plantilla de notificaciones contiene un campo desconocido: {exc}") from exc


class ComunicadorNotificacionesCliente:
    """Publica los PDF y, si procede, envia un email agrupado por cliente."""

    def __init__(self, gestor, publicador=None, correo=None):
        self._gestor = gestor
        self._publicador = publicador or PublicadorDocumentosAAPP(gestor)
        self._correo = correo or BackendMailService()

    def comunicar(self, notificaciones: list[dict]) -> ResultadoComunicacion:
        resultado = ResultadoComunicacion(total=len(notificaciones))
        config = self._gestor.get_notif_config_global()
        publicadas: dict[str, list[dict]] = {}
        for item in notificaciones:
            try:
                seguridad = getattr(self._gestor, "security", None)
                if seguridad is not None:
                    seguridad.ensure_company_write(item.get("codigo_empresa"))
                if not item.get("enviada_cliente"):
                    publicado = self._publicador.publicar_notificacion(item)
                    if not publicado.ok:
                        raise RuntimeError(publicado.mensaje)
            except Exception as exc:
                resultado.errores.append(f"{item.get('asunto') or item.get('id')}: {exc}")
                continue
            resultado.publicadas += 1
            if item.get("email_cliente_estado") not in {"ENVIADO", "ENVIANDO", "DESCONOCIDO"}:
                publicadas.setdefault(str(item.get("codigo_empresa") or ""), []).append(item)

        if not config.get("avisar_cliente_email"):
            return resultado

        for codigo, items in publicadas.items():
            empresa = {}
            enviado = False
            try:
                empresa = self._gestor.get_empresa(codigo) or {}
                destinatarios = _direcciones(empresa.get("email") or "")
                if not destinatarios or any("@" not in email for email in destinatarios):
                    raise ValueError("La ficha del cliente no tiene un email valido.")
                asunto, html = render_email_notificaciones(config, empresa, items)
                for item in items:
                    self._gestor.marcar_notif_bandeja_email_cliente(codigo, str(item["id"]), "ENVIANDO")
                self._correo.send(
                    to=destinatarios,
                    subject=asunto,
                    body=html,
                    attachments=[str(item.get("pdf_path") or "") for item in items],
                )
                enviado = True
                resultado.emails_enviados += 1
                for item in items:
                    self._gestor.marcar_notif_bandeja_email_cliente(codigo, str(item["id"]), "ENVIADO")
            except Exception as exc:
                resultado.errores.append(f"{empresa.get('nombre') or codigo}: {exc}")
                estado = "DESCONOCIDO" if enviado or isinstance(exc, (Timeout, ConnectionError)) else "ERROR"
                for item in items:
                    try:
                        self._gestor.marcar_notif_bandeja_email_cliente(codigo, str(item["id"]), estado, str(exc))
                    except Exception:
                        pass
        return resultado
