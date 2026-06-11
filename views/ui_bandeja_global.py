"""
Vista: Bandeja Global de Notificaciones Electronicas.

Centro operativo del modulo "Notificaciones Electronicas". Muestra las
notificaciones de TODOS los clientes (empresas) en una unica pantalla, con
filtros por cliente, NIF, organismo, estado, responsable y fechas.

La gestion diaria del despacho se realiza siempre desde aqui: el cliente es
una dimension de configuracion y filtrado, no un punto de navegacion
obligatorio.
"""
from __future__ import annotations

import os
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, simpledialog, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_bandeja_notificaciones import (
    ESTADOS,
    LABEL_ESTADO,
    COLOR_ESTADO,
    _dias_restantes,
    _fmt_fecha,
)


class UIBandejaGlobal(ttk.Frame):
    """
    Bandeja global: notificaciones de todos los clientes.
    Layout maestro-detalle con filtros y acciones masivas/individuales.
    """

    _COLS = [
        ("cliente",     "Cliente",          150, "w"),
        ("nif",         "NIF",               90, "center"),
        ("organismo",   "Organismo",        110, "w"),
        ("buzon",       "Buzon",            130, "w"),
        ("asunto",      "Asunto",           220, "w"),
        ("f_disp",      "Disposicion",       85, "center"),
        ("f_venc",      "Vencimiento",       95, "center"),
        ("estado",      "Estado",            80, "center"),
        ("responsable", "Responsable",      110, "w"),
    ]

    def __init__(self, master, gestor, session=None, on_open_empresa=None):
        super().__init__(master)
        self._gestor = gestor
        self._session = session
        self._on_open_empresa = on_open_empresa
        self._selected_id: str | None = None
        self._cache: list[dict] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        self._build_header()
        self._build_filter_bar()
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
        tk.Label(hdr, text="✉  Bandeja global de notificaciones", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Notificaciones de todos los clientes",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)
        tk.Button(
            hdr, text="↻  Actualizar",
            bg="#334155", fg=_HDR_SUB,
            font=("Segoe UI", 8), relief="flat", padx=8, pady=4, cursor="hand2",
            command=self.refresh,
        ).pack(side="right", padx=12, pady=8)

    def _build_filter_bar(self) -> None:
        fb = tk.Frame(self, bg="#e2e8f0", pady=4)
        fb.pack(fill="x", padx=8, pady=(0, 2))

        tk.Label(fb, text="Cliente:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_cliente = tk.StringVar(value="Todos")
        self._cb_cliente = ttk.Combobox(fb, textvariable=self._var_cliente, state="readonly", width=18)
        self._cb_cliente.pack(side="left", padx=(0, 10))
        self._cb_cliente.bind("<<ComboboxSelected>>", self._on_filter)

        tk.Label(fb, text="NIF:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_nif = tk.StringVar()
        ent_nif = ttk.Entry(fb, textvariable=self._var_nif, width=11)
        ent_nif.pack(side="left", padx=(0, 10))
        ent_nif.bind("<KeyRelease>", self._on_filter)

        tk.Label(fb, text="Organismo:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_org = tk.StringVar(value="Todos")
        self._cb_org = ttk.Combobox(fb, textvariable=self._var_org, state="readonly", width=16)
        self._cb_org.pack(side="left", padx=(0, 10))
        self._cb_org.bind("<<ComboboxSelected>>", self._on_filter)

        tk.Label(fb, text="Estado:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_estado = tk.StringVar(value="Todos")
        cb_estado = ttk.Combobox(
            fb, textvariable=self._var_estado,
            values=["Todos"] + [LABEL_ESTADO.get(e, e) for e in ESTADOS if e],
            state="readonly", width=12,
        )
        cb_estado.pack(side="left", padx=(0, 10))
        cb_estado.bind("<<ComboboxSelected>>", self._on_filter)

        tk.Label(fb, text="Responsable:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_responsable = tk.StringVar()
        ent_resp = ttk.Entry(fb, textvariable=self._var_responsable, width=12)
        ent_resp.pack(side="left", padx=(0, 10))
        ent_resp.bind("<KeyRelease>", self._on_filter)

        # Segunda fila: fechas y checkboxes
        fb2 = tk.Frame(self, bg="#e2e8f0", pady=4)
        fb2.pack(fill="x", padx=8, pady=(0, 2))

        tk.Label(fb2, text="Desde (AAAA-MM-DD):", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_desde = tk.StringVar()
        ent_desde = ttk.Entry(fb2, textvariable=self._var_desde, width=11)
        ent_desde.pack(side="left", padx=(0, 10))
        ent_desde.bind("<KeyRelease>", self._on_filter)

        tk.Label(fb2, text="Hasta (AAAA-MM-DD):", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_hasta = tk.StringVar()
        ent_hasta = ttk.Entry(fb2, textvariable=self._var_hasta, width=11)
        ent_hasta.pack(side="left", padx=(0, 10))
        ent_hasta.bind("<KeyRelease>", self._on_filter)

        self._var_solo_pendientes = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb2, text="Solo pendientes", variable=self._var_solo_pendientes,
                        command=self._on_filter).pack(side="left", padx=(0, 10))

        self._var_solo_urgentes = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb2, text="Solo urgentes", variable=self._var_solo_urgentes,
                        command=self._on_filter).pack(side="left", padx=(0, 10))

        self._var_mostrar_archivadas = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb2, text="Mostrar archivadas", variable=self._var_mostrar_archivadas,
                        command=self._on_filter).pack(side="left", padx=(0, 10))

        tk.Label(fb2, text="Buscar:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_buscar = tk.StringVar()
        ent_buscar = ttk.Entry(fb2, textvariable=self._var_buscar, width=18)
        ent_buscar.pack(side="left", padx=(0, 4))
        ent_buscar.bind("<KeyRelease>", self._on_filter)

        self._lbl_count = tk.Label(fb2, text="", bg="#e2e8f0", fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

    def _build_list_panel(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        tb = tk.Frame(left, bg=_BG, pady=4)
        tb.grid(row=0, column=0, sticky="ew")
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=8, pady=3)
        self._btn_comparecer = tk.Button(tb, text="✔ Comparecer", bg=_SUCCESS, fg="white",
                                          command=self._on_comparecer, state="disabled", **btn)
        self._btn_comparecer.pack(side="left", padx=(0, 3))
        self._btn_rechazar = tk.Button(tb, text="✘ Rechazar", bg=_DANGER, fg="white",
                                        command=self._on_rechazar, state="disabled", **btn)
        self._btn_rechazar.pack(side="left", padx=(0, 3))
        self._btn_descargar = tk.Button(tb, text="Descargar", bg="#475569", fg="white",
                                         command=self._on_descargar, state="disabled", **btn)
        self._btn_descargar.pack(side="left", padx=(0, 3))
        self._btn_enviar = tk.Button(tb, text="Enviar al cliente", bg=_PRIMARY, fg="white",
                                      command=self._on_enviar_cliente, state="disabled", **btn)
        self._btn_enviar.pack(side="left", padx=(0, 3))
        self._btn_archivar = tk.Button(tb, text="Archivar", bg="#475569", fg="white",
                                        command=self._on_archivar, state="disabled", **btn)
        self._btn_archivar.pack(side="left", padx=(0, 3))
        tk.Button(tb, text="↻", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")

        tree_wrap = tk.Frame(left, bg=_BG)
        tree_wrap.grid(row=1, column=0, sticky="nsew")

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
        self._tv.tag_configure("ARCHIVADA", foreground=_SUB)

        sb_v = ttk.Scrollbar(tree_wrap, orient="vertical",   command=self._tv.yview)
        sb_h = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tv.xview)
        self._tv.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        sb_v.pack(side="right",  fill="y")
        sb_h.pack(side="bottom", fill="x")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

    def _build_detail_panel(self, parent: tk.Frame) -> None:
        right = tk.Frame(parent, bg=_CARD,
                         highlightbackground=_BORDER, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew")

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

        self._dv_cliente      = tk.StringVar(value="—")
        self._dv_nif          = tk.StringVar(value="—")
        self._dv_organismo    = tk.StringVar(value="—")
        self._dv_buzon        = tk.StringVar(value="—")
        self._dv_asunto       = tk.StringVar(value="—")
        self._dv_tipo_acto    = tk.StringVar(value="—")
        self._dv_referencia   = tk.StringVar(value="—")
        self._dv_estado       = tk.StringVar(value="—")
        self._dv_f_disp       = tk.StringVar(value="—")
        self._dv_f_venc       = tk.StringVar(value="—")
        self._dv_f_accion     = tk.StringVar(value="—")
        self._dv_responsable  = tk.StringVar(value="—")
        self._dv_envio        = tk.StringVar(value="—")
        self._dv_descripcion  = tk.StringVar(value="—")

        _campo("Cliente",                 self._dv_cliente, _TITLE)
        _campo("NIF",                     self._dv_nif)
        _campo("Organismo",               self._dv_organismo)
        _campo("Buzon",                   self._dv_buzon)
        _campo("Asunto",                  self._dv_asunto, _TITLE)
        _campo("Tipo de acto",            self._dv_tipo_acto)
        _campo("Referencia",              self._dv_referencia)
        _campo("Estado",                  self._dv_estado)
        _campo("Puesta a disposicion",    self._dv_f_disp)
        _campo("Vencimiento",             self._dv_f_venc)
        _campo("Fecha accion",            self._dv_f_accion)
        _campo("Responsable",             self._dv_responsable)
        _campo("Envio al cliente",        self._dv_envio)
        _campo("Descripcion",             self._dv_descripcion)

        acciones = tk.Frame(right, bg=_CARD)
        acciones.pack(fill="x", padx=10, pady=(0, 10))
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=8, pady=3)
        self._btn_ver_cliente = tk.Button(acciones, text="Ver cliente", bg="#475569", fg="white",
                                           command=self._on_ver_cliente, state="disabled", **btn)
        self._btn_ver_cliente.pack(side="left", padx=(0, 4), pady=(4, 0))
        self._btn_ver_buzon = tk.Button(acciones, text="Ver buzon", bg="#475569", fg="white",
                                         command=self._on_ver_buzon, state="disabled", **btn)
        self._btn_ver_buzon.pack(side="left", padx=(0, 4), pady=(4, 0))
        self._btn_responsable = tk.Button(acciones, text="Asignar responsable", bg="#475569", fg="white",
                                           command=self._on_asignar_responsable, state="disabled", **btn)
        self._btn_responsable.pack(side="left", padx=(0, 4), pady=(4, 0))

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self, bg=_BG, height=22)
        sb.pack(fill="x", side="bottom")
        self._lbl_status = tk.Label(sb, text="", bg=_BG, fg=_SUB,
                                    font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(side="left", padx=8)

    # ----------------------------------------------------------------- helpers

    def _row_by_id(self, item_id: str) -> dict | None:
        return next((r for r in self._cache if str(r.get("id")) == str(item_id)), None)

    # ----------------------------------------------------------------- eventos

    def _on_select(self, _e=None) -> None:
        sel = self._tv.selection()
        if not sel:
            self._selected_id = None
            self._clear_detail()
            self._set_action_buttons_state("disabled")
            return
        self._selected_id = self._tv.set(sel[0], "_id")
        item = self._row_by_id(self._selected_id)
        if item:
            self._populate_detail(item)
            estado = item.get("estado", "")
            archivada = bool(item.get("archivada"))
            self._btn_comparecer.configure(state="normal" if estado == "PENDIENTE" else "disabled")
            self._btn_rechazar.configure(state="normal" if estado == "PENDIENTE" else "disabled")
            self._btn_descargar.configure(state="normal")
            self._btn_enviar.configure(state="normal" if not item.get("enviada_cliente") else "disabled")
            self._btn_archivar.configure(text="Desarchivar" if archivada else "Archivar", state="normal")
            self._btn_ver_cliente.configure(state="normal" if self._on_open_empresa else "disabled")
            self._btn_ver_buzon.configure(state="normal" if item.get("buzon_id") else "disabled")
            self._btn_responsable.configure(state="normal")

    def _on_filter(self, _e=None) -> None:
        self._render_rows(self._filtrar(self._cache))

    def _filtrar(self, rows: list[dict]) -> list[dict]:
        cliente_lbl = self._var_cliente.get()
        nif         = self._var_nif.get().strip().upper()
        org_lbl     = self._var_org.get()
        estado_lbl  = self._var_estado.get()
        responsable = self._var_responsable.get().strip().lower()
        desde       = self._var_desde.get().strip()
        hasta       = self._var_hasta.get().strip()
        solo_pend   = self._var_solo_pendientes.get()
        solo_urg    = self._var_solo_urgentes.get()
        mostrar_arch = self._var_mostrar_archivadas.get()
        buscar      = self._var_buscar.get().strip().lower()

        inv_estado = {v: k for k, v in LABEL_ESTADO.items()}
        estado_val = inv_estado.get(estado_lbl, "") if estado_lbl not in ("", "Todos") else ""

        out = []
        for r in rows:
            if not mostrar_arch and r.get("archivada"):
                continue
            cliente = r.get("empresa_nombre") or r.get("codigo_empresa") or ""
            if cliente_lbl not in ("", "Todos") and cliente != cliente_lbl:
                continue
            if nif:
                r_nif = (r.get("empresa_cif") or r.get("nif_interesado") or "").upper()
                if nif not in r_nif:
                    continue
            if org_lbl not in ("", "Todos"):
                org = r.get("organismo_nombre") or r.get("organismo_codigo") or ""
                if org != org_lbl:
                    continue
            if estado_val and r.get("estado") != estado_val:
                continue
            if responsable and responsable not in (r.get("responsable") or "").lower():
                continue
            f_disp = (r.get("fecha_puesta_disposicion") or "")[:10]
            if desde and (not f_disp or f_disp < desde):
                continue
            if hasta and (not f_disp or f_disp > hasta):
                continue
            dias = _dias_restantes(r.get("fecha_vencimiento"))
            if solo_pend and r.get("estado") != "PENDIENTE":
                continue
            if solo_urg and not (r.get("estado") == "PENDIENTE" and dias is not None and dias <= 10):
                continue
            if buscar:
                texto = " ".join(str(r.get(k) or "") for k in (
                    "asunto", "tipo_acto", "referencia", "empresa_nombre", "codigo_empresa",
                )).lower()
                if buscar not in texto:
                    continue
            out.append(r)
        return out

    def _on_comparecer(self) -> None:
        self._cambiar_estado("ACEPTADA", "Marcar esta notificacion como ACEPTADA (Comparecer)?")

    def _on_rechazar(self) -> None:
        self._cambiar_estado("RECHAZADA", "Marcar esta notificacion como RECHAZADA?\nEsta accion queda registrada.")

    def _cambiar_estado(self, estado: str, pregunta: str) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item:
            return
        if not messagebox.askyesno("Gest2A3Eco", pregunta, parent=self.winfo_toplevel()):
            return
        fecha = datetime.now().strftime("%Y-%m-%d")
        try:
            self._gestor.cambiar_estado_notif_bandeja(item["codigo_empresa"], item["id"], estado, fecha)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_descargar(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item:
            return
        pdf_path = item.get("pdf_path")
        if pdf_path and os.path.isfile(pdf_path):
            try:
                os.startfile(pdf_path)  # noqa: S606 (uso local en Windows)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        messagebox.showinfo(
            "Descargar notificacion",
            "Esta notificacion no tiene un documento asociado todavia.\n\n"
            "La descarga automatica desde el organismo se activara cuando se "
            "configuren los conectores reales.",
            parent=self.winfo_toplevel(),
        )

    def _on_enviar_cliente(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item:
            return
        if not messagebox.askyesno(
            "Enviar al cliente",
            "Marcar esta notificacion como enviada al cliente?",
            parent=self.winfo_toplevel(),
        ):
            return
        fecha = datetime.now().strftime("%Y-%m-%d")
        try:
            self._gestor.marcar_notif_bandeja_enviada_cliente(item["codigo_empresa"], item["id"], fecha)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_archivar(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item:
            return
        nueva = not bool(item.get("archivada"))
        try:
            self._gestor.archivar_notif_bandeja_item(item["codigo_empresa"], item["id"], nueva)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_ver_cliente(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item or not self._on_open_empresa:
            return
        self._on_open_empresa(item.get("codigo_empresa"), item.get("ejercicio"))

    def _on_ver_buzon(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item or not item.get("buzon_id"):
            return
        buzon = self._gestor.get_notif_buzon(item["buzon_id"])
        if not buzon:
            messagebox.showinfo("Ver buzon", "El buzon ya no existe.", parent=self.winfo_toplevel())
            return
        info = (
            f"Nombre: {buzon.get('nombre', '')}\n"
            f"Organismo: {buzon.get('organismo_nombre') or buzon.get('organismo_codigo') or ''}\n"
            f"Tipo: {buzon.get('tipo_buzon', '')}\n"
            f"Certificado: {buzon.get('certificado_nombre') or '(sin certificado)'}\n"
            f"Periodicidad: {buzon.get('periodicidad_sync', '')}\n"
            f"Modo descarga: {buzon.get('modo_descarga', '')}\n"
            f"Ultima consulta: {buzon.get('ultima_consulta') or '-'}"
        )
        messagebox.showinfo("Ver buzon", info, parent=self.winfo_toplevel())

    def _on_asignar_responsable(self) -> None:
        item = self._row_by_id(self._selected_id) if self._selected_id else None
        if not item:
            return
        actual = item.get("responsable") or ""
        nuevo = simpledialog.askstring(
            "Asignar responsable",
            "Persona responsable de esta notificacion:",
            initialvalue=actual,
            parent=self.winfo_toplevel(),
        )
        if nuevo is None:
            return
        try:
            self._gestor.asignar_responsable_notif_bandeja(item["codigo_empresa"], item["id"], nuevo.strip() or None)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        self._cache = self._gestor.listar_notif_bandeja_global()

        clientes = sorted({r.get("empresa_nombre") or r.get("codigo_empresa") or "" for r in self._cache} - {""})
        self._cb_cliente.configure(values=["Todos"] + clientes)
        if self._cb_cliente.get() not in (["Todos"] + clientes):
            self._cb_cliente.set("Todos")

        organismos = sorted({r.get("organismo_nombre") or r.get("organismo_codigo") or "" for r in self._cache} - {""})
        self._cb_org.configure(values=["Todos"] + organismos)
        if self._cb_org.get() not in (["Todos"] + organismos):
            self._cb_org.set("Todos")

        self._render_rows(self._filtrar(self._cache))
        self._clear_detail()
        self._set_action_buttons_state("disabled")

    def _render_rows(self, rows: list[dict]) -> None:
        self._tv.delete(*self._tv.get_children())
        for r in rows:
            estado = r.get("estado", "")
            tag = estado
            dias = _dias_restantes(r.get("fecha_vencimiento"))
            if r.get("archivada"):
                tag = "ARCHIVADA"
            elif estado == "PENDIENTE" and dias is not None and dias <= 10:
                tag = "URGENTE"
            f_disp = _fmt_fecha(r.get("fecha_puesta_disposicion"))
            f_venc = _fmt_fecha(r.get("fecha_vencimiento"))
            if dias is not None and estado == "PENDIENTE":
                f_venc = f"{f_venc} ({dias}d)" if dias >= 0 else f"{f_venc} (!)"
            cliente = r.get("empresa_nombre") or r.get("codigo_empresa") or ""
            nif = r.get("empresa_cif") or r.get("nif_interesado") or ""
            org = r.get("organismo_nombre") or r.get("organismo_codigo") or ""
            buzon = r.get("buzon_nombre") or ""
            self._tv.insert("", tk.END, values=(
                r["id"], cliente, nif, org, buzon,
                r.get("asunto", ""),
                f_disp, f_venc,
                LABEL_ESTADO.get(estado, estado),
                r.get("responsable") or "",
            ), tags=(tag,))

        pendientes = sum(1 for r in rows if r.get("estado") == "PENDIENTE")
        urgentes = sum(1 for r in rows
                       if r.get("estado") == "PENDIENTE"
                       and (_dias_restantes(r.get("fecha_vencimiento")) or 999) <= 10)
        self._lbl_count.configure(
            text=f"{len(rows)} notificaciones  |  Pendientes: {pendientes}"
                 + (f"  |  URGENTES: {urgentes}" if urgentes else "")
        )
        total = len(self._cache)
        archivadas = sum(1 for r in self._cache if r.get("archivada"))
        clientes_distintos = len({r.get("codigo_empresa") for r in self._cache})
        self._lbl_status.configure(
            text=f"Total: {total}  |  Archivadas: {archivadas}  |  Clientes con notificaciones: {clientes_distintos}"
        )

    # ----------------------------------------------------------------- detalle

    def _populate_detail(self, item: dict) -> None:
        estado = item.get("estado", "")
        f_accion = _fmt_fecha(item.get("fecha_aceptacion") or item.get("fecha_rechazo"))
        if f_accion:
            accion_lbl = f"Aceptada: {f_accion}" if item.get("fecha_aceptacion") else f"Rechazada: {f_accion}"
        else:
            accion_lbl = "—"
        if item.get("enviada_cliente"):
            envio_lbl = f"Si ({_fmt_fecha(item.get('fecha_envio_cliente')) or '-'})"
        else:
            envio_lbl = "No"

        self._dv_cliente.set(item.get("empresa_nombre") or item.get("codigo_empresa") or "—")
        self._dv_nif.set(item.get("empresa_cif") or item.get("nif_interesado") or "—")
        self._dv_organismo.set(item.get("organismo_nombre") or item.get("organismo_codigo") or "—")
        self._dv_buzon.set(item.get("buzon_nombre") or "—")
        self._dv_asunto.set(item.get("asunto") or "—")
        self._dv_tipo_acto.set(item.get("tipo_acto") or "—")
        self._dv_referencia.set(item.get("referencia") or "—")
        self._dv_estado.set(LABEL_ESTADO.get(estado, estado) + (" (archivada)" if item.get("archivada") else ""))
        self._dv_f_disp.set(_fmt_fecha(item.get("fecha_puesta_disposicion")) or "—")
        self._dv_f_venc.set(_fmt_fecha(item.get("fecha_vencimiento")) or "—")
        self._dv_f_accion.set(accion_lbl)
        self._dv_responsable.set(item.get("responsable") or "—")
        self._dv_envio.set(envio_lbl)
        self._dv_descripcion.set(item.get("descripcion") or "—")

    def _clear_detail(self) -> None:
        for var in (self._dv_cliente, self._dv_nif, self._dv_organismo, self._dv_buzon,
                    self._dv_tipo_acto, self._dv_referencia, self._dv_estado,
                    self._dv_f_disp, self._dv_f_venc, self._dv_f_accion,
                    self._dv_responsable, self._dv_envio,
                    self._dv_asunto, self._dv_descripcion):
            var.set("—")

    def _set_action_buttons_state(self, state: str) -> None:
        self._btn_comparecer.configure(state=state)
        self._btn_rechazar.configure(state=state)
        self._btn_descargar.configure(state=state)
        self._btn_enviar.configure(state=state)
        self._btn_archivar.configure(state=state)
        self._btn_ver_cliente.configure(state=state)
        self._btn_ver_buzon.configure(state=state)
        self._btn_responsable.configure(state=state)
