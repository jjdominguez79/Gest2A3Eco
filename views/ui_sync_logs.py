"""
Vista: Sincronizaciones / Logs (modulo "Notificaciones Electronicas").

Historico global de sincronizaciones con los organismos, de todos los
clientes: fecha/hora, cliente, organismo, buzon, resultado, error y
notificaciones detectadas. Pantalla de solo lectura.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from views.notificaciones_theme import *  # noqa: F401,F403


class UISyncLogs(ttk.Frame):
    """Listado global de sincronizaciones (notif_sync_logs)."""

    _COLS = [
        ("fecha_hora",  "Fecha / hora",       140, "center"),
        ("cliente",     "Cliente",            170, "w"),
        ("organismo",   "Organismo",          130, "w"),
        ("buzon",       "Buzon",              150, "w"),
        ("resultado",   "Resultado",           80, "center"),
        ("detectadas",  "Notif. detectadas",  110, "center"),
        ("error",       "Error",              260, "w"),
    ]

    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor  = gestor
        self._session = session
        self._cache: list[dict] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        self._build_header()
        self._build_filter_bar()
        self._build_tree()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="↻  Sincronizaciones / Logs", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Historico de sincronizaciones de todos los clientes",
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
        self._cb_cliente = ttk.Combobox(fb, textvariable=self._var_cliente, state="readonly", width=22)
        self._cb_cliente.pack(side="left", padx=(0, 10))
        self._cb_cliente.bind("<<ComboboxSelected>>", lambda _e: self._render())

        tk.Label(fb, text="Organismo:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_org = tk.StringVar(value="Todos")
        self._cb_org = ttk.Combobox(fb, textvariable=self._var_org, state="readonly", width=18)
        self._cb_org.pack(side="left", padx=(0, 10))
        self._cb_org.bind("<<ComboboxSelected>>", lambda _e: self._render())

        tk.Label(fb, text="Resultado:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_resultado = tk.StringVar(value="Todos")
        cb_res = ttk.Combobox(fb, textvariable=self._var_resultado, state="readonly", width=10,
                               values=["Todos", "OK", "ERROR"])
        cb_res.pack(side="left", padx=(0, 10))
        cb_res.bind("<<ComboboxSelected>>", lambda _e: self._render())

        tk.Label(fb, text="Desde:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_desde = tk.StringVar()
        ent_desde = ttk.Entry(fb, textvariable=self._var_desde, width=11)
        ent_desde.pack(side="left", padx=(0, 10))
        ent_desde.bind("<KeyRelease>", lambda _e: self._render())

        tk.Label(fb, text="Hasta:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_hasta = tk.StringVar()
        ent_hasta = ttk.Entry(fb, textvariable=self._var_hasta, width=11)
        ent_hasta.pack(side="left", padx=(0, 10))
        ent_hasta.bind("<KeyRelease>", lambda _e: self._render())

        self._lbl_count = tk.Label(fb, text="", bg="#e2e8f0", fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

    def _build_tree(self) -> None:
        wrapper = tk.Frame(self, bg=_BG)
        wrapper.pack(fill="both", expand=True, padx=8, pady=4)
        self._tv = ttk.Treeview(wrapper, columns=[c[0] for c in self._COLS], show="headings", selectmode="browse")
        for key, header, width, anchor in self._COLS:
            self._tv.heading(key, text=header)
            self._tv.column(key, width=width, anchor=anchor, stretch=(key == "error"))
        self._tv.tag_configure("OK",    foreground=_SUCCESS)
        self._tv.tag_configure("ERROR", foreground=_DANGER)
        sb_v = ttk.Scrollbar(wrapper, orient="vertical",   command=self._tv.yview)
        sb_h = ttk.Scrollbar(wrapper, orient="horizontal", command=self._tv.xview)
        self._tv.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        sb_v.pack(side="right", fill="y")
        sb_h.pack(side="bottom", fill="x")
        self._tv.pack(fill="both", expand=True)

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self, bg=_BG, height=22)
        sb.pack(fill="x", side="bottom")
        self._lbl_status = tk.Label(sb, text="", bg=_BG, fg=_SUB, font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(side="left", padx=8)

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        self._cache = self._gestor.listar_notif_sync_logs()
        clientes = sorted({l.get("empresa_nombre") or l.get("codigo_empresa") or "" for l in self._cache} - {""})
        self._cb_cliente.configure(values=["Todos"] + clientes)
        if self._cb_cliente.get() not in (["Todos"] + clientes):
            self._cb_cliente.set("Todos")

        organismos = sorted({l.get("organismo_nombre") or l.get("organismo_codigo") or "" for l in self._cache} - {""})
        self._cb_org.configure(values=["Todos"] + organismos)
        if self._cb_org.get() not in (["Todos"] + organismos):
            self._cb_org.set("Todos")

        self._render()

    def _render(self) -> None:
        cliente_lbl = self._var_cliente.get()
        org_lbl = self._var_org.get()
        resultado_lbl = self._var_resultado.get()
        desde = self._var_desde.get().strip()
        hasta = self._var_hasta.get().strip()

        self._tv.delete(*self._tv.get_children())
        for log in self._cache:
            cliente = log.get("empresa_nombre") or log.get("codigo_empresa") or ""
            if cliente_lbl not in ("", "Todos") and cliente != cliente_lbl:
                continue
            org = log.get("organismo_nombre") or log.get("organismo_codigo") or ""
            if org_lbl not in ("", "Todos") and org != org_lbl:
                continue
            resultado = log.get("resultado", "")
            if resultado_lbl not in ("", "Todos") and resultado != resultado_lbl:
                continue
            fecha = (log.get("fecha_hora") or "")[:10]
            if desde and (not fecha or fecha < desde):
                continue
            if hasta and (not fecha or fecha > hasta):
                continue
            fecha_lbl = (log.get("fecha_hora") or "")[:16].replace("T", " ")
            self._tv.insert("", tk.END, values=(
                fecha_lbl, cliente, org, log.get("buzon_nombre") or "",
                resultado, log.get("notificaciones_detectadas", 0),
                log.get("error_detalle") or "",
            ), tags=(resultado,))

        n = len(self._tv.get_children())
        self._lbl_count.configure(text=f"{n} registro{'s' if n != 1 else ''}")
        ok = sum(1 for l in self._cache if l.get("resultado") == "OK")
        error = sum(1 for l in self._cache if l.get("resultado") == "ERROR")
        self._lbl_status.configure(text=f"Total: {len(self._cache)}  |  OK: {ok}  |  ERROR: {error}")
