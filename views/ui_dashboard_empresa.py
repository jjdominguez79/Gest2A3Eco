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
        ("inicio",         "\u2190", "Inicio",            "inicio"),
        ("facturacion",    "\u25a3", "Facturacion",       "facturacion"),
        ("ocr",            "\u25ce", "Captura documental","ocr"),
        ("contabilidad",   "\u25a0", "Contabilidad",      "contabilidad"),
        ("importaciones",  "\u25a4", "Importaciones",     "importaciones"),
        ("plantillas",     "\u2630", "Plantillas",        "plantillas"),
        ("comunicaciones",  "\u2709", "Comunicaciones",   "comunicaciones"),
        ("maestro_cuentas",    "\u25a1", "Maestro cuentas",       "maestro_cuentas"),
        ("configuracion",      "\u2699", "Configuracion",         "configuracion"),
    ]

    # Stat cards: (key, label, color)
    _STATS = [
        ("facturacion", "Facturacion ejercicio", "#2563eb"),
        ("emitidas",    "Facturas emitidas",    "#0ea5e9"),
        ("recibidos",   "Emails recibidos",     "#8b5cf6"),
        ("enviados",    "Emails enviados",      "#10b981"),
        ("pendientes",  "Pendientes de gestionar", "#f59e0b"),
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
        on_open_terceros=None,
        on_open_maestro_cuentas=None,
        on_open_comunicaciones=None,
        on_previous_company=None,
        on_next_company=None,
        company_position: int = 0,
        company_total: int = 0,
        on_back=None,
    ):
        super().__init__(parent)
        self._empresa_service = empresa_service
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._on_back = on_back or (lambda: None)  # usado solo desde el boton Empresas del header
        self._on_previous_company = on_previous_company
        self._on_next_company = on_next_company
        self._company_position = company_position
        self._company_total = company_total
        self._callbacks = {
            "inicio":          self._go_dashboard,
            "facturacion":     on_open_facturacion,
            "ocr":             on_open_ocr,
            "contabilidad":    on_open_contabilidad,
            "importaciones":   on_open_importaciones,
            "plantillas":      on_open_plantillas,
            "terceros":        on_open_terceros or (lambda: None),
            "maestro_cuentas": on_open_maestro_cuentas or (lambda: None),
            "comunicaciones":  on_open_comunicaciones or (lambda: None),
            "configuracion":   on_open_configuracion,
        }
        self._ctx = {}
        self._nav_items: dict[str, dict] = {}
        self._stat_value_labels: dict[str, tk.Label] = {}
        self._pending_rows: list[tuple[tk.Label, tk.Label]] = []
        self._disabled_keys: set[str] = set()
        self._current_module_widget = None
        self._current_nav_key = "inicio"
        self._build()
        self.show_dashboard()

    # ------------------------------------------------------------------ build

    def _build(self):
        body = tk.Frame(self, bg=self._S_BG)
        body.pack(fill="both", expand=True)
        self._build_sidebar(body)
        self._content_holder = tk.Frame(body, bg=self._M_BG)
        self._content_holder.pack(side="left", fill="both", expand=True)
        self._dashboard_frame = tk.Frame(self._content_holder, bg=self._M_BG)
        self._build_main_into(self._dashboard_frame)

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=self._S_BG, width=210)
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

        nav_wrap = tk.Frame(topbar, bg=self._M_CARD)
        nav_wrap.pack(side="right", fill="y", padx=16)
        self.btn_previous_company = ttk.Button(
            nav_wrap, text="\u2190 Cliente anterior",
            command=self._on_previous_company or (lambda: None),
            state="normal" if self._on_previous_company else "disabled",
        )
        self.btn_previous_company.pack(side="left", pady=12, padx=(0, 6))
        position_text = (
            f"Cliente {self._company_position} de {self._company_total}"
            if self._company_position and self._company_total else ""
        )
        tk.Label(
            nav_wrap, text=position_text, bg=self._M_CARD, fg=self._M_SUB,
            font=("Segoe UI", 9),
        ).pack(side="left", pady=18, padx=6)
        self.btn_next_company = ttk.Button(
            nav_wrap, text="Cliente siguiente \u2192",
            command=self._on_next_company or (lambda: None),
            state="normal" if self._on_next_company else "disabled",
        )
        self.btn_next_company.pack(side="left", pady=12, padx=(6, 0))

        tk.Frame(parent, bg=self._M_BORDER, height=1).pack(fill="x")

        # --- Indicadores principales ---
        stats_row = tk.Frame(parent, bg=self._M_BG)
        stats_row.pack(fill="x", padx=24, pady=20)
        for i, (key, label, color) in enumerate(self._STATS):
            pad_right = 14 if i < len(self._STATS) - 1 else 0
            commands = {
                "facturacion": self._callbacks["facturacion"],
                "emitidas": self._callbacks["facturacion"],
                "recibidos": self._callbacks["comunicaciones"],
                "enviados": self._callbacks["comunicaciones"],
                "pendientes": self._open_pendientes,
            }
            card = self._make_stat_card(stats_row, label, color, commands[key])
            card.grid(row=0, column=i, padx=(0, pad_right), sticky="nsew")
            stats_row.columnconfigure(i, weight=1)
            self._stat_value_labels[key] = card._val_lbl  # type: ignore[attr-defined]

        # --- Centro operativo ---
        mid = tk.Frame(parent, bg=self._M_BG)
        mid.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        mid.columnconfigure(0, weight=3, minsize=440)
        mid.columnconfigure(1, weight=2, minsize=300)
        mid.rowconfigure(0, weight=1)

        chart_card = self._make_card(mid, "Facturacion mensual")
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.lbl_chart_total = tk.Label(
            chart_card, text="", bg=self._M_CARD, fg=self._M_SUB,
            font=("Segoe UI", 9),
        )
        self.lbl_chart_total.pack(anchor="w", padx=16, pady=(8, 0))
        self.chart_canvas = tk.Canvas(chart_card, bg=self._M_CARD, highlightthickness=0, height=250)
        self.chart_canvas.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.chart_canvas.bind("<Configure>", lambda _event: self._draw_chart())
        self.chart_canvas.bind("<Button-1>", lambda _event: self._callbacks["facturacion"]())

        right = tk.Frame(mid, bg=self._M_BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)

        pending_card = self._make_card(right, "Pendientes de gestionar")
        pending_card.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
        self.pending_body = tk.Frame(pending_card, bg=self._M_CARD)
        self.pending_body.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        for label, command in (
            ("Correos sin cerrar", self._callbacks["comunicaciones"]),
            ("Documentos OCR por revisar", self._callbacks["ocr"]),
            ("Facturas por completar", self._callbacks["facturacion"]),
        ):
            row = tk.Frame(self.pending_body, bg=self._M_CARD, cursor="hand2")
            row.pack(fill="x", pady=3)
            text = tk.Label(row, text=label, bg=self._M_CARD, fg=self._M_TEXT, font=("Segoe UI", 9), anchor="w")
            text.pack(side="left", fill="x", expand=True)
            value = tk.Label(row, text="0", bg=self._M_CARD, fg="#f59e0b", font=("Segoe UI", 10, "bold"))
            value.pack(side="right")
            for widget in (row, text, value):
                widget.bind("<Button-1>", lambda _event, cmd=command: cmd())
            self._pending_rows.append((text, value))

        activity_card = self._make_card(right, "Actividad de correo")
        activity_card.grid(row=1, column=0, sticky="nsew")
        self.activity_body = tk.Frame(activity_card, bg=self._M_CARD)
        self.activity_body.pack(fill="both", expand=True, padx=16, pady=(6, 10))

    def _make_stat_card(self, parent, label: str, color: str, command=None) -> tk.Frame:
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
        if command:
            card.configure(cursor="hand2")
            for widget in card.winfo_children():
                widget.bind("<Button-1>", lambda _event, cmd=command: cmd())
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
        self._current_nav_key = active_key
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

    @property
    def current_nav_key(self) -> str:
        return self._current_nav_key

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
        fact     = self._ctx.get("resumen_facturacion") or {}
        correos  = self._ctx.get("resumen_comunicaciones") or {}
        pendientes = self._ctx.get("pendientes") or {}

        nombre    = empresa.get("nombre", "")
        codigo    = empresa.get("codigo", self._codigo)
        ejercicio = empresa.get("ejercicio", self._ejercicio)
        permiso   = self._ctx.get("permiso", "")

        self.lbl_title.configure(text=f"{nombre}  ({codigo})")
        self.lbl_sub.configure(text=f"Ejercicio {ejercicio}   \u00b7   {permiso}")

        # Stats
        self._set_stat("facturacion", self._format_euro(fact.get("importe_total", 0)))
        self._set_stat("emitidas", fact.get("total", 0))
        self._set_stat("recibidos", correos.get("recibidos", 0))
        self._set_stat("enviados", correos.get("enviados", 0))
        self._set_stat("pendientes", pendientes.get("total", 0))
        self.lbl_chart_total.configure(
            text=f"Total facturado: {self._format_euro(fact.get('importe_total', 0))}"
        )
        self._chart_values = list(fact.get("mensual") or [])
        self._draw_chart()

        for (label, value), text, count in zip(
            self._pending_rows,
            ("Correos sin cerrar", "Documentos OCR por revisar", "Facturas por completar"),
            (pendientes.get("correos", 0), pendientes.get("ocr", 0), pendientes.get("facturacion", 0)),
        ):
            label.configure(text=text)
            value.configure(text=str(count))

        for child in self.activity_body.winfo_children():
            child.destroy()
        activity = self._ctx.get("actividad_comunicaciones") or []
        if not activity:
            tk.Label(
                self.activity_body, text="Sin correos recientes.", bg=self._M_CARD,
                fg=self._M_SUB, font=("Segoe UI", 9), anchor="w",
            ).pack(fill="x", pady=4)
        for item in activity:
            direction = "Recibido" if item.get("direccion") == "entrante" else "Enviado"
            text = f"{direction}  ·  {item.get('asunto', '')}"
            row = tk.Label(
                self.activity_body, text=text, bg=self._M_CARD, fg=self._M_TEXT,
                font=("Segoe UI", 9), anchor="w", cursor="hand2",
            )
            row.pack(fill="x", pady=3)
            row.bind("<Button-1>", lambda _event: self._callbacks["comunicaciones"]())

        # Permissions
        can_write = bool(self._ctx.get("can_write"))
        for key in ("configuracion", "plantillas", "importaciones", "ocr", "contabilidad"):
            self._set_nav_enabled(key, can_write)

    def _set_stat(self, key: str, value):
        lbl = self._stat_value_labels.get(key)
        if lbl:
            lbl.configure(text=str(value))

    def _open_pendientes(self):
        pendientes = self._ctx.get("pendientes") or {}
        if pendientes.get("correos"):
            self._callbacks["comunicaciones"]()
        elif pendientes.get("ocr"):
            self._callbacks["ocr"]()
        else:
            self._callbacks["facturacion"]()

    def _draw_chart(self):
        canvas = getattr(self, "chart_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        values = list(getattr(self, "_chart_values", []) or [])
        if len(values) != 12:
            values = [0.0] * 12
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 80 or height < 80:
            return
        left, right, top, bottom = 38, 12, 18, 28
        chart_width, chart_height = width - left - right, height - top - bottom
        max_value = max(values) if values else 0
        if max_value <= 0:
            canvas.create_text(width / 2, height / 2, text="Aun no hay facturacion en este ejercicio.", fill=self._M_SUB, font=("Segoe UI", 10))
            return
        for index in range(4):
            y = top + chart_height * index / 3
            canvas.create_line(left, y, width - right, y, fill="#e2e8f0")
            amount = max_value * (3 - index) / 3
            canvas.create_text(left - 6, y, text=self._compact_euro(amount), fill=self._M_SUB, font=("Segoe UI", 8), anchor="e")
        step = chart_width / 12
        bar_width = max(8, step * 0.56)
        for index, value in enumerate(values):
            x = left + step * index + (step - bar_width) / 2
            bar_height = chart_height * value / max_value
            y = top + chart_height - bar_height
            canvas.create_rectangle(x, y, x + bar_width, top + chart_height, fill="#2563eb", outline="")
            canvas.create_text(x + bar_width / 2, height - 12, text=("E F M A M J J A S O N D".split()[index]), fill=self._M_SUB, font=("Segoe UI", 8))

    def _format_euro(self, value) -> str:
        try:
            return f"{float(value or 0):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return "0,00 €"

    def _compact_euro(self, value) -> str:
        if value >= 1000:
            return f"{value / 1000:.0f}k"
        return f"{value:.0f} €"

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
