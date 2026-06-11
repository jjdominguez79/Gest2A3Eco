"""
Vista: Certificados globales (modulo "Notificaciones Electronicas").

Listado de los certificados digitales de TODOS los clientes, con filtros
por cliente y estado de vigencia. El alta y la edicion reutilizan el mismo
dialogo que la pestana de certificados de la ficha de cliente; ambas vistas
trabajan contra la misma tabla `notif_certificados`. La baja es logica
(activo/inactivo), no se elimina el registro.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_certificados import _CertificadoDialog, _vigencia
from views.ui_notificaciones_shared import seleccionar_cliente


class UICertificadosGlobal(ttk.Frame):
    """Listado global de certificados digitales de todos los clientes."""

    _COLS = [
        ("cliente",         "Cliente",          170, "w"),
        ("nombre",          "Nombre",           170, "w"),
        ("nif_titular",     "NIF Titular",       90, "center"),
        ("tipo",            "Tipo",              60, "center"),
        ("fecha_caducidad", "Caduca",           100, "center"),
        ("vigencia",        "Estado vigencia",  120, "center"),
        ("clave",           "Clave",             60, "center"),
        ("activo",          "Activo",            70, "center"),
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
        tk.Label(hdr, text="①  Certificados (todos los clientes)", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Certificados digitales de todos los clientes",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

    def _build_filter_bar(self) -> None:
        fb = tk.Frame(self, bg="#e2e8f0", pady=4)
        fb.pack(fill="x", padx=8, pady=(0, 2))

        tk.Label(fb, text="Cliente:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_cliente = tk.StringVar(value="Todos")
        self._cb_cliente = ttk.Combobox(fb, textvariable=self._var_cliente, state="readonly", width=24)
        self._cb_cliente.pack(side="left", padx=(0, 10))
        self._cb_cliente.bind("<<ComboboxSelected>>", lambda _e: self._render())

        tk.Label(fb, text="Vigencia:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_vigencia = tk.StringVar(value="Todas")
        cb_vig = ttk.Combobox(
            fb, textvariable=self._var_vigencia, state="readonly", width=14,
            values=["Todas", "Vigente", "Por vencer", "Caducado", "Sin fecha"],
        )
        cb_vig.pack(side="left", padx=(0, 10))
        cb_vig.bind("<<ComboboxSelected>>", lambda _e: self._render())

        self._var_solo_activos = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb, text="Solo activos", variable=self._var_solo_activos,
                        command=self._render).pack(side="left", padx=(0, 10))

        self._lbl_count = tk.Label(fb, text="", bg="#e2e8f0", fg=_SUB, font=("Segoe UI", 9))
        self._lbl_count.pack(side="right", padx=8)

    def _build_toolbar(self) -> None:
        tb = tk.Frame(self, bg=_BG, pady=6)
        tb.pack(fill="x", padx=8)
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=10, pady=4)
        tk.Button(tb, text="+ Nuevo", bg=_PRIMARY, fg="white", command=self._on_nuevo, **btn).pack(side="left", padx=(0, 5))
        self._btn_editar = tk.Button(tb, text="Editar", bg="#475569", fg="white",
                                      command=self._on_editar, state="disabled", **btn)
        self._btn_editar.pack(side="left", padx=(0, 5))
        self._btn_toggle = tk.Button(tb, text="Activar/Desactivar", bg="#475569", fg="white",
                                      command=self._on_toggle_activo, state="disabled", **btn)
        self._btn_toggle.pack(side="left", padx=(0, 5))
        self._btn_probar = tk.Button(tb, text="Probar certificado", bg="#0ea5e9", fg="white",
                                      command=self._on_probar, state="disabled", **btn)
        self._btn_probar.pack(side="left", padx=(0, 5))
        self._btn_buzones = tk.Button(tb, text="Ver buzones vinculados", bg="#475569", fg="white",
                                       command=self._on_ver_buzones, state="disabled", **btn)
        self._btn_buzones.pack(side="left", padx=(0, 5))
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
        self._tv.tag_configure("vigente",    foreground=_SUCCESS)
        self._tv.tag_configure("por_vencer", foreground=_WARNING)
        self._tv.tag_configure("caducado",   foreground=_DANGER)
        self._tv.tag_configure("neutro",     foreground=_SUB)
        self._tv.tag_configure("inactivo",   foreground=_SUB)
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

    # ----------------------------------------------------------------- helpers

    def _row_seleccionada(self) -> dict | None:
        sel = self._tv.selection()
        if not sel:
            return None
        cert_id = self._tv.set(sel[0], "_id")
        return next((c for c in self._cache if str(c.get("id")) == str(cert_id)), None)

    # ----------------------------------------------------------------- eventos

    def _on_select(self, _e=None) -> None:
        ok = bool(self._tv.selection())
        s = "normal" if ok else "disabled"
        self._btn_editar.configure(state=s)
        self._btn_toggle.configure(state=s)
        self._btn_probar.configure(state=s)
        self._btn_buzones.configure(state=s)

    def _on_nuevo(self) -> None:
        empresa = seleccionar_cliente(self.winfo_toplevel(), self._gestor)
        if not empresa:
            return
        dlg = _CertificadoDialog(self.winfo_toplevel(), None, empresa["codigo"])
        if dlg.result:
            try:
                self._gestor.upsert_notif_certificado(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_editar(self) -> None:
        cert = self._row_seleccionada()
        if not cert:
            return
        dlg = _CertificadoDialog(self.winfo_toplevel(), cert, cert["codigo_empresa"])
        if dlg.result:
            try:
                self._gestor.upsert_notif_certificado(dlg.result)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
                return
            self.refresh()

    def _on_toggle_activo(self) -> None:
        cert = self._row_seleccionada()
        if not cert:
            return
        nuevo = dict(cert)
        nuevo["activo"] = 0 if cert.get("activo") else 1
        try:
            self._gestor.upsert_notif_certificado(nuevo)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    def _on_probar(self) -> None:
        cert = self._row_seleccionada()
        if not cert:
            return
        ruta = cert.get("ruta_archivo")
        tiene_ruta = bool(ruta and os.path.isfile(ruta))
        tiene_pwd = bool(cert.get("password_cifrada"))
        if tiene_ruta and tiene_pwd:
            messagebox.showinfo(
                "Prueba de certificado",
                f"Simulacion correcta para '{cert.get('nombre')}'.\n\n"
                "Fichero localizado y contrasena configurada.\n"
                "(No se realiza conexion real con el organismo todavia.)",
                parent=self.winfo_toplevel(),
            )
            return
        problemas = []
        if not ruta:
            problemas.append("- No se ha indicado ningun fichero de certificado.")
        elif not tiene_ruta:
            problemas.append(f"- No se encuentra el fichero: {ruta}")
        if not tiene_pwd:
            problemas.append("- No hay contrasena configurada.")
        messagebox.showwarning(
            "Prueba de certificado",
            "La simulacion ha detectado incidencias:\n" + "\n".join(problemas),
            parent=self.winfo_toplevel(),
        )

    def _on_ver_buzones(self) -> None:
        cert = self._row_seleccionada()
        if not cert:
            return
        buzones = [b for b in self._gestor.listar_notif_buzones_global() if b.get("certificado_id") == cert.get("id")]
        if not buzones:
            messagebox.showinfo(
                "Buzones vinculados",
                f"El certificado '{cert.get('nombre')}' no tiene buzones vinculados.",
                parent=self.winfo_toplevel(),
            )
            return
        lineas = [
            f"- {b.get('empresa_nombre') or b.get('codigo_empresa')}: "
            f"{b.get('nombre')} ({b.get('organismo_nombre') or b.get('organismo_codigo') or 'sin organismo'})"
            for b in buzones
        ]
        messagebox.showinfo(
            "Buzones vinculados",
            f"Buzones que usan el certificado '{cert.get('nombre')}':\n\n" + "\n".join(lineas),
            parent=self.winfo_toplevel(),
        )

    # ----------------------------------------------------------------- refresh

    def refresh(self) -> None:
        self._cache = self._gestor.listar_notif_certificados_global()
        clientes = sorted({c.get("empresa_nombre") or c.get("codigo_empresa") or "" for c in self._cache} - {""})
        self._cb_cliente.configure(values=["Todos"] + clientes)
        if self._cb_cliente.get() not in (["Todos"] + clientes):
            self._cb_cliente.set("Todos")
        self._render()

    def _render(self) -> None:
        cliente_lbl = self._var_cliente.get()
        vig_lbl = self._var_vigencia.get()
        solo_activos = self._var_solo_activos.get()

        vig_map = {"Vigente": "vigente", "Por vencer": "por_vencer", "Caducado": "caducado", "Sin fecha": "neutro"}
        vig_filtro = vig_map.get(vig_lbl)

        self._tv.delete(*self._tv.get_children())
        rows_mostradas = 0
        for c in self._cache:
            cliente = c.get("empresa_nombre") or c.get("codigo_empresa") or ""
            if cliente_lbl not in ("", "Todos") and cliente != cliente_lbl:
                continue
            if solo_activos and not c.get("activo"):
                continue
            vig_label, vig_tag = _vigencia(c.get("fecha_caducidad"))
            if vig_filtro and vig_tag != vig_filtro:
                continue
            tag = vig_tag if c.get("activo") else "inactivo"
            self._tv.insert("", tk.END, values=(
                c["id"], cliente, c.get("nombre", ""), c.get("nif_titular", ""),
                c.get("tipo", ""), c.get("fecha_caducidad", "") or "", vig_label,
                "Si" if c.get("password_cifrada") else "-",
                "Si" if c.get("activo") else "No",
            ), tags=(tag,))
            rows_mostradas += 1

        self._lbl_count.configure(text=f"{rows_mostradas} certificado{'s' if rows_mostradas != 1 else ''}")
        urgentes = sum(1 for c in self._cache if _vigencia(c.get("fecha_caducidad"))[1] == "por_vencer")
        caducados = sum(1 for c in self._cache if _vigencia(c.get("fecha_caducidad"))[1] == "caducado")
        self._lbl_status.configure(
            text=f"Total: {len(self._cache)}  |  Por vencer: {urgentes}  |  Caducados: {caducados}"
        )
        self._btn_editar.configure(state="disabled")
        self._btn_toggle.configure(state="disabled")
        self._btn_probar.configure(state="disabled")
        self._btn_buzones.configure(state="disabled")
