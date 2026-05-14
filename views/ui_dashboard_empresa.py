from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class UIDashboardEmpresa(ttk.Frame):
    # Sidebar colors
    _S_BG      = "#1e293b"
    _S_ACTIVE  = "#2563eb"
    _S_HOVER   = "#334155"
    _S_FG      = "#94a3b8"
    _S_FG_ACT  = "#ffffff"
    _S_SEP     = "#334155"

    # Main area colors
    _M_BG      = "#f1f5f9"
    _M_CARD    = "#ffffff"
    _M_BORDER  = "#e2e8f0"
    _M_TITLE   = "#0f172a"
    _M_SUB     = "#64748b"
    _M_TEXT    = "#475569"

    # Nav items: (key, unicode_icon, label, cb_key)
    _NAV = [
        ("inicio",        "\u2190", "Inicio",             "inicio"),
        ("facturacion",   "\u25a3", "Facturacion",        "facturacion"),
        ("ocr",           "\u25ce", "OCR",                "ocr"),
        ("contabilidad",  "\u25a0", "Contabilidad",       "contabilidad"),
        ("importaciones", "\u25a4", "Importaciones",      "importaciones"),
        ("plantillas",    "\u2630", "Plantillas",         "plantillas"),
        ("configuracion", "\u2699", "Configuracion",      "configuracion"),
    ]

    # Stat cards: (key, label, color)
    _STATS = [
        ("total_emitidas", "Facturas emitidas", "#2563eb"),
        ("borradores",     "Borradores",        "#f59e0b"),
        ("generadas",      "Generadas",         "#10b981"),
        ("terceros",       "Terceros",          "#8b5cf6"),
    ]

    def __init__(
        self,
        parent,
        empresa_service,
        codigo,
        ejercicio,
        *,
        on_open_facturacion,
        on_open_importaciones,
        on_open_contabilidad,
        on_open_plantillas,
        on_open_configuracion,
        on_open_ocr,
        on_back,
    ):
        super().__init__(parent)
        self._empresa_service = empresa_service
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._on_back = on_back  # usado solo desde el boton Empresas del header
        self._callbacks = {
            "inicio":        self._go_dashboard,
            "facturacion":   on_open_facturacion,
            "ocr":           on_open_ocr,
            "contabilidad":  on_open_contabilidad,
            "importaciones": on_open_importaciones,
            "plantillas":    on_open_plantillas,
            "configuracion": on_open_configuracion,
        }
        self._ctx = {}
        self._nav_items: dict[str, dict] = {}
        self._stat_value_labels: dict[str, tk.Label] = {}
        self._disabled_keys: set[str] = set()
        self._current_module_widget = None
        self._build()
        self.show_dashboard()

    # ------------------------------------------------------------------ build

    def _build(self):
        self._build_sidebar()
        # Area de contenido intercambiable (derecha)
        self._content_holder = tk.Frame(self, bg=self._M_BG)
        self._content_holder.pack(side="left", fill="both", expand=True)
        # Frame del dashboard (pre-construido, se oculta/muestra)
        self._dashboard_frame = tk.Frame(self._content_holder, bg=self._M_BG)
        self._build_main_into(self._dashboard_frame)

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=self._S_BG, width=210)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # Separador superior
        tk.Frame(sb, bg=self._S_SEP, height=1).pack(fill="x", padx=12, pady=(14, 6))

        # Nav items
        for key, icon, label, cb_key in self._NAV:
            self._add_nav_item(sb, key, icon, label, self._callbacks[cb_key])

    def _add_nav_item(self, parent, key, icon, label, command):
        row = tk.Frame(parent, bg=self._S_BG, cursor="hand2")
        row.pack(fill="x", pady=1)

        accent = tk.Frame(row, bg=self._S_BG, width=3)
        accent.pack(side="left", fill="y")

        inner = tk.Frame(row, bg=self._S_BG)
        inner.pack(side="left", fill="x", expand=True)

        lbl_icon = tk.Label(
            inner, text=icon,
            bg=self._S_BG, fg=self._S_FG,
            font=("Segoe UI", 11), width=3,
        )
        lbl_icon.pack(side="left", pady=10, padx=(10, 0))

        lbl_text = tk.Label(
            inner, text=label,
            bg=self._S_BG, fg=self._S_FG,
            font=("Segoe UI", 10), anchor="w",
        )
        lbl_text.pack(side="left", pady=10, padx=(6, 16), fill="x", expand=True)

        self._nav_items[key] = {
            "row": row, "accent": accent, "inner": inner,
            "lbl_icon": lbl_icon, "lbl_text": lbl_text,
            "command": command, "active": False,
        }

        widgets = (row, accent, inner, lbl_icon, lbl_text)
        for w in widgets:
            w.bind("<Button-1>", lambda e, cmd=command, k=key: self._on_nav_click(k, cmd))
            w.bind("<Enter>", lambda e, k=key: self._on_nav_hover(k, True))
            w.bind("<Leave>", lambda e, k=key: self._on_nav_hover(k, False))

    def _build_main_into(self, parent):
        # --- Top bar ---
        topbar = tk.Frame(parent, bg=self._M_CARD, height=58)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Frame(topbar, bg=self._M_BORDER, width=1).pack(side="left", fill="y")

        title_wrap = tk.Frame(topbar, bg=self._M_CARD)
        title_wrap.pack(side="left", fill="y", padx=20)

        self.lbl_title = tk.Label(
            title_wrap, text="",
            bg=self._M_CARD, fg=self._M_TITLE,
            font=("Segoe UI", 13, "bold"),
        )
        self.lbl_title.pack(side="left", pady=16)

        self.lbl_sub = tk.Label(
            title_wrap, text="",
            bg=self._M_CARD, fg=self._M_SUB,
            font=("Segoe UI", 9),
        )
        self.lbl_sub.pack(side="left", padx=(8, 0), pady=18)

        tk.Frame(parent, bg=self._M_BORDER, height=1).pack(fill="x")

        # --- Stat cards row ---
        stats_row = tk.Frame(parent, bg=self._M_BG)
        stats_row.pack(fill="x", padx=24, pady=20)
        for i, (key, label, color) in enumerate(self._STATS):
            pad_right = 14 if i < len(self._STATS) - 1 else 0
            card = self._make_stat_card(stats_row, label, color)
            card.grid(row=0, column=i, padx=(0, pad_right), sticky="nsew")
            stats_row.columnconfigure(i, weight=1)
            self._stat_value_labels[key] = card._val_lbl  # type: ignore[attr-defined]

        # --- Mid section ---
        mid = tk.Frame(parent, bg=self._M_BG)
        mid.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)

        # Config status card
        cfg_card = self._make_card(mid, "Configuracion")
        cfg_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.lbl_config_detail = tk.Label(
            cfg_card, text="",
            bg=self._M_CARD, fg=self._M_TEXT,
            font=("Segoe UI", 9), justify="left",
        )
        self.lbl_config_detail.pack(anchor="w", padx=16, pady=(8, 16))

        # Processes card
        proc_card = self._make_card(mid, "Ultimos procesos")
        proc_card.grid(row=0, column=1, sticky="nsew")
        self.lb_procesos = tk.Listbox(
            proc_card,
            bg=self._M_CARD, fg=self._M_TEXT,
            font=("Segoe UI", 9),
            relief="flat", bd=0,
            selectbackground="#eff6ff", selectforeground="#1e40af",
            highlightthickness=0,
        )
        self.lb_procesos.pack(fill="both", expand=True, padx=8, pady=(4, 12))

    def _make_stat_card(self, parent, label: str, color: str) -> tk.Frame:
        card = tk.Frame(parent, bg=self._M_CARD,
                        highlightbackground=self._M_BORDER, highlightthickness=1)
        tk.Frame(card, bg=color, height=4).pack(fill="x")
        val_lbl = tk.Label(
            card, text="—",
            bg=self._M_CARD, fg=color,
            font=("Segoe UI", 26, "bold"),
        )
        val_lbl.pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(
            card, text=label,
            bg=self._M_CARD, fg=self._M_SUB,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16, pady=(0, 14))
        card._val_lbl = val_lbl  # type: ignore[attr-defined]
        return card

    def _make_card(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=self._M_CARD,
                        highlightbackground=self._M_BORDER, highlightthickness=1)
        tk.Label(
            card, text=title,
            bg=self._M_CARD, fg=self._M_TITLE,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))
        tk.Frame(card, bg=self._M_BORDER, height=1).pack(fill="x", padx=16)
        return card

    # ----------------------------------------------------------------- public API

    def get_content_holder(self) -> tk.Frame:
        return self._content_holder

    def show_dashboard(self):
        """Muestra el panel de dashboard en el area de contenido."""
        if self._current_module_widget is not None:
            self._current_module_widget.destroy()
            self._current_module_widget = None
        self._dashboard_frame.pack(fill="both", expand=True)
        self._set_active_nav("inicio")
        self.refresh()

    def show_module(self, widget, nav_key: str | None = None):
        """Reemplaza el contenido con el widget de modulo dado."""
        # Ocultar dashboard
        self._dashboard_frame.pack_forget()
        # Destruir modulo anterior
        if self._current_module_widget is not None:
            self._current_module_widget.destroy()
        self._current_module_widget = widget
        if not widget.winfo_manager():
            widget.pack(fill="both", expand=True)
        if nav_key:
            self._set_active_nav(nav_key)

    def _go_dashboard(self):
        self.show_dashboard()

    # ----------------------------------------------------------------- nav helpers

    def _set_active_nav(self, active_key: str):
        for key, item in self._nav_items.items():
            is_active = (key == active_key)
            bg_item  = self._S_ACTIVE if is_active else self._S_BG
            fg_item  = self._S_FG_ACT if is_active else self._S_FG
            acc_bg   = "#60a5fa"      if is_active else self._S_BG
            for w in (item["row"], item["inner"], item["lbl_icon"], item["lbl_text"]):
                w.configure(bg=bg_item)
            item["accent"].configure(bg=acc_bg)
            item["lbl_icon"].configure(fg=fg_item)
            item["lbl_text"].configure(fg=fg_item)
            item["active"] = is_active

    def _on_nav_click(self, key, command):
        if key not in self._disabled_keys:
            command()

    def _on_nav_hover(self, key, entering):
        if key in self._disabled_keys:
            return
        item = self._nav_items.get(key)
        if not item or item.get("active"):
            return
        bg = self._S_HOVER if entering else self._S_BG
        fg = "#e2e8f0"     if entering else self._S_FG
        for w in (item["row"], item["inner"], item["lbl_icon"], item["lbl_text"]):
            w.configure(bg=bg)
        item["lbl_icon"].configure(fg=fg)
        item["lbl_text"].configure(fg=fg)
        item["accent"].configure(bg=bg)

    # ----------------------------------------------------------------- refresh

    def refresh(self):
        self._ctx = self._empresa_service.get_dashboard_context(self._codigo, self._ejercicio)
        empresa  = self._ctx.get("empresa") or {}
        contab   = self._ctx.get("resumen_contabilidad") or {}
        fact     = self._ctx.get("resumen_facturacion") or {}

        nombre    = empresa.get("nombre", "")
        codigo    = empresa.get("codigo", self._codigo)
        ejercicio = empresa.get("ejercicio", self._ejercicio)
        permiso   = self._ctx.get("permiso", "")

        self.lbl_title.configure(text=f"{nombre}  ({codigo})")
        self.lbl_sub.configure(text=f"Ejercicio {ejercicio}   \u00b7   {permiso}")

        # Stats
        self._set_stat("total_emitidas", fact.get("total", 0))
        self._set_stat("borradores",     fact.get("borrador", 0))
        self._set_stat("generadas",      fact.get("generadas", 0))
        self._set_stat("terceros",       self._ctx.get("terceros_count", 0))

        # Config detail
        lines = [
            f"Estado:               {self._ctx.get('estado_configuracion', '')}",
            f"Plan contable:        {contab.get('plan_cuentas', 0)} cuentas",
            f"Plantillas bancos:    {contab.get('plantillas_bancos', 0)}",
            f"Plantillas emitidas:  {contab.get('plantillas_emitidas', 0)}",
            f"Plantillas recibidas: {contab.get('plantillas_recibidas', 0)}",
            f"Terceros asignados:   {self._ctx.get('terceros_count', 0)}",
        ]
        self.lbl_config_detail.configure(text="\n".join(lines))

        # Processes
        self.lb_procesos.delete(0, tk.END)
        for item in self._ctx.get("ultimos_procesos") or []:
            self.lb_procesos.insert(
                tk.END,
                f"{item.get('fecha', '')}  \u00b7  {item.get('descripcion', '')}",
            )
        if self.lb_procesos.size() == 0:
            self.lb_procesos.insert(tk.END, "Sin procesos recientes.")

        # Permissions
        can_write = bool(self._ctx.get("can_write"))
        for key in ("configuracion", "plantillas", "importaciones", "ocr", "contabilidad"):
            self._set_nav_enabled(key, can_write)

    def _set_stat(self, key: str, value):
        lbl = self._stat_value_labels.get(key)
        if lbl:
            lbl.configure(text=str(value))

    def _set_nav_enabled(self, key: str, enabled: bool):
        item = self._nav_items.get(key)
        if not item:
            return
        if enabled:
            self._disabled_keys.discard(key)
            fg = self._S_FG if not item.get("active") else self._S_FG_ACT
        else:
            self._disabled_keys.add(key)
            fg = "#4b5563"
        item["lbl_icon"].configure(fg=fg)
        item["lbl_text"].configure(fg=fg)
