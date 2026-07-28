from __future__ import annotations

import html
import json
import tkinter as tk
from html.parser import HTMLParser
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.graph_mail_service import GraphMailService
from utils.utilidades import (
    load_app_config,
    load_user_config,
    get_install_dir,
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
  <div><strong>Gestinem</strong></div>
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


def html_a_texto(value: str) -> str:
    parser = _HTMLToText()
    parser.feed(value or "")
    lines = [line.rstrip() for line in "".join(parser.parts).splitlines()]
    texto = "\n".join(lines).strip()
    while "\n\n\n" in texto:
        texto = texto.replace("\n\n\n", "\n\n")
    return texto


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
        self._tree = ttk.Treeview(
            self, columns=("fecha", "asunto", "remitente", "estado", "mensajes"),
            show="headings", selectmode="browse",
        )
        for key, title, width in (
            ("fecha", "Ultima actividad", 170), ("asunto", "Asunto", 430),
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
            self._tree.insert("", "end", iid=row["id"], values=(
                row.get("ultima_fecha") or "", row.get("asunto") or "",
                row.get("ultimo_remitente") or "", row.get("estado") or "",
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
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        for message in messages:
            message["adjuntos"] = [
                dict(row) for row in self._gestor.conn.execute(
                    "SELECT nombre,ruta,tamano FROM comunicaciones_adjuntos WHERE mensaje_id=? ORDER BY nombre",
                    (message["id"],),
                ).fetchall()
            ]
        CommunicationDetailDialog(self, messages)


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
    def __init__(self, parent, messages: list[dict]):
        super().__init__(parent)
        self.title("Historial de la comunicacion")
        self.geometry("900x650")
        self.transient(parent.winfo_toplevel())
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self._messages = messages
        self._list = ttk.Treeview(
            frame, columns=("fecha", "remitente", "asunto", "estado"),
            show="headings", height=7, selectmode="browse",
        )
        for key, title, width in (
            ("fecha", "Fecha", 180), ("remitente", "Remitente", 220),
            ("asunto", "Asunto", 330), ("estado", "Estado", 120),
        ):
            self._list.heading(key, text=title)
            self._list.column(key, width=width, anchor="w")
        self._list.pack(fill="x")
        self._list.bind("<<TreeviewSelect>>", self._show)
        self._content = tk.Text(frame, wrap="word", state="disabled")
        self._content.pack(fill="both", expand=True, pady=(10, 0))
        for index, item in enumerate(messages):
            self._list.insert("", "end", iid=str(index), values=(
                item.get("fecha") or "", item.get("remitente") or "",
                item.get("asunto") or "", item.get("estado_envio") or "",
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
        destinatarios = ", ".join(json.loads(message.get("destinatarios_json") or "[]"))
        cc = ", ".join(json.loads(message.get("cc_json") or "[]")) or "-"
        adjuntos = message.get("adjuntos") or []
        nombres = ", ".join(item.get("nombre") or "" for item in adjuntos) or "Ninguno"
        error = message.get("error_envio") or "-"
        contenido = (
            f"De: {message.get('remitente') or ''}\n"
            f"Para: {destinatarios}\n"
            f"CC: {cc}\n"
            f"Fecha: {message.get('fecha') or ''}\n"
            f"Estado: {message.get('estado_envio') or ''}\n"
            f"Adjuntos: {nombres}\n"
            f"Error: {error}\n\n"
            f"Asunto: {message.get('asunto') or ''}\n\n"
            f"{html_a_texto(message.get('cuerpo_html') or '')}"
        )
        self._set_content(contenido)

    def _set_content(self, value: str):
        self._content.configure(state="normal")
        self._content.delete("1.0", "end")
        self._content.insert("1.0", value)
        self._content.configure(state="disabled")


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
        ttk.Combobox(
            form, textvariable=self._sender, state="readonly",
            values=("Mi cuenta de Microsoft 365", f"Buzon compartido: {shared}"),
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
        sender = "me" if self._sender.get().startswith("Mi cuenta") else shared
        is_shared = sender != "me"
        signature = (
            FIRMA_OFICINA_HTML
            if is_shared
            else (
                load_user_config().get("email_signature_html")
                or FIRMA_PERSONAL_HTML
            )
        )
        user = getattr(self._session, "user", None)
        body_html = construir_cuerpo_html(
            plain, signature,
            "" if is_shared else getattr(user, "nombre", ""),
        )
        logo_path = get_install_dir() / "logo.png"
        inline_attachments = (
            [{"path": str(logo_path), "content_id": "gestinem-logo"}]
            if "cid:gestinem-logo" in signature else []
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
        })
        messagebox.showinfo("Correo", "Exchange ha aceptado el mensaje y se ha registrado.", parent=self)
        self._on_sent()
        self.destroy()
