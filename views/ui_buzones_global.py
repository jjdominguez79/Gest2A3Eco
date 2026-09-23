"""
Vista: Buzones globales (modulo "Notificaciones Electronicas") - SOLO LECTURA.

Matriz de los buzones DEHu y DGT/DEV de TODOS los clientes. Permite seleccionar
varias filas, activar o desactivar el servicio masivamente y sincronizar todos
los buzones activos con el certificado propio de cada cliente.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from services.backend_client_service import BackendClientService
from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_buzones import LABELS_MODO_DESCARGA


class UIBuzonesGlobal(ttk.Frame):
    """Configuracion masiva y sincronizacion de buzones electronicos."""

    _COLS = [
        ("cliente",         "Cliente",          170, "w"),
        ("organismo",       "Organismo",        150, "w"),
        ("nombre",          "Nombre buzon",     150, "w"),
        ("tipo_buzon",      "Tipo",              70, "center"),
        ("certificado",     "Certificado",      140, "w"),
        ("modo_descarga",   "Modo de consulta",  140, "center"),
        ("ultima_consulta", "Ultima consulta",  120, "center"),
        ("activo",          "Activo",            60, "center"),
        ("conexion",        "Conexion",         115, "center"),
    ]

    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor  = gestor
        self._session = session
        self._cache: list[dict] = []
        self._dev_status: dict[str, dict] = {}
        self._cargando_dev_status = False
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
        tk.Label(hdr, text="▦  Buzones y sincronizacion", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Solo los buzones activos entran en la sincronizacion global.",
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
        self._btn_sync_all = tk.Button(tb, text="↻ Sincronizar todos los activos", bg="#0284c7", fg="white",
                                       command=self._on_sincronizar_todos, **btn)
        self._btn_sync_all.pack(side="left", padx=(0, 5))
        self._btn_activar = tk.Button(
            tb, text="Activar seleccionados", bg="#15803d", fg="white",
            command=lambda: self._on_cambiar_activos(True), state="disabled", **btn,
        )
        self._btn_activar.pack(side="left", padx=(8, 5))
        self._btn_desactivar = tk.Button(
            tb, text="Desactivar seleccionados", bg="#b91c1c", fg="white",
            command=lambda: self._on_cambiar_activos(False), state="disabled", **btn,
        )
        self._btn_desactivar.pack(side="left", padx=(0, 5))
        self._btn_ver_notif = tk.Button(tb, text="Ver notificaciones", bg="#475569", fg="white",
                                         command=self._on_ver_notificaciones, state="disabled", **btn)
        self._btn_ver_notif.pack(side="left", padx=(0, 5))
        tk.Button(tb, text="↻ Actualizar", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")

    def _build_tree(self) -> None:
        wrapper = tk.Frame(self, bg=_BG)
        wrapper.pack(fill="both", expand=True, padx=8, pady=4)
        col_ids = ["_id"] + [c[0] for c in self._COLS]
        self._tv = ttk.Treeview(wrapper, columns=col_ids, show="headings", selectmode="extended")
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

    def _filas_seleccionadas(self) -> list[dict]:
        ids = {str(self._tv.set(item, "_id")) for item in self._tv.selection()}
        return [row for row in self._cache if str(row.get("id")) in ids]

    def _on_select(self, _e=None) -> None:
        ok = bool(self._tv.selection())
        s = "normal" if ok else "disabled"
        self._btn_sync.configure(state=s)
        self._btn_ver_notif.configure(state=s)
        self._btn_activar.configure(state=s)
        self._btn_desactivar.configure(state=s)

    def _on_cambiar_activos(self, activo: bool) -> None:
        filas = self._filas_seleccionadas()
        if not filas:
            return
        accion = "activar" if activo else "desactivar"
        if not messagebox.askyesno(
            "Configurar buzones",
            f"Se van a {accion} {len(filas)} buzon(es) seleccionado(s).\n\n"
            "Cada consulta utilizara exclusivamente el certificado del cliente. Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._set_busy(True)
        import threading

        def _worker():
            guardados = 0
            errores = []
            validaciones_dev = 0
            for row in filas:
                try:
                    if not activo and row.get("_virtual"):
                        continue
                    self._guardar_estado_buzon(row, activo)
                    guardados += 1
                    if activo and row.get("organismo_codigo") == "DEV":
                        self._encolar_buzon({**row, "activo": 1})
                        validaciones_dev += 1
                except Exception as exc:
                    errores.append(
                        f"{row.get('codigo_empresa')} {row.get('organismo_codigo')}: {exc}"
                    )
            self.after(
                0,
                lambda: self._cambio_activos_fin(
                    activo, guardados, validaciones_dev, errores,
                ),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _guardar_estado_buzon(self, row: dict, activo: bool) -> None:
        codigo = str(row.get("codigo_empresa") or "")
        provider = str(row.get("organismo_codigo") or "").upper()
        config = self._gestor.get_notif_config_global()
        empresa = self._gestor.get_empresa(codigo) or {}
        certs = self._gestor.listar_notif_certificados(codigo, solo_activos=True)
        cert = certs[0] if certs else None
        local = dict(row)
        local.pop("_virtual", None)
        local.update({
            "id": str(uuid.uuid4()) if row.get("_virtual") else str(row.get("id") or uuid.uuid4()),
            "codigo_empresa": codigo,
            "nombre": "DEHu" if provider == "DEHU" else "DGT / DEV",
            "organismo_id": row.get("organismo_id"),
            "tipo_buzon": provider,
            "nif_titular": (cert or {}).get("nif_titular") or empresa.get("cif"),
            "certificado_id": (cert or {}).get("id"),
            "activo": 1 if activo else 0,
            "periodicidad_sync": config.get("periodicidad_sync") or "MANUAL",
            "modo_descarga": "SOLO_DETECTAR",
            "envio_automatico_cliente": 0,
            "email_aviso": str(empresa.get("email") or "").strip() or None,
        })
        backend = BackendClientService()
        save = (
            backend.save_dehu_mailbox_config
            if provider == "DEHU" else backend.save_dev_mailbox_config
        )
        save(
            company_code=codigo,
            mailbox_id=local["id"],
            mailbox_name=local["nombre"],
            active=activo,
            periodicity=local["periodicidad_sync"],
            daily_sync_time=str(config.get("hora_sync_diaria") or ""),
            notification_email=str(config.get("email_resumen_interno") or ""),
        )
        self._gestor.upsert_notif_buzon(local)

    def _cambio_activos_fin(
        self, activo: bool, guardados: int, validaciones_dev: int, errores: list[str],
    ) -> None:
        self._set_busy(False)
        accion = "activados" if activo else "desactivados"
        detalle_dev = (
            f"\nValidaciones DEV en cola: {validaciones_dev}. "
            "Si un titular no esta de alta, la columna Conexion mostrara 'No alta'."
            if validaciones_dev else ""
        )
        messagebox.showinfo(
            "Configuracion masiva",
            f"Buzones {accion}: {guardados}."
            f"{detalle_dev}\nErrores: {len(errores)}"
            + (("\n\n" + "\n".join(errores[:8])) if errores else ""),
            parent=self.winfo_toplevel(),
        )
        self.refresh()

    # ----------------------------------------------------------------- sync (manual)
    def _on_sincronizar(self) -> None:
        buzon = self._row_seleccionada()
        if not buzon:
            return
        if not messagebox.askyesno(
            "Sincronizar buzon",
            f"El worker consultara '{buzon.get('nombre')}' utilizando exclusivamente "
            "el certificado cifrado de Azure.\n\n"
            "La copia privada nunca se descargara en este equipo. Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._set_busy(True)
        import threading

        def _worker():
            try:
                res = self._encolar_buzon(buzon)
                self.after(0, lambda: self._sync_fin(res, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._sync_fin(None, error))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_sincronizar_todos(self) -> None:
        activos = [b for b in self._cache if b.get("activo")]
        if not activos:
            messagebox.showinfo("Sincronizar", "No hay buzones activos que sincronizar.",
                                parent=self.winfo_toplevel())
            return
        if not messagebox.askyesno(
            "Sincronizar todos",
            f"Se enviaran al worker {len(activos)} buzon(es) activo(s). Cada operacion "
            "usara la copia cifrada de Azure.\n\nContinuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._set_busy(True)
        import threading

        def _worker():
            encoladas = 0
            errores = []
            buzones_encolados = set()
            for buzon in activos:
                codigo = buzon.get("codigo_empresa")
                provider = buzon.get("organismo_codigo")
                clave = (codigo, provider)
                if not codigo or clave in buzones_encolados:
                    continue
                buzones_encolados.add(clave)
                try:
                    self._encolar_buzon(buzon)
                    encoladas += 1
                except Exception as exc:
                    errores.append(f"{codigo}: {exc}")
            self.after(0, lambda: self._sync_todos_fin(encoladas, errores))

        threading.Thread(target=_worker, daemon=True).start()

    def _encolar_buzon(self, buzon):
        codigo = buzon.get("codigo_empresa") or ""
        provider = str(buzon.get("organismo_codigo") or "DEHU").upper()
        empresa = self._gestor.get_empresa(codigo) or {}
        return BackendClientService().create_certificate_request(
            company_code=codigo,
            certificate_type="DEV_SYNC" if provider == "DEV" else "DEHU_SYNC",
            parameters={
                "company_code": codigo,
                "tax_id": empresa.get("cif") or "",
                "mailbox_id": buzon.get("id") or "",
                "mailbox_name": buzon.get("nombre") or provider,
                "download_mode": "SOLO_DETECTAR",
            },
            idempotency_key=f"desktop-{provider.lower()}-{uuid.uuid4().hex}",
        )

    def _sync_fin(self, res, error=None) -> None:
        self._set_busy(False)
        if error is None:
            messagebox.showinfo(
                "Sincronizacion en cola",
                "La solicitud se ha enviado al worker. Se consultaran exclusivamente "
                "los metadatos; no se aceptara ni descargara ninguna notificacion.",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showerror(
                "No se pudo encolar",
                str(error),
                parent=self.winfo_toplevel(),
            )
        self.refresh()

    def _sync_todos_fin(self, encoladas, errores) -> None:
        self._set_busy(False)
        messagebox.showinfo(
            "Sincronizacion en cola",
            f"Clientes enviados al worker: {encoladas}\n"
            f"No encolados: {len(errores)}"
            + (("\n\n" + "\n".join(errores[:8])) if errores else ""),
            parent=self.winfo_toplevel(),
        )
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        st = "disabled" if busy else "normal"
        try:
            self._btn_sync_all.configure(state=st)
            self._btn_sync.configure(state=st if self._tv.selection() else "disabled")
            self._btn_activar.configure(state=st if self._tv.selection() else "disabled")
            self._btn_desactivar.configure(state=st if self._tv.selection() else "disabled")
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
        try:
            items = BackendClientService().list_certificate_requests(
                company_code=buzon["codigo_empresa"], limit=50,
            )
            provider = str(buzon.get("organismo_codigo") or "DEHU").upper()
            tipo = "DEV_SYNC" if provider == "DEV" else "DEHU_SYNC"
            items = [item for item in items if item.get("certificate_type") == tipo]
        except Exception as exc:
            messagebox.showerror("Notificaciones DEHu", str(exc), parent=self.winfo_toplevel())
            return
        resumen = "\n".join(
            f"- {(item.get('created_at') or '')[:16].replace('T', ' ')}: "
            f"{item.get('status')} - {item.get('result_summary') or item.get('error_message') or ''}"
            for item in items[:10]
        )
        messagebox.showinfo(
            f"Sincronizaciones {provider}",
            resumen or "Todavia no hay sincronizaciones centrales para este cliente.",
            parent=self.winfo_toplevel(),
        )

    # ----------------------------------------------------------------- refresh
    def refresh(self) -> None:
        existentes = self._gestor.listar_notif_buzones_global()
        empresas = self._gestor.listar_empresas_resumen()
        organismos = {
            str(row.get("codigo") or "").upper(): row
            for row in self._gestor.listar_notif_organismos(solo_activos=True)
        }
        por_clave = {
            (str(row.get("codigo_empresa") or ""), str(row.get("organismo_codigo") or "").upper()): row
            for row in existentes
        }
        cache = []
        for empresa in empresas:
            codigo = str(empresa.get("codigo") or "")
            for provider in ("DEHU", "DEV"):
                row = por_clave.get((codigo, provider))
                if row is None and provider in organismos:
                    org = organismos[provider]
                    row = {
                        "id": f"virtual:{codigo}:{provider}",
                        "_virtual": True,
                        "codigo_empresa": codigo,
                        "empresa_nombre": empresa.get("nombre") or codigo,
                        "empresa_cif": empresa.get("cif") or "",
                        "nombre": "DEHu" if provider == "DEHU" else "DGT / DEV",
                        "organismo_id": org.get("id"),
                        "organismo_codigo": provider,
                        "organismo_nombre": org.get("nombre") or provider,
                        "tipo_buzon": provider,
                        "activo": 0,
                    }
                if row is not None:
                    cache.append(row)
        self._cache = sorted(
            cache,
            key=lambda row: (
                str(row.get("empresa_nombre") or row.get("codigo_empresa") or "").upper(),
                str(row.get("organismo_codigo") or ""),
            ),
        )
        clientes = sorted({b.get("empresa_nombre") or b.get("codigo_empresa") or "" for b in self._cache} - {""})
        self._cb_cliente.configure(values=["Todos"] + clientes)
        if self._cb_cliente.get() not in (["Todos"] + clientes):
            self._cb_cliente.set("Todos")

        organismos = sorted({b.get("organismo_nombre") or b.get("organismo_codigo") or "" for b in self._cache} - {""})
        self._cb_org.configure(values=["Todos"] + organismos)
        if self._cb_org.get() not in (["Todos"] + organismos):
            self._cb_org.set("Todos")

        self._render()
        self._cargar_estados_dev()

    def _cargar_estados_dev(self) -> None:
        if self._cargando_dev_status:
            return
        self._cargando_dev_status = True
        import threading

        def _worker():
            try:
                rows = BackendClientService().list_dev_mailbox_configs()
                estados = {str(row.get("company_code") or ""): row for row in rows}
                self.after(0, lambda: self._estados_dev_fin(estados))
            except Exception:
                self.after(0, lambda: self._estados_dev_fin(None))

        threading.Thread(target=_worker, daemon=True).start()

    def _estados_dev_fin(self, estados: dict | None) -> None:
        self._cargando_dev_status = False
        if estados is not None:
            self._dev_status = estados
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
            modo = LABELS_MODO_DESCARGA["SOLO_DETECTAR"]
            ultima = (b.get("ultima_consulta") or "")[:16].replace("T", " ")
            provider = str(b.get("organismo_codigo") or "").upper()
            if provider == "DEV":
                estado_dev = str(
                    self._dev_status.get(str(b.get("codigo_empresa") or ""), {}).get(
                        "registration_status", "PENDIENTE",
                    )
                ).upper()
                conexion = {
                    "ACTIVO": "Conectado",
                    "NO_ALTA": "No alta DEV",
                    "PENDIENTE": "Por comprobar",
                }.get(estado_dev, estado_dev.title())
            else:
                conexion = "Configurado" if b.get("activo") else "-"
            self._tv.insert("", tk.END, values=(
                b["id"], cliente, org, b.get("nombre", ""), b.get("tipo_buzon", ""),
                b.get("certificado_nombre") or "", modo, ultima,
                "Si" if b.get("activo") else "No", conexion,
            ), tags=(tag,))
            rows_mostradas += 1

        self._lbl_count.configure(text=f"{rows_mostradas} buzon{'es' if rows_mostradas != 1 else ''}")
        self._lbl_status.configure(
            text=f"Total: {len(self._cache)}  |  Activos: {sum(1 for b in self._cache if b.get('activo'))}  |  "
                 f"Inactivos: {sum(1 for b in self._cache if not b.get('activo'))}  |  "
                 "La sincronizacion global encola DEHu y DEV por cada cliente activo"
        )
        self._btn_sync.configure(state="disabled")
        self._btn_ver_notif.configure(state="disabled")
        self._btn_activar.configure(state="disabled")
        self._btn_desactivar.configure(state="disabled")
