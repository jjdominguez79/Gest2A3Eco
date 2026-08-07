from __future__ import annotations

import json
import logging
import os
import threading
import tkinter as tk
import unicodedata
from tkinter import messagebox, simpledialog, ttk

from services.documentos_correo_service import DocumentosCorreoService
from services.gestion_documental_service import GestionDocumentalService
from utils.utilidades import load_app_config
from views.ui_comunicaciones import CommunicationDetailDialog, ReplyMailDialog


LOG = logging.getLogger(__name__)
AUTO_REFRESH_MS = 30_000


def _normalizar_texto(value: str) -> str:
    """Normaliza nombres para casar el responsable de la ficha con un usuario."""
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()


def _buscar_usuario_responsable(company: dict, users: dict) -> dict | None:
    """Devuelve el usuario que coincide con empresas.responsable, si existe."""
    responsable = _normalizar_texto(company.get("responsable"))
    if not responsable:
        return None
    candidatos = []
    for user in users.values():
        nombres = (
            user.get("nombre"), user.get("username"),
        )
        if any(_normalizar_texto(value) == responsable for value in nombres):
            return user
        if len(responsable) >= 3 and any(
            _normalizar_texto(value).startswith(responsable) for value in nombres
        ):
            candidatos.append(user)
    return candidatos[0] if len(candidatos) == 1 else None


class ReassignCommunicationDialog(tk.Toplevel):
    def __init__(self, parent, companies, users, item, on_save):
        super().__init__(parent)
        self.title("Reasignar comunicacion")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, False)
        self._companies = companies
        self._users = users
        self._on_save = on_save

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text=item.get("asunto") or "(Sin asunto)",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Buscar cliente").grid(row=1, column=0, sticky="w")
        self._search = tk.StringVar()
        ttk.Entry(frame, textvariable=self._search, width=44).grid(
            row=1, column=1, sticky="ew", padx=(8, 0),
        )
        ttk.Label(frame, text="Cliente").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._company = tk.StringVar()
        self._company_combo = ttk.Combobox(
            frame, textvariable=self._company, state="readonly", width=42,
        )
        self._company_combo.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(frame, text="Responsable").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._user = tk.StringVar()
        user_combo = ttk.Combobox(
            frame, textvariable=self._user, state="readonly", width=32,
            values=sorted(users),
        )
        user_combo.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        self._company_combo.bind("<<ComboboxSelected>>", lambda _event: self._suggest_responsible())
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Guardar reasignacion", command=self._save).pack(side="left")
        frame.columnconfigure(1, weight=1)

        current_code = str(item.get("codigo_empresa") or "")
        for label, company in companies.items():
            if str(company.get("codigo") or "") == current_code:
                self._company.set(label)
                break
        current_user = item.get("responsable_usuario_id")
        for label, user in users.items():
            if current_user is not None and int(user["id"]) == int(current_user):
                self._user.set(label)
                break
        self._search.trace_add("write", lambda *_: self._filter_companies())
        self._filter_companies()
        self._suggest_responsible()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.focus_set()

    def _filter_companies(self):
        query = self._search.get().strip().lower()
        values = [
            label for label, company in self._companies.items()
            if not query or query in " ".join((
                label, str(company.get("cif") or ""),
                str(company.get("email") or ""),
            )).lower()
        ]
        self._company_combo["values"] = sorted(values)

    def _suggest_responsible(self):
        company = self._companies.get(self._company.get())
        user = _buscar_usuario_responsable(company or {}, self._users)
        if user:
            for label, candidate in self._users.items():
                if candidate.get("id") == user.get("id"):
                    self._user.set(label)
                    break

    def _save(self):
        company = self._companies.get(self._company.get())
        user = self._users.get(self._user.get())
        if not company or not user:
            messagebox.showwarning(
                "Reasignacion", "Selecciona un cliente y un responsable.", parent=self,
            )
            return
        self._on_save(company, user)
        self.destroy()


class AttachmentSelectionDialog(tk.Toplevel):
    """Seleccion multiple de adjuntos antes de incorporarlos al OCR."""
    def __init__(self, parent, attachments: list[dict], on_save):
        super().__init__(parent)
        self.title("Adjuntos del correo")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._attachments = attachments
        self._on_save = on_save
        self._selected = {str(item.get("id")): tk.BooleanVar(value=True) for item in attachments}
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Marca los adjuntos que quieres guardar en Documentacion/OCR.").pack(anchor="w", pady=(0, 8))
        for item in attachments:
            name = str(item.get("name") or "Adjunto")
            size = int(item.get("size") or 0)
            text = f"{name}  ({size / 1024:.1f} KB)"
            ttk.Checkbutton(frame, text=text, variable=self._selected[str(item.get("id"))]).pack(anchor="w", pady=2)
        actions = ttk.Frame(frame)
        actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Guardar seleccionados", command=self._save).pack(side="left")

    def _save(self):
        selected = [item_id for item_id, value in self._selected.items() if value.get()]
        if not selected:
            messagebox.showwarning("Documentacion", "Marca al menos un adjunto.", parent=self)
            return
        self._on_save(selected)
        self.destroy()


class AttachmentPreviewDialog(tk.Toplevel):
    """Lista adjuntos y permite abrir una copia temporal sin asignar el correo."""

    def __init__(self, parent, attachments: list[dict], on_open, on_inspect=None):
        super().__init__(parent)
        self.title("Revisar adjuntos del correo")
        self.geometry("680x360")
        self.transient(parent.winfo_toplevel())
        self._attachments = {
            str(item.get("id") or ""): item for item in attachments
        }
        self._on_open = on_open
        self._on_inspect = on_inspect
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                "Abre una copia temporal para identificar el cliente. "
                "El adjunto no se guardara en Documentacion hasta que lo asignes."
            ),
            wraplength=640,
        ).pack(anchor="w", pady=(0, 8))
        self._tree = ttk.Treeview(
            frame, columns=("nombre", "tipo", "tamano"),
            show="headings", selectmode="browse",
        )
        for key, title, width in (
            ("nombre", "Archivo", 390), ("tipo", "Tipo", 150),
            ("tamano", "Tamano", 100),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        for item_id, item in self._attachments.items():
            size = int(item.get("size") or 0)
            self._tree.insert("", "end", iid=item_id, values=(
                item.get("name") or "Adjunto",
                item.get("contentType") or "",
                f"{size / 1024:.1f} KB",
            ))
        self._tree.bind("<Double-1>", lambda _event: self._open())
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Cerrar", command=self.destroy).pack(side="right")
        ttk.Button(
            actions, text="Abrir adjunto", command=self._open,
        ).pack(side="right", padx=(0, 7))
        ttk.Button(
            actions, text="Ver contenido ZIP", command=self._inspect,
        ).pack(side="right", padx=(0, 7))
        if self._attachments:
            first = next(iter(self._attachments))
            self._tree.selection_set(first)
            self._tree.focus(first)

    def _open(self):
        selected = self._tree.selection()
        if selected:
            self._on_open(selected[0])

    def _inspect(self):
        selected = self._tree.selection()
        if not selected or not self._on_inspect:
            return
        item = self._attachments[selected[0]]
        if not str(item.get("name") or "").lower().endswith(".zip"):
            messagebox.showinfo("ZIP", "Selecciona un archivo ZIP.", parent=self)
            return
        self._on_inspect(selected[0])


class ArchiveContentsDialog(tk.Toplevel):
    """Contenido de un ZIP, sin ejecutar ni extraer todos sus archivos."""

    def __init__(self, parent, members: list[dict], on_open,
                 companies=None, categories=None, on_assign=None):
        super().__init__(parent)
        self.title("Contenido del ZIP")
        self.geometry("700x400")
        self.transient(parent.winfo_toplevel())
        self._members = {item["name"]: item for item in members}
        self._on_open = on_open
        self._companies = companies or {}
        self._categories = {item["nombre"]: item for item in (categories or [])}
        self._on_assign = on_assign
        self._values = {item["name"]: {"company": "", "category": ""} for item in members}
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Puedes abrir un documento concreto. Los demás archivos no se extraen.",
        ).pack(anchor="w", pady=(0, 8))
        self._tree = ttk.Treeview(
            frame, columns=("nombre", "tamano", "cliente", "categoria"),
            show="headings", selectmode="extended",
        )
        self._tree.heading("nombre", text="Documento")
        self._tree.heading("tamano", text="Tamano")
        self._tree.heading("cliente", text="Cliente")
        self._tree.heading("categoria", text="Categoria")
        self._tree.column("nombre", width=540, anchor="w")
        self._tree.column("tamano", width=90, anchor="e")
        self._tree.column("cliente", width=180, anchor="w")
        self._tree.column("categoria", width=150, anchor="w")
        self._tree.pack(fill="both", expand=True)
        for name, item in self._members.items():
            self._tree.insert("", "end", iid=name, values=(
                name, f"{item['size'] / 1024:.1f} KB", "", "",
            ))
        self._tree.bind("<Double-1>", lambda _event: self._open())
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Label(controls, text="Asignar seleccionados a").pack(side="left")
        self._company = tk.StringVar()
        ttk.Combobox(
            controls, textvariable=self._company, state="readonly", width=28,
            values=sorted(self._companies),
        ).pack(side="left", padx=5)
        self._category = tk.StringVar()
        ttk.Combobox(
            controls, textvariable=self._category, state="readonly", width=22,
            values=sorted(self._categories),
        ).pack(side="left", padx=5)
        ttk.Button(controls, text="Aplicar", command=self._apply_assignment).pack(side="left")
        ttk.Button(controls, text="Abrir documento", command=self._open).pack(side="right")
        if self._on_assign:
            ttk.Button(controls, text="Guardar asignaciones", command=self._assign).pack(side="right", padx=(0, 7))
        if members:
            self._tree.selection_set(members[0]["name"])

    def _open(self):
        selected = self._tree.selection()
        if selected:
            self._on_open(selected[0])

    def _apply_assignment(self):
        company = self._company.get()
        category = self._category.get()
        if not company or not category:
            messagebox.showwarning("ZIP", "Selecciona cliente y categoria.", parent=self)
            return
        for name in self._tree.selection():
            self._values[name] = {"company": company, "category": category}
            values = list(self._tree.item(name, "values"))
            values[2], values[3] = company, category
            self._tree.item(name, values=values)

    def _assign(self):
        decisions = [
            {"name": name, **value}
            for name, value in self._values.items()
            if value["company"] and value["category"]
        ]
        if not decisions:
            messagebox.showwarning("ZIP", "Asigna al menos un documento.", parent=self)
            return
        self._on_assign(decisions)
        self.destroy()


class AttachmentClassificationDialog(tk.Toplevel):
    """Clasifica cada adjunto antes de asignar definitivamente el correo."""

    def __init__(self, parent, attachments: list[dict], categories: list[dict], on_save):
        super().__init__(parent)
        self.title("Clasificar adjuntos antes de asignar")
        self.geometry("900x520")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._attachments = {item["key"]: item for item in attachments}
        self._categories = {item["nombre"]: item for item in categories}
        self._on_save = on_save
        self._values = {key: "No guardar" for key in self._attachments}
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                "Selecciona el destino de cada adjunto. Los marcados como "
                "No guardar solo quedaran registrados como omitidos."
            ), wraplength=850,
        ).pack(anchor="w", pady=(0, 8))
        self._tree = ttk.Treeview(
            frame, columns=("correo", "archivo", "tamano", "categoria"),
            show="headings", selectmode="extended",
        )
        for key, title, width in (
            ("correo", "Correo", 250), ("archivo", "Adjunto", 330),
            ("tamano", "Tamano", 90), ("categoria", "Destino", 180),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        for key, item in self._attachments.items():
            self._tree.insert("", "end", iid=key, values=(
                item.get("subject") or "(Sin asunto)", item.get("name") or "Adjunto",
                f"{int(item.get('size') or 0) / 1024:.1f} KB", "No guardar",
            ))
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Label(controls, text="Destino seleccionados").pack(side="left")
        self._category = tk.StringVar(value="No guardar")
        combo = ttk.Combobox(
            controls, textvariable=self._category, state="readonly", width=28,
            values=["No guardar", *self._categories.keys()],
        )
        combo.pack(side="left", padx=6)
        ttk.Button(controls, text="Aplicar", command=self._apply).pack(side="left")
        ttk.Button(controls, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(controls, text="Guardar y asignar", command=self._save).pack(side="right", padx=6)

    def _apply(self):
        value = self._category.get()
        for key in self._tree.selection():
            self._values[key] = value
            values = list(self._tree.item(key, "values"))
            values[3] = value
            self._tree.item(key, values=values)

    def _save(self):
        decisions = []
        for key, item in self._attachments.items():
            category = self._categories.get(self._values[key])
            decisions.append({
                **item, "categoria_id": (category or {}).get("id") or "",
            })
        self._on_save(decisions)
        self.destroy()


class UIComunicacionesGlobal(ttk.Frame):
    def __init__(self, parent, gestor, session):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._session = session
        self._pending: dict[str, dict] = {}
        self._mine: dict[str, dict] = {}
        self._supervision: dict[str, dict] = {}
        self._discarded: dict[str, dict] = {}
        self._companies: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
        self._auto_refresh_after_id = None
        self._auto_refresh_running = False
        self._destroying = False
        self._refresh_generation = 0
        self._build()
        self.bind("<Destroy>", self._on_destroy, add="+")
        # No bloquear el hilo de Tkinter: en una base compartida estas consultas
        # pueden tardar lo suficiente para dejar el Buzon aparentemente en blanco.
        self.after_idle(self._refresh)
        self._schedule_auto_refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Buzon de comunicaciones", font=("Segoe UI", 16, "bold")).pack(side="left")
        self._loading_label = ttk.Label(top, text="Cargando mensajes...", foreground="#64748b")
        self._loading_label.pack(side="right")

        tabs = ttk.Notebook(self)
        self._tabs = tabs
        tabs.pack(fill="both", expand=True)
        pending_tab = ttk.Frame(tabs, padding=8)
        mine_tab = ttk.Frame(tabs, padding=8)
        tabs.add(pending_tab, text="Entrada sin asignar")
        tabs.add(mine_tab, text="Mi buzon")
        supervision_tab = None
        if self._session.is_admin():
            supervision_tab = ttk.Frame(tabs, padding=8)
            tabs.add(supervision_tab, text="Supervision")
            discarded_tab = ttk.Frame(tabs, padding=8)
            tabs.add(discarded_tab, text="Descartados")

        self._pending_tree = self._tree(
            pending_tab,
            (("fecha", "Fecha", 170), ("buzon", "Buzon", 180),
             ("remitente", "Remitente", 230), ("asunto", "Asunto", 330),
             ("adjuntos", "Adjuntos", 85),
             ("etiqueta", "Etiqueta", 150),
             ("sugerencia", "Cliente sugerido", 220)),
            selectmode="extended",
        )
        assign = ttk.Frame(pending_tab)
        assign.pack(fill="x", pady=(8, 0))
        ttk.Label(assign, text="Buscar cliente").grid(row=0, column=0, sticky="w")
        self._company_search = tk.StringVar()
        search_company = ttk.Entry(assign, textvariable=self._company_search, width=30)
        search_company.grid(row=0, column=1, sticky="ew", padx=5)
        self._company_search.trace_add("write", lambda *_: self._filter_companies())
        ttk.Label(assign, text="Cliente").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self._company_var = tk.StringVar()
        self._company_combo = ttk.Combobox(assign, textvariable=self._company_var, state="readonly", width=42)
        self._company_combo.grid(row=0, column=3, sticky="ew", padx=5)
        self._company_combo.bind("<<ComboboxSelected>>", lambda _event: self._suggest_pending_responsible())
        ttk.Label(assign, text="Responsable").grid(row=1, column=0, sticky="w", pady=(7, 0))
        self._user_var = tk.StringVar()
        self._user_combo = ttk.Combobox(assign, textvariable=self._user_var, state="readonly", width=28)
        self._user_combo.grid(row=1, column=1, sticky="w", padx=5, pady=(7, 0))
        self._selection_label = ttk.Label(assign, text="0 mensajes seleccionados")
        self._selection_label.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(7, 0))
        buttons = ttk.Frame(assign)
        buttons.grid(row=1, column=3, sticky="e", pady=(7, 0))
        ttk.Button(
            buttons, text="Seleccionar mismo remitente",
            command=self._select_same_sender,
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            buttons, text="Editar etiqueta",
            command=lambda: self._edit_label("pending"),
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            buttons, text="Revisar adjuntos",
            command=self._preview_selected_pending,
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            buttons, text="Asignar sin cliente",
            command=self._assign_without_client,
        ).pack(side="left", padx=(0, 5))
        if self._session.is_admin():
            ttk.Button(
                buttons, text="Descartar",
                command=self._discard,
            ).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Asignar seleccionados", command=self._assign).pack(side="left")
        assign.columnconfigure(1, weight=1)
        assign.columnconfigure(3, weight=1)
        self._pending_tree.bind("<<TreeviewSelect>>", self._on_pending_selection)
        self._pending_tree.bind("<Double-1>", lambda _event: self._pending_detail())

        self._mine_tree = self._tree(
            mine_tab,
            (("fecha", "Ultima actividad", 170), ("cliente", "Cliente", 220),
             ("etiqueta", "Etiqueta", 150), ("asunto", "Asunto", 320),
             ("remitente", "Remitente", 210),
             ("estado", "Estado", 110)),
        )
        actions = ttk.Frame(mine_tab)
        actions.pack(fill="x", pady=(8, 0))
        for estado, label in (
            ("pendiente", "Marcar pendiente"),
            ("respondido", "Marcar respondido"),
            ("gestionado", "Marcar gestionado"),
        ):
            ttk.Button(
                actions, text=label,
                command=lambda value=estado: self._set_status(value),
            ).pack(side="left", padx=(0, 5))
        ttk.Button(
            actions, text="Editar etiqueta",
            command=lambda: self._edit_label("mine"),
        ).pack(side="left", padx=(8, 5))
        ttk.Button(
            actions, text="Responder",
            command=lambda: self._reply_selected("mine"),
        ).pack(side="left", padx=(0, 5))
        if self._session.is_admin():
            ttk.Button(
                actions, text="Reasignar",
                command=lambda: self._reassign("mine"),
            ).pack(side="left", padx=(8, 5))
            ttk.Button(
                actions, text="Descartar",
                command=lambda: self._discard_assigned("mine"),
            ).pack(side="left", padx=(0, 5))
        ttk.Button(actions, text="Ver conversacion", command=self._detail).pack(side="right")
        self._mine_tree.bind("<Double-1>", lambda _event: self._detail())

        if supervision_tab is not None:
            self._build_supervision(supervision_tab)
            self._build_discarded(discarded_tab)

    def _build_discarded(self, parent):
        self._discarded_tree = self._tree(
            parent,
            (("fecha", "Fecha", 170), ("buzon", "Buzon", 180),
             ("remitente", "Remitente", 240), ("asunto", "Asunto", 340),
             ("por", "Descartado por", 170), ("motivo", "Motivo", 240)),
            selectmode="extended",
        )
        ttk.Button(
            parent, text="Restaurar seleccionados",
            command=self._restore,
        ).pack(anchor="e", pady=(8, 0))

    def _build_supervision(self, parent):
        filters = ttk.Frame(parent)
        filters.pack(fill="x", pady=(0, 8))
        self._sup_status = tk.StringVar(value="Todos")
        self._sup_user = tk.StringVar(value="Todos")
        self._sup_company = tk.StringVar(value="Todos")
        self._sup_mailbox = tk.StringVar(value="Todos")
        self._sup_search = tk.StringVar()
        for label, variable, width in (
            ("Estado", self._sup_status, 14),
            ("Responsable", self._sup_user, 24),
            ("Cliente", self._sup_company, 28),
            ("Buzon", self._sup_mailbox, 24),
        ):
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 3))
            combo = ttk.Combobox(
                filters, textvariable=variable, state="readonly", width=width,
            )
            combo.pack(side="left", padx=(0, 8))
            combo.bind("<<ComboboxSelected>>", lambda _event: self._filter_supervision())
            if variable is self._sup_status:
                self._sup_status_combo = combo
            elif variable is self._sup_user:
                self._sup_user_combo = combo
            elif variable is self._sup_company:
                self._sup_company_combo = combo
            else:
                self._sup_mailbox_combo = combo
        ttk.Label(filters, text="Buscar").pack(side="left")
        search = ttk.Entry(filters, textvariable=self._sup_search, width=24)
        search.pack(side="left", padx=4, fill="x", expand=True)
        self._sup_search.trace_add("write", lambda *_: self._filter_supervision())
        self._sup_summary = ttk.Label(parent, text="")
        self._sup_summary.pack(anchor="w", pady=(0, 5))
        self._supervision_tree = self._tree(
            parent,
            (("fecha", "Ultima actividad", 165), ("buzon", "Buzon", 175),
             ("cliente", "Cliente", 210), ("responsable", "Responsable", 170),
             ("etiqueta", "Etiqueta", 145), ("asunto", "Asunto", 280),
             ("remitente", "Ultimo remitente", 200),
             ("estado", "Estado", 105)),
        )
        self._supervision_tree.bind(
            "<Double-1>", lambda _event: self._supervision_detail(),
        )
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(
            actions, text="Reasignar",
            command=lambda: self._reassign("supervision"),
        ).pack(side="left")
        ttk.Button(
            actions, text="Editar etiqueta",
            command=lambda: self._edit_label("supervision"),
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Descartar",
            command=lambda: self._discard_assigned("supervision"),
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Ver conversacion",
            command=self._supervision_detail,
        ).pack(side="right")

    @staticmethod
    def _tree(parent, columns, selectmode="browse"):
        tree = ttk.Treeview(
            parent, columns=tuple(item[0] for item in columns),
            show="headings", selectmode=selectmode,
        )
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        return tree

    def _refresh(self):
        self._refresh_generation += 1
        self._loading_label.configure(text="Cargando mensajes...")
        self._start_auto_refresh()

    def _collect_refresh_data(self) -> dict:
        data = {
            "companies": self._gestor.listar_empresas(),
            "users": self._gestor.listar_usuarios(),
            "pending": self._gestor.listar_comunicaciones_sin_asignar(),
            "mine": self._gestor.listar_buzon_responsable(self._session.user.id),
            "mine_pending": self._gestor.listar_pendientes_responsable(
                self._session.user.id
            ),
        }
        if self._session.is_admin():
            data.update({
                "supervision": self._gestor.listar_comunicaciones_supervision(),
                "supervision_unassigned": (
                    self._gestor.listar_comunicaciones_sin_cliente_asignadas()
                ),
                "discarded": self._gestor.listar_comunicaciones_descartadas(),
                "discarded_conversations": (
                    self._gestor.listar_conversaciones_descartadas()
                ),
            })
        return data

    def _apply_refresh_data(self, data: dict):
        selections = {
            "pending": self._pending_tree.selection(),
            "mine": self._mine_tree.selection(),
        }
        if self._session.is_admin():
            selections.update({
                "supervision": self._supervision_tree.selection(),
                "discarded": self._discarded_tree.selection(),
            })
        companies = {}
        for item in data["companies"]:
            code = str(item.get("codigo") or "")
            if code not in companies or int(item.get("ejercicio") or 0) > int(companies[code].get("ejercicio") or 0):
                companies[code] = item
        self._companies = {f"{item.get('nombre') or code} [{code}]": item for code, item in companies.items()}
        self._filter_companies()

        users = [item for item in data["users"] if bool(item.get("activo"))]
        self._users = {f"{item.get('nombre')} [{item.get('username')}]": item for item in users}
        self._user_combo["values"] = sorted(self._users)

        self._pending_tree.delete(*self._pending_tree.get_children())
        self._pending = {}
        allowed = self._allowed_mailboxes()
        for item in data["pending"]:
            if str(item.get("mailbox") or "").lower() not in allowed:
                continue
            graph_id = item["graph_message_id"]
            try:
                payload = json.loads(item.get("payload_json") or "{}")
            except (TypeError, ValueError):
                payload = {}
            self._pending[graph_id] = item
            self._pending_tree.insert("", "end", iid=graph_id, values=(
                item.get("fecha") or "", item.get("mailbox") or "",
                item.get("remitente") or "", item.get("asunto") or "",
                "Si" if payload.get("tiene_adjuntos") else "",
                item.get("etiqueta") or "",
                item.get("sugerencia_nombre") or "",
            ))

        self._mine_tree.delete(*self._mine_tree.get_children())
        self._mine = {}
        shared_mailbox = self._shared_mailbox()
        for item in data["mine"]:
            if str(item.get("mailbox") or "").strip().lower() != shared_mailbox:
                continue
            comm_id = item["id"]
            self._mine[comm_id] = item
            company = companies.get(str(item.get("codigo_empresa") or ""), {})
            self._mine_tree.insert("", "end", iid=comm_id, values=(
                item.get("ultima_fecha") or "",
                item.get("cliente_nombre") or company.get("nombre") or item.get("codigo_empresa"),
                item.get("etiqueta") or "",
                item.get("asunto") or "", item.get("ultimo_remitente") or "",
                item.get("estado") or "pendiente",
            ))
        for item in data["mine_pending"]:
            if str(item.get("mailbox") or "").strip().lower() != shared_mailbox:
                continue
            iid = f"pending::{item['graph_message_id']}"
            item["_pending_client"] = True
            self._mine[iid] = item
            self._mine_tree.insert("", "end", iid=iid, values=(
                item.get("fecha") or "",
                "Sin cliente" if item.get("sin_cliente_confirmado") else "Sin asignar",
                item.get("etiqueta") or "",
                item.get("asunto") or "", item.get("remitente") or "",
                item.get("estado") or "pendiente",
            ))
        if self._session.is_admin():
            self._refresh_supervision(
                data["supervision"], data["supervision_unassigned"],
            )
            self._refresh_discarded(
                data["discarded"], data["discarded_conversations"],
            )
        self._restore_selection(self._pending_tree, selections["pending"])
        self._restore_selection(self._mine_tree, selections["mine"])
        if self._session.is_admin():
            self._restore_selection(
                self._supervision_tree, selections["supervision"],
            )
            self._restore_selection(
                self._discarded_tree, selections["discarded"],
            )

    @staticmethod
    def _restore_selection(tree, selected):
        existing = [iid for iid in selected if tree.exists(iid)]
        if existing:
            tree.selection_set(existing)

    def _refresh_discarded(self, discarded=None, conversations=None):
        self._discarded_tree.delete(*self._discarded_tree.get_children())
        self._discarded = {}
        shared_mailbox = self._shared_mailbox()
        discarded = (
            self._gestor.listar_comunicaciones_descartadas()
            if discarded is None else discarded
        )
        conversations = (
            self._gestor.listar_conversaciones_descartadas()
            if conversations is None else conversations
        )
        for item in discarded:
            if str(item.get("mailbox") or "").strip().lower() != shared_mailbox:
                continue
            graph_id = item["graph_message_id"]
            iid = f"queue::{graph_id}"
            self._discarded[iid] = item
            self._discarded_tree.insert("", "end", iid=iid, values=(
                item.get("fecha") or "", item.get("mailbox") or "",
                item.get("remitente") or "", item.get("asunto") or "",
                item.get("descartado_por") or "", item.get("motivo_descarte") or "",
            ))
        for item in conversations:
            if str(item.get("mailbox") or "").strip().lower() != shared_mailbox:
                continue
            iid = f"comm::{item['id']}"
            self._discarded[iid] = item
            self._discarded_tree.insert("", "end", iid=iid, values=(
                item.get("fecha") or "", item.get("mailbox") or "",
                item.get("remitente") or "", item.get("asunto") or "",
                item.get("descartado_por") or "", item.get("motivo_descarte") or "",
            ))

    def _refresh_supervision(self, supervision=None, unassigned=None):
        shared_mailbox = self._shared_mailbox()
        supervision = (
            self._gestor.listar_comunicaciones_supervision()
            if supervision is None else supervision
        )
        unassigned = (
            self._gestor.listar_comunicaciones_sin_cliente_asignadas()
            if unassigned is None else unassigned
        )
        self._supervision = {
            item["id"]: item
            for item in supervision
            if str(item.get("mailbox") or "").strip().lower() == shared_mailbox
        }
        for item in unassigned:
            if str(item.get("mailbox") or "").strip().lower() != shared_mailbox:
                continue
            self._supervision[f"queue::{item['graph_message_id']}"] = item
        statuses = sorted({str(item.get("estado") or "pendiente") for item in self._supervision.values()})
        users = sorted({str(item.get("responsable_nombre") or "") for item in self._supervision.values() if item.get("responsable_nombre")})
        companies = sorted({str(item.get("cliente_nombre") or item.get("codigo_empresa") or "") for item in self._supervision.values()})
        mailboxes = sorted({str(item.get("mailbox") or "") for item in self._supervision.values() if item.get("mailbox")})
        self._sup_status_combo["values"] = ["Todos", *statuses]
        self._sup_user_combo["values"] = ["Todos", *users]
        self._sup_company_combo["values"] = ["Todos", *companies]
        self._sup_mailbox_combo["values"] = ["Todos", *mailboxes]
        self._filter_supervision()

    def _filter_supervision(self):
        self._supervision_tree.delete(*self._supervision_tree.get_children())
        query = self._sup_search.get().strip().lower()
        visible = 0
        counts = {"pendiente": 0, "respondido": 0, "gestionado": 0}
        for comm_id, item in self._supervision.items():
            status = str(item.get("estado") or "pendiente")
            user = str(item.get("responsable_nombre") or "")
            company = str(item.get("cliente_nombre") or item.get("codigo_empresa") or "")
            mailbox = str(item.get("mailbox") or "")
            if self._sup_status.get() != "Todos" and status != self._sup_status.get():
                continue
            if self._sup_user.get() != "Todos" and user != self._sup_user.get():
                continue
            if self._sup_company.get() != "Todos" and company != self._sup_company.get():
                continue
            if self._sup_mailbox.get() != "Todos" and mailbox != self._sup_mailbox.get():
                continue
            searchable = " ".join((
                company, user, mailbox, str(item.get("asunto") or ""),
                str(item.get("etiqueta") or ""),
                str(item.get("ultimo_remitente") or ""), status,
            )).lower()
            if query and query not in searchable:
                continue
            visible += 1
            counts[status] = counts.get(status, 0) + 1
            self._supervision_tree.insert("", "end", iid=comm_id, values=(
                item.get("ultima_fecha") or "", mailbox, company, user,
                item.get("etiqueta") or "", item.get("asunto") or "",
                item.get("ultimo_remitente") or "",
                status,
            ))
        self._sup_summary.configure(
            text=(
                f"Mostrados: {visible} · Pendientes: {counts.get('pendiente', 0)} · "
                f"Respondidos: {counts.get('respondido', 0)} · "
                f"Gestionados: {counts.get('gestionado', 0)}"
            )
        )

    @staticmethod
    def _shared_mailbox() -> str:
        return str(
            (load_app_config().get("microsoft_graph") or {}).get("shared_mailbox")
            or "Oficina@gestinem.es"
        ).strip().lower()

    def _allowed_mailboxes(self) -> set[str]:
        return {self._shared_mailbox()}

    def _schedule_auto_refresh(self):
        if self._destroying or self._auto_refresh_after_id is not None:
            return
        self._auto_refresh_after_id = self.after(
            AUTO_REFRESH_MS, self._start_auto_refresh,
        )

    def _start_auto_refresh(self):
        self._auto_refresh_after_id = None
        if self._destroying or self._auto_refresh_running:
            self._schedule_auto_refresh()
            return
        self._auto_refresh_running = True
        generation = self._refresh_generation

        def worker():
            try:
                data = self._collect_refresh_data()
                error = None
            except Exception as exc:
                data = None
                error = exc
            try:
                self.after(
                    0, self._finish_auto_refresh, data, error, generation,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_auto_refresh(self, data, error, generation):
        self._auto_refresh_running = False
        if self._destroying:
            return
        if error is None and generation == self._refresh_generation:
            self._apply_refresh_data(data)
            self._refresh_generation += 1
            self._loading_label.configure(text="")
        else:
            if error is not None:
                LOG.warning(
                    "No se pudo actualizar el buzon en segundo plano: %s", error,
                )
                self._loading_label.configure(text="No se pudieron cargar los mensajes.")
        self._schedule_auto_refresh()

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._destroying = True
        if self._auto_refresh_after_id is not None:
            try:
                self.after_cancel(self._auto_refresh_after_id)
            except tk.TclError:
                pass
            self._auto_refresh_after_id = None

    def _on_pending_selection(self, _event=None):
        selected = self._pending_tree.selection()
        # Nunca arrastrar el responsable del correo anterior. La propuesta se
        # recalcula abajo para el cliente/correo actualmente seleccionado.
        self._user_var.set("")
        self._selection_label.configure(
            text=f"{len(selected)} mensajes seleccionados",
        )
        self._select_suggestion()
        self._select_automatic_responsible()

    def _select_suggestion(self):
        selected = self._pending_tree.selection()
        if not selected:
            return
        suggestion = self._pending[selected[0]].get("sugerencia_codigo_empresa")
        for label, company in self._companies.items():
            if company.get("codigo") == suggestion:
                self._company_search.set(
                    str(company.get("nombre") or company.get("codigo") or ""),
                )
                self._company_var.set(label)
                self._suggest_pending_responsible()
                break

    def _suggest_pending_responsible(self):
        """Propone el responsable configurado en la ficha del cliente."""
        self._user_var.set("")
        company = self._companies.get(self._company_var.get())
        user = _buscar_usuario_responsable(company or {}, self._users)
        if user:
            for label, candidate in self._users.items():
                if candidate.get("id") == user.get("id"):
                    self._user_var.set(label)
                    break

    def _select_automatic_responsible(self):
        selected = self._pending_tree.selection()
        if not selected:
            return
        responsible_ids = {
            int(self._pending[item].get("responsable_usuario_id"))
            for item in selected
            if self._pending[item].get("responsable_usuario_id") is not None
        }
        if len(responsible_ids) != 1:
            return
        responsible_id = next(iter(responsible_ids))
        for label, user in self._users.items():
            if int(user["id"]) == responsible_id:
                self._user_var.set(label)
                break

    def _filter_companies(self):
        query = self._company_search.get().strip().lower()
        values = []
        for label, company in self._companies.items():
            searchable = " ".join((
                label, str(company.get("cif") or ""),
                str(company.get("email") or ""),
            )).lower()
            if not query or query in searchable:
                values.append(label)
        values.sort()
        self._company_combo["values"] = values
        if self._company_var.get() not in values:
            self._company_var.set(values[0] if len(values) == 1 else "")

    def _select_same_sender(self):
        selected = self._pending_tree.selection()
        if not selected:
            messagebox.showwarning(
                "Seleccion multiple", "Selecciona primero un correo.", parent=self,
            )
            return
        sender = str(self._pending[selected[0]].get("remitente") or "").strip().lower()
        if not sender:
            return
        matches = [
            graph_id for graph_id, item in self._pending.items()
            if str(item.get("remitente") or "").strip().lower() == sender
        ]
        self._pending_tree.selection_set(matches)
        if matches:
            self._pending_tree.see(matches[0])
        self._on_pending_selection()

    def _assign(self):
        selected = self._pending_tree.selection()
        company = self._companies.get(self._company_var.get())
        user = self._users.get(self._user_var.get())
        if not selected or not company or not user:
            messagebox.showwarning(
                "Asignacion", "Selecciona correo, cliente y responsable.", parent=self,
            )
            return
        automatic_ids = {
            int(self._pending[item].get("responsable_usuario_id"))
            for item in selected
            if self._pending[item].get("responsable_usuario_id") is not None
        }
        without_automatic = [
            item for item in selected
            if self._pending[item].get("responsable_usuario_id") is None
        ]
        if automatic_ids and without_automatic:
            messagebox.showwarning(
                "Asignacion",
                (
                    "La seleccion mezcla correos personales preasignados y correos "
                    "de Oficina. Asignalos en dos operaciones separadas."
                ),
                parent=self,
            )
            return
        if automatic_ids:
            automatic_id = next(iter(automatic_ids))
            if len(automatic_ids) > 1 or int(user["id"]) != automatic_id:
                messagebox.showwarning(
                    "Asignacion",
                    "Los correos personales deben conservar su responsable automatico.",
                    parent=self,
                )
                return
        if not messagebox.askyesno(
            "Confirmar asignacion masiva",
            (
                f"Se asignaran {len(selected)} mensajes a:\n\n"
                f"Cliente: {company.get('nombre') or company['codigo']}\n"
                f"Responsable: {user['nombre']}\n\n"
                "Si contienen adjuntos, podras decidir cuales se guardan."
            ),
            parent=self,
        ):
            return
        self._prepare_attachment_classification(list(selected), company, user)

    def _prepare_attachment_classification(self, graph_ids, company, user):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            attachments = []
            errors = []
            service = DocumentosCorreoService(self._gestor)
            for graph_id in graph_ids:
                item = self._pending[graph_id]
                try:
                    listed = service.listar_adjuntos(
                        mailbox=str(item.get("mailbox") or ""),
                        graph_message_id=graph_id,
                    )
                    for attachment in listed:
                        attachment_id = str(attachment.get("id") or "")
                        attachments.append({
                            **attachment,
                            "key": f"{graph_id}::{attachment_id}",
                            "attachment_id": attachment_id,
                            "graph_message_id": graph_id,
                            "mailbox": item.get("mailbox") or "",
                            "subject": item.get("asunto") or "",
                            "sender": item.get("remitente") or "",
                        })
                except Exception as exc:
                    errors.append(f"{item.get('asunto') or graph_id}: {exc}")
            try:
                self.after(
                    0, self._show_classification,
                    graph_ids, company, user, attachments, errors,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _show_classification(self, graph_ids, company, user, attachments, errors):
        self.winfo_toplevel().configure(cursor="")
        if errors:
            messagebox.showerror(
                "Asignacion",
                "No se pudieron consultar todos los adjuntos:\n- " + "\n- ".join(errors),
                parent=self,
            )
            return
        if not attachments:
            self._complete_assignment(graph_ids, company, user, [])
            return
        categories = self._gestor.listar_categorias_documentales()
        AttachmentClassificationDialog(
            self, attachments, categories,
            on_save=lambda decisions: self._complete_assignment(
                graph_ids, company, user, decisions,
            ),
        )

    def _complete_assignment(self, graph_ids, company, user, decisions):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            saved = ignored = duplicates = 0
            errors = []
            service = GestionDocumentalService(self._gestor)
            for graph_id in graph_ids:
                item = self._pending[graph_id]
                current = [
                    decision for decision in decisions
                    if decision["graph_message_id"] == graph_id
                ]
                if current:
                    summary = service.archivar_adjuntos_correo(
                        codigo_empresa=company["codigo"],
                        ejercicio=int(company.get("ejercicio") or 0),
                        mailbox=str(item.get("mailbox") or ""),
                        graph_message_id=graph_id,
                        remitente=str(item.get("remitente") or ""),
                        asunto=str(item.get("asunto") or ""),
                        decisiones=current,
                        usuario=str(self._session.user.nombre),
                    )
                    saved += len(summary.saved)
                    ignored += len(summary.ignored)
                    duplicates += len(summary.duplicates)
                    errors.extend(summary.errors)
            result = None
            if not errors:
                result = self._gestor.asignar_comunicaciones_pendientes(
                    graph_ids, company["codigo"], int(user["id"]), str(user["nombre"]),
                )
                for graph_id in result["asignadas"]:
                    self._gestor.vincular_documentos_graph_comunicacion(graph_id)
            try:
                self.after(
                    0, self._finish_assignment,
                    result, saved, ignored, duplicates, errors,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_assignment(self, result, saved, ignored, duplicates, errors):
        self.winfo_toplevel().configure(cursor="")
        if errors:
            messagebox.showerror(
                "Asignacion",
                "No se ha completado la asignacion. Corrige o marca como No guardar:\n- "
                + "\n- ".join(errors[:8]), parent=self,
            )
            return
        self._refresh()
        messagebox.showinfo(
            "Asignacion",
            f"Mensajes asignados: {len(result['asignadas'])}\n"
            f"Documentos guardados: {saved}\nAdjuntos no guardados: {ignored}\n"
            f"Duplicados detectados: {duplicates}\n\n"
            "Los documentos quedan archivados. Puedes enviarlos a OCR manualmente "
            "desde Gestion documental cuando el modulo este configurado.", parent=self,
        )

    def _assign_without_client(self):
        selected = self._pending_tree.selection()
        user = self._users.get(self._user_var.get())
        if not selected or not user:
            messagebox.showwarning(
                "Asignacion", "Selecciona mensajes y responsable.", parent=self,
            )
            return
        automatic_ids = {
            int(self._pending[item].get("responsable_usuario_id"))
            for item in selected
            if self._pending[item].get("responsable_usuario_id") is not None
        }
        if automatic_ids and (
            len(automatic_ids) > 1 or int(user["id"]) not in automatic_ids
        ):
            messagebox.showwarning(
                "Asignacion",
                "Los correos personales deben conservar su responsable automatico.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Asignar sin cliente",
            (
                f"Se asignaran {len(selected)} mensajes a {user['nombre']} "
                "sin vincularlos a ningun cliente.\n\n¿Deseas continuar?"
            ),
            parent=self,
        ):
            return
        count = self._gestor.asignar_comunicaciones_sin_cliente(
            list(selected), int(user["id"]), str(user["nombre"]),
        )
        self._refresh()
        messagebox.showinfo(
            "Asignacion", f"Mensajes asignados sin cliente: {count}", parent=self,
        )

    def _discard(self):
        selected = self._pending_tree.selection()
        if not selected:
            return
        motivo = simpledialog.askstring(
            "Descartar correos", "Motivo opcional:", parent=self,
        )
        if motivo is None:
            return
        count = self._gestor.descartar_comunicaciones(
            list(selected), self._session.user.nombre, motivo,
        )
        self._refresh()
        messagebox.showinfo(
            "Descartar", f"Correos descartados: {count}", parent=self,
        )

    def _restore(self):
        selected = self._discarded_tree.selection()
        if not selected:
            return
        queue_ids = [iid.split("::", 1)[1] for iid in selected if iid.startswith("queue::")]
        comm_ids = [iid.split("::", 1)[1] for iid in selected if iid.startswith("comm::")]
        count = self._gestor.restaurar_comunicaciones(queue_ids)
        count += self._gestor.restaurar_conversaciones(comm_ids)
        self._refresh()
        messagebox.showinfo(
            "Restaurar", f"Correos restaurados: {count}", parent=self,
        )

    def _selected_assigned(self, source: str):
        tree = self._mine_tree if source == "mine" else self._supervision_tree
        items = self._mine if source == "mine" else self._supervision
        selected = tree.selection()
        if not selected:
            return None, None
        return selected[0], items.get(selected[0])

    def _edit_label(self, source: str):
        if source == "pending":
            selected = list(self._pending_tree.selection())
            items = self._pending
        else:
            tree = self._mine_tree if source == "mine" else self._supervision_tree
            selected = list(tree.selection())
            items = self._mine if source == "mine" else self._supervision
        if not selected:
            messagebox.showwarning(
                "Etiqueta", "Selecciona al menos un correo.", parent=self,
            )
            return
        current = str((items.get(selected[0]) or {}).get("etiqueta") or "")
        etiqueta = simpledialog.askstring(
            "Etiqueta del correo",
            "Etiqueta visible para identificar o clasificar este correo:\n"
            "(dejala vacia para quitarla)",
            initialvalue=current,
            parent=self,
        )
        if etiqueta is None:
            return
        updated = 0
        for iid in selected:
            if source == "pending" or iid.startswith(("pending::", "queue::")):
                graph_id = iid.split("::", 1)[-1]
                updated += int(bool(self._gestor.actualizar_etiqueta_pendiente(
                    graph_id, etiqueta,
                )))
            else:
                updated += int(bool(self._gestor.actualizar_etiqueta_comunicacion(
                    iid, etiqueta,
                )))
        self._refresh()
        if not updated:
            messagebox.showwarning(
                "Etiqueta", "No se ha podido actualizar la etiqueta.", parent=self,
            )

    def _reassign(self, source: str):
        iid, item = self._selected_assigned(source)
        if not iid or not item:
            messagebox.showwarning(
                "Reasignacion", "Selecciona primero una comunicacion.", parent=self,
            )
            return

        def save(company, user):
            if iid.startswith(("pending::", "queue::")):
                graph_id = iid.split("::", 1)[1]
                result = self._gestor.asignar_comunicacion_pendiente(
                    graph_id, company["codigo"], int(user["id"]), str(user["nombre"]),
                )
            else:
                result = self._gestor.reasignar_comunicacion(
                    iid, company["codigo"], int(user["id"]), str(user["nombre"]),
                )
            if not result:
                messagebox.showwarning(
                    "Reasignacion", "No se ha podido reasignar la comunicacion.", parent=self,
                )
                return
            self._refresh()

        ReassignCommunicationDialog(
            self, self._companies, self._users, item, save,
        )

    def _discard_assigned(self, source: str):
        iid, item = self._selected_assigned(source)
        if not iid or not item:
            messagebox.showwarning(
                "Descartar", "Selecciona primero una comunicacion.", parent=self,
            )
            return
        motivo = simpledialog.askstring(
            "Descartar comunicacion", "Motivo opcional:", parent=self,
        )
        if motivo is None:
            return
        if iid.startswith(("pending::", "queue::")):
            count = self._gestor.descartar_comunicaciones(
                [iid.split("::", 1)[1]], self._session.user.nombre, motivo,
            )
        else:
            count = self._gestor.descartar_conversaciones(
                [iid], self._session.user.nombre, motivo,
            )
        self._refresh()
        messagebox.showinfo(
            "Descartar", f"Comunicaciones descartadas: {count}", parent=self,
        )

    def _pending_detail(self):
        selected = self._pending_tree.selection()
        if not selected:
            return
        item = self._pending[selected[0]]
        payload = json.loads(item.get("payload_json") or "{}")
        message = {
            "graph_message_id": item.get("graph_message_id"),
            "mailbox": item.get("mailbox"),
            "fecha": payload.get("fecha"),
            "remitente": payload.get("remitente"),
            "destinatarios_json": json.dumps(payload.get("destinatarios") or []),
            "cc_json": json.dumps(payload.get("cc") or []),
            "asunto": payload.get("asunto"),
            "cuerpo_html": payload.get("cuerpo_html"),
            "estado_envio": "sin asignar",
            "error_envio": "",
            "adjuntos": [],
        }
        CommunicationDetailDialog(
            self, [message], on_preview_attachments=self._preview_attachments,
        )

    def _preview_selected_pending(self):
        selected = self._pending_tree.selection()
        if not selected:
            messagebox.showwarning(
                "Adjuntos", "Selecciona primero un correo.", parent=self,
            )
            return
        item = self._pending[selected[0]]
        self._preview_attachments({
            "graph_message_id": item.get("graph_message_id"),
            "mailbox": item.get("mailbox"),
        })

    def _set_status(self, estado: str):
        selected = self._mine_tree.selection()
        if not selected:
            return
        if selected[0].startswith("pending::"):
            graph_id = selected[0].split("::", 1)[1]
            self._gestor.cambiar_estado_pendiente_responsable(
                graph_id, estado, self._session.user.id,
            )
            self._refresh()
            return
        self._gestor.cambiar_estado_comunicacion(
            selected[0], estado, self._session.user.id,
        )
        self._refresh()

    def _detail(self):
        selected = self._mine_tree.selection()
        if not selected:
            return
        if selected[0].startswith("pending::"):
            item = self._mine[selected[0]]
            payload = json.loads(item.get("payload_json") or "{}")
            message = {
                "graph_message_id": item.get("graph_message_id"),
                "mailbox": item.get("mailbox"),
                "fecha": payload.get("fecha"),
                "remitente": payload.get("remitente"),
                "destinatarios_json": json.dumps(payload.get("destinatarios") or []),
                "cc_json": json.dumps(payload.get("cc") or []),
                "asunto": payload.get("asunto"),
                "cuerpo_html": payload.get("cuerpo_html"),
                "estado_envio": "pendiente de cliente",
                "error_envio": "",
                "adjuntos": [],
            }
            CommunicationDetailDialog(
                self, [message],
                on_preview_attachments=self._preview_attachments,
            )
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        company = self._mine[selected[0]].get("codigo_empresa")
        CommunicationDetailDialog(
            self, messages,
            on_import_attachments=lambda message: self._choose_attachments(company, message),
            on_preview_attachments=self._preview_attachments,
            on_reply=lambda message: self._reply(selected[0], company, message),
        )

    def _reply_selected(self, source: str):
        iid, item = self._selected_assigned(source)
        if not iid:
            return
        messages = self._gestor.listar_mensajes_comunicacion(iid)
        message = next(
            (entry for entry in messages if entry.get("direccion") != "saliente"
             and entry.get("graph_message_id") and entry.get("mailbox")),
            None,
        )
        if not message:
            messagebox.showwarning(
                "Correo", "La conversacion no contiene un correo recibido que se pueda responder.",
                parent=self,
            )
            return
        self._reply(iid, str(item.get("codigo_empresa") or ""), message)

    def _reply(self, comunicacion_id: str, codigo_empresa: str, message: dict):
        if not codigo_empresa:
            messagebox.showwarning(
                "Correo", "Asigna primero el correo a un cliente para poder responderlo.",
                parent=self,
            )
            return
        ReplyMailDialog(
            self, self._gestor, codigo_empresa, self._session,
            comunicacion_id, message, self._refresh,
        )

    def _supervision_detail(self):
        selected = self._supervision_tree.selection()
        if not selected:
            return
        if selected[0].startswith("queue::"):
            item = self._supervision[selected[0]]
            payload = json.loads(item.get("payload_json") or "{}")
            message = {
                "graph_message_id": item.get("graph_message_id"),
                "mailbox": item.get("mailbox"),
                "fecha": payload.get("fecha"),
                "remitente": payload.get("remitente"),
                "destinatarios_json": json.dumps(payload.get("destinatarios") or []),
                "cc_json": json.dumps(payload.get("cc") or []),
                "asunto": payload.get("asunto"),
                "cuerpo_html": payload.get("cuerpo_html"),
                "estado_envio": item.get("estado") or "pendiente",
                "error_envio": "",
                "adjuntos": [],
            }
            CommunicationDetailDialog(
                self, [message],
                on_preview_attachments=self._preview_attachments,
            )
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        company = self._supervision[selected[0]].get("codigo_empresa")
        CommunicationDetailDialog(
            self, messages,
            on_import_attachments=lambda message: self._choose_attachments(company, message),
            on_preview_attachments=self._preview_attachments,
            on_reply=lambda message: self._reply(selected[0], company, message),
        )

    def _preview_attachments(self, message: dict):
        graph_id = str(message.get("graph_message_id") or "").strip()
        mailbox = str(message.get("mailbox") or "").strip()
        if not graph_id or not mailbox:
            messagebox.showinfo(
                "Adjuntos", "Este mensaje no tiene adjuntos disponibles en Microsoft 365.",
                parent=self,
            )
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
                self.after(
                    0, self._show_attachment_preview_list,
                    message, attachments, error,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _show_attachment_preview_list(self, message, attachments, error):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror(
                "Adjuntos", f"No se pudieron consultar los adjuntos:\n{error}",
                parent=self,
            )
            return
        if not attachments:
            messagebox.showinfo(
                "Adjuntos", "El correo no tiene adjuntos descargables.", parent=self,
            )
            return
        AttachmentPreviewDialog(
            self, attachments,
            on_open=lambda attachment_id: self._open_temporary_attachment(
                message, attachment_id,
            ),
            on_inspect=lambda attachment_id: self._inspect_zip(
                message, attachment_id,
            ),
        )

    def _inspect_zip(self, message, attachment_id):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                service = DocumentosCorreoService(self._gestor)
                archive = service.descargar_adjunto_temporal(
                    mailbox=str(message.get("mailbox") or ""),
                    graph_message_id=str(message.get("graph_message_id") or ""),
                    attachment_id=attachment_id,
                )
                members = service.listar_contenido_zip(archive)
                error = None
            except Exception as exc:
                archive, members, error = None, [], exc
            self.after(0, lambda: self._show_zip_contents(message, archive, members, error))

        threading.Thread(target=worker, daemon=True).start()

    def _show_zip_contents(self, message, archive, members, error):
        self.winfo_toplevel().configure(cursor="")
        if error:
            messagebox.showerror("ZIP", f"No se pudo leer el ZIP:\n{error}", parent=self)
            return
        if not members:
            messagebox.showinfo("ZIP", "El ZIP no contiene documentos.", parent=self)
            return
        service = DocumentosCorreoService(self._gestor)
        categories = self._gestor.listar_categorias_documentales()
        ArchiveContentsDialog(
            self, members,
            on_open=lambda name: self._open_extracted_zip_member(service, archive, name),
            companies=self._companies,
            categories=categories,
            on_assign=lambda decisions: self._assign_zip_members(archive, decisions),
        )

    def _open_extracted_zip_member(self, service, archive, name):
        try:
            path = service.extraer_zip_temporal(archive, name)
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("ZIP", f"No se pudo abrir el documento:\n{exc}", parent=self)

    def _assign_zip_members(self, archive, decisions):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            saved, errors = [], []
            service = DocumentosCorreoService(self._gestor)
            documental = GestionDocumentalService(self._gestor)
            for decision in decisions:
                try:
                    company = self._companies[decision["company"]]
                    path = service.extraer_zip_temporal(archive, decision["name"])
                    documental.importar_archivo(
                        codigo_empresa=company["codigo"],
                        ejercicio=int(company.get("ejercicio") or 0),
                        categoria_id=self._category_id(decision["category"]),
                        source=path, usuario=self._session.user.nombre,
                    )
                    saved.append(decision["name"])
                except Exception as exc:
                    errors.append(f"{decision['name']}: {exc}")
            self.after(0, lambda: self._finish_zip_assignment(saved, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _category_id(self, name):
        category = next(
            item for item in self._gestor.listar_categorias_documentales()
            if item["nombre"] == name
        )
        return str(category["id"])

    def _finish_zip_assignment(self, saved, errors):
        self.winfo_toplevel().configure(cursor="")
        text = f"Documentos asignados: {len(saved)}"
        if errors:
            text += "\n\nErrores:\n- " + "\n- ".join(errors)
        messagebox.showinfo("ZIP", text, parent=self)

    def _open_temporary_attachment(self, message: dict, attachment_id: str):
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                path = DocumentosCorreoService(
                    self._gestor,
                ).descargar_adjunto_temporal(
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
            messagebox.showerror(
                "Adjuntos", f"No se pudo abrir el adjunto:\n{error}", parent=self,
            )
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror(
                "Adjuntos", f"Windows no pudo abrir el archivo:\n{exc}", parent=self,
            )

    def _choose_attachments(self, codigo_empresa: str, message: dict):
        graph_id = str(message.get("graph_message_id") or "").strip()
        mailbox = str(message.get("mailbox") or "").strip()
        if not codigo_empresa or not graph_id or not mailbox:
            messagebox.showwarning(
                "Documentacion", "Este mensaje no tiene adjuntos de correo disponibles para descargar.", parent=self,
            )
            return
        try:
            attachments = DocumentosCorreoService(self._gestor).listar_adjuntos(
                mailbox=mailbox, graph_message_id=graph_id,
            )
        except Exception as exc:
            messagebox.showerror("Documentacion", f"No se pudieron consultar los adjuntos:\n{exc}", parent=self)
            return
        if not attachments:
            messagebox.showinfo("Documentacion", "El correo no tiene adjuntos descargables.", parent=self)
            return
        AttachmentSelectionDialog(
            self, attachments,
            on_save=lambda ids: self._import_attachments(codigo_empresa, message, ids),
        )

    def _import_attachments(self, codigo_empresa: str, message: dict, attachment_ids: list[str]):
        empresa = self._gestor.get_empresa(codigo_empresa) or {}
        ejercicio = int(empresa.get("ejercicio") or 0)
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                summary = DocumentosCorreoService(self._gestor).importar_adjuntos(
                    codigo_empresa=codigo_empresa, ejercicio=ejercicio,
                    mensaje_id=str(message.get("id") or ""), mailbox=str(message.get("mailbox") or ""),
                    graph_message_id=str(message.get("graph_message_id") or ""),
                    attachment_ids=attachment_ids, usuario=self._session.user.nombre,
                )
            except Exception as exc:
                self.after(0, lambda err=exc: self._show_import_error(err))
                return
            self.after(0, lambda: self._show_import_summary(summary))

        threading.Thread(target=worker, daemon=True).start()

    def _show_import_error(self, exc: Exception):
        self.winfo_toplevel().configure(cursor="")
        messagebox.showerror("Documentacion", f"No se pudieron guardar los adjuntos:\n{exc}", parent=self)

    def _show_import_summary(self, summary):
        self.winfo_toplevel().configure(cursor="")
        parts = [f"Incorporados a OCR: {len(summary.imported)}"]
        if summary.duplicates:
            parts.append(f"Duplicados omitidos: {len(summary.duplicates)}")
        if summary.unsupported:
            parts.append(f"No compatibles: {len(summary.unsupported)}")
        if summary.errors:
            parts.append("Errores:\n- " + "\n- ".join(summary.errors[:4]))
        messagebox.showinfo("Documentacion", "\n".join(parts), parent=self)
