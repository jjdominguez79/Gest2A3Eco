from __future__ import annotations

import html
import json
import os
import re
import threading
import tkinter as tk
from html.parser import HTMLParser
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.graph_mail_service import GraphMailService
from services.documentos_correo_service import DocumentosCorreoService
from utils.utilidades import (
    load_app_config,
    load_user_config,
    get_packaged_resource_path,
    save_app_config,
    save_user_config,
)


def _emails(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


FIRMA_PERSONAL_HTML = """
<div style="font-family:'Times New Roman',serif;color:#111;font-size:11pt;line-height:1.2">
  <img src="cid:gestinem-logo" alt="Gestinem" width="140"
       style="display:block;width:140px;height:auto;margin:8px 0 18px 0">
  <div><strong>Juan José Domínguez Barrero</strong></div>
  <div><strong>Asesor Fiscal, Contable y Mercantil</strong></div>
  <div>Mail: <a href="mailto:jjdominguez@gestinem.es">jjdominguez@gestinem.es</a></div>
  <div>Web: <a href="http://www.gestinem.es/">www.gestinem.es</a></div>
  <div>F: 942 79 14 04 / M: 691 474 519</div>
  <div style="margin-top:18px">CL Atilano Rodríguez 4, Entreplanta, Local 7<br>
  39002 Santander (Cantabria) - (Frente a Estaciones)</div>
  <div style="margin:20px 0 10px;text-align:center;font-family:Tahoma,sans-serif;font-size:10pt">
    _________ ADVERTENCIA LEGAL _________
  </div>
  <div style="font-family:Tahoma,sans-serif;font-size:10pt;text-align:justify">
    JUAN JOSE DOMINGUEZ BARRERO (GESTINEM), le informa que su dirección de correo
    electrónico, así como el resto de los datos de carácter personal que nos facilite,
    serán objeto de tratamiento automatizado en nuestros ficheros, con la finalidad del
    envío de información comercial y/o personal por vía electrónica. Podrá ejercer los
    derechos de acceso, rectificación, cancelación y oposición en los términos establecidos
    en la normativa aplicable, dirigiendo un escrito a JUAN JOSE DOMINGUEZ BARRERO
    (GESTINEM), con domicilio en CL ATILANO RODRIGUEZ 4, ENTREPLANTA LOCAL 7 - 39002
    SANTANDER CANTABRIA, o a
    <a href="mailto:jjdominguez@gestinem.es">jjdominguez@gestinem.es</a>.
    La información incluida en este e-mail es CONFIDENCIAL y para uso exclusivo de su
    destinatario. Si ha recibido este mensaje por error, le rogamos que lo notifique y
    proceda a su eliminación.
  </div>
  <div style="font-family:Tahoma,sans-serif;font-size:10pt;font-weight:bold;margin-top:12px">
    En caso de que no quiera seguir recibiendo información sobre los servicios prestados
    por nuestra empresa, responda a este mail con el asunto “dar de baja”.
  </div>
</div>
""".strip()

FIRMA_OFICINA_HTML = """
<div style="font-family:'Times New Roman',serif;color:#111;font-size:11pt;line-height:1.2">
  <img src="cid:gestinem-logo" alt="Gestinem" width="140"
       style="display:block;width:140px;height:auto;margin:8px 0 18px 0">
  <div><strong>Gestinem{{RESPONSABLE}}</strong></div>
  <div><strong>Asesoría Fiscal, Contable y Laboral</strong></div>
  <div>Mail: <a href="mailto:oficina@gestinem.es">oficina@gestinem.es</a></div>
  <div>Web: <a href="http://www.gestinem.es/">www.gestinem.es</a></div>
  <div>F: 942 79 14 04</div>
  <div style="margin-top:18px">CL Atilano Rodríguez 4, Entreplanta, Local 7<br>
  39002 Santander (Cantabria) - (Frente a Estaciones)</div>
  <div style="margin:20px 0 10px;text-align:center;font-family:Tahoma,sans-serif;font-size:10pt">
    _________ ADVERTENCIA LEGAL _________
  </div>
  <div style="font-family:Tahoma,sans-serif;font-size:10pt;text-align:justify">
    GESTINEM le informa que su dirección de correo electrónico, así como el resto
    de los datos de carácter personal que nos facilite, serán tratados con la
    finalidad de gestionar las comunicaciones profesionales y prestar nuestros
    servicios. Podrá ejercer los derechos que reconoce la normativa aplicable
    dirigiéndose a CL ATILANO RODRIGUEZ 4, ENTREPLANTA LOCAL 7 - 39002 SANTANDER
    CANTABRIA, o a
    <a href="mailto:oficina@gestinem.es">oficina@gestinem.es</a>.
    La información incluida en este e-mail es CONFIDENCIAL y para uso exclusivo
    de su destinatario. Si ha recibido este mensaje por error, notifíquelo y
    proceda a su eliminación.
  </div>
  <div style="font-family:Tahoma,sans-serif;font-size:10pt;font-weight:bold;margin-top:12px">
    En caso de que no quiera seguir recibiendo información sobre los servicios
    prestados por nuestra empresa, responda a este mail con el asunto “dar de baja”.
  </div>
</div>
""".strip()

# Alias conservado para configuraciones y llamadas existentes.
FIRMA_CORPORATIVA_HTML = FIRMA_PERSONAL_HTML


def construir_firma_oficina(
    usuario_nombre: str = "", nombre_remitente: str = "Gestinem",
) -> str:
    nombre = html.escape(str(usuario_nombre or "").strip())
    remitente = html.escape(str(nombre_remitente or "Gestinem").strip())
    responsable = f" - {nombre}" if nombre else ""
    return FIRMA_OFICINA_HTML.replace(
        "Gestinem{{RESPONSABLE}}", f"{remitente}{responsable}",
    )


def construir_cuerpo_html(
    mensaje: str, firma_html: str = "", usuario_nombre: str = "",
) -> str:
    partes = [html.escape(mensaje.strip()).replace("\n", "<br>")]
    if firma_html.strip():
        despedida = "Saludos,"
        if usuario_nombre.strip():
            despedida += f"<br><strong>{html.escape(usuario_nombre.strip())}</strong>"
        partes.append(
            f'<div style="margin-top:24px">{despedida}</div>'
            f'<div style="margin-top:18px">{firma_html.strip()}</div>'
        )
    return f"<html><body>{''.join(partes)}</body></html>"


class _HTMLToText(HTMLParser):
    _BLOCK_TAGS = {"br", "div", "p", "li", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._BLOCK_TAGS - {"br"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def normalizar_html_correo(value: str) -> str:
    """Corrige cuerpos que Microsoft entrega con el HTML escapado una vez."""
    value = str(value or "")
    if re.search(
        r"&lt;\s*(?:html|body|div|p|table|span|br|blockquote)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return html.unescape(value)
    return value


def html_a_texto(value: str) -> str:
    parser = _HTMLToText()
    parser.feed(normalizar_html_correo(value))
    lines = [line.rstrip() for line in "".join(parser.parts).splitlines()]
    texto = "\n".join(lines).strip()
    while "\n\n\n" in texto:
        texto = texto.replace("\n\n\n", "\n\n")
    return texto


class _HTMLTextRenderer(HTMLParser):
    """Renderiza HTML de correo en un Text sin ejecutar contenido externo."""

    _BLOCKS = {"div", "p", "section", "article", "header", "footer", "tr"}
    _SKIPPED = {"script", "style", "head", "title", "meta", "link"}
    _VOID_SKIPPED = {"meta", "link"}

    def __init__(self, widget: tk.Text):
        super().__init__(convert_charrefs=True)
        self.widget = widget
        self.styles: list[str] = []
        self.skip_depth = 0
        self._in_pre = False

    def _last_char(self) -> str:
        value = self.widget.get("end-2c", "end-1c")
        return value if value != "\n" or self.widget.index("end-1c") != "1.0" else ""

    def _newline(self, count: int = 1):
        current = self.widget.get("1.0", "end-1c")
        if not current:
            return
        trailing = len(current) - len(current.rstrip("\n"))
        if trailing < count:
            self.widget.insert("end", "\n" * (count - trailing))

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in self._VOID_SKIPPED:
            return
        if tag in self._SKIPPED:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self._BLOCKS:
            self._newline(2 if tag == "p" else 1)
        elif tag == "br":
            self._newline()
        elif tag == "li":
            self._newline()
            self.widget.insert("end", "  • ", ("bullet",))
        elif tag in {"td", "th"}:
            current = self.widget.get("1.0", "end-1c")
            if current and not current.endswith(("\n", "  ")):
                self.widget.insert("end", "   ")
        elif tag == "hr":
            self._newline()
            self.widget.insert("end", "─" * 72, ("muted",))
            self._newline()
        elif tag == "img":
            alt = str(attrs.get("alt") or "").strip()
            if alt:
                self.widget.insert("end", f"[{alt}]", ("muted", "italic"))
        if tag in {"strong", "b", "th"}:
            self.styles.append("bold")
        elif tag in {"em", "i"}:
            self.styles.append("italic")
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._newline(2)
            self.styles.append("heading")
        elif tag == "a":
            self.styles.append("link")
        elif tag == "blockquote":
            self._newline()
            self.styles.append("quote")
        elif tag == "pre":
            self._newline()
            self._in_pre = True
            self.styles.append("mono")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._VOID_SKIPPED:
            return
        if tag in self._SKIPPED:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        style = {
            "strong": "bold", "b": "bold", "th": "bold",
            "em": "italic", "i": "italic", "a": "link",
            "blockquote": "quote", "pre": "mono",
            "h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading",
        }.get(tag)
        if style and style in self.styles:
            index = len(self.styles) - 1 - self.styles[::-1].index(style)
            self.styles.pop(index)
        if tag == "pre":
            self._in_pre = False
        if tag in self._BLOCKS or tag in {"li", "ul", "ol", "blockquote", "pre"}:
            self._newline(2 if tag == "p" else 1)

    def handle_data(self, data):
        if self.skip_depth or not data:
            return
        value = data if self._in_pre else re.sub(r"\s+", " ", data)
        if not value.strip():
            return
        current = self.widget.get("1.0", "end-1c")
        if current and not current.endswith((" ", "\n")) and data[:1].isspace():
            value = " " + value.lstrip()
        self.widget.insert("end", value, tuple(dict.fromkeys(self.styles)))


def insertar_html_en_texto(widget: tk.Text, value: str) -> None:
    """Inserta HTML de forma visual y segura en un widget Text."""
    parser = _HTMLTextRenderer(widget)
    try:
        parser.feed(normalizar_html_correo(value))
        parser.close()
    except Exception:
        widget.insert("end", html_a_texto(value or ""))


class UIComunicaciones(ttk.Frame):
    def __init__(self, parent, gestor, codigo_empresa, ejercicio, nombre, session=None):
        super().__init__(parent, padding=12)
        self._gestor, self._codigo, self._session = gestor, codigo_empresa, session
        self._empresa = gestor.get_empresa(codigo_empresa, ejercicio) or {}
        self._rows: dict[str, dict] = {}
        self._build()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Comunicaciones", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top, text="Configurar Microsoft 365", command=self._configure).pack(side="right")
        ttk.Button(top, text="Configurar firma", command=self._configure_signature).pack(side="right", padx=6)
        ttk.Button(top, text="Nuevo correo", command=self._compose).pack(side="right", padx=6)
        ttk.Button(top, text="Ver conversacion", command=self._detail).pack(side="right", padx=6)
        ttk.Button(top, text="Ver adjuntos", command=self._preview_selected_attachments).pack(side="right", padx=6)
        ttk.Button(top, text="Responder", command=self._reply_selected).pack(side="right", padx=6)
        self._tree = ttk.Treeview(
            self, columns=("fecha", "tipo", "asunto", "remitente", "estado", "mensajes"),
            show="headings", selectmode="browse",
        )
        for key, title, width in (
            ("fecha", "Ultima actividad", 170), ("tipo", "Tipo", 85), ("asunto", "Asunto", 345),
            ("remitente", "Remitente", 230), ("estado", "Estado", 100),
            ("mensajes", "Mensajes", 80),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", self._detail)

    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        self._rows.clear()
        for row in self._gestor.listar_comunicaciones(self._codigo):
            self._rows[row["id"]] = row
            remitente = row.get("ultimo_remitente") or "(sin remitente)"
            self._tree.insert("", "end", iid=row["id"], values=(
                row.get("ultima_fecha") or "", "Enviado" if row.get("ultima_direccion") == "saliente" else "Recibido", row.get("asunto") or "",
                remitente, row.get("estado") or "",
                row.get("mensajes") or 0,
            ))

    def _configure(self):
        cfg = load_app_config()
        graph = dict(cfg.get("microsoft_graph") or {})
        tenant = simpledialog.askstring(
            "Microsoft 365", "Tenant ID de Microsoft Entra:",
            initialvalue=graph.get("tenant_id", ""), parent=self,
        )
        if tenant is None:
            return
        client = simpledialog.askstring(
            "Microsoft 365", "Application (client) ID:",
            initialvalue=graph.get("client_id", ""), parent=self,
        )
        if client is None:
            return
        shared = simpledialog.askstring(
            "Microsoft 365", "Buzon compartido:",
            initialvalue=graph.get("shared_mailbox", "Oficina@gestinem.es"), parent=self,
        )
        graph.update(tenant_id=tenant.strip(), client_id=client.strip(),
                     shared_mailbox=(shared or "Oficina@gestinem.es").strip())
        cfg["microsoft_graph"] = graph
        save_app_config(cfg)
        messagebox.showinfo("Microsoft 365", "Configuracion guardada. No se ha almacenado ninguna contraseña.", parent=self)

    def _configure_signature(self):
        cfg = load_user_config()
        SignatureDialog(
            self,
            cfg.get("email_signature_html") or FIRMA_PERSONAL_HTML,
        )

    def _compose(self):
        ComposeMailDialog(self, self._gestor, self._codigo, self._empresa, self._session, self._refresh)

    def _detail(self, _event=None):
        selected = self._tree.selection()
        if not selected:
            return
        messages = self._messages_with_local_attachments(selected[0])
        CommunicationDetailDialog(
            self, messages,
            on_preview_attachments=self._preview_attachments,
            on_reply=lambda message: self._reply(selected[0], message),
        )

    def _messages_with_local_attachments(self, comunicacion_id: str) -> list[dict]:
        messages = self._gestor.listar_mensajes_comunicacion(comunicacion_id)
        for message in messages:
            message["adjuntos"] = [
                dict(row) for row in self._gestor.conn.execute(
                    "SELECT nombre,ruta,tamano FROM comunicaciones_adjuntos WHERE mensaje_id=? ORDER BY nombre",
                    (message["id"],),
                ).fetchall()
            ]
        return messages

    def _preview_selected_attachments(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning(
                "Adjuntos", "Selecciona una conversacion.", parent=self,
            )
            return
        messages = self._messages_with_local_attachments(selected[0])
        message = next(
            (
                item for item in messages
                if item.get("adjuntos") or item.get("tiene_adjuntos")
                or (
                    item.get("direccion") != "saliente"
                    and item.get("graph_message_id") and item.get("mailbox")
                )
            ),
            None,
        )
        if not message:
            messagebox.showinfo(
                "Adjuntos", "La conversacion no contiene adjuntos disponibles.",
                parent=self,
            )
            return
        self._preview_attachments(message)

    def _reply(self, comunicacion_id: str, message: dict):
        ReplyMailDialog(
            self, self._gestor, self._codigo, self._session,
            comunicacion_id, message, self._refresh,
        )

    def _reply_selected(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("Correo", "Selecciona una conversacion para responder.", parent=self)
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        message = next(
            (item for item in messages if item.get("direccion") != "saliente"
             and item.get("graph_message_id") and item.get("mailbox")),
            None,
        )
        if not message:
            messagebox.showwarning(
                "Correo", "La conversacion no contiene un correo recibido que se pueda responder.",
                parent=self,
            )
            return
        self._reply(selected[0], message)

    def _preview_attachments(self, message: dict):
        """Abre adjuntos archivados localmente o los disponibles en Graph."""
        local = message.get("adjuntos") or []
        graph_id = str(message.get("graph_message_id") or "").strip()
        mailbox = str(message.get("mailbox") or "").strip()
        # Los enviados y las respuestas conservan una copia local de sus
        # ficheros. Es la fuente fiable despues de enviar (Graph no devuelve
        # el identificador definitivo del mensaje enviado).
        if local and message.get("direccion") == "saliente":
            LocalAttachmentsDialog(self, local)
            return
        if not graph_id or not mailbox:
            if local:
                LocalAttachmentsDialog(self, local)
            else:
                messagebox.showinfo("Adjuntos", "Este mensaje no tiene adjuntos disponibles.", parent=self)
            return

        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                attachments = DocumentosCorreoService(self._gestor).listar_adjuntos(
                    mailbox=mailbox, graph_message_id=graph_id,
                )
                error = None
            except Exception as exc:
                attachments, error = [], exc
            try:
                self.after(0, self._finish_preview_attachments, message, attachments, error)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_preview_attachments(self, message: dict, attachments: list[dict], error):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror("Adjuntos", f"No se pudieron consultar los adjuntos:\n{error}", parent=self)
            return
        if not attachments:
            messagebox.showinfo("Adjuntos", "El correo no tiene adjuntos descargables.", parent=self)
            return
        GraphAttachmentsDialog(
            self, attachments,
            on_open=lambda attachment_id: self._open_graph_attachment(message, attachment_id),
        )

    def _open_graph_attachment(self, message: dict, attachment_id: str):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                path = DocumentosCorreoService(self._gestor).descargar_adjunto_temporal(
                    mailbox=str(message.get("mailbox") or ""),
                    graph_message_id=str(message.get("graph_message_id") or ""),
                    attachment_id=attachment_id,
                )
                error = None
            except Exception as exc:
                path, error = None, exc
            try:
                self.after(0, self._finish_open_attachment, path, error)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_open_attachment(self, path, error):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror("Adjuntos", f"No se pudo abrir el adjunto:\n{error}", parent=self)
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Adjuntos", f"Windows no pudo abrir el archivo:\n{exc}", parent=self)


class _AttachmentsDialog(tk.Toplevel):
    """Selector comun para adjuntos locales y los descargados desde Graph."""

    def __init__(self, parent, attachments: list[dict], on_open):
        super().__init__(parent)
        self.title("Adjuntos del correo")
        self.geometry("650x330")
        self.transient(parent.winfo_toplevel())
        self._attachments = {str(item.get("id") or item.get("ruta") or ""): item for item in attachments}
        self._on_open = on_open
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(frame, columns=("nombre", "tamano"), show="headings")
        self._tree.heading("nombre", text="Archivo")
        self._tree.heading("tamano", text="Tamano")
        self._tree.column("nombre", width=480, anchor="w")
        self._tree.column("tamano", width=110, anchor="e")
        self._tree.pack(fill="both", expand=True)
        for key, item in self._attachments.items():
            size = int(item.get("size") or item.get("tamano") or 0)
            self._tree.insert("", "end", iid=key, values=(
                item.get("name") or item.get("nombre") or "Adjunto",
                f"{size / 1024:.1f} KB" if size else "",
            ))
        self._tree.bind("<Double-1>", lambda _event: self._open())
        actions = ttk.Frame(frame)
        actions.pack(anchor="e", pady=(10, 0))
        ttk.Button(actions, text="Cerrar", command=self.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Abrir", command=self._open).pack(side="left")
        if self._attachments:
            first = next(iter(self._attachments))
            self._tree.selection_set(first)

    def _open(self):
        selected = self._tree.selection()
        if selected:
            self._on_open(selected[0])


class LocalAttachmentsDialog(_AttachmentsDialog):
    def __init__(self, parent, attachments: list[dict]):
        super().__init__(parent, attachments, self._open_local)

    def _open_local(self, key: str):
        path = str(self._attachments[key].get("ruta") or "")
        if not path or not os.path.isfile(path):
            messagebox.showerror("Adjuntos", "El archivo local ya no esta disponible.", parent=self)
            return
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Adjuntos", f"Windows no pudo abrir el archivo:\n{exc}", parent=self)


class GraphAttachmentsDialog(_AttachmentsDialog):
    pass


class UnmatchedMailDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa: str, on_assigned):
        super().__init__(parent)
        self.title("Correos pendientes de asignar")
        self.geometry("850x430")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._on_assigned = on_assigned
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                "Selecciona un correo para asignarlo al cliente actual. "
                "Los siguientes correos de ese remitente se asociaran automaticamente "
                "si guardas su direccion en la ficha del cliente."
            ),
            wraplength=800,
        ).pack(anchor="w", pady=(0, 8))
        self._tree = ttk.Treeview(
            frame, columns=("fecha", "remitente", "asunto", "buzon"),
            show="headings", selectmode="browse",
        )
        for key, title, width in (
            ("fecha", "Fecha", 175), ("remitente", "Remitente", 220),
            ("asunto", "Asunto", 300), ("buzon", "Buzon", 140),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        for item in gestor.listar_comunicaciones_sin_asignar():
            self._tree.insert("", "end", iid=item["graph_message_id"], values=(
                item.get("fecha") or "", item.get("remitente") or "",
                item.get("asunto") or "", item.get("mailbox") or "",
            ))
        ttk.Button(
            frame, text="Asignar al cliente actual",
            command=self._assign,
        ).pack(anchor="e", pady=(10, 0))

    def _assign(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning(
                "Asignacion", "Selecciona un correo.", parent=self,
            )
            return
        self._gestor.asignar_comunicacion_pendiente(
            selected[0], self._codigo, 0, "",
        )
        self._tree.delete(selected[0])
        self._on_assigned()


class SignatureDialog(tk.Toplevel):
    def __init__(self, parent, signature: str):
        super().__init__(parent)
        self.title("Firma de correo")
        self.geometry("620x360")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                "Firma corporativa en HTML. Antes de este bloque se añadiran "
                "automaticamente «Saludos,» y el nombre del usuario conectado."
            ),
            wraplength=580,
        ).pack(anchor="w", pady=(0, 8))
        self._text = tk.Text(frame, wrap="word", height=12)
        self._text.insert("1.0", signature)
        self._text.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=5)
        ttk.Button(actions, text="Guardar", command=self._save).pack(side="left")

    def _save(self):
        cfg = load_user_config()
        cfg["email_signature_html"] = self._text.get("1.0", "end").strip()
        save_user_config(cfg)
        messagebox.showinfo("Firma", "Firma guardada.", parent=self)
        self.destroy()


class CommunicationDetailDialog(tk.Toplevel):
    def __init__(
        self, parent, messages: list[dict], on_import_attachments=None,
        on_preview_attachments=None, on_reply=None,
    ):
        super().__init__(parent)
        self.title("Historial de la comunicacion")
        self.geometry("1120x650")
        self.minsize(1050, 560)
        self.transient(parent.winfo_toplevel())
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self._messages = messages
        self._on_import_attachments = on_import_attachments
        self._on_preview_attachments = on_preview_attachments
        self._on_reply = on_reply
        self._list = ttk.Treeview(
            frame, columns=("fecha", "tipo", "remitente", "asunto", "adjuntos", "estado"),
            show="headings", height=7, selectmode="browse",
        )
        for key, title, width in (
            ("fecha", "Fecha", 180), ("tipo", "Tipo", 85), ("remitente", "Remitente", 180),
            ("asunto", "Asunto", 270), ("adjuntos", "Adjuntos", 85),
            ("estado", "Estado", 120),
        ):
            self._list.heading(key, text=title)
            self._list.column(key, width=width, anchor="w")
        self._list.pack(fill="x")
        self._list.bind("<<TreeviewSelect>>", self._show)
        self._content = tk.Text(frame, wrap="word", state="disabled")
        self._content.configure(
            font=("Segoe UI", 10), padx=14, pady=12,
            bg="#ffffff", fg="#1f2937", relief="solid", borderwidth=1,
        )
        self._content.tag_configure("metadata_label", font=("Segoe UI", 9, "bold"), foreground="#41566b")
        self._content.tag_configure("metadata", font=("Segoe UI", 9), foreground="#41566b")
        self._content.tag_configure("subject", font=("Segoe UI", 13, "bold"), foreground="#123b5d", spacing1=8, spacing3=10)
        self._content.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        self._content.tag_configure("italic", font=("Segoe UI", 10, "italic"))
        self._content.tag_configure("heading", font=("Segoe UI", 12, "bold"), foreground="#123b5d")
        self._content.tag_configure("link", foreground="#1267a5", underline=True)
        self._content.tag_configure("quote", foreground="#52606d", lmargin1=22, lmargin2=22)
        self._content.tag_configure("mono", font=("Consolas", 9), background="#f3f4f6")
        self._content.tag_configure("bullet", foreground="#2b6ea6", font=("Segoe UI", 10, "bold"))
        self._content.tag_configure("muted", foreground="#6b7280")
        self._content.pack(fill="both", expand=True, pady=(10, 0))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        self._import_button = ttk.Button(
            actions, text="Guardar adjuntos en documentacion",
            command=self._import_attachments,
        )
        self._import_button.pack(side="left")
        if not on_import_attachments:
            self._import_button.configure(state="disabled")
        self._preview_button = ttk.Button(
            actions, text="Ver adjuntos",
            command=self._preview_attachments,
        )
        self._preview_button.pack(side="left", padx=(7, 0))
        if not on_preview_attachments:
            self._preview_button.configure(state="disabled")
        self._reply_button = ttk.Button(
            actions, text="Responder", command=self._reply,
        )
        self._reply_button.pack(side="right")
        if not on_reply:
            self._reply_button.configure(state="disabled")
        for index, item in enumerate(messages):
            tiene_adjuntos = bool(item.get("adjuntos")) or bool(item.get("tiene_adjuntos"))
            remitente = item.get("remitente") or "(sin remitente)"
            self._list.insert("", "end", iid=str(index), values=(
                item.get("fecha") or "", "Enviado" if item.get("direccion") == "saliente" else "Recibido", remitente,
                item.get("asunto") or "", "Si" if tiene_adjuntos else "",
                item.get("estado_envio") or "",
            ))
        if messages:
            self._list.selection_set("0")
            self._show()
        else:
            self._set_content("Sin mensajes.")

    def _show(self, _event=None):
        selected = self._list.selection()
        if not selected:
            return
        message = self._messages[int(selected[0])]
        can_reply = bool(
            self._on_reply
            and message.get("direccion") != "saliente"
            and message.get("graph_message_id")
            and message.get("mailbox")
        )
        self._reply_button.configure(state="normal" if can_reply else "disabled")
        destinatarios = ", ".join(json.loads(message.get("destinatarios_json") or "[]"))
        cc = ", ".join(json.loads(message.get("cc_json") or "[]")) or "-"
        adjuntos = message.get("adjuntos") or []
        nombres = ", ".join(item.get("nombre") or "" for item in adjuntos)
        if not nombres and message.get("tiene_adjuntos"):
            nombres = "Disponibles (pulsa «Ver adjuntos»)"
        nombres = nombres or "Ninguno"
        error = message.get("error_envio") or "-"
        self._content.configure(state="normal")
        self._content.delete("1.0", "end")
        for label, value in (
            ("De", message.get("remitente") or "(sin remitente)"),
            ("Para", destinatarios), ("CC", cc),
            ("Fecha", message.get("fecha") or ""),
            ("Estado", message.get("estado_envio") or ""),
            ("Adjuntos", nombres), ("Error", error),
        ):
            self._content.insert("end", f"{label}: ", ("metadata_label",))
            self._content.insert("end", f"{value}\n", ("metadata",))
        self._content.insert(
            "end", f"\n{message.get('asunto') or '(Sin asunto)'}\n", ("subject",),
        )
        insertar_html_en_texto(self._content, message.get("cuerpo_html") or "")
        self._content.configure(state="disabled")

    def _set_content(self, value: str):
        self._content.configure(state="normal")
        self._content.delete("1.0", "end")
        self._content.insert("1.0", value)
        self._content.configure(state="disabled")

    def _import_attachments(self):
        if not self._on_import_attachments:
            return
        selected = self._list.selection()
        if not selected:
            return
        self._on_import_attachments(self._messages[int(selected[0])])

    def _preview_attachments(self):
        if not self._on_preview_attachments:
            return
        selected = self._list.selection()
        if not selected:
            return
        self._on_preview_attachments(self._messages[int(selected[0])])

    def _reply(self):
        if not self._on_reply:
            return
        selected = self._list.selection()
        if selected:
            self._on_reply(self._messages[int(selected[0])])


class ComposeMailDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo, empresa, session, on_sent):
        super().__init__(parent)
        self.title("Nuevo correo")
        self.geometry("760x650")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._gestor, self._codigo, self._session, self._on_sent = gestor, codigo, session, on_sent
        self._attachments: list[str] = []
        cfg = load_app_config().get("microsoft_graph") or {}
        shared = cfg.get("shared_mailbox") or "Oficina@gestinem.es"
        self._sender = tk.StringVar(value=f"Buzon compartido: {shared}")
        self._to = tk.StringVar(value=empresa.get("email") or "")
        self._cc, self._subject = tk.StringVar(), tk.StringVar()
        self._build(shared)

    def _build(self, shared):
        form = ttk.Frame(self, padding=14)
        form.pack(fill="both", expand=True)
        for row, (label, var) in enumerate((("Para", self._to), ("CC", self._cc), ("Asunto", self._subject))):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Remitente").grid(row=3, column=0, sticky="w", pady=4)
        is_admin = bool(self._session and self._session.is_admin())
        sender_values = [f"Buzon compartido: {shared}"]
        if is_admin:
            sender_values.insert(0, "Mi cuenta de Microsoft 365")
        ttk.Combobox(
            form, textvariable=self._sender, state="readonly",
            values=sender_values,
        ).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Mensaje").grid(row=4, column=0, sticky="nw", pady=4)
        self._body = tk.Text(form, wrap="word", height=20)
        self._body.grid(row=4, column=1, sticky="nsew", pady=4)
        self._files = ttk.Label(form, text="Sin adjuntos")
        self._files.grid(row=5, column=1, sticky="w")
        ttk.Button(form, text="Añadir adjuntos", command=self._attach).grid(row=5, column=0, sticky="w")
        signature = (
            load_user_config().get("email_signature_html")
            or FIRMA_PERSONAL_HTML
        ).strip()
        firma_estado = "Se añadira la firma configurada." if signature else "No hay una firma configurada."
        ttk.Label(form, text=firma_estado, foreground="gray").grid(row=6, column=1, sticky="w", pady=(5, 0))
        actions = ttk.Frame(form)
        actions.grid(row=7, column=1, sticky="e", pady=14)
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=5)
        ttk.Button(actions, text="Enviar y registrar", command=self._send).pack(side="left")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(4, weight=1)

    def _attach(self):
        chosen = filedialog.askopenfilenames(parent=self, title="Seleccionar adjuntos")
        self._attachments.extend(path for path in chosen if path not in self._attachments)
        self._files.configure(text=", ".join(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for path in self._attachments) or "Sin adjuntos")

    def _send(self):
        to, cc = _emails(self._to.get()), _emails(self._cc.get())
        subject, plain = self._subject.get().strip(), self._body.get("1.0", "end").strip()
        if not to or not subject or not plain:
            messagebox.showwarning("Correo", "Para, asunto y mensaje son obligatorios.", parent=self)
            return
        shared = (load_app_config().get("microsoft_graph") or {}).get("shared_mailbox") or "Oficina@gestinem.es"
        is_admin = bool(self._session and self._session.is_admin())
        sender = "me" if is_admin and self._sender.get().startswith("Mi cuenta") else shared
        is_shared = sender != "me"
        user = getattr(self._session, "user", None)
        signature = (
            construir_firma_oficina(getattr(user, "nombre", ""))
            if is_shared
            else (
                load_user_config().get("email_signature_html")
                or FIRMA_PERSONAL_HTML
            )
        )
        body_html = construir_cuerpo_html(
            plain, signature, "",
        )
        logo_path = get_packaged_resource_path("logo.png")
        inline_attachments = (
            [{"path": str(logo_path), "content_id": "gestinem-logo"}]
            if "cid:gestinem-logo" in signature and logo_path.is_file() else []
        )
        service = GraphMailService()
        try:
            result = service.send(
                sender=sender, to=to, cc=cc, subject=subject,
                body=body_html,
                attachments=self._attachments,
                inline_attachments=inline_attachments,
            )
        except Exception as exc:
            self._gestor.registrar_envio_comunicacion({
                "codigo_empresa": self._codigo, "asunto": subject,
                "remitente": sender, "destinatarios": to, "cc": cc,
                "cuerpo_html": body_html, "estado_envio": "error",
                "error_envio": str(exc),
                "usuario_id": getattr(user, "id", None),
                "usuario_nombre": getattr(user, "nombre", None),
                "adjuntos": self._attachments,
                "mailbox": sender,
            })
            self._on_sent()
            messagebox.showerror("No se pudo enviar", str(exc), parent=self)
            return
        self._gestor.registrar_envio_comunicacion({
            "codigo_empresa": self._codigo, "asunto": subject,
            "remitente": result.sender, "destinatarios": to, "cc": cc,
            "cuerpo_html": body_html, "estado_envio": "aceptado_graph",
            "graph_message_id": result.message_id,
            "internet_message_id": result.internet_message_id,
            "usuario_id": getattr(user, "id", None),
            "usuario_nombre": getattr(user, "nombre", None),
            "adjuntos": self._attachments,
            "mailbox": sender,
        })
        messagebox.showinfo("Correo", "Exchange ha aceptado el mensaje y se ha registrado.", parent=self)
        self._on_sent()
        self.destroy()


class ReplyMailDialog(tk.Toplevel):
    """Respuesta de un correo existente, incluida en su hilo de Exchange."""

    def __init__(self, parent, gestor, codigo, session, comunicacion_id, message, on_sent):
        super().__init__(parent)
        self.title("Responder correo")
        self.geometry("720x530")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._gestor = gestor
        self._codigo = codigo
        self._session = session
        self._comunicacion_id = str(comunicacion_id)
        self._message = message
        self._on_sent = on_sent
        self._attachments: list[str] = []
        self._mark_answered = tk.BooleanVar(value=True)
        cfg = load_app_config().get("microsoft_graph") or {}
        self._shared_mailbox = str(
            cfg.get("shared_mailbox") or "Oficina@gestinem.es"
        ).strip()
        self._is_admin = bool(self._session and self._session.is_admin())
        self._sender = tk.StringVar(
            value="Mi cuenta de Microsoft 365" if self._is_admin
            else f"Buzon compartido: {self._shared_mailbox}"
        )
        self._build()

    def _build(self):
        form = ttk.Frame(self, padding=14)
        form.pack(fill="both", expand=True)
        ttk.Label(form, text="Responder a", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(form, text=self._message.get("remitente") or "").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(form, text="Asunto", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(form, text=self._message.get("asunto") or "").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(form, text="Enviar desde").grid(row=2, column=0, sticky="w", pady=4)
        sender_values = [f"Buzon compartido: {self._shared_mailbox}"]
        if self._is_admin:
            sender_values.insert(0, "Mi cuenta de Microsoft 365")
        ttk.Combobox(
            form, textvariable=self._sender, state="readonly", values=sender_values,
        ).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Mensaje").grid(row=3, column=0, sticky="nw", pady=(10, 4))
        self._body = tk.Text(form, wrap="word", height=16)
        self._body.grid(row=3, column=1, sticky="nsew", pady=(10, 4))
        ttk.Button(form, text="Adjuntar archivos", command=self._attach).grid(row=4, column=0, sticky="w", pady=4)
        self._files = ttk.Label(form, text="Sin adjuntos")
        self._files.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Checkbutton(
            form, text="Marcar la comunicacion como respondida al enviar",
            variable=self._mark_answered,
        ).grid(row=5, column=1, sticky="w", pady=(8, 0))
        actions = ttk.Frame(form)
        actions.grid(row=6, column=1, sticky="e", pady=14)
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=5)
        ttk.Button(actions, text="Enviar respuesta", command=self._send).pack(side="left")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(3, weight=1)

    def _attach(self):
        chosen = filedialog.askopenfilenames(parent=self, title="Seleccionar adjuntos")
        self._attachments.extend(path for path in chosen if path not in self._attachments)
        names = [path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for path in self._attachments]
        self._files.configure(text=", ".join(names) or "Sin adjuntos")

    def _send(self):
        plain = self._body.get("1.0", "end").strip()
        if not plain:
            messagebox.showwarning("Correo", "Escribe el mensaje de respuesta.", parent=self)
            return
        mailbox = str(self._message.get("mailbox") or "").strip()
        recipient = str(self._message.get("remitente") or "").strip()
        send_personal = self._sender.get() == "Mi cuenta de Microsoft 365"
        graph_id = str(self._message.get("graph_message_id") or "").strip()
        if not recipient:
            messagebox.showerror("Correo", "El mensaje no contiene un remitente valido.", parent=self)
            return
        if not send_personal and (not graph_id or not mailbox):
            messagebox.showerror("Correo", "No se dispone del identificador de Microsoft 365 para responder.", parent=self)
            return
        user = getattr(self._session, "user", None)
        signature = (
            load_user_config().get("email_signature_html") or FIRMA_PERSONAL_HTML
            if send_personal
            else construir_firma_oficina(getattr(user, "nombre", ""))
        )
        body_html = construir_cuerpo_html(plain, signature, "")
        try:
            service = GraphMailService()
            if send_personal:
                subject = self._message.get("asunto") or ""
                if not subject.lower().startswith("re:"):
                    subject = f"Re: {subject}"
                result = service.send(
                    sender="me", to=[recipient], subject=subject, body=body_html,
                    attachments=self._attachments,
                )
                sent_mailbox = result.sender
            else:
                result = service.reply(
                    mailbox=mailbox, message_id=graph_id, body=body_html,
                    attachments=self._attachments,
                )
                sent_mailbox = mailbox
        except Exception as exc:
            messagebox.showerror("No se pudo enviar", str(exc), parent=self)
            return
        self._gestor.registrar_envio_comunicacion({
            "comunicacion_id": self._comunicacion_id,
            "codigo_empresa": self._codigo,
            "asunto": subject if send_personal else self._message.get("asunto") or "",
            "remitente": result.sender,
            "destinatarios": [self._message.get("remitente") or ""],
            "cc": [], "cuerpo_html": body_html,
            "estado_envio": "aceptado_graph",
            "graph_message_id": result.message_id,
            "internet_message_id": result.internet_message_id,
            "usuario_id": getattr(user, "id", None),
            "usuario_nombre": getattr(user, "nombre", None),
            "adjuntos": self._attachments,
            "mailbox": sent_mailbox,
        })
        if self._mark_answered.get():
            self._gestor.cambiar_estado_comunicacion(
                self._comunicacion_id, "respondido", getattr(user, "id", 0),
            )
        messagebox.showinfo("Correo", "Respuesta enviada y registrada.", parent=self)
        self._on_sent()
        self.destroy()
