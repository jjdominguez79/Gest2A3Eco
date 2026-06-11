"""
Vista: Gestion de Organismos (catalogo global).

Catalogo de organismos/administraciones (AEAT, TGSS, DGT...) que pueden
emitir notificaciones electronicas. Operativo sobre SQLite local.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403

TIPOS_ORGANISMO = ["HACIENDA", "SS", "TRANSPORTE", "EMPLEO", "CONTROL", "TRABAJO", "LOCAL", "AAPP", "OTRO"]


class UIOrganismos(ttk.Frame):
    """Pantalla de gestion del catalogo de organismos."""

    _COLS = [
        ("codigo",      "Codigo",    80,  "center"),
        ("nombre",      "Nombre",   280,  "w"),
        ("tipo",        "Tipo",      90,  "center"),
        ("url_portal",  "Portal",   220,  "w"),
        ("activo",      "Estado",    70,  "center"),
    ]

    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor  = gestor
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
        tk.Label(hdr, text="\u2318  Organismos", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Catalogo global de administraciones y organismos emisores",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

    def _build_toolbar(self) -> None:
        tb = tk.Frame(self, bg=_BG, pady=6)
        tb.pack(fill="x", padx=8)
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=10, pady=4)
        tk.Button(tb, text="+ Nuevo",   bg=_PRIMARY, fg="white", command=self._on_nuevo,   **btn).pack(side="left", padx=(0, 5))
        self._btn_editar  = tk.Button(tb, text="Editar",   bg="#475569", fg="white", command=self._on_editar,   state="disabled", **btn)
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
        self._tv.tag_configure("activo",   foreground="#10b981")
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
        dlg = _OrganismoDialog(self.winfo_toplevel(), None)
        if dlg.result:
            try:
                self._gestor.upsert_notif_organismo(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_editar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        org_id = int(self._tv.set(sel[0], "_id"))
        org    = self._gestor.get_notif_organismo(org_id)
        if not org:
            return
        dlg = _OrganismoDialog(self.winfo_toplevel(), org)
        if dlg.result:
            try:
                self._gestor.upsert_notif_organismo(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_eliminar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        org_id = int(self._tv.set(sel[0], "_id"))
        nombre = self._tv.set(sel[0], "nombre")
        if not messagebox.askyesno("Eliminar organismo",
                                   f"Eliminar el organismo '{nombre}'?\n"
                                   "Se perderan los buzones y notificaciones asociados.",
                                   parent=self.winfo_toplevel()):
            return
        try:
            self._gestor.eliminar_notif_organismo(org_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        rows = self._gestor.listar_notif_organismos()
        self._tv.delete(*self._tv.get_children())
        for r in rows:
            tag = "activo" if r.get("activo") else "inactivo"
            estado = "Activo" if r.get("activo") else "Inactivo"
            self._tv.insert("", tk.END, values=(
                r["id"], r.get("codigo", ""), r.get("nombre", ""),
                r.get("tipo", ""), r.get("url_portal", ""), estado,
            ), tags=(tag,))
        n = len(rows)
        self._lbl_count.configure(text=f"{n} organismo{'s' if n != 1 else ''}")
        self._lbl_status.configure(text=f"Total: {n} | Activos: {sum(1 for r in rows if r.get('activo'))}")
        self._btn_editar.configure(state="disabled")
        self._btn_eliminar.configure(state="disabled")


# ── Dialog ───────────────────────────────────────────────────────────────────

class _OrganismoDialog(tk.Toplevel):
    """Dialogo de creacion/edicion de organismo."""

    def __init__(self, parent, org: dict | None):
        super().__init__(parent)
        self.title("Nuevo organismo" if org is None else "Editar organismo")
        self.resizable(False, False)
        self.result: dict | None = None
        self._org = org or {}
        self._build()
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self) -> None:
        pad = dict(padx=12, pady=4)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        fields = [
            ("Codigo *",      "_codigo",      ttk.Entry,    {"width": 14}),
            ("Nombre *",      "_nombre",      ttk.Entry,    {"width": 44}),
            ("Tipo",          "_tipo",        ttk.Combobox, {"width": 20, "values": TIPOS_ORGANISMO, "state": "readonly"}),
            ("URL Portal",    "_url",         ttk.Entry,    {"width": 44}),
            ("Descripcion",   "_descripcion", ttk.Entry,    {"width": 44}),
        ]
        self._vars: dict[str, tk.StringVar] = {}
        for row_idx, (label, key, widget_cls, kwargs) in enumerate(fields):
            ttk.Label(frm, text=label, anchor="e").grid(row=row_idx, column=0, sticky="e", **pad)
            var = tk.StringVar()
            w   = widget_cls(frm, textvariable=var, **kwargs)
            w.grid(row=row_idx, column=1, sticky="w", **pad)
            self._vars[key] = var

        # Activo
        self._var_activo = tk.BooleanVar(value=bool(self._org.get("activo", True)))
        ttk.Checkbutton(frm, text="Activo", variable=self._var_activo).grid(
            row=len(fields), column=1, sticky="w", **pad)

        # Pre-fill
        self._vars["_codigo"].set(str(self._org.get("codigo", "")))
        self._vars["_nombre"].set(str(self._org.get("nombre", "")))
        self._vars["_tipo"].set(str(self._org.get("tipo", "AAPP")))
        self._vars["_url"].set(str(self._org.get("url_portal", "") or ""))
        self._vars["_descripcion"].set(str(self._org.get("descripcion", "") or ""))

        # Bloquear codigo si es edicion
        if self._org.get("id"):
            frm.children[list(frm.children.keys())[1]].configure(state="disabled")

        # Botones
        btn_row = ttk.Frame(self, padding=(16, 8))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="Guardar", style="Accent.TButton", command=self._on_ok).pack(side="right")

    def _on_ok(self) -> None:
        codigo = self._vars["_codigo"].get().strip().upper()
        nombre = self._vars["_nombre"].get().strip()
        if not codigo:
            messagebox.showerror("Gest2A3Eco", "El codigo es obligatorio.", parent=self)
            return
        if not nombre:
            messagebox.showerror("Gest2A3Eco", "El nombre es obligatorio.", parent=self)
            return
        self.result = {
            "codigo":      codigo,
            "nombre":      nombre,
            "tipo":        self._vars["_tipo"].get().strip() or "AAPP",
            "url_portal":  self._vars["_url"].get().strip() or None,
            "descripcion": self._vars["_descripcion"].get().strip() or None,
            "activo":      1 if self._var_activo.get() else 0,
        }
        if self._org.get("id"):
            self.result["id"] = self._org["id"]
        self.destroy()
