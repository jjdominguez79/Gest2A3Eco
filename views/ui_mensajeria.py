from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.gestion_documental_service import GestionDocumentalService
from services.mensajeria_service import MensajeriaRemoteClient


class UIMensajeria(ttk.Frame):
    def __init__(self, parent, gestor, session):
        super().__init__(parent, padding=8)
        self.gestor = gestor
        self.session = session
        self.client = MensajeriaRemoteClient(
            user_id=session.user.id, user_name=session.user.nombre,
        )
        self.conversations = {}
        self.messages = {}
        self.attachments = {}
        self.selected_files: list[str] = []
        self._event_stop = threading.Event()
        self._event_started = False
        self._event_refresh_id = None
        self._build()
        self.bind("<Destroy>", self._on_destroy, add="+")
        if self.client.configured:
            self.after_idle(self.refresh)
            self.after(1_500, self._sync_attachments)
            self._schedule_refresh()
        else:
            self.status.configure(text="Mensajeria no configurada")

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="left")
        ttk.Button(bar, text="Actualizar", command=self.refresh).pack(side="right")
        if self.session.is_admin():
            ttk.Button(bar, text="Activar cliente / invitar", command=self._invite).pack(side="right", padx=6)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        chats = ttk.Frame(notebook, padding=4)
        incoming = ttk.Frame(notebook, padding=4)
        notebook.add(chats, text="Chats")
        notebook.add(incoming, text="Adjuntos por clasificar")
        self._build_chats(chats)
        self._build_incoming(incoming)

    def _build_chats(self, parent):
        paned = ttk.Panedwindow(parent, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1); paned.add(right, weight=3)
        self.conv_tree = ttk.Treeview(left, columns=("cliente", "tipo", "estado", "fecha"), show="headings")
        for key, title, width in (("cliente", "Cliente", 190), ("tipo", "Tipo", 75), ("estado", "Estado", 95), ("fecha", "Actividad", 145)):
            self.conv_tree.heading(key, text=title); self.conv_tree.column(key, width=width, anchor="w")
        self.conv_tree.pack(fill="both", expand=True)
        self.conv_tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected())

        controls = ttk.Frame(right); controls.pack(fill="x", pady=(0, 5))
        ttk.Button(controls, text="Pendiente", command=lambda: self._set_state("pendiente")).pack(side="left")
        ttk.Button(controls, text="En curso", command=lambda: self._set_state("en_curso")).pack(side="left", padx=4)
        ttk.Button(controls, text="Resuelta", command=lambda: self._set_state("resuelta")).pack(side="left")
        ttk.Button(controls, text="Asignarme", command=self._assign_me).pack(side="left", padx=8)

        self.msg_tree = ttk.Treeview(right, columns=("fecha", "autor", "mensaje", "adjuntos"), show="headings", height=12)
        for key, title, width in (("fecha", "Fecha", 145), ("autor", "Autor", 150), ("mensaje", "Mensaje", 420), ("adjuntos", "Adjuntos", 80)):
            self.msg_tree.heading(key, text=title); self.msg_tree.column(key, width=width, anchor="w")
        self.msg_tree.pack(fill="both", expand=True)
        self.msg_tree.bind("<<TreeviewSelect>>", lambda _event: self._show_message_attachments())
        self.att_tree = ttk.Treeview(right, columns=("nombre", "tamano", "caduca"), show="headings", height=3)
        for key, title, width in (("nombre", "Adjunto", 320), ("tamano", "Tamano", 90), ("caduca", "Disponible hasta", 170)):
            self.att_tree.heading(key, text=title); self.att_tree.column(key, width=width, anchor="w")
        self.att_tree.pack(fill="x", pady=(5, 0))
        ttk.Button(right, text="Ver registro de descargas", command=self._show_downloads).pack(anchor="e", pady=(4, 0))

        compose = ttk.LabelFrame(right, text="Responder", padding=6); compose.pack(fill="x", pady=(7, 0))
        self.body = tk.Text(compose, height=3, wrap="word"); self.body.pack(fill="x")
        actions = ttk.Frame(compose); actions.pack(fill="x", pady=(5, 0))
        self.file_label = ttk.Label(actions, text="Sin adjuntos"); self.file_label.pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Adjuntar", command=self._choose_files).pack(side="right", padx=4)
        ttk.Button(actions, text="Enviar", command=self._send).pack(side="right")

    def _build_incoming(self, parent):
        self.incoming_tree = ttk.Treeview(
            parent, columns=("cliente", "archivo", "remitente", "fecha"), show="headings",
        )
        for key, title, width in (("cliente", "Cliente", 220), ("archivo", "Archivo", 330), ("remitente", "Enviado por", 180), ("fecha", "Recibido", 170)):
            self.incoming_tree.heading(key, text=title); self.incoming_tree.column(key, width=width, anchor="w")
        self.incoming_tree.pack(fill="both", expand=True)
        actions = ttk.Frame(parent); actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Descargar nuevos", command=self._sync_attachments).pack(side="left")
        ttk.Button(actions, text="Abrir", command=self._open_incoming).pack(side="left", padx=5)
        ttk.Button(actions, text="Clasificar", command=self._classify).pack(side="left")
        ttk.Button(actions, text="No guardar", command=self._ignore).pack(side="left", padx=5)

    def _run(self, label, work, done=None):
        self.status.configure(text=label)
        def worker():
            try: result, error = work(), None
            except Exception as exc: result, error = None, exc
            self.after(0, lambda: self._finish(result, error, done))
        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, result, error, done):
        if error:
            self.status.configure(text="Error")
            messagebox.showerror("Mensajeria", str(error), parent=self)
            return
        self.status.configure(text="Actualizado")
        if done: done(result)

    def refresh(self):
        def work():
            self.client.sync_staff(role=str(getattr(self.session.role, "value", self.session.role)))
            return self.client.list_conversations()
        self._run("Actualizando chats...", work, self._render_conversations)
        self._render_incoming()

    def _schedule_refresh(self):
        if not self.winfo_exists():
            return
        self.after(30_000, self._periodic_refresh)

    def _periodic_refresh(self):
        if not self.winfo_exists():
            return
        self.refresh()
        self._sync_attachments(silent=True)
        self._schedule_refresh()

    def _render_conversations(self, rows):
        self.conv_tree.delete(*self.conv_tree.get_children()); self.conversations = {}
        for item in rows:
            self.conversations[item["id"]] = item
            self.conv_tree.insert("", "end", iid=item["id"], values=(
                item.get("company_name"), "Privado" if item.get("kind") == "private" else "General",
                item.get("state"), item.get("updated_at"),
            ))
        if not self._event_started:
            self._event_started = True
            threading.Thread(
                target=self.client.listen_events,
                args=(self._event_stop, self._on_remote_event), daemon=True,
            ).start()

    def _on_remote_event(self, _event_type, _data):
        try:
            self.after(0, self._schedule_event_refresh)
        except (RuntimeError, tk.TclError):
            pass

    def _schedule_event_refresh(self):
        if self._event_refresh_id is not None:
            return
        self._event_refresh_id = self.after(250, self._refresh_from_event)

    def _refresh_from_event(self):
        self._event_refresh_id = None
        self.refresh()
        self._sync_attachments(silent=True)
        if self._selected_conversation_id():
            self._load_selected()

    def _on_destroy(self, event):
        if event.widget is self:
            self._event_stop.set()

    def _selected_conversation_id(self):
        selected = self.conv_tree.selection()
        return selected[0] if selected else ""

    def _load_selected(self):
        conversation_id = self._selected_conversation_id()
        if conversation_id:
            self._run("Cargando conversacion...", lambda: self.client.list_messages(conversation_id), self._render_messages)

    def _render_messages(self, rows):
        self.msg_tree.delete(*self.msg_tree.get_children()); self.messages = {}; self.attachments = {}
        for item in rows:
            self.messages[item["id"]] = item
            for attachment in item.get("attachments") or []:
                self.attachments[attachment["id"]] = attachment
            self.msg_tree.insert("", "end", iid=item["id"], values=(
                item.get("created_at"), item.get("author_name"),
                (item.get("body") or "").replace("\n", " ")[:240], len(item.get("attachments") or []),
            ))

    def _show_message_attachments(self):
        self.att_tree.delete(*self.att_tree.get_children())
        selected = self.msg_tree.selection()
        if not selected: return
        for item in self.messages[selected[0]].get("attachments") or []:
            self.att_tree.insert("", "end", iid=item["id"], values=(
                item["name"], self._size(item.get("size")), item.get("expires_at") or "Entregado al despacho",
            ))

    @staticmethod
    def _size(value):
        size = int(value or 0)
        return f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.0f} KB"

    def _choose_files(self):
        self.selected_files = list(filedialog.askopenfilenames(parent=self, title="Seleccionar adjuntos"))
        self.file_label.configure(text=", ".join(Path(path).name for path in self.selected_files) or "Sin adjuntos")

    def _send(self):
        conversation_id = self._selected_conversation_id(); body = self.body.get("1.0", "end").strip()
        if not conversation_id or (not body and not self.selected_files): return
        paths = list(self.selected_files)
        def done(_result):
            self.body.delete("1.0", "end"); self.selected_files = []; self.file_label.configure(text="Sin adjuntos"); self._load_selected()
        self._run("Enviando...", lambda: self.client.send_message(conversation_id, body, paths), done)

    def _set_state(self, state):
        conversation_id = self._selected_conversation_id()
        if conversation_id: self._run("Actualizando...", lambda: self.client.update_conversation(conversation_id, state=state), lambda _r: self.refresh())

    def _assign_me(self):
        conversation_id = self._selected_conversation_id()
        if conversation_id: self._run("Asignando...", lambda: self.client.update_conversation(conversation_id, assigned_to=str(self.session.user.id)), lambda _r: self.refresh())

    def _show_downloads(self):
        selected = self.att_tree.selection()
        if not selected: return
        attachment = self.attachments.get(selected[0]) or {}
        if attachment.get("direction") != "outgoing":
            messagebox.showinfo("Descargas", "Este archivo fue enviado por el cliente.", parent=self); return
        def done(rows):
            if not rows: text = "El cliente todavia no ha descargado el documento."
            else: text = "\n".join(f"{r.get('downloaded_at')} · {r.get('client_name')} · {r.get('ip')}" for r in rows)
            messagebox.showinfo("Registro de descargas", text, parent=self)
        self._run("Consultando descargas...", lambda: self.client.download_audit(selected[0]), done)

    def _sync_attachments(self, silent=False):
        def done(result):
            self._render_incoming()
            if result.errors and not silent: messagebox.showwarning("Adjuntos", "\n".join(result.errors), parent=self)
        self._run("Descargando adjuntos...", lambda: self.client.download_pending_attachments(self.gestor), done)

    def _render_incoming(self):
        self.incoming_tree.delete(*self.incoming_tree.get_children())
        for item in self.gestor.listar_adjuntos_mensajeria_entrada():
            self.incoming_tree.insert("", "end", iid=item["id"], values=(
                item.get("empresa_nombre") or item.get("codigo_empresa"), item.get("nombre_original"),
                item.get("remitente"), item.get("created_at"),
            ))

    def _selected_incoming(self):
        selected = self.incoming_tree.selection()
        return self.gestor.get_adjunto_mensajeria_entrada(selected[0]) if selected else None

    def _open_incoming(self):
        item = self._selected_incoming()
        if item and Path(item["ruta_entrada"]).is_file():
            import os
            os.startfile(item["ruta_entrada"])

    def _classify(self):
        item = self._selected_incoming()
        if not item: return
        categories = self.gestor.listar_categorias_documentales()
        names = {row["nombre"]: row for row in categories}
        category_name = simpledialog.askstring(
            "Clasificar adjunto", "Destino:\n" + "\n".join(names),
            initialvalue="Facturas recibidas", parent=self,
        )
        category = names.get(str(category_name or "").strip())
        if not category:
            messagebox.showwarning("Clasificar", "Selecciona exactamente una categoria de la lista.", parent=self); return
        companies = [row for row in self.gestor.listar_empresas() if str(row.get("codigo")) == str(item["codigo_empresa"])]
        exercise = max((int(row.get("ejercicio") or 0) for row in companies), default=0)
        if not exercise:
            messagebox.showerror("Clasificar", "No se encontro el ejercicio del cliente.", parent=self); return
        try:
            document_id = GestionDocumentalService(self.gestor).archivar_adjunto_mensajeria(
                item, ejercicio=exercise, categoria_id=category["id"], usuario=self.session.user.nombre,
            )
            self.gestor.actualizar_adjunto_mensajeria_entrada(item["id"], "archivado", documento_id=document_id)
            self._render_incoming()
            extra = " Ya puede enviarse a OCR desde Gestion documental." if category.get("permite_ocr") else ""
            messagebox.showinfo("Clasificar", "Documento archivado." + extra, parent=self)
        except Exception as exc:
            messagebox.showerror("Clasificar", str(exc), parent=self)

    def _ignore(self):
        item = self._selected_incoming()
        if not item: return
        if messagebox.askyesno("No guardar", "¿Marcar este adjunto como no guardado?", parent=self):
            Path(item["ruta_entrada"]).unlink(missing_ok=True)
            self.gestor.actualizar_adjunto_mensajeria_entrada(item["id"], "no_guardar")
            self._render_incoming()

    def _invite(self):
        companies = {}
        for row in self.gestor.listar_empresas():
            code = str(row.get("codigo") or "")
            if code not in companies or int(row.get("ejercicio") or 0) > int(companies[code].get("ejercicio") or 0): companies[code] = row
        code = simpledialog.askstring("Mensajeria", "Codigo de empresa:", parent=self)
        company = companies.get(str(code or "").strip())
        if not company:
            messagebox.showerror("Mensajeria", "Empresa no encontrada.", parent=self); return
        users = [row for row in self.gestor.listar_usuarios() if bool(row.get("activo")) and str(row.get("rol")) in {"admin", "empleado"}]
        owner_options = {f"{row.get('nombre')} [{row.get('id')}]": str(row.get("id")) for row in users}
        default_owner = next((label for label, value in owner_options.items() if value == str(self.session.user.id)), "")
        owner_label = simpledialog.askstring(
            "Chat privado", "Titular del chat privado:\n" + "\n".join(owner_options),
            initialvalue=default_owner, parent=self,
        )
        owner_id = owner_options.get(str(owner_label or "").strip())
        if not owner_id:
            messagebox.showerror("Mensajeria", "Selecciona exactamente un titular de la lista.", parent=self); return
        name = simpledialog.askstring("Invitacion", "Nombre del contacto:", parent=self)
        email = simpledialog.askstring("Invitacion", "Email del contacto:", parent=self)
        if not name or not email: return
        def work():
            self.client.sync_organization(code=code, name=company.get("nombre") or code, private_owner_id=owner_id)
            return self.client.invite(code=code, name=name, email=email)
        def done(result):
            self.clipboard_clear(); self.clipboard_append(result["url"])
            prefix = "Invitacion encolada para envio por email.\n\n" if result.get("email_queued") else "SMTP cloud no configurado; usa el enlace copiado.\n\n"
            messagebox.showinfo("Invitacion", prefix + result["url"], parent=self)
            self.refresh()
        self._run("Creando invitacion...", work, done)
