from __future__ import annotations

import html
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.graph_mail_service import GraphMailService
from utils.utilidades import load_app_config, save_app_config


def _emails(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


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

    def _compose(self):
        ComposeMailDialog(self, self._gestor, self._codigo, self._empresa, self._session, self._refresh)

    def _detail(self, _event=None):
        selected = self._tree.selection()
        if not selected:
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        body = "\n\n".join(
            f"{m.get('fecha','')} · {m.get('remitente','')} · {m.get('estado_envio','')}\n"
            f"{m.get('asunto','')}\n{m.get('cuerpo_html','')}"
            for m in messages
        )
        messagebox.showinfo("Historial de la comunicacion", body or "Sin mensajes.", parent=self)


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
        actions = ttk.Frame(form)
        actions.grid(row=6, column=1, sticky="e", pady=14)
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
        service = GraphMailService()
        user = getattr(self._session, "user", None)
        try:
            result = service.send(
                sender=sender, to=to, cc=cc, subject=subject,
                body=f"<html><body>{html.escape(plain).replace(chr(10), '<br>')}</body></html>",
                attachments=self._attachments,
            )
        except Exception as exc:
            self._gestor.registrar_envio_comunicacion({
                "codigo_empresa": self._codigo, "asunto": subject,
                "remitente": sender, "destinatarios": to, "cc": cc,
                "cuerpo_html": plain, "estado_envio": "error",
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
            "cuerpo_html": plain, "estado_envio": "aceptado_graph",
            "graph_message_id": result.message_id,
            "internet_message_id": result.internet_message_id,
            "usuario_id": getattr(user, "id", None),
            "usuario_nombre": getattr(user, "nombre", None),
            "adjuntos": self._attachments,
        })
        messagebox.showinfo("Correo", "Exchange ha aceptado el mensaje y se ha registrado.", parent=self)
        self._on_sent()
        self.destroy()
