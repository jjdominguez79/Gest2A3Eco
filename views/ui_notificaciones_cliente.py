"""
Vista: Notificaciones electronicas del cliente (pantalla dividida en 2).

Izquierda:
  - Certificado digital unico del cliente (panel UICertificados).
  - Opciones comunes que se aplican a TODOS los buzones del cliente
    (email de aviso, modo de descarga, periodicidad, envio automatico,
    responsable interno).

Derecha (patron Portal NEOS):
  - Tabla con todas las administraciones/organismos configurados globalmente
    (Organismo, Descripcion, notificaciones Pendientes), con una marca por fila
    para elegir cuales gestiona el cliente. La URL del organismo seleccionado se
    muestra debajo. Cada organismo marcado se materializa como un buzon activo.

Un unico boton "Guardar configuracion" concilia todo.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_certificados import UICertificados
from views.ui_buzones import MODOS_DESCARGA, PERIODICIDADES, LABELS_MODO_DESCARGA

_MARCADO = "☑"     # casilla marcada
_SIN_MARCAR = "☐"  # casilla vacia


class UINotificacionesCliente(ttk.Frame):
    def __init__(self, master, gestor, codigo, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._codigo = codigo
        self._session = session
        self._organismos = []
        self._orgs_by_id = {}
        self._org_marca = {}
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=3)
        paned.add(right, weight=3)
        self._build_left(left)
        self._build_right(right)

        bar = tk.Frame(self, bg=_BG)
        bar.pack(fill="x", side="bottom")
        tk.Button(bar, text="Guardar configuracion", bg=_PRIMARY, fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                  padx=14, pady=6, command=self._on_guardar).pack(side="right", padx=12, pady=8)

    def _build_left(self, left):
        self._cert_panel = UICertificados(left, self._gestor, self._codigo, session=self._session)
        self._cert_panel.pack(fill="x")

        card = tk.Frame(left, bg=_BG)
        card.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(card, text="Opciones comunes de los buzones", bg=_BG, fg=_HDR_FG,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._var_email = tk.StringVar()
        self._var_periodicidad = tk.StringVar(value="MANUAL")
        self._var_responsable = tk.StringVar()
        self._var_envio = tk.BooleanVar(value=False)
        self._modo_labels = [LABELS_MODO_DESCARGA[m] for m in MODOS_DESCARGA]
        self._var_modo = tk.StringVar(value=self._modo_labels[0])

        filas = [
            ("Email de aviso", ttk.Entry(card, textvariable=self._var_email, width=34)),
            ("Modo de descarga", ttk.Combobox(card, textvariable=self._var_modo, width=24,
                                               values=self._modo_labels, state="readonly")),
            ("Periodicidad sincronizacion", ttk.Combobox(card, textvariable=self._var_periodicidad, width=24,
                                                         values=PERIODICIDADES, state="readonly")),
            ("Responsable interno", ttk.Entry(card, textvariable=self._var_responsable, width=34)),
        ]
        for i, (lbl, widget) in enumerate(filas, start=1):
            tk.Label(card, text=lbl + ":", bg=_BG, fg=_SUB, font=("Segoe UI", 9),
                     anchor="e").grid(row=i, column=0, sticky="e", padx=(0, 8), pady=3)
            widget.grid(row=i, column=1, sticky="w", pady=3)
        ttk.Checkbutton(card, text="Envio automatico al cliente",
                        variable=self._var_envio).grid(row=len(filas) + 1, column=1, sticky="w", pady=(4, 0))

    def _build_right(self, right):
        hdr = tk.Frame(right, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Administraciones", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Marca (doble clic) las que gestionas para este cliente",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

        cont = tk.Frame(right, bg=_BG)
        cont.pack(fill="both", expand=True, padx=8, pady=(8, 2))
        cols = ("_id", "marca", "organismo", "descripcion", "pend")
        self._tv = ttk.Treeview(cont, columns=cols, show="headings", selectmode="browse")
        self._tv.column("_id", width=0, stretch=False)
        self._tv.heading("_id", text="")
        for key, txt, w, anc in (
            ("marca", "", 40, "center"),
            ("organismo", "Administracion / Organismo", 210, "w"),
            ("descripcion", "Descripcion", 230, "w"),
            ("pend", "Pend.", 55, "center"),
        ):
            self._tv.heading(key, text=txt)
            self._tv.column(key, width=w, anchor=anc, stretch=(key == "descripcion"))
        self._tv.tag_configure("marcado", background="#eef6ff")
        sb = ttk.Scrollbar(cont, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        self._tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tv.bind("<Double-1>", lambda _e: self._toggle_marca())
        self._tv.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self._tv.bind("<space>", lambda _e: self._toggle_marca())

        acc = tk.Frame(right, bg=_BG)
        acc.pack(fill="x", padx=8, pady=(0, 2))
        tk.Button(acc, text="Marcar / Desmarcar", bg="#475569", fg="white", relief="flat",
                  cursor="hand2", padx=10, pady=3, command=self._toggle_marca).pack(side="left")
        self._lbl_url = tk.Label(right, text="", bg=_BG, fg="#2563eb", font=("Segoe UI", 8),
                                 anchor="w", justify="left", wraplength=520)
        self._lbl_url.pack(fill="x", padx=10, pady=(2, 8))

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        try:
            self._cert_panel.refresh()
        except Exception:
            pass

        self._organismos = self._gestor.listar_notif_organismos(solo_activos=True)
        self._orgs_by_id = {o["id"]: o for o in self._organismos}
        buzones = {b.get("organismo_id"): b for b in self._gestor.listar_notif_buzones(self._codigo)}

        counts = {}
        try:
            cur = self._gestor.conn.execute(
                "SELECT organismo_id, COUNT(*) FROM notif_bandeja "
                "WHERE codigo_empresa=? AND estado='PENDIENTE' GROUP BY organismo_id",
                (self._codigo,),
            )
            counts = {r[0]: r[1] for r in cur.fetchall()}
        except Exception:
            counts = {}

        self._org_marca = {}
        self._tv.delete(*self._tv.get_children())
        for org in self._organismos:
            oid = org["id"]
            buzon = buzones.get(oid)
            marcado = bool(buzon and buzon.get("activo"))
            self._org_marca[oid] = marcado
            self._tv.insert("", "end", values=(
                oid,
                _MARCADO if marcado else _SIN_MARCAR,
                f"{org.get('nombre','')}",
                org.get("descripcion", "") or "",
                counts.get(oid, 0) or "",
            ), tags=("marcado",) if marcado else ())

        # Prefill de opciones desde un buzon existente
        alguno = next(iter(buzones.values()), None)
        if alguno:
            self._var_email.set(alguno.get("email_aviso") or "")
            self._var_responsable.set(alguno.get("responsable_interno") or "")
            self._var_periodicidad.set(alguno.get("periodicidad_sync") or "MANUAL")
            self._var_envio.set(bool(alguno.get("envio_automatico_cliente")))
            modo = alguno.get("modo_descarga") or "SOLO_DETECTAR"
            if modo in MODOS_DESCARGA:
                self._var_modo.set(self._modo_labels[MODOS_DESCARGA.index(modo)])

    # ------------------------------------------------------------------ tabla
    def _fila_sel(self):
        sel = self._tv.selection()
        return sel[0] if sel else None

    def _on_select(self):
        it = self._fila_sel()
        if not it:
            self._lbl_url.configure(text="")
            return
        oid = int(self._tv.set(it, "_id"))
        org = self._orgs_by_id.get(oid, {})
        self._lbl_url.configure(text=org.get("url_portal", "") or "")

    def _toggle_marca(self):
        it = self._fila_sel()
        if not it:
            return
        oid = int(self._tv.set(it, "_id"))
        nuevo = not self._org_marca.get(oid, False)
        self._org_marca[oid] = nuevo
        self._tv.set(it, "marca", _MARCADO if nuevo else _SIN_MARCAR)
        self._tv.item(it, tags=("marcado",) if nuevo else ())

    # ------------------------------------------------------------------ helpers
    def _opciones(self):
        modo_label = self._var_modo.get()
        modo = MODOS_DESCARGA[self._modo_labels.index(modo_label)] if modo_label in self._modo_labels else "SOLO_DETECTAR"
        return {
            "modo_descarga": modo,
            "periodicidad_sync": self._var_periodicidad.get() or "MANUAL",
            "email_aviso": self._var_email.get().strip() or None,
            "responsable_interno": self._var_responsable.get().strip() or None,
            "envio_automatico_cliente": 1 if self._var_envio.get() else 0,
        }

    def _cert(self):
        certs = self._gestor.listar_notif_certificados(self._codigo, solo_activos=True)
        if not certs:
            certs = self._gestor.listar_notif_certificados(self._codigo)
        return certs[0] if certs else None

    # ------------------------------------------------------------------ guardar
    def _on_guardar(self):
        opts = self._opciones()
        cert = self._cert()
        cert_id = cert["id"] if cert else None
        nif = (cert.get("nif_titular") if cert else None) or None

        buzones = {b.get("organismo_id"): b for b in self._gestor.listar_notif_buzones(self._codigo)}
        creados = activados = desactivados = 0
        try:
            for org in self._organismos:
                oid = org["id"]
                marcado = self._org_marca.get(oid, False)
                existente = buzones.get(oid)
                if marcado:
                    data = {
                        "codigo_empresa": self._codigo,
                        "nombre": (existente.get("nombre") if existente else None) or org.get("nombre") or "Buzon",
                        "organismo_id": oid,
                        "tipo_buzon": (existente.get("tipo_buzon") if existente else None) or "DEH",
                        "nif_titular": nif,
                        "certificado_id": cert_id,
                        "activo": 1,
                        **opts,
                    }
                    if existente:
                        data["id"] = existente["id"]
                        if existente.get("ultima_consulta"):
                            data["ultima_consulta"] = existente["ultima_consulta"]
                        if not existente.get("activo"):
                            activados += 1
                    else:
                        creados += 1
                    self._gestor.upsert_notif_buzon(data)
                elif existente and existente.get("activo"):
                    data = dict(existente)
                    data["activo"] = 0
                    data["id"] = existente["id"]
                    self._gestor.upsert_notif_buzon(data)
                    desactivados += 1
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return

        messagebox.showinfo(
            "Configuracion guardada",
            f"Administraciones activas actualizadas.\n\n"
            f"Nuevas: {creados}   Reactivadas: {activados}   Desactivadas: {desactivados}",
            parent=self.winfo_toplevel(),
        )
        self.refresh()
