"""
Vista: Gestion de Certificados Digitales.

Permite registrar, editar y controlar los certificados digitales de la empresa
usados para autenticarse en los portales de organismos. Operativo sobre SQLite local.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403

TIPOS_CERT = ["PFX", "PEM", "P12", "PKCS12", "Renovacion", "Otro"]


def _vigencia(fecha_caducidad_str: str | None) -> tuple[str, str]:
    """Devuelve (label, tag) segun la fecha de caducidad."""
    if not fecha_caducidad_str:
        return "Sin fecha", "neutro"
    try:
        cad = datetime.strptime(fecha_caducidad_str[:10], "%Y-%m-%d").date()
        hoy = date.today()
        dias = (cad - hoy).days
        if dias < 0:
            return "Caducado", "caducado"
        if dias <= 30:
            return f"Vence en {dias}d", "por_vencer"
        return f"Vigente ({dias}d)", "vigente"
    except ValueError:
        return fecha_caducidad_str, "neutro"


class UICertificados(ttk.Frame):
    """Pantalla de gestion de certificados digitales de una empresa."""

    _COLS = [
        ("nombre",          "Nombre",           200, "w"),
        ("nif_titular",     "NIF Titular",        90, "center"),
        ("tipo",            "Tipo",               60, "center"),
        ("fecha_emision",   "Emitido",           100, "center"),
        ("fecha_caducidad", "Caduca",            100, "center"),
        ("vigencia",        "Estado vigencia",   120, "center"),
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
        self._build_alert_banner()
        self._build_toolbar()
        self._build_tree()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\u2460  Certificados Digitales", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Certificados de autenticacion ante organismos",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

    def _build_alert_banner(self) -> None:
        self._banner = tk.Frame(self, bg=_WARNING)
        self._lbl_banner = tk.Label(
            self._banner, text="", bg=_WARNING, fg="white",
            font=("Segoe UI", 9, "bold"), anchor="w",
        )
        self._lbl_banner.pack(side="left", padx=12, pady=5)

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
        self._tv.tag_configure("vigente",    foreground=_SUCCESS)
        self._tv.tag_configure("por_vencer", foreground=_WARNING)
        self._tv.tag_configure("caducado",   foreground=_DANGER)
        self._tv.tag_configure("neutro",     foreground=_SUB)
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
        dlg = _CertificadoDialog(self.winfo_toplevel(), None, self._codigo)
        if dlg.result:
            try:
                self._gestor.upsert_notif_certificado(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_editar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        cert_id = self._tv.set(sel[0], "_id")
        cert    = self._gestor.get_notif_certificado(cert_id)
        if not cert:
            return
        dlg = _CertificadoDialog(self.winfo_toplevel(), cert, self._codigo)
        if dlg.result:
            try:
                self._gestor.upsert_notif_certificado(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_eliminar(self) -> None:
        sel = self._tv.selection()
        if not sel:
            return
        cert_id = self._tv.set(sel[0], "_id")
        nombre  = self._tv.set(sel[0], "nombre")
        if not messagebox.askyesno("Eliminar certificado",
                                   f"Eliminar el certificado '{nombre}'?",
                                   parent=self.winfo_toplevel()):
            return
        try:
            self._gestor.eliminar_notif_certificado(self._codigo, cert_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        rows = self._gestor.listar_notif_certificados(self._codigo)
        self._tv.delete(*self._tv.get_children())
        urgentes = 0
        for r in rows:
            vig_label, vig_tag = _vigencia(r.get("fecha_caducidad"))
            if vig_tag == "por_vencer":
                urgentes += 1
            self._tv.insert("", tk.END, values=(
                r["id"],
                r.get("nombre", ""),
                r.get("nif_titular", ""),
                r.get("tipo", ""),
                r.get("fecha_emision", "") or "",
                r.get("fecha_caducidad", "") or "",
                vig_label,
            ), tags=(vig_tag,))

        # Banner de advertencia
        if urgentes > 0:
            self._lbl_banner.configure(
                text=f"\u26a0  {urgentes} certificado{'s' if urgentes > 1 else ''} "
                     f"vence{'n' if urgentes > 1 else ''} en menos de 30 dias. Revisa y renueva."
            )
            self._banner.pack(fill="x", after=self.winfo_children()[0])
        else:
            self._banner.pack_forget()

        n = len(rows)
        self._lbl_count.configure(text=f"{n} certificado{'s' if n != 1 else ''}")
        self._lbl_status.configure(
            text=f"Vigentes: {sum(1 for r in rows if _vigencia(r.get('fecha_caducidad'))[1] == 'vigente')}  "
                 f"Por vencer: {urgentes}  "
                 f"Caducados: {sum(1 for r in rows if _vigencia(r.get('fecha_caducidad'))[1] == 'caducado')}"
        )
        self._btn_editar.configure(state="disabled")
        self._btn_eliminar.configure(state="disabled")


# ── Dialog ───────────────────────────────────────────────────────────────────

class _CertificadoDialog(tk.Toplevel):
    """Dialogo de creacion/edicion de certificado digital."""

    def __init__(self, parent, cert: dict | None, codigo_empresa: str):
        super().__init__(parent)
        self.title("Nuevo certificado" if cert is None else "Editar certificado")
        self.resizable(False, False)
        self.result: dict | None = None
        self._cert    = cert or {}
        self._empresa = codigo_empresa
        self._build()
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self) -> None:
        pad = dict(padx=12, pady=4)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        self._var_nombre  = tk.StringVar(value=self._cert.get("nombre", ""))
        self._var_nif     = tk.StringVar(value=self._cert.get("nif_titular", ""))
        self._var_tipo    = tk.StringVar(value=self._cert.get("tipo", "PFX"))
        self._var_ruta    = tk.StringVar(value=self._cert.get("ruta_archivo", "") or "")
        self._var_emision = tk.StringVar(value=self._cert.get("fecha_emision", "") or "")
        self._var_cad     = tk.StringVar(value=self._cert.get("fecha_caducidad", "") or "")
        self._var_notas   = tk.StringVar(value=self._cert.get("notas", "") or "")
        self._var_activo  = tk.BooleanVar(value=bool(self._cert.get("activo", True)))

        rows = [
            ("Nombre *",          self._var_nombre,  ttk.Entry,    {"width": 44}),
            ("NIF Titular *",     self._var_nif,     ttk.Entry,    {"width": 20}),
            ("Tipo",              self._var_tipo,    ttk.Combobox, {"width": 18, "values": TIPOS_CERT, "state": "readonly"}),
            ("Fecha emision\n(AAAA-MM-DD)", self._var_emision, ttk.Entry, {"width": 14}),
            ("Fecha caducidad\n(AAAA-MM-DD)", self._var_cad, ttk.Entry,   {"width": 14}),
            ("Notas",             self._var_notas,   ttk.Entry,    {"width": 44}),
        ]
        for i, (lbl, var, cls, kw) in enumerate(rows):
            ttk.Label(frm, text=lbl, anchor="e", justify="right").grid(row=i, column=0, sticky="e", **pad)
            cls(frm, textvariable=var, **kw).grid(row=i, column=1, sticky="w", **pad)

        # Fila ruta con boton examinar
        r = len(rows)
        ttk.Label(frm, text="Ruta archivo", anchor="e").grid(row=r, column=0, sticky="e", **pad)
        ruta_frm = tk.Frame(frm)
        ruta_frm.grid(row=r, column=1, sticky="w", **pad)
        ttk.Entry(ruta_frm, textvariable=self._var_ruta, width=34).pack(side="left")
        ttk.Button(ruta_frm, text="...", width=3, command=self._browse_file).pack(side="left", padx=(4, 0))

        ttk.Checkbutton(frm, text="Activo", variable=self._var_activo).grid(
            row=r + 1, column=1, sticky="w", **pad)

        btn_row = ttk.Frame(self, padding=(16, 8))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="Guardar", command=self._on_ok).pack(side="right")

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar fichero de certificado",
            filetypes=[("Certificados", "*.pfx *.p12 *.pem *.cer"), ("Todos", "*.*")],
        )
        if path:
            self._var_ruta.set(path)

    def _on_ok(self) -> None:
        nombre = self._var_nombre.get().strip()
        nif    = self._var_nif.get().strip().upper()
        if not nombre:
            messagebox.showerror("Gest2A3Eco", "El nombre es obligatorio.", parent=self)
            return
        if not nif:
            messagebox.showerror("Gest2A3Eco", "El NIF titular es obligatorio.", parent=self)
            return
        self.result = {
            "codigo_empresa": self._empresa,
            "nombre":         nombre,
            "nif_titular":    nif,
            "tipo":           self._var_tipo.get().strip() or "PFX",
            "ruta_archivo":   self._var_ruta.get().strip() or None,
            "fecha_emision":  self._var_emision.get().strip() or None,
            "fecha_caducidad":self._var_cad.get().strip() or None,
            "notas":          self._var_notas.get().strip() or None,
            "activo":         1 if self._var_activo.get() else 0,
        }
        if self._cert.get("id"):
            self.result["id"] = self._cert["id"]
        self.destroy()
