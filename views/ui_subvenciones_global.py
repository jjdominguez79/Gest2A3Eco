"""Panel central de ayudas BDNS, suscripciones y avisos a clientes."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from services.backend_client_service import BackendClientService


class UISubvencionesGlobal(ttk.Frame):
    """Administra el servicio central sin duplicar datos en el escritorio."""

    def __init__(self, master, service: BackendClientService | None = None):
        super().__init__(master, padding=10)
        self.service = service or BackendClientService()
        self._busy = False
        self._config_loaded = False
        self._organization_items: list[dict] = []
        self._build()
        self.after_idle(self.refresh)

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header, text="Ayudas y subvenciones",
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left")
        ttk.Label(
            header,
            text="BDNS · catálogo para clientes · suscripciones territoriales",
            foreground="#5B6573",
        ).pack(side="left", padx=14)
        self.status_var = tk.StringVar(value="Conectando con el servicio...")
        ttk.Label(header, textvariable=self.status_var).pack(side="right", padx=8)
        self.refresh_button = ttk.Button(header, text="Actualizar", command=self.refresh)
        self.refresh_button.pack(side="right")

        metrics = ttk.Frame(self)
        metrics.pack(fill="x", pady=(0, 10))
        self.metric_vars = {
            key: tk.StringVar(value="—")
            for key in ("convocatorias", "vigentes", "suscriptores", "fallos_entrega")
        }
        labels = {
            "convocatorias": "Convocatorias",
            "vigentes": "Vigentes",
            "suscriptores": "Clientes con avisos",
            "fallos_entrega": "Fallos de envío",
        }
        for index, key in enumerate(labels):
            card = ttk.LabelFrame(metrics, text=labels[key], padding=(18, 8))
            card.grid(row=0, column=index, sticky="ew", padx=(0, 8))
            metrics.columnconfigure(index, weight=1)
            ttk.Label(
                card, textvariable=self.metric_vars[key],
                font=("Segoe UI", 17, "bold"),
            ).pack()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self._build_calls_tab()
        self._build_organizations_tab()
        self._build_subscriptions_tab()
        self._build_deliveries_tab()
        self._build_settings_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)

    def _tree(
        self, parent, columns: tuple[tuple[str, str, int], ...],
        *, selectmode: str = "browse",
    ) -> ttk.Treeview:
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        names = tuple(item[0] for item in columns)
        tree = ttk.Treeview(wrapper, columns=names, show="headings", selectmode=selectmode)
        for name, title, width in columns:
            tree.heading(name, text=title)
            tree.column(name, width=width, minwidth=70, stretch=name in {"titulo", "empresa"})
        scroll_y = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        return tree

    def _build_calls_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Convocatorias")
        toolbar = ttk.Frame(tab, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Buscar:").pack(side="left")
        self.query_var = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self.query_var, width=42)
        search.pack(side="left", padx=6)
        search.bind("<Return>", lambda _event: self._load_calls())
        ttk.Button(toolbar, text="Buscar", command=self._load_calls).pack(side="left")
        ttk.Label(toolbar, text="Estado:").pack(side="left", padx=(14, 4))
        self.calls_status_var = tk.StringVar(value="En vigor")
        status = ttk.Combobox(
            toolbar,
            textvariable=self.calls_status_var,
            values=("En vigor", "Finalizadas", "Todas"),
            state="readonly",
            width=12,
        )
        status.pack(side="left")
        status.bind("<<ComboboxSelected>>", lambda _event: self._load_calls())
        ttk.Label(toolbar, text="Visibilidad:").pack(side="left", padx=(14, 4))
        self.calls_visibility_var = tk.StringVar(value="Visibles")
        visibility = ttk.Combobox(
            toolbar,
            textvariable=self.calls_visibility_var,
            values=("Visibles", "Ocultas", "Todas"),
            state="readonly",
            width=10,
        )
        visibility.pack(side="left")
        visibility.bind("<<ComboboxSelected>>", lambda _event: self._load_calls())
        ttk.Button(
            toolbar, text="Mostrar", command=lambda: self._set_visibility(True),
        ).pack(side="right", padx=4)
        ttk.Button(
            toolbar, text="Ocultar", command=lambda: self._set_visibility(False),
        ).pack(side="right", padx=4)
        ttk.Button(
            toolbar, text="Marcar revisada", command=self._mark_reviewed,
        ).pack(side="right", padx=4)
        ttk.Button(
            toolbar, text="Rehacer resumen", command=self._redo_summary,
        ).pack(side="right", padx=4)
        self.calls_tree = self._tree(tab, (
            ("codigo", "BDNS", 90), ("fecha", "Publicación", 100),
            ("ambito", "Ámbito", 95), ("titulo", "Título", 560),
            ("fin", "Fin", 130), ("visible", "Visible", 70),
            ("revisada", "Revisada", 75), ("resumen", "Resumen", 90),
        ))

    def _build_organizations_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Empresas")
        toolbar = ttk.Frame(tab, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="Active la función solo para las empresas que deban verla en Flutter.",
        ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))
        self.organization_count_var = tk.StringVar(value="")
        ttk.Label(
            toolbar, textvariable=self.organization_count_var, foreground="#5B6573",
        ).grid(row=0, column=6, sticky="e", pady=(0, 8))
        toolbar.columnconfigure(2, weight=1)
        ttk.Label(toolbar, text="Buscar:").grid(row=1, column=0, sticky="w")
        self.organization_query_var = tk.StringVar()
        organization_search = ttk.Entry(
            toolbar, textvariable=self.organization_query_var, width=38,
        )
        organization_search.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 14))
        organization_search.bind("<KeyRelease>", lambda _event: self._apply_organization_filters())
        ttk.Label(toolbar, text="Estado:").grid(row=1, column=3, sticky="w")
        self.organization_status_var = tk.StringVar(value="Todas")
        status = ttk.Combobox(
            toolbar,
            textvariable=self.organization_status_var,
            values=("Todas", "Activadas", "Desactivadas", "Con usuarios", "Sin usuarios"),
            state="readonly", width=16,
        )
        status.grid(row=1, column=4, sticky="w", padx=6)
        status.bind("<<ComboboxSelected>>", lambda _event: self._apply_organization_filters())
        ttk.Button(
            toolbar, text="Seleccionar visibles", command=self._select_visible_organizations,
        ).grid(row=1, column=5, padx=(14, 4))
        ttk.Button(
            toolbar, text="Activar selección",
            command=lambda: self._set_selected_organizations(True),
        ).grid(row=1, column=6, padx=4)
        ttk.Button(
            toolbar, text="Desactivar selección",
            command=lambda: self._set_selected_organizations(False),
        ).grid(row=1, column=7, padx=(4, 0))
        self.organizations_tree = self._tree(tab, (
            ("codigo", "Código", 90), ("empresa", "Empresa", 330),
            ("territorio", "Territorio", 260), ("usuarios", "Usuarios", 80),
            ("activa", "Configurada", 90), ("efectiva", "Disponible", 90),
        ), selectmode="extended")
        self.organizations_tree.bind("<Double-1>", lambda _event: self._toggle_organization())
        self.organizations_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._update_organization_count(),
        )

    def _build_subscriptions_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Preferencias clientes")
        header = ttk.Frame(tab, padding=(8, 8, 8, 0))
        header.pack(fill="x")
        ttk.Label(
            header,
            text=(
                "Solo se muestran usuarios de empresas habilitadas. “Sin configurar” "
                "significa que el cliente todavía no ha guardado sus preferencias."
            ),
        ).pack(side="left")
        self.subscription_count_var = tk.StringVar(value="")
        ttk.Label(
            header, textvariable=self.subscription_count_var, foreground="#5B6573",
        ).pack(side="right")
        self.subscriptions_tree = self._tree(tab, (
            ("codigo", "Empresa", 90), ("empresa", "Razón social", 260),
            ("usuario", "Usuario", 180), ("email", "Email", 240),
            ("estado", "Preferencias", 110),
            ("avisos", "Avisos", 70), ("nacional", "España", 70),
            ("domicilio", "Domicilio", 80), ("territorios", "Otros territorios", 380),
        ))

    def _build_deliveries_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Envíos")
        self.deliveries_tree = self._tree(tab, (
            ("fecha", "Fecha", 140), ("estado", "Estado", 100),
            ("usuario", "Usuario", 170), ("email", "Email", 220),
            ("codigo", "BDNS", 90), ("titulo", "Convocatoria", 420),
            ("dispositivos", "Dispositivos", 90), ("error", "Último error", 280),
        ))

    def _build_settings_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(tab, text="Configuración")
        self.service_active_var = tk.BooleanVar(value=True)
        self.alerts_active_var = tk.BooleanVar(value=False)
        self.ai_active_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab, text="Sincronización BDNS activa", variable=self.service_active_var,
        ).pack(anchor="w", pady=5)
        ttk.Checkbutton(
            tab, text="Enviar notificaciones a clientes suscritos",
            variable=self.alerts_active_var,
        ).pack(anchor="w", pady=5)
        ttk.Checkbutton(
            tab, text="Generar resúmenes orientativos con IA",
            variable=self.ai_active_var,
        ).pack(anchor="w", pady=5)
        self.ai_status_var = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.ai_status_var, foreground="#5B6573").pack(
            anchor="w", padx=24,
        )
        self.global_status_var = tk.StringVar(value="")
        ttk.Label(
            tab, textvariable=self.global_status_var, foreground="#8A4B08",
        ).pack(anchor="w", pady=(10, 0))
        ttk.Separator(tab).pack(fill="x", pady=18)
        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        ttk.Button(
            actions, text="Guardar configuración", command=self._save_settings,
        ).pack(side="left")
        ttk.Button(
            actions, text="Sincronizar ahora", command=self._sync_now,
        ).pack(side="left", padx=8)
        self.last_run_var = tk.StringVar(value="Todavía no hay ejecuciones registradas.")
        ttk.Label(
            tab, textvariable=self.last_run_var, justify="left", wraplength=900,
        ).pack(anchor="w", pady=20)
        ttk.Label(
            tab,
            text=(
                "Los datos se obtienen de la BDNS. Los resúmenes son orientativos y la "
                "convocatoria oficial siempre prevalece. El proceso programado se ejecuta "
                "en Railway, aunque el escritorio esté cerrado."
            ),
            foreground="#5B6573", wraplength=900, justify="left",
        ).pack(anchor="w")

    def _run(self, label: str, operation, success) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.configure(state="disabled")
        self.status_var.set(label)

        def worker():
            try:
                result = operation()
            except Exception as exc:
                self.after(0, lambda: self._failed(exc))
            else:
                self.after(0, lambda: self._succeeded(result, success))

        threading.Thread(target=worker, daemon=True).start()

    def _failed(self, error: Exception) -> None:
        self._busy = False
        self.refresh_button.configure(state="normal")
        self.status_var.set("No se pudo completar la operación")
        messagebox.showerror("Ayudas y subvenciones", str(error), parent=self)

    def _succeeded(self, result, callback) -> None:
        self._busy = False
        self.refresh_button.configure(state="normal")
        self.status_var.set("Actualizado")
        callback(result)

    def refresh(self) -> None:
        self._run("Actualizando panel...", self.service.get_subvenciones_dashboard, self._show_dashboard)

    def _show_dashboard(self, data: dict) -> None:
        totals = data.get("totales") or {}
        for key, variable in self.metric_vars.items():
            variable.set(str(totals.get(key, 0)))
        config = data.get("configuracion") or {}
        self.service_active_var.set(bool(config.get("servicio_activo", True)))
        self.alerts_active_var.set(bool(config.get("avisos_activos", False)))
        self.ai_active_var.set(bool(config.get("resumenes_ia_activos", False)))
        self.ai_status_var.set(
            "Clave de IA configurada" if config.get("ia_configurada")
            else "No hay clave de IA: el catálogo funcionará sin resúmenes automáticos."
        )
        self.global_status_var.set(
            "Módulo global habilitado en el backend."
            if config.get("global_activo") else
            "Módulo global deshabilitado: configure CLIENT_SUBSIDIES_ENABLED=true en Railway."
        )
        last = data.get("ultima_ejecucion")
        if last:
            self.last_run_var.set(
                f"Última ejecución: {_date(last.get('inicio'))} · {last.get('estado', '')}\n"
                f"Leídas: {last.get('leidas', 0)} · Nuevas: {last.get('nuevas', 0)} · "
                f"Actualizadas: {last.get('actualizadas', 0)} · "
                f"Resumidas: {last.get('resumidas', 0)} · "
                f"Avisos enviados: {last.get('avisos_enviados', 0)}"
            )
        self._config_loaded = True
        self._load_calls()

    def _replace(self, tree: ttk.Treeview, rows: list[tuple]) -> None:
        tree.delete(*tree.get_children())
        for iid, values in rows:
            tree.insert("", "end", iid=iid, values=values)

    def _load_calls(self) -> None:
        query = self.query_var.get().strip()
        status = {
            "En vigor": "en_vigor",
            "Finalizadas": "finalizadas",
            "Todas": "todas",
        }[self.calls_status_var.get()]
        visibility = {
            "Visibles": "visibles",
            "Ocultas": "ocultas",
            "Todas": "todas",
        }[self.calls_visibility_var.get()]
        self._run(
            "Cargando convocatorias...",
            lambda: self.service.list_subvenciones(
                query, estado=status, visibilidad=visibility,
            ),
            self._show_calls,
        )

    def _show_calls(self, items: list[dict]) -> None:
        self._replace(self.calls_tree, [
            (str(item.get("codigo_bdns")), (
                item.get("codigo_bdns", ""), item.get("fecha_publicacion", ""),
                item.get("ambito", ""), item.get("titulo", ""),
                fecha_fin_presentable(item.get("fecha_fin")),
                _yes(item.get("visible")), _yes(item.get("revisada")),
                item.get("resumen_estado", ""),
            )) for item in items
        ])

    def _selected_call(self) -> tuple[str, dict] | None:
        selection = self.calls_tree.selection()
        if not selection:
            messagebox.showinfo("Ayudas", "Seleccione una convocatoria.", parent=self)
            return None
        iid = selection[0]
        values = self.calls_tree.item(iid, "values")
        return iid, {"visible": values[5] == "Sí", "revisada": values[6] == "Sí"}

    def _patch_call(self, **changes) -> None:
        selected = self._selected_call()
        if not selected:
            return
        code, _state = selected
        self._run(
            "Guardando convocatoria...",
            lambda: self.service.update_subvencion(code, **changes),
            lambda _result: self._load_calls(),
        )

    def _set_visibility(self, visible: bool) -> None:
        self._patch_call(visible=visible)

    def _mark_reviewed(self) -> None:
        self._patch_call(revisada=True)

    def _redo_summary(self) -> None:
        self._patch_call(rehacer_resumen=True)

    def _load_organizations(self) -> None:
        self._run(
            "Cargando empresas...", self.service.list_subvenciones_organizations,
            self._show_organizations,
        )

    def _show_organizations(self, items: list[dict]) -> None:
        self._organization_items = list(items)
        self._apply_organization_filters()

    def _apply_organization_filters(self) -> None:
        items = filtrar_organizaciones(
            self._organization_items,
            self.organization_query_var.get(),
            self.organization_status_var.get(),
        )
        rows = []
        for item in items:
            territory = item.get("territorio") or {}
            label = " · ".join(filter(None, (
                territory.get("municipio"), territory.get("provincia_nombre"),
                territory.get("ccaa_nombre"),
            )))
            code = str(item.get("codigo_empresa", ""))
            rows.append((code, (
                code, item.get("empresa", ""), label,
                item.get("usuarios_activos", 0), _yes(item.get("activa")),
                _yes(item.get("efectiva")),
            )))
        self._replace(self.organizations_tree, rows)
        self._update_organization_count()

    def _update_organization_count(self) -> None:
        visible = len(self.organizations_tree.get_children())
        selected = len(self.organizations_tree.selection())
        total = len(self._organization_items)
        suffix = f" · {selected} seleccionadas" if selected else ""
        self.organization_count_var.set(f"Mostrando {visible} de {total}{suffix}")

    def _select_visible_organizations(self) -> None:
        visible = self.organizations_tree.get_children()
        self.organizations_tree.selection_set(visible)
        self._update_organization_count()

    def _set_selected_organizations(self, active: bool) -> None:
        selection = list(self.organizations_tree.selection())
        if not selection:
            messagebox.showinfo(
                "Empresas", "Seleccione una o varias empresas.", parent=self,
            )
            return
        action = "activar" if active else "desactivar"
        if not messagebox.askyesno(
            "Empresas",
            f"¿Desea {action} ayudas y subvenciones para {len(selection)} empresa(s)?",
            parent=self,
        ):
            return
        self._run(
            f"Guardando {len(selection)} empresas...",
            lambda: self.service.set_subvenciones_organizations(selection, active),
            lambda _result: self._load_organizations(),
        )

    def _toggle_organization(self) -> None:
        selection = self.organizations_tree.selection()
        if not selection:
            messagebox.showinfo("Empresas", "Seleccione una empresa.", parent=self)
            return
        if len(selection) > 1:
            messagebox.showinfo(
                "Empresas",
                "Para varias empresas use Activar selección o Desactivar selección.",
                parent=self,
            )
            return
        code = selection[0]
        active = self.organizations_tree.item(code, "values")[4] == "Sí"
        self._run(
            "Guardando activación...",
            lambda: self.service.set_subvenciones_organization(code, not active),
            lambda _result: self._load_organizations(),
        )

    def _load_subscriptions(self) -> None:
        self._run(
            "Cargando suscripciones...", self.service.list_subvenciones_subscriptions,
            self._show_subscriptions,
        )

    def _show_subscriptions(self, items: list[dict]) -> None:
        configured = sum(bool(item.get("configurada")) for item in items)
        with_alerts = sum(bool(item.get("notificaciones_activas")) for item in items)
        self.subscription_count_var.set(
            f"{len(items)} usuarios · {configured} configurados · {with_alerts} con avisos"
        )
        self._replace(self.subscriptions_tree, [
            (str(item.get("client_id")), (
                item.get("codigo_empresa", ""), item.get("empresa", ""),
                item.get("usuario", ""), item.get("email", ""),
                "Configuradas" if item.get("configurada") else "Sin configurar",
                _yes(item.get("notificaciones_activas")),
                _preference_value(item.get("incluir_nacionales")),
                _preference_value(item.get("usar_territorio_empresa")),
                ", ".join(item.get("territorios") or []),
            )) for item in items
        ])

    def _load_deliveries(self) -> None:
        self._run(
            "Cargando envíos...", self.service.list_subvenciones_deliveries,
            self._show_deliveries,
        )

    def _show_deliveries(self, items: list[dict]) -> None:
        self._replace(self.deliveries_tree, [
            (str(item.get("id")), (
                _date(item.get("enviada_at")), item.get("estado", ""),
                item.get("usuario", ""), item.get("email", ""),
                item.get("codigo_bdns", ""), item.get("titulo", ""),
                item.get("dispositivos_enviados", 0), item.get("ultimo_error", ""),
            )) for item in items
        ])

    def _save_settings(self) -> None:
        if not self._config_loaded:
            return
        self._run(
            "Guardando configuración...",
            lambda: self.service.update_subvenciones_config(
                servicio=self.service_active_var.get(),
                avisos=self.alerts_active_var.get(),
                ia=self.ai_active_var.get(),
            ),
            lambda _result: self.refresh(),
        )

    def _sync_now(self) -> None:
        self._run(
            "Lanzando sincronización...", self.service.sync_subvenciones,
            lambda _result: self._sync_started(),
        )

    def _sync_started(self) -> None:
        self.status_var.set("Sincronización iniciada en segundo plano")
        messagebox.showinfo(
            "Ayudas y subvenciones",
            "La sincronización se ha iniciado. Actualice el panel en unos minutos.",
            parent=self,
        )

    def _tab_changed(self, _event=None) -> None:
        index = self.notebook.index(self.notebook.select())
        if index == 0:
            self._load_calls()
        elif index == 1:
            self._load_organizations()
        elif index == 2:
            self._load_subscriptions()
        elif index == 3:
            self._load_deliveries()


def _yes(value) -> str:
    return "Sí" if bool(value) else "No"


def fecha_fin_presentable(value) -> str:
    return str(value) if value else "Sin fecha indicada"


def _preference_value(value) -> str:
    if value is None:
        return "—"
    return _yes(value)


def filtrar_organizaciones(
    items: list[dict], query: str = "", status: str = "Todas",
) -> list[dict]:
    needle = query.strip().casefold()
    result = []
    for item in items:
        territory = item.get("territorio") or {}
        searchable = " ".join((
            str(item.get("codigo_empresa") or ""),
            str(item.get("empresa") or ""),
            str(territory.get("municipio") or ""),
            str(territory.get("provincia_nombre") or ""),
            str(territory.get("ccaa_nombre") or ""),
        )).casefold()
        if needle and needle not in searchable:
            continue
        active = bool(item.get("activa"))
        users = int(item.get("usuarios_activos") or 0)
        if status == "Activadas" and not active:
            continue
        if status == "Desactivadas" and active:
            continue
        if status == "Con usuarios" and users <= 0:
            continue
        if status == "Sin usuarios" and users > 0:
            continue
        result.append(item)
    return result


def _date(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    return parsed.astimezone().strftime("%d/%m/%Y %H:%M")
