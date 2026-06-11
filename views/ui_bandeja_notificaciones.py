"""
Vista: Bandeja de Notificaciones Electronicas.

Pantalla principal del modulo. Muestra todas las notificaciones recibidas de
organismos, con panel de detalle lateral, filtros por estado/organismo, y
acciones de aceptacion, rechazo y eliminacion. Operativo sobre SQLite local.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403

ESTADOS = ["", "PENDIENTE", "ACEPTADA", "RECHAZADA", "VENCIDA"]
LABEL_ESTADO = {
    "PENDIENTE":  "Pendiente",
    "ACEPTADA":   "Aceptada",
    "RECHAZADA":  "Rechazada",
    "VENCIDA":    "Vencida",
}
COLOR_ESTADO = {
    "PENDIENTE":  _WARNING,
    "ACEPTADA":   _SUCCESS,
    "RECHAZADA":  _SUB,
    "VENCIDA":    _DANGER,
}


def _dias_restantes(fecha_str: str | None) -> int | None:
    if not fecha_str:
        return None
    try:
        return (datetime.strptime(fecha_str[:10], "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def _fmt_fecha(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return valor[:10]


class UIBandejaNotificaciones(ttk.Frame):
    """
    Bandeja de entrada de notificaciones electronicas.
    Layout maestro-detalle: lista a la izquierda, ficha a la derecha.
    """

    _COLS = [
        ("organismo",   "Organismo",        130, "w"),
        ("tipo_acto",   "Tipo acto",        110, "w"),
        ("asunto",      "Asunto",           260, "w"),
        ("f_disp",      "Disposicion",       88, "center"),
        ("f_venc",      "Vencimiento",       88, "center"),
        ("estado",      "Estado",            80, "center"),
    ]

    def __init__(self, master, controller, session=None):
        super().__init__(master)
        self._controller  = controller
        self._session     = session
        self._selected_id: str | None = None
        self._cache: list[dict] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        self._build_header()
        self._build_filter_bar()
        # Cuerpo principal: lista + detalle
        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        self._build_list_panel(body)
        self._build_detail_panel(body)
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\u2709  Bandeja de Notificaciones", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Notificaciones recibidas de organismos publicos",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)
        # Boton actualizar en el header
        tk.Button(
            hdr, text="\u21bb  Sincronizar (simulado)",
            bg="#334155", fg=_HDR_SUB,
            font=("Segoe UI", 8), relief="flat", padx=8, pady=4, cursor="hand2",
            command=self._on_sincronizar,
        ).pack(side="right", padx=12, pady=8)

    def _build_filter_bar(self) -> None:
        fb = tk.Frame(self, bg="#e2e8f0", pady=4)
        fb.pack(fill="x", padx=8, pady=(0, 2))

        tk.Label(fb, text="Estado:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_estado = tk.StringVar(value="")
        cb_estado = ttk.Combobox(
            fb, textvariable=self._var_estado,
            values=["Todos"] + [LABEL_ESTADO.get(e, e) for e in ESTADOS if e],
            state="readonly", width=13,
        )
        cb_estado.set("Todos")
        cb_estado.pack(side="left", padx=(0, 12))
        cb_estado.bind("<<ComboboxSelected>>", self._on_filter)

        tk.Label(fb, text="Organismo:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_org = tk.StringVar(value="")
        self._cb_org  = ttk.Combobox(fb, textvariable=self._var_org, state="readonly", width=22)
        self._cb_org.set("Todos")
        self._cb_org.pack(side="left", padx=(0, 12))
        self._cb_org.bind("<<ComboboxSelected>>", self._on_filter)

        tk.Label(fb, text="Buscar:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_buscar = tk.StringVar()
        ent = ttk.Entry(fb, textvariable=self._var_buscar, width=20)
        ent.pack(side="left", padx=(0, 4))
        ent.bind("<Return>",   self._on_filter)
        ent.bind("<KeyRelease>", self._on_filter)

        self._lbl_count = tk.Label(fb, text="", bg="#e2e8f0", fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

    def _build_list_panel(self, parent: tk.Frame) -> None:
        # Toolbar de acciones sobre lista
        left = tk.Frame(parent, bg=_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)

        tb = tk.Frame(left, bg=_BG, pady=4)
        tb.grid(row=0, column=0, sticky="ew")
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=9, pady=3)
        self._btn_aceptar  = tk.Button(tb, text="\u2714 Aceptar",  bg=_SUCCESS, fg="white", command=self._on_aceptar,  state="disabled", **btn)
        self._btn_aceptar.pack(side="left", padx=(0, 4))
        self._btn_rechazar = tk.Button(tb, text="\u2718 Rechazar", bg=_DANGER,  fg="white", command=self._on_rechazar, state="disabled", **btn)
        self._btn_rechazar.pack(side="left", padx=(0, 4))
        self._btn_eliminar_b = tk.Button(tb, text="Eliminar", bg="#475569", fg="white", command=self._on_eliminar,  state="disabled", **btn)
        self._btn_eliminar_b.pack(side="left", padx=(0, 4))
        tk.Button(tb, text="\u21bb", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")

        # Treeview
        tree_wrap = tk.Frame(left, bg=_BG)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        col_ids = ["_id"] + [c[0] for c in self._COLS]
        self._tv = ttk.Treeview(tree_wrap, columns=col_ids, show="headings", selectmode="browse")
        self._tv.column("_id", width=0, stretch=False)
        self._tv.heading("_id", text="")
        for key, header, width, anchor in self._COLS:
            self._tv.heading(key, text=header)
            self._tv.column(key, width=width, anchor=anchor, stretch=(key == "asunto"))
        for estado in ("PENDIENTE", "ACEPTADA", "RECHAZADA", "VENCIDA"):
            self._tv.tag_configure(estado, foreground=COLOR_ESTADO[estado])
        self._tv.tag_configure("URGENTE", foreground="#dc2626", font=("Segoe UI", 9, "bold"))

        sb_v = ttk.Scrollbar(tree_wrap, orient="vertical",   command=self._tv.yview)
        sb_h = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tv.xview)
        self._tv.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        sb_v.pack(side="right",  fill="y")
        sb_h.pack(side="bottom", fill="x")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

    def _build_detail_panel(self, parent: tk.Frame) -> None:
        """Panel derecho: ficha de la notificacion seleccionada."""
        right = tk.Frame(parent, bg=_CARD,
                         highlightbackground=_BORDER, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew")

        # Cabecera del panel
        hdr = tk.Frame(right, bg=_TITLE)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Detalle", bg=_TITLE, fg="white",
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(padx=12, pady=8)

        scroll_frame = tk.Frame(right, bg=_CARD)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=8)

        def _campo(lbl_text: str, var: tk.StringVar, fg=_TEXT) -> None:
            f = tk.Frame(scroll_frame, bg=_CARD)
            f.pack(fill="x", pady=(0, 6))
            tk.Label(f, text=lbl_text, bg=_CARD, fg=_SUB,
                     font=("Segoe UI", 8), anchor="w").pack(anchor="w")
            tk.Label(f, textvariable=var, bg=_CARD, fg=fg,
                     font=("Segoe UI", 9), anchor="w", wraplength=260, justify="left").pack(anchor="w")

        self._dv_organismo    = tk.StringVar(value="—")
        self._dv_tipo_acto    = tk.StringVar(value="—")
        self._dv_referencia   = tk.StringVar(value="—")
        self._dv_estado       = tk.StringVar(value="—")
        self._dv_f_disp       = tk.StringVar(value="—")
        self._dv_f_venc       = tk.StringVar(value="—")
        self._dv_f_accion     = tk.StringVar(value="—")
        self._dv_nif          = tk.StringVar(value="—")
        self._dv_nombre       = tk.StringVar(value="—")
        self._dv_asunto       = tk.StringVar(value="—")
        self._dv_descripcion  = tk.StringVar(value="—")

        _campo("Organismo",               self._dv_organismo)
        _campo("Asunto",                  self._dv_asunto,  _TITLE)
        _campo("Tipo de acto",            self._dv_tipo_acto)
        _campo("Referencia",              self._dv_referencia)
        _campo("Estado",                  self._dv_estado)
        _campo("Puesta a disposicion",    self._dv_f_disp)
        _campo("Vencimiento",             self._dv_f_venc)
        _campo("Fecha accion",            self._dv_f_accion)
        _campo("NIF interesado",          self._dv_nif)
        _campo("Nombre interesado",       self._dv_nombre)
        _campo("Descripcion",             self._dv_descripcion)

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self, bg=_BG, height=22)
        sb.pack(fill="x", side="bottom")
        self._lbl_status = tk.Label(sb, text="", bg=_BG, fg=_SUB,
                                    font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(side="left", padx=8)

    # ----------------------------------------------------------------- eventos

    def _on_select(self, _e=None) -> None:
        sel = self._tv.selection()
        if not sel:
            self._selected_id = None
            self._clear_detail()
            self._set_action_buttons_state("disabled")
            return
        self._selected_id = self._tv.set(sel[0], "_id")
        item = self._controller.get_bandeja_item(self._selected_id)
        if item:
            self._populate_detail(item)
            estado = item.get("estado", "")
            can_accept  = estado == "PENDIENTE"
            can_reject  = estado == "PENDIENTE"
            self._btn_aceptar.configure(state="normal" if can_accept else "disabled")
            self._btn_rechazar.configure(state="normal" if can_reject else "disabled")
            self._btn_eliminar_b.configure(state="normal")

    def _on_filter(self, _e=None) -> None:
        estado_lbl = self._var_estado.get()
        org_lbl    = self._var_org.get()
        buscar     = self._var_buscar.get().lower().strip()
        # Mapear labels a valores internos
        inv_estado = {v: k for k, v in LABEL_ESTADO.items()}
        estado_val = inv_estado.get(estado_lbl, "") if estado_lbl not in ("", "Todos") else ""
        self._render_rows(
            [r for r in self._cache
             if (not estado_val or r.get("estado") == estado_val)
             and (not org_lbl or org_lbl in ("Todos", "", r.get("organismo_nombre", ""), r.get("organismo_codigo", "")))
             and (not buscar or buscar in (r.get("asunto", "") + r.get("tipo_acto", "") + r.get("referencia", "")).lower())
            ]
        )

    def _on_aceptar(self) -> None:
        if not self._selected_id:
            return
        if not messagebox.askyesno("Aceptar notificacion",
                                   "Marcar esta notificacion como ACEPTADA?",
                                   parent=self.winfo_toplevel()):
            return
        fecha = datetime.now().strftime("%Y-%m-%d")
        try:
            self._controller.cambiar_estado_bandeja(self._selected_id, "ACEPTADA", fecha)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_rechazar(self) -> None:
        if not self._selected_id:
            return
        if not messagebox.askyesno("Rechazar notificacion",
                                   "Marcar esta notificacion como RECHAZADA?\n"
                                   "Esta accion queda registrada.",
                                   parent=self.winfo_toplevel()):
            return
        fecha = datetime.now().strftime("%Y-%m-%d")
        try:
            self._controller.cambiar_estado_bandeja(self._selected_id, "RECHAZADA", fecha)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_eliminar(self) -> None:
        if not self._selected_id:
            return
        if not messagebox.askyesno("Eliminar notificacion",
                                   "Eliminar definitivamente esta notificacion del registro local?",
                                   parent=self.winfo_toplevel()):
            return
        try:
            self._controller.eliminar_bandeja_item(self._selected_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self._selected_id = None
        self.refresh()

    def _on_sincronizar(self) -> None:
        """Sincronizacion simulada: muestra mensaje informativo."""
        messagebox.showinfo(
            "Sincronizar notificaciones",
            "La conexion con organismos no esta disponible todavia.\n\n"
            "Esta funcion se activara cuando se configuren los conectores reales\n"
            "(DEH, 060, NOTIFIC@) en la seccion de Buzones.",
            parent=self.winfo_toplevel(),
        )

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        self._cache = self._controller.listar_bandeja()

        # Poblar combo de organismos
        org_nombres = sorted({r.get("organismo_nombre") or r.get("organismo_codigo") or ""
                               for r in self._cache if r.get("organismo_nombre") or r.get("organismo_codigo")})
        self._cb_org.configure(values=["Todos"] + org_nombres)
        if self._cb_org.get() not in (["Todos"] + org_nombres):
            self._cb_org.set("Todos")

        self._render_rows(self._cache)
        self._clear_detail()
        self._set_action_buttons_state("disabled")

    def _render_rows(self, rows: list[dict]) -> None:
        self._tv.delete(*self._tv.get_children())
        for r in rows:
            estado  = r.get("estado", "")
            tag     = estado
            dias    = _dias_restantes(r.get("fecha_vencimiento"))
            if estado == "PENDIENTE" and dias is not None and dias <= 10:
                tag = "URGENTE"  # sobreescribe color para urgencia
            f_disp = _fmt_fecha(r.get("fecha_puesta_disposicion"))
            f_venc = _fmt_fecha(r.get("fecha_vencimiento"))
            if dias is not None and estado == "PENDIENTE":
                f_venc = f"{f_venc} ({dias}d)" if dias >= 0 else f"{f_venc} (!)"
            org    = r.get("organismo_nombre") or r.get("organismo_codigo") or ""
            self._tv.insert("", tk.END, values=(
                r["id"], org, r.get("tipo_acto", "") or "",
                r.get("asunto", ""),
                f_disp, f_venc,
                LABEL_ESTADO.get(estado, estado),
            ), tags=(tag,))

        # Estadisticas
        pendientes = sum(1 for r in rows if r.get("estado") == "PENDIENTE")
        urgentes   = sum(1 for r in rows
                         if r.get("estado") == "PENDIENTE"
                         and (_dias_restantes(r.get("fecha_vencimiento")) or 999) <= 10)
        self._lbl_count.configure(
            text=f"{len(rows)} notificaciones  |  Pendientes: {pendientes}"
                 + (f"  |  URGENTES: {urgentes}" if urgentes else "")
        )
        total    = len(self._cache)
        aceptadas = sum(1 for r in self._cache if r.get("estado") == "ACEPTADA")
        vencidas  = sum(1 for r in self._cache if r.get("estado") == "VENCIDA")
        self._lbl_status.configure(
            text=f"Total ejercicio: {total}  |  Aceptadas: {aceptadas}  |  Vencidas: {vencidas}"
        )

    # ----------------------------------------------------------------- detalle

    def _populate_detail(self, item: dict) -> None:
        estado = item.get("estado", "")
        # Fecha de accion (aceptacion o rechazo)
        f_accion = _fmt_fecha(item.get("fecha_aceptacion") or item.get("fecha_rechazo"))
        if f_accion:
            accion_lbl = f"Aceptada: {f_accion}" if item.get("fecha_aceptacion") else f"Rechazada: {f_accion}"
        else:
            accion_lbl = "—"
        self._dv_organismo.set(item.get("organismo_nombre") or item.get("organismo_codigo") or "—")
        self._dv_asunto.set(item.get("asunto") or "—")
        self._dv_tipo_acto.set(item.get("tipo_acto") or "—")
        self._dv_referencia.set(item.get("referencia") or "—")
        self._dv_estado.set(LABEL_ESTADO.get(estado, estado))
        self._dv_f_disp.set(_fmt_fecha(item.get("fecha_puesta_disposicion")) or "—")
        self._dv_f_venc.set(_fmt_fecha(item.get("fecha_vencimiento")) or "—")
        self._dv_f_accion.set(accion_lbl)
        self._dv_nif.set(item.get("nif_interesado") or "—")
        self._dv_nombre.set(item.get("nombre_interesado") or "—")
        self._dv_descripcion.set(item.get("descripcion") or "—")

    def _clear_detail(self) -> None:
        for var in (self._dv_organismo, self._dv_tipo_acto, self._dv_referencia,
                    self._dv_estado, self._dv_f_disp, self._dv_f_venc,
                    self._dv_f_accion, self._dv_nif, self._dv_nombre,
                    self._dv_asunto, self._dv_descripcion):
            var.set("—")

    def _set_action_buttons_state(self, state: str) -> None:
        self._btn_aceptar.configure(state=state)
        self._btn_rechazar.configure(state=state)
        self._btn_eliminar_b.configure(state=state)
