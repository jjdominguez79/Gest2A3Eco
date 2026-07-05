"""
Vista: Buzones globales (modulo "Notificaciones Electronicas") - SOLO LECTURA.

Listado de los buzones de notificacion de TODOS los clientes, con filtros por
cliente, organismo y estado. Esta pantalla NO permite crear, editar ni activar/
desactivar buzones: eso se hace en la ficha de cada cliente (pestana
"Notificaciones electronicas"). Aqui solo se consulta y se puede solicitar la
SINCRONIZACION MANUAL (de un buzon seleccionado o de todos los activos).
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_bandeja_notificaciones import LABEL_ESTADO, _fmt_fecha
from views.ui_buzones import LABELS_MODO_DESCARGA


class UIBuzonesGlobal(ttk.Frame):
    """Listado global de buzones (solo lectura + sincronizacion manual)."""

    _COLS = [
        ("cliente",         "Cliente",          170, "w"),
        ("organismo",       "Organismo",        150, "w"),
        ("nombre",          "Nombre buzon",     150, "w"),
        ("tipo_buzon",      "Tipo",              70, "center"),
        ("certificado",     "Certificado",      140, "w"),
        ("modo_descarga",   "Modo descarga",    130, "center"),
        ("ultima_consulta", "Ultima consulta",  120, "center"),
        ("activo",          "Activo",            60, "center"),
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
        self._build_toolbar()
        self._build_tree()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="▦  Buzones (todos los clientes)", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Solo lectura. La configuracion se hace en la ficha de cada cliente.",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

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

        self._var_solo_activos = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb, text="Solo activos", variable=self._var_solo_activos,
                        command=self._render).pack(side="left", padx=(0, 10))

        self._lbl_count = tk.Label(fb, text="", bg="#e2e8f0", fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

    def _build_toolbar(self) -> None:
        tb = tk.Frame(self, bg=_BG, pady=6)
        tb.pack(fill="x", padx=8)
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=10, pady=4)
        self._btn_sync = tk.Button(tb, text="↻ Sincronizar seleccionado", bg="#0ea5e9", fg="white",
                                    command=self._on_sincronizar, state="disabled", **btn)
        self._btn_sync.pack(side="left", padx=(0, 5))
        self._btn_sync_all = tk.Button(tb, text="↻ Sincronizar todos", bg="#0284c7", fg="white",
                                       command=self._on_sincronizar_todos, **btn)
        self._btn_sync_all.pack(side="left", padx=(0, 5))
        self._btn_ver_notif = tk.Button(tb, text="Ver notificaciones", bg="#475569", fg="white",
                                         command=self._on_ver_notificaciones, state="disabled", **btn)
        self._btn_ver_notif.pack(side="left", padx=(0, 5))
        tk.Button(tb, text="↻ Actualizar", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")

    def _build_tree(self) -> None:
        wrapper = tk.Frame(self, bg=_BG)
        wrapper.pack(fill="both", expand=True, padx=8, pady=4)
        col_ids = ["_id"] + [c[0] for c in self._COLS]
        self._tv = ttk.Treeview(wrapper, columns=col_ids, show="headings", selectmode="browse")
        self._tv.column("_id", width=0, stretch=False)
        self._tv.heading("_id", text="")
        for key, header, width, anchor in self._COLS:
            self._tv.heading(key, text=header)
            self._tv.column(key, width=width, anchor=anchor, stretch=(key == "nombre"))
        self._tv.tag_configure("activo",   foreground=_SUCCESS)
        self._tv.tag_configure("inactivo", foreground=_SUB)
        sb_v = ttk.Scrollbar(wrapper, orient="vertical",   command=self._tv.yview)
        sb_h = ttk.Scrollbar(wrapper, orient="horizontal", command=self._tv.xview)
        self._tv.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        sb_v.pack(side="right", fill="y")
        sb_h.pack(side="bottom", fill="x")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)
        self._tv.bind("<Double-1>", lambda _e: self._on_ver_notificaciones())

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self, bg=_BG, height=22)
        sb.pack(fill="x", side="bottom")
        self._lbl_status = tk.Label(sb, text="", bg=_BG, fg=_SUB, font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(side="left", padx=8)

    # ----------------------------------------------------------------- helpers
    def _row_seleccionada(self) -> dict | None:
        sel = self._tv.selection()
        if not sel:
            return None
        buzon_id = self._tv.set(sel[0], "_id")
        return next((b for b in self._cache if str(b.get("id")) == str(buzon_id)), None)

    def _on_select(self, _e=None) -> None:
        ok = bool(self._tv.selection())
        s = "normal" if ok else "disabled"
        self._btn_sync.configure(state=s)
        self._btn_ver_notif.configure(state=s)

    # ----------------------------------------------------------------- sync (manual)
    def _on_sincronizar(self) -> None:
        buzon = self._row_seleccionada()
        if not buzon:
            return
        try:
            from services.aapp.sync_service import sincronizar_buzon
            from services.aapp.base import OpcionesSync
        except Exception as exc:
            self._sync_no_disponible(str(exc))
            return
        if not messagebox.askyesno(
            "Sincronizar buzon",
            f"Se accedera al organismo con el certificado del buzon "
            f"'{buzon.get('nombre')}' para buscar notificaciones pendientes.\n\n"
            "El proceso puede tardar unos segundos. Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._set_busy(True)
        import threading

        def _worker():
            res = sincronizar_buzon(self._gestor, buzon, OpcionesSync(headless=True))
            self.after(0, lambda: self._sync_fin(res))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_sincronizar_todos(self) -> None:
        try:
            from services.aapp.sync_service import sincronizar_buzones
            from services.aapp.base import OpcionesSync
        except Exception as exc:
            self._sync_no_disponible(str(exc))
            return
        activos = [b for b in self._cache if b.get("activo")]
        if not activos:
            messagebox.showinfo("Sincronizar", "No hay buzones activos que sincronizar.",
                                parent=self.winfo_toplevel())
            return
        if not messagebox.askyesno(
            "Sincronizar todos",
            f"Se sincronizaran {len(activos)} buzon(es) activo(s) de todos los clientes.\n\n"
            "Puede tardar bastante. Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._set_busy(True)
        import threading

        def _worker():
            glob = sincronizar_buzones(self._gestor, activos, OpcionesSync(headless=True))
            self.after(0, lambda: self._sync_todos_fin(glob))

        threading.Thread(target=_worker, daemon=True).start()

    def _sync_fin(self, res) -> None:
        self._set_busy(False)
        if getattr(res, "ok", False):
            messagebox.showinfo(
                "Sincronizacion completada",
                f"Buzon '{res.buzon_nombre}':\n"
                f"{res.total_detectadas} notificacion(es) detectada(s), {res.nuevas} nueva(s).",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showerror(
                "Sincronizacion con errores",
                f"Buzon '{getattr(res, 'buzon_nombre', '?')}':\n{getattr(res, 'mensaje', '')}",
                parent=self.winfo_toplevel(),
            )
        self.refresh()

    def _sync_todos_fin(self, glob) -> None:
        self._set_busy(False)
        errores = getattr(glob, "con_error", [])
        messagebox.showinfo(
            "Sincronizacion completada",
            f"Buzones procesados: {len(glob.resultados)}\n"
            f"Notificaciones nuevas: {glob.total_nuevas}\n"
            f"Con error: {len(errores)}",
            parent=self.winfo_toplevel(),
        )
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        st = "disabled" if busy else "normal"
        try:
            self._btn_sync_all.configure(state=st)
            self._btn_sync.configure(state=st if self._tv.selection() else "disabled")
        except Exception:
            pass

    def _sync_no_disponible(self, motivo: str = "") -> None:
        messagebox.showwarning(
            "Sincronizar no disponible",
            "El conector de notificaciones no esta disponible en este equipo.\n\n"
            f"Detalle: {motivo}\n\n"
            "Instala las dependencias:\n"
            "  pip install cryptography playwright\n"
            "  playwright install chromium",
            parent=self.winfo_toplevel(),
        )

    def _on_ver_notificaciones(self) -> None:
        buzon = self._row_seleccionada()
        if not buzon:
            return
        items = [
            n for n in self._gestor.listar_notif_bandeja_global({"codigo_empresa": buzon["codigo_empresa"]})
            if n.get("buzon_id") == buzon.get("id")
        ]
        dlg = tk.Toplevel(self.winfo_toplevel())
        dlg.title(f"Notificaciones del buzon '{buzon.get('nombre')}'")
        dlg.geometry("720x360")
        cols = ("asunto", "f_disp", "f_venc", "estado")
        tv = ttk.Treeview(dlg, columns=cols, show="headings")
        for key, header, width in (
            ("asunto", "Asunto", 380), ("f_disp", "Disposicion", 100),
            ("f_venc", "Vencimiento", 100), ("estado", "Estado", 100),
        ):
            tv.heading(key, text=header)
            tv.column(key, width=width, anchor="w" if key == "asunto" else "center")
        for n in items:
            tv.insert("", tk.END, values=(
                n.get("asunto", ""),
                _fmt_fecha(n.get("fecha_puesta_disposicion")),
                _fmt_fecha(n.get("fecha_vencimiento")),
                LABEL_ESTADO.get(n.get("estado", ""), n.get("estado", "")),
            ))
        tv.pack(fill="both", expand=True, padx=8, pady=8)
        if not items:
            ttk.Label(dlg, text="Este buzon no tiene notificaciones registradas.").pack(pady=(0, 8))
        ttk.Button(dlg, text="Cerrar", command=dlg.destroy).pack(pady=(0, 8))
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

    # ----------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self._cache = self._gestor.listar_notif_buzones_global()
        clientes = sorted({b.get("empresa_nombre") or b.get("codigo_empresa") or "" for b in self._cache} - {""})
        self._cb_cliente.configure(values=["Todos"] + clientes)
        if self._cb_cliente.get() not in (["Todos"] + clientes):
            self._cb_cliente.set("Todos")

        organismos = sorted({b.get("organismo_nombre") or b.get("organismo_codigo") or "" for b in self._cache} - {""})
        self._cb_org.configure(values=["Todos"] + organismos)
        if self._cb_org.get() not in (["Todos"] + organismos):
            self._cb_org.set("Todos")

        self._render()

    def _render(self) -> None:
        cliente_lbl = self._var_cliente.get()
        org_lbl = self._var_org.get()
        solo_activos = self._var_solo_activos.get()

        self._tv.delete(*self._tv.get_children())
        rows_mostradas = 0
        for b in self._cache:
            cliente = b.get("empresa_nombre") or b.get("codigo_empresa") or ""
            if cliente_lbl not in ("", "Todos") and cliente != cliente_lbl:
                continue
            org = b.get("organismo_nombre") or b.get("organismo_codigo") or ""
            if org_lbl not in ("", "Todos") and org != org_lbl:
                continue
            if solo_activos and not b.get("activo"):
                continue
            tag = "activo" if b.get("activo") else "inactivo"
            modo = LABELS_MODO_DESCARGA.get(b.get("modo_descarga"), b.get("modo_descarga", ""))
            ultima = (b.get("ultima_consulta") or "")[:16].replace("T", " ")
            self._tv.insert("", tk.END, values=(
                b["id"], cliente, org, b.get("nombre", ""), b.get("tipo_buzon", ""),
                b.get("certificado_nombre") or "", modo, ultima,
                "Si" if b.get("activo") else "No",
            ), tags=(tag,))
            rows_mostradas += 1

        self._lbl_count.configure(text=f"{rows_mostradas} buzon{'es' if rows_mostradas != 1 else ''}")
        self._lbl_status.configure(
            text=f"Total: {len(self._cache)}  |  Activos: {sum(1 for b in self._cache if b.get('activo'))}  |  "
                 f"Inactivos: {sum(1 for b in self._cache if not b.get('activo'))}"
        )
        self._btn_sync.configure(state="disabled")
        self._btn_ver_notif.configure(state="disabled")
