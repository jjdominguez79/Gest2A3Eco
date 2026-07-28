from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk

from services.comunicaciones_sync_service import ComunicacionesSyncService
from utils.utilidades import load_app_config
from views.ui_comunicaciones import CommunicationDetailDialog


class UIComunicacionesGlobal(ttk.Frame):
    def __init__(self, parent, gestor, session, on_open_empresas):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._session = session
        self._on_open_empresas = on_open_empresas
        self._pending: dict[str, dict] = {}
        self._mine: dict[str, dict] = {}
        self._supervision: dict[str, dict] = {}
        self._companies: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
        self._build()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Buzon de comunicaciones", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top, text="Empresas", command=self._on_open_empresas).pack(side="right")
        ttk.Button(top, text="Sincronizar", command=self._sync).pack(side="right", padx=6)

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        pending_tab = ttk.Frame(tabs, padding=8)
        mine_tab = ttk.Frame(tabs, padding=8)
        tabs.add(pending_tab, text="Entrada sin asignar")
        tabs.add(mine_tab, text="Mi buzon")
        supervision_tab = None
        if self._session.is_admin():
            supervision_tab = ttk.Frame(tabs, padding=8)
            tabs.add(supervision_tab, text="Supervision")

        self._pending_tree = self._tree(
            pending_tab,
            (("fecha", "Fecha", 170), ("buzon", "Buzon", 180),
             ("remitente", "Remitente", 230), ("asunto", "Asunto", 330),
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
        ttk.Button(buttons, text="Asignar seleccionados", command=self._assign).pack(side="left")
        assign.columnconfigure(1, weight=1)
        assign.columnconfigure(3, weight=1)
        self._pending_tree.bind("<<TreeviewSelect>>", self._on_pending_selection)
        self._pending_tree.bind("<Double-1>", lambda _event: self._pending_detail())

        self._mine_tree = self._tree(
            mine_tab,
            (("fecha", "Ultima actividad", 170), ("cliente", "Cliente", 220),
             ("asunto", "Asunto", 350), ("remitente", "Remitente", 220),
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
        ttk.Button(actions, text="Ver conversacion", command=self._detail).pack(side="right")
        self._mine_tree.bind("<Double-1>", lambda _event: self._detail())

        if supervision_tab is not None:
            self._build_supervision(supervision_tab)

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
             ("asunto", "Asunto", 310), ("remitente", "Ultimo remitente", 210),
             ("estado", "Estado", 105)),
        )
        self._supervision_tree.bind(
            "<Double-1>", lambda _event: self._supervision_detail(),
        )
        ttk.Button(
            parent, text="Ver conversacion",
            command=self._supervision_detail,
        ).pack(anchor="e", pady=(8, 0))

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
        companies = {}
        for item in self._gestor.listar_empresas():
            code = str(item.get("codigo") or "")
            if code not in companies or int(item.get("ejercicio") or 0) > int(companies[code].get("ejercicio") or 0):
                companies[code] = item
        self._companies = {f"{item.get('nombre') or code} [{code}]": item for code, item in companies.items()}
        self._filter_companies()

        users = [item for item in self._gestor.listar_usuarios() if bool(item.get("activo"))]
        self._users = {f"{item.get('nombre')} [{item.get('username')}]": item for item in users}
        self._user_combo["values"] = sorted(self._users)

        self._pending_tree.delete(*self._pending_tree.get_children())
        self._pending = {}
        allowed = self._allowed_mailboxes()
        for item in self._gestor.listar_comunicaciones_sin_asignar():
            if str(item.get("mailbox") or "").lower() not in allowed:
                continue
            graph_id = item["graph_message_id"]
            self._pending[graph_id] = item
            self._pending_tree.insert("", "end", iid=graph_id, values=(
                item.get("fecha") or "", item.get("mailbox") or "",
                item.get("remitente") or "", item.get("asunto") or "",
                item.get("sugerencia_nombre") or "",
            ))

        self._mine_tree.delete(*self._mine_tree.get_children())
        self._mine = {}
        for item in self._gestor.listar_buzon_responsable(self._session.user.id):
            comm_id = item["id"]
            self._mine[comm_id] = item
            company = companies.get(str(item.get("codigo_empresa") or ""), {})
            self._mine_tree.insert("", "end", iid=comm_id, values=(
                item.get("ultima_fecha") or "", company.get("nombre") or item.get("codigo_empresa"),
                item.get("asunto") or "", item.get("ultimo_remitente") or "",
                item.get("estado") or "pendiente",
            ))
        for item in self._gestor.listar_pendientes_responsable(self._session.user.id):
            iid = f"pending::{item['graph_message_id']}"
            item["_pending_client"] = True
            self._mine[iid] = item
            self._mine_tree.insert("", "end", iid=iid, values=(
                item.get("fecha") or "", "Sin asignar",
                item.get("asunto") or "", item.get("remitente") or "",
                "pendiente de cliente",
            ))
        if self._session.is_admin():
            self._refresh_supervision()

    def _refresh_supervision(self):
        self._supervision = {
            item["id"]: item
            for item in self._gestor.listar_comunicaciones_supervision()
        }
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
                str(item.get("ultimo_remitente") or ""), status,
            )).lower()
            if query and query not in searchable:
                continue
            visible += 1
            counts[status] = counts.get(status, 0) + 1
            self._supervision_tree.insert("", "end", iid=comm_id, values=(
                item.get("ultima_fecha") or "", mailbox, company, user,
                item.get("asunto") or "", item.get("ultimo_remitente") or "",
                status,
            ))
        self._sup_summary.configure(
            text=(
                f"Mostrados: {visible} · Pendientes: {counts.get('pendiente', 0)} · "
                f"Respondidos: {counts.get('respondido', 0)} · "
                f"Gestionados: {counts.get('gestionado', 0)}"
            )
        )

    def _allowed_mailboxes(self) -> set[str]:
        shared = str((load_app_config().get("microsoft_graph") or {}).get("shared_mailbox") or "Oficina@gestinem.es").lower()
        allowed = {shared}
        if self._session.is_admin():
            allowed.add("me")
            # Las entradas de Graph guardan la direccion real de la cuenta personal.
            allowed.update(
                str(item.get("mailbox") or "").lower()
                for item in self._gestor.listar_comunicaciones_sin_asignar()
                if str(item.get("mailbox") or "").lower() != shared
            )
        return allowed

    def _sync(self):
        shared = str((load_app_config().get("microsoft_graph") or {}).get("shared_mailbox") or "Oficina@gestinem.es")
        mailboxes = [shared] + (["me"] if self._session.is_admin() else [])
        total = 0
        try:
            service = ComunicacionesSyncService(self._gestor)
            for mailbox in mailboxes:
                responsable = None
                if mailbox == "me":
                    responsable = {
                        "id": self._session.user.id,
                        "nombre": self._session.user.nombre,
                    }
                total += service.sync(
                    mailbox, responsable=responsable,
                ).recibidos
        except Exception as exc:
            messagebox.showerror("Sincronizacion", str(exc), parent=self)
            return
        self._refresh()
        messagebox.showinfo("Sincronizacion", f"Correos revisados: {total}", parent=self)

    def _on_pending_selection(self, _event=None):
        selected = self._pending_tree.selection()
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
                "¿Deseas continuar?"
            ),
            parent=self,
        ):
            return
        result = self._gestor.asignar_comunicaciones_pendientes(
            list(selected), company["codigo"], int(user["id"]), str(user["nombre"]),
        )
        self._refresh()
        messagebox.showinfo(
            "Asignacion masiva",
            (
                f"Mensajes asignados: {len(result['asignadas'])}\n"
                f"Mensajes omitidos: {len(result['omitidas'])}"
            ),
            parent=self,
        )

    def _pending_detail(self):
        selected = self._pending_tree.selection()
        if not selected:
            return
        item = self._pending[selected[0]]
        payload = json.loads(item.get("payload_json") or "{}")
        message = {
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
        CommunicationDetailDialog(self, [message])

    def _set_status(self, estado: str):
        selected = self._mine_tree.selection()
        if not selected:
            return
        if selected[0].startswith("pending::"):
            messagebox.showinfo(
                "Estado",
                "Asigna primero el cliente para gestionar el estado del correo.",
                parent=self,
            )
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
            CommunicationDetailDialog(self, [message])
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        CommunicationDetailDialog(self, messages)

    def _supervision_detail(self):
        selected = self._supervision_tree.selection()
        if not selected:
            return
        messages = self._gestor.listar_mensajes_comunicacion(selected[0])
        CommunicationDetailDialog(self, messages)
