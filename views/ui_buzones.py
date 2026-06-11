"""
Vista: Gestion de Buzones de Notificacion.

Un buzon es la combinacion empresa + organismo + tipo de servicio (DEH, 060...)
que permite recibir notificaciones electronicas. Operativo sobre SQLite local.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403

TIPOS_BUZON = ["DEH", "060", "NOTIFIC@", "SNE", "CARPETA CIUDADANA", "OTRO"]


class UIBuzones(ttk.Frame):
    """Pantalla de gestion de buzones de notificacion electronica."""

    _COLS = [
        ("organismo",       "Organismo",       160, "w"),
        ("nombre",          "Nombre buzon",    180, "w"),
        ("tipo_buzon",      "Tipo",             70, "center"),
        ("nif_titular",     "NIF Titular",       90, "center"),
        ("certificado",     "Certificado",      160, "w"),
        ("ultima_consulta", "Ultima consulta",  120, "center"),
        ("activo",          "Estado",            70, "center"),
    ]

    def __init__(self, master, gestor, codigo: str, session=None):
        super().__init__(master)
        self._gestor  = gestor
        self._codigo  = codigo
        self._session = session
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        self._build_header()
        self._build_toolbar()
        self._build_tree()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\u25a6  Buzones", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Canales de recepcion de notificaciones electronicas",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

    def _build_toolbar(self) -> None:
        tb = tk.Frame(self, bg=_BG, pady=6)
        tb.pack(fill="x", padx=8)
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=10, pady=4)
        tk.Button(tb, text="+ Nuevo",   bg=_PRIMARY, fg="white", command=self._on_nuevo,   **btn).pack(side="left", padx=(0, 5))
        self._btn_editar   = tk.Button(tb, text="Editar",   bg="#475569", fg="white", command=self._on_editar,   state="disabled", **btn)
        self._btn_editar.pack(side="left", padx=(0, 5))
        self._btn_eliminar = tk.Button(tb, text="Eliminar", bg=_DANGER,   fg="white", command=self._on_eliminar, state="disabled", **btn)
        self._btn_eliminar.pack(side="left", padx=(0, 5))
        tk.Button(tb, text="\u21bb Actualizar", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")
        self._lbl_count = tk.Label(tb, text="", bg=_BG, fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

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
        self._tv.bind("<Double-1>", lambda _e: self._on_editar())

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self, bg=_BG, height=22)
        sb.pack(fill="x", side="bottom")
        self._lbl_status = tk.Label(sb, text="", bg=_BG, fg=_SUB, font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(side="left", padx=8)

    # ----------------------------------------------------------------- eventos

    def _on_select(self, _e=None) -> None:
        ok = bool(self._tv.selection())
        s  = "normal" if ok else "disabled"
        self._btn_editar.configure(state=s)
        self._btn_eliminar.configure(state=s)

    def _on_nuevo(self) -> None:
        dlg = _BuzonDialog(self.winfo_toplevel(), None, self._gestor, self._codigo)
        if dlg.result:
            try:
                self._gestor.upsert_notif_buzon(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_editar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        buzon_id = self._tv.set(sel[0], "_id")
        buzon    = self._gestor.get_notif_buzon(buzon_id)
        if not buzon:
            return
        dlg = _BuzonDialog(self.winfo_toplevel(), buzon, self._gestor, self._codigo)
        if dlg.result:
            try:
                self._gestor.upsert_notif_buzon(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_eliminar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        buzon_id = self._tv.set(sel[0], "_id")
        nombre   = self._tv.set(sel[0], "nombre")
        if not messagebox.askyesno("Eliminar buzon",
                                   f"Eliminar el buzon '{nombre}'?",
                                   parent=self.winfo_toplevel()):
            return
        try:
            self._gestor.eliminar_notif_buzon(self._codigo, buzon_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        rows = self._gestor.listar_notif_buzones(self._codigo)
        self._tv.delete(*self._tv.get_children())
        for r in rows:
            tag    = "activo" if r.get("activo") else "inactivo"
            estado = "Activo" if r.get("activo") else "Inactivo"
            org    = r.get("organismo_nombre") or r.get("organismo_codigo") or ""
            cert   = r.get("certificado_nombre") or ""
            ultima = (r.get("ultima_consulta") or "")[:16].replace("T", " ")
            self._tv.insert("", tk.END, values=(
                r["id"], org, r.get("nombre", ""),
                r.get("tipo_buzon", ""), r.get("nif_titular", "") or "",
                cert, ultima, estado,
            ), tags=(tag,))
        n = len(rows)
        self._lbl_count.configure(text=f"{n} buzon{'es' if n != 1 else ''}")
        self._lbl_status.configure(
            text=f"Activos: {sum(1 for r in rows if r.get('activo'))}  |  "
                 f"Inactivos: {sum(1 for r in rows if not r.get('activo'))}"
        )
        self._btn_editar.configure(state="disabled")
        self._btn_eliminar.configure(state="disabled")


# ── Dialog ───────────────────────────────────────────────────────────────────

class _BuzonDialog(tk.Toplevel):
    """Dialogo de creacion/edicion de buzon."""

    def __init__(self, parent, buzon: dict | None, gestor, codigo_empresa: str):
        super().__init__(parent)
        self.title("Nuevo buzon" if buzon is None else "Editar buzon")
        self.resizable(False, False)
        self.result: dict | None = None
        self._buzon   = buzon or {}
        self._gestor  = gestor
        self._empresa = codigo_empresa
        # Listas de organismos y certificados para los combos
        self._organismos  = gestor.listar_notif_organismos(solo_activos=True)
        self._certificados = gestor.listar_notif_certificados(codigo_empresa, solo_activos=True)
        self._build()
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self) -> None:
        pad = dict(padx=12, pady=4)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        # Mapas id → nombre para los combos
        self._org_nombres  = [""] + [f"{o['codigo']} - {o['nombre']}" for o in self._organismos]
        self._org_ids      = [None] + [o["id"] for o in self._organismos]
        self._cert_nombres = ["(sin certificado)"] + [c["nombre"] for c in self._certificados]
        self._cert_ids     = [None] + [c["id"] for c in self._certificados]

        self._var_nombre     = tk.StringVar(value=self._buzon.get("nombre", ""))
        self._var_tipo       = tk.StringVar(value=self._buzon.get("tipo_buzon", "DEH"))
        self._var_nif        = tk.StringVar(value=self._buzon.get("nif_titular", "") or "")
        self._var_activo     = tk.BooleanVar(value=bool(self._buzon.get("activo", True)))

        # Organismo combo
        curr_org_id  = self._buzon.get("organismo_id")
        org_sel      = next((f"{o['codigo']} - {o['nombre']}" for o in self._organismos if o["id"] == curr_org_id), "")
        self._var_org = tk.StringVar(value=org_sel)

        # Certificado combo
        curr_cert_id = self._buzon.get("certificado_id")
        cert_sel     = next((c["nombre"] for c in self._certificados if c["id"] == curr_cert_id), "(sin certificado)")
        self._var_cert = tk.StringVar(value=cert_sel)

        rows_def = [
            ("Nombre *",     self._var_nombre, ttk.Entry,    {"width": 36}),
            ("Organismo",    self._var_org,    ttk.Combobox, {"width": 36, "values": self._org_nombres, "state": "readonly"}),
            ("Tipo buzon",   self._var_tipo,   ttk.Combobox, {"width": 22, "values": TIPOS_BUZON, "state": "readonly"}),
            ("NIF Titular",  self._var_nif,    ttk.Entry,    {"width": 22}),
            ("Certificado",  self._var_cert,   ttk.Combobox, {"width": 36, "values": self._cert_nombres, "state": "readonly"}),
        ]
        for i, (lbl, var, cls, kw) in enumerate(rows_def):
            ttk.Label(frm, text=lbl, anchor="e").grid(row=i, column=0, sticky="e", **pad)
            cls(frm, textvariable=var, **kw).grid(row=i, column=1, sticky="w", **pad)

        ttk.Checkbutton(frm, text="Activo", variable=self._var_activo).grid(
            row=len(rows_def), column=1, sticky="w", **pad)

        btn_row = ttk.Frame(self, padding=(16, 8))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="Guardar", command=self._on_ok).pack(side="right")

    def _on_ok(self) -> None:
        nombre = self._var_nombre.get().strip()
        if not nombre:
            messagebox.showerror("Gest2A3Eco", "El nombre del buzon es obligatorio.", parent=self)
            return

        org_text = self._var_org.get()
        org_id   = None
        if org_text:
            idx = next((i for i, n in enumerate(self._org_nombres) if n == org_text), 0)
            org_id = self._org_ids[idx] if idx < len(self._org_ids) else None

        cert_text = self._var_cert.get()
        cert_id   = None
        if cert_text and cert_text != "(sin certificado)":
            idx = next((i for i, n in enumerate(self._cert_nombres) if n == cert_text), 0)
            cert_id = self._cert_ids[idx] if idx < len(self._cert_ids) else None

        self.result = {
            "codigo_empresa": self._empresa,
            "nombre":         nombre,
            "organismo_id":   org_id,
            "tipo_buzon":     self._var_tipo.get().strip() or "DEH",
            "nif_titular":    self._var_nif.get().strip().upper() or None,
            "certificado_id": cert_id,
            "activo":         1 if self._var_activo.get() else 0,
        }
        if self._buzon.get("id"):
            self.result["id"] = self._buzon["id"]
        self.destroy()
