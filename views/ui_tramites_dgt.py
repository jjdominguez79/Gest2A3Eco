from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.email_service import open_outlook_email
from services.dataprius_service import DatapriusClient
from services.signrequest_service import SignRequestClient
from services.tramites_dgt_repository import ApiDgtRepository
from services.tramites_dgt_service import TramitesDgtService
from utils.utilidades import load_app_config
from views.ui_tramites_dgt_public import UITramitesDgtPublicForm


class UITramitesDgt(ttk.Frame):
    def __init__(self, parent, gestor, session=None, on_back=None):
        super().__init__(parent)
        cfg = load_app_config()
        api_url = str(cfg.get("dgt_api_url") or "").strip()
        api_key = str(cfg.get("dgt_api_key") or "").strip()
        repository = ApiDgtRepository(api_url, api_key) if api_url and api_key else None
        firma_client = None
        almacenamiento_client = None
        if cfg.get("signrequest_token") and cfg.get("signrequest_from_email"):
            firma_client = SignRequestClient(
                cfg["signrequest_token"],
                cfg["signrequest_from_email"],
                cfg.get("signrequest_base_url") or "https://signrequest.com/api/v1",
            )
        if cfg.get("dataprius_api_key") and cfg.get("dataprius_api_secret"):
            almacenamiento_client = DatapriusClient(
                cfg["dataprius_api_key"],
                cfg["dataprius_api_secret"],
                cfg.get("dataprius_base_url") or "https://api.v2.dataprius.com",
            )
        self._signrequest_use_sms = bool(cfg.get("signrequest_use_sms", False))
        self._service = TramitesDgtService(
            gestor,
            session=session,
            repository=repository,
            firma_client=firma_client,
            almacenamiento_client=almacenamiento_client,
            almacenamiento_base_path=cfg.get("dataprius_base_path") or "",
        )
        self._online = repository is not None
        self._on_back = on_back
        self._expedientes = []
        self._current_id = None
        self._last_links = {}
        self._links_by_expediente = {}
        self.var_firma_estado = tk.StringVar(value="Firma: sin solicitud")
        self._vars = {
            "titulo": tk.StringVar(),
            "vendedor_nombre": tk.StringVar(),
            "vendedor_email": tk.StringVar(),
            "vendedor_telefono": tk.StringVar(),
            "comprador_nombre": tk.StringVar(),
            "comprador_email": tk.StringVar(),
            "comprador_telefono": tk.StringVar(),
            "vehiculo_matricula": tk.StringVar(),
            "vehiculo_bastidor": tk.StringVar(),
            "precio_venta": tk.StringVar(),
            "fecha_operacion": tk.StringVar(),
            "codigo_tasa": tk.StringVar(),
            "modelo_620_presentado": tk.BooleanVar(value=False),
            "observaciones": tk.StringVar(),
        }
        self._build()
        self.refresh()
        if self._online:
            self.after(60000, self._refresh_online)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(8, 6))
        ttk.Label(top, text="Tramites DGT", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        if self._on_back:
            ttk.Button(top, text="Volver", command=self._on_back).pack(side=tk.RIGHT)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=3)

        self.tv = ttk.Treeview(
            left,
            columns=("referencia", "estado", "vendedor_estado", "comprador_estado", "matricula", "vendedor", "comprador"),
            show="headings",
            height=20,
        )
        for col, text, width in (
            ("referencia", "Referencia", 105),
            ("estado", "Estado", 90),
            ("vendedor_estado", "Vend.", 80),
            ("comprador_estado", "Comp.", 80),
            ("matricula", "Matricula", 80),
            ("vendedor", "Vendedor", 130),
            ("comprador", "Comprador", 130),
        ):
            self.tv.heading(col, text=text)
            self.tv.column(col, width=width, anchor="w")
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())

        left_buttons = ttk.Frame(left)
        left_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(left_buttons, text="Nuevo expediente", style="Primary.TButton", command=self._nuevo).pack(side=tk.LEFT)
        ttk.Button(left_buttons, text="Actualizar", command=self.refresh).pack(side=tk.LEFT, padx=6)
        ttk.Button(left_buttons, text="Plantillas", command=self._gestionar_plantillas).pack(side=tk.LEFT)
        ttk.Button(left_buttons, text="Eliminar", command=self._eliminar_expediente).pack(side=tk.RIGHT)

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        detail_tab = ttk.Frame(notebook, padding=8)
        documents_tab = ttk.Frame(notebook, padding=8)
        notebook.add(detail_tab, text="Expediente y acciones")
        notebook.add(documents_tab, text="Documentos")

        form = ttk.LabelFrame(detail_tab, text="Datos del expediente", padding=(4, 3))
        form.pack(fill="x")
        for idx, (label, key) in enumerate(
            (
                ("Titulo", "titulo"),
                ("Vendedor", "vendedor_nombre"),
                ("Email vendedor", "vendedor_email"),
                ("Telefono vendedor", "vendedor_telefono"),
                ("Comprador", "comprador_nombre"),
                ("Email comprador", "comprador_email"),
                ("Telefono comprador", "comprador_telefono"),
                ("Matricula", "vehiculo_matricula"),
                ("Bastidor", "vehiculo_bastidor"),
                ("Precio venta", "precio_venta"),
                ("Fecha operacion", "fecha_operacion"),
                ("Codigo de tasa pagada", "codigo_tasa"),
                ("Observaciones", "observaciones"),
            )
        ):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", padx=8, pady=3)
            entry = ttk.Entry(form, textvariable=self._vars[key], width=48)
            entry.grid(row=idx, column=1, sticky="ew", padx=8, pady=3)
            if key == "titulo":
                self._title_entry = entry
        ttk.Checkbutton(
            form,
            text="Modelo 620 presentado",
            variable=self._vars["modelo_620_presentado"],
        ).grid(row=13, column=1, sticky="w", padx=8, pady=3)
        form.columnconfigure(1, weight=1)

        actions = ttk.LabelFrame(detail_tab, text="Acciones", padding=5)
        actions.pack(fill="x", pady=8)
        primary_actions = ttk.Frame(actions)
        primary_actions.pack(fill="x")
        secondary_actions = ttk.Frame(actions)
        secondary_actions.pack(fill="x", pady=(5, 0))
        subsanation_actions = ttk.Frame(actions)
        subsanation_actions.pack(fill="x", pady=(5, 0))
        for parent, text, command, primary in (
            (primary_actions, "Guardar", self._guardar, True),
            (primary_actions, "Validar", self._validar, False),
            (primary_actions, "Generar documentos", self._generar_documentos, False),
            (primary_actions, "Enviar a firma", self._enviar_a_firma, False),
            (secondary_actions, "Actualizar firma", self._actualizar_firma, False),
            (secondary_actions, "Datos vendedor", lambda: self._editar_parte("vendedor"), False),
            (secondary_actions, "Datos comprador", lambda: self._editar_parte("comprador"), False),
            (secondary_actions, "Adjuntar documento", self._adjuntar_documento, False),
            (secondary_actions, "Subir modelo 620", self._subir_modelo_620, False),
            (secondary_actions, "Regenerar enlaces", self._regenerar_links, False),
        ):
            options = {"style": "Primary.TButton"} if primary else {}
            ttk.Button(parent, text=text, command=command, **options).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(secondary_actions, textvariable=self.var_firma_estado).pack(
            side=tk.RIGHT, padx=(8, 2)
        )
        ttk.Label(subsanation_actions, text="Pedir correccion al cliente:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            subsanation_actions,
            text="Vendedor",
            command=lambda: self._solicitar_subsanacion("vendedor"),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            subsanation_actions,
            text="Comprador",
            command=lambda: self._solicitar_subsanacion("comprador"),
        ).pack(side=tk.LEFT)

        links = ttk.LabelFrame(detail_tab, text="Enlaces seguros")
        links.pack(fill="x", pady=(0, 8))
        self.var_link_vendedor = tk.StringVar()
        self.var_link_comprador = tk.StringVar()
        self._link_row(links, "Vendedor", self.var_link_vendedor, self._email_vendedor, self._whatsapp_vendedor, self._form_vendedor, lambda: self._copy_link("vendedor"), lambda: self._revoke_link("vendedor"), 0)
        self._link_row(links, "Comprador", self.var_link_comprador, self._email_comprador, self._whatsapp_comprador, self._form_comprador, lambda: self._copy_link("comprador"), lambda: self._revoke_link("comprador"), 1)

        attached = ttk.LabelFrame(documents_tab, text="Documentacion aportada")
        attached.pack(fill="both", expand=True, pady=(0, 8))
        attached_actions = ttk.Frame(attached)
        attached_actions.pack(fill="x", padx=6, pady=(4, 2))
        ttk.Button(
            attached_actions, text="Eliminar documento seleccionado", command=self._eliminar_adjunto
        ).pack(side=tk.RIGHT)
        self.attach_tv = ttk.Treeview(attached, columns=("rol", "tipo", "archivo", "hash"), show="headings", height=5)
        for col, text, width in (
            ("rol", "Rol", 90),
            ("tipo", "Tipo", 140),
            ("archivo", "Archivo", 280),
            ("hash", "SHA256", 190),
        ):
            self.attach_tv.heading(col, text=text)
            self.attach_tv.column(col, width=width, anchor="w")
        self.attach_tv.pack(fill="both", expand=True)
        self.attach_tv.bind("<Double-1>", lambda _e: self._abrir_adjunto())

        docs = ttk.LabelFrame(documents_tab, text="Documentos generados")
        docs.pack(fill="both", expand=True)
        docs_actions = ttk.Frame(docs)
        docs_actions.pack(fill="x", padx=6, pady=(4, 2))
        ttk.Button(
            docs_actions, text="Eliminar documento seleccionado", command=self._eliminar_documento_generado
        ).pack(side=tk.RIGHT)
        self.docs_tv = ttk.Treeview(
            docs, columns=("tipo", "fecha_generacion", "ruta"), show="headings", height=7
        )
        self.docs_tv.heading("tipo", text="Tipo")
        self.docs_tv.heading("fecha_generacion", text="Fecha de generacion")
        self.docs_tv.heading("ruta", text="Ruta")
        self.docs_tv.column("tipo", width=180, anchor="w")
        self.docs_tv.column("fecha_generacion", width=145, anchor="center")
        self.docs_tv.column("ruta", width=360, anchor="w")
        self.docs_tv.pack(fill="both", expand=True)
        self.docs_tv.bind("<Double-1>", lambda _e: self._abrir_documento())

    def _link_row(self, parent, label, var, email_cmd, whatsapp_cmd, form_cmd, copy_cmd, revoke_cmd, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, padx=8, pady=4, sticky="ew")
        ttk.Button(parent, text="Email", command=email_cmd).grid(row=row, column=2, padx=3)
        ttk.Button(parent, text="WhatsApp", command=whatsapp_cmd).grid(row=row, column=3, padx=3)
        ttk.Button(parent, text="Formulario", command=form_cmd).grid(row=row, column=4, padx=3)
        ttk.Button(parent, text="Copiar", command=copy_cmd).grid(row=row, column=5, padx=3)
        ttk.Button(parent, text="Revocar", command=revoke_cmd).grid(row=row, column=6, padx=3)
        parent.columnconfigure(1, weight=1)

    def refresh(self, select_id: str | None = None):
        previous_id = select_id or self._current_id
        self._expedientes = self._service.listar_expedientes()
        self.tv.delete(*self.tv.get_children())
        for item in self._expedientes:
            iid = item.get("id")
            self.tv.insert(
                "",
                "end",
                iid=iid,
                values=(
                    item.get("referencia", ""),
                    item.get("estado", ""),
                    item.get("vendedor_estado", ""),
                    item.get("comprador_estado", ""),
                    item.get("vehiculo_matricula", ""),
                    item.get("vendedor_nombre", ""),
                    item.get("comprador_nombre", ""),
                ),
            )
        children = list(self.tv.get_children())
        target_id = previous_id if previous_id in children else (children[0] if children else None)
        if target_id:
            self.tv.selection_set(target_id)
            self.tv.focus(target_id)
            self.tv.see(target_id)
            self._load_selected()
        else:
            self._clear_form()

    def _refresh_online(self):
        if not self.winfo_exists():
            return
        try:
            self.refresh()
        finally:
            self.after(60000, self._refresh_online)

    def _nuevo(self):
        self._clear_form()
        self._vars["titulo"].set(
            f"Cambio de titularidad DGT - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        try:
            expediente_id = self._service.crear_expediente_minimo(self._payload())
            self._last_links = self._service.regenerar_links(expediente_id)
            self._links_by_expediente[expediente_id] = dict(self._last_links)
            self.refresh(select_id=expediente_id)
            self.var_link_vendedor.set(self._last_links.get("vendedor", ""))
            self.var_link_comprador.set(self._last_links.get("comprador", ""))
            self._title_entry.focus_set()
        except Exception as exc:
            self._clear_form()
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _guardar(self):
        if not self._current_id:
            if not self._vars["titulo"].get().strip():
                messagebox.showwarning(
                    "Tramites DGT",
                    "Indica un titulo para crear el expediente.",
                    parent=self.winfo_toplevel(),
                )
                self._title_entry.focus_set()
                return
            try:
                expediente_id = self._service.crear_expediente_minimo(self._payload())
                self._last_links = self._service.regenerar_links(expediente_id)
                self._links_by_expediente[expediente_id] = dict(self._last_links)
                self.refresh(select_id=expediente_id)
                self.var_link_vendedor.set(self._last_links.get("vendedor", ""))
                self.var_link_comprador.set(self._last_links.get("comprador", ""))
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        try:
            self._service.guardar_expediente(self._current_id, self._payload())
            self.refresh(select_id=self._current_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _validar(self):
        if not self._current_id:
            return
        try:
            self._guardar()
            self._service.validar_expediente(self._current_id)
            messagebox.showinfo("Gest2A3Eco", "Expediente validado.", parent=self.winfo_toplevel())
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _generar_documentos(self):
        if not self._current_id:
            return
        try:
            docs = self._service.generar_documentos(self._current_id)
            messagebox.showinfo("Gest2A3Eco", f"Documentos generados: {len(docs)}", parent=self.winfo_toplevel())
            self._load_docs()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _preparar_firma(self):
        if not self._current_id:
            return
        provider = simpledialog.askstring(
            "Tramites DGT",
            "Proveedor de firma (opcional):",
            parent=self.winfo_toplevel(),
        ) or ""
        try:
            paquete = self._service.preparar_paquete_firma(self._current_id, provider=provider)
            messagebox.showinfo(
                "Gest2A3Eco",
                f"Paquete de firma preparado con {len(paquete['documentos'])} documento(s).",
                parent=self.winfo_toplevel(),
            )
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _gestionar_plantillas(self):
        PlantillasDgtDialog(self.winfo_toplevel(), self._service)

    def _regenerar_links(self):
        if not self._current_id:
            return
        try:
            self._last_links = self._service.regenerar_links(self._current_id)
            self._links_by_expediente[self._current_id] = dict(self._last_links)
            self.var_link_vendedor.set(self._last_links.get("vendedor", ""))
            self.var_link_comprador.set(self._last_links.get("comprador", ""))
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _load_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        self._current_id = str(sel[0])
        expediente = self._service.get_expediente(self._current_id) or {}
        for key, var in self._vars.items():
            var.set("" if expediente.get(key) is None else str(expediente.get(key)))
        links = (
            self._links_by_expediente.get(self._current_id, {})
            if self._online
            else self._service.get_links(expediente)
        )
        self.var_link_vendedor.set(links.get("vendedor", ""))
        self.var_link_comprador.set(links.get("comprador", ""))
        estado_firma = str(expediente.get("firma_estado") or "sin solicitud").replace("_", " ")
        self.var_firma_estado.set(f"Firma: {estado_firma}")
        self._load_docs()
        self._load_adjuntos(expediente)

    def _load_docs(self):
        self.docs_tv.delete(*self.docs_tv.get_children())
        if not self._current_id:
            return
        for doc in self._service.listar_documentos(self._current_id):
            path = doc.get("ruta_pdf") or doc.get("ruta_docx") or doc.get("ruta_txt") or ""
            fecha = doc.get("fecha_generacion") or doc.get("created_at") or ""
            if not fecha and path:
                try:
                    fecha = datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat()
                except OSError:
                    pass
            self.docs_tv.insert(
                "",
                "end",
                iid=str(doc.get("id")),
                values=(doc.get("tipo_documento", ""), self._formatear_fecha(fecha), path),
            )

    def _load_adjuntos(self, expediente: dict | None = None):
        self.attach_tv.delete(*self.attach_tv.get_children())
        if expediente is None and self._current_id:
            expediente = self._service.get_expediente(self._current_id)
        for doc in (expediente or {}).get("documentos") or []:
            self.attach_tv.insert(
                "",
                "end",
                iid=str(doc.get("id") or doc.get("ruta") or ""),
                values=(
                    doc.get("rol", ""),
                    doc.get("tipo", ""),
                    doc.get("nombre_archivo") or doc.get("ruta") or "",
                    str(doc.get("sha256") or "")[:16],
                ),
            )

    def _abrir_documento(self):
        sel = self.docs_tv.selection()
        if not sel:
            return
        path = self.docs_tv.item(sel[0], "values")[2]
        if path:
            webbrowser.open(path)

    @staticmethod
    def _formatear_fecha(value) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            fecha = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return fecha.astimezone().strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return raw

    def _abrir_adjunto(self):
        sel = self.attach_tv.selection()
        if not sel or not self._current_id:
            return
        expediente = self._service.get_expediente(self._current_id) or {}
        selected_id = str(sel[0])
        for doc in expediente.get("documentos") or []:
            if str(doc.get("id")) != selected_id:
                continue
            if doc.get("ruta"):
                webbrowser.open(doc["ruta"])
                return
            target = filedialog.asksaveasfilename(
                title="Guardar documento DGT",
                initialfile=doc.get("nombre_archivo") or "documento",
            )
            if target:
                try:
                    self._service.descargar_documento_aportado(selected_id, target)
                    webbrowser.open(target)
                except Exception as exc:
                    messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return

    def _eliminar_expediente(self):
        if not self._current_id:
            return
        expediente = self._service.get_expediente(self._current_id) or {}
        referencia = expediente.get("referencia") or self._current_id
        if not messagebox.askyesno(
            "Eliminar expediente DGT",
            f"Se eliminara definitivamente el expediente {referencia}, sus documentos y enlaces.\n\n"
            "Esta accion no se puede deshacer. ¿Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._service.eliminar_expediente(self._current_id)
            self._current_id = None
            self._clear_form()
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _enviar_a_firma(self):
        if not self._current_id:
            return
        if not messagebox.askyesno(
            "Enviar a SignRequest",
            "Se enviaran las ultimas versiones al vendedor y/o comprador. ¿Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            resultado = self._service.enviar_a_firma(
                self._current_id, usar_sms=self._signrequest_use_sms
            )
            messagebox.showinfo(
                "Gest2A3Eco",
                f"Solicitudes enviadas: {len(resultado['solicitudes'])}.",
                parent=self.winfo_toplevel(),
            )
            self.refresh(select_id=self._current_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _actualizar_firma(self):
        if not self._current_id:
            return
        try:
            resultado = self._service.actualizar_estado_firma(self._current_id)
            messagebox.showinfo(
                "Gest2A3Eco",
                f"Estado de firma: {resultado['estado']}.",
                parent=self.winfo_toplevel(),
            )
            self.refresh(select_id=self._current_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _solicitar_subsanacion(self, rol: str):
        if not self._current_id:
            return
        mensaje = simpledialog.askstring(
            "Solicitar subsanacion",
            f"Indica al {rol} que debe corregir o completar:",
            parent=self.winfo_toplevel(),
        )
        if not mensaje:
            return
        try:
            result = self._service.solicitar_subsanacion(self._current_id, rol, mensaje)
            link = result.get("url") or ""
            cached_links = dict(self._links_by_expediente.get(self._current_id, {}))
            cached_links[rol] = link
            self._links_by_expediente[self._current_id] = cached_links
            self.refresh(select_id=self._current_id)
            if rol == "vendedor":
                self.var_link_vendedor.set(link)
            else:
                self.var_link_comprador.set(link)
            if link:
                self.clipboard_clear()
                self.clipboard_append(link)
            messagebox.showinfo(
                "Gest2A3Eco",
                f"Subsanacion solicitada al {rol}.\n\n"
                "Se ha generado un enlace nuevo solo para esa parte"
                + (" y se ha copiado al portapapeles." if link else "."),
                parent=self.winfo_toplevel(),
            )
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _eliminar_adjunto(self):
        sel = self.attach_tv.selection()
        if not sel or not self._current_id:
            return
        nombre = self.attach_tv.item(sel[0], "values")[2]
        if not messagebox.askyesno(
            "Eliminar fichero aportado",
            f"Se eliminara definitivamente el fichero {nombre}. ¿Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._service.eliminar_documento_aportado(self._current_id, str(sel[0]))
            self._load_adjuntos(self._service.get_expediente(self._current_id))
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _eliminar_documento_generado(self):
        sel = self.docs_tv.selection()
        if not sel:
            return
        tipo = self.docs_tv.item(sel[0], "values")[0]
        if not messagebox.askyesno(
            "Eliminar documento generado",
            f"Se eliminara definitivamente el documento {tipo} y sus ficheros. ¿Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._service.eliminar_documento_generado(str(sel[0]))
            self._load_docs()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _editar_parte(self, rol: str):
        if not self._current_id:
            return
        expediente = self._service.get_expediente(self._current_id) or {}
        dlg = DatosParteDialog(self.winfo_toplevel(), rol, expediente)
        if not dlg.result:
            return
        try:
            self._service.guardar_datos_parte(self._current_id, rol, dlg.result)
            self.refresh()
            self.tv.selection_set(self._current_id)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _adjuntar_documento(self):
        if not self._current_id:
            return
        rol = simpledialog.askstring("Tramites DGT", "Rol del documento (vendedor/comprador):", parent=self.winfo_toplevel())
        if not rol:
            return
        tipo = simpledialog.askstring("Tramites DGT", "Tipo de documento:", parent=self.winfo_toplevel()) or "documentacion"
        path = filedialog.askopenfilename(
            title="Seleccionar documento DGT",
            filetypes=(("Documentos", "*.pdf *.jpg *.jpeg *.png *.doc *.docx"), ("Todos", "*.*")),
        )
        if not path:
            return
        try:
            self._service.adjuntar_documento(self._current_id, rol, path, tipo=tipo)
            expediente = self._service.get_expediente(self._current_id)
            self._load_adjuntos(expediente)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _email_vendedor(self):
        self._email("vendedor")

    def _email_comprador(self):
        self._email("comprador")

    def _whatsapp_vendedor(self):
        self._whatsapp("vendedor")

    def _whatsapp_comprador(self):
        self._whatsapp("comprador")

    def _form_vendedor(self):
        self._abrir_formulario_link(self.var_link_vendedor.get())

    def _form_comprador(self):
        self._abrir_formulario_link(self.var_link_comprador.get())

    def _abrir_formulario_link(self, link: str):
        try:
            if link.lower().startswith(("https://", "http://")):
                webbrowser.open(link)
                return
            parsed = self._service.parse_link_seguro(link)
            UITramitesDgtPublicForm(
                self.winfo_toplevel(),
                self._service,
                referencia=parsed["referencia"],
                rol=parsed["rol"],
                token=parsed["token"],
            )
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _subir_modelo_620(self):
        if not self._current_id:
            return
        path = filedialog.askopenfilename(
            title="Seleccionar modelo 620 presentado",
            filetypes=(("PDF o imagen", "*.pdf *.jpg *.jpeg *.png"), ("Todos", "*.*")),
        )
        if not path:
            return
        try:
            self._service.adjuntar_documento(
                self._current_id, "gestor", path, tipo="modelo_620", descripcion="Modelo 620 presentado"
            )
            self._vars["modelo_620_presentado"].set(True)
            self._service.guardar_expediente(self._current_id, self._payload())
            self._load_adjuntos(self._service.get_expediente(self._current_id))
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _copy_link(self, rol: str):
        link = self.var_link_vendedor.get() if rol == "vendedor" else self.var_link_comprador.get()
        if not link or "token=" not in link:
            messagebox.showwarning("Gest2A3Eco", "Regenera el enlace antes de copiarlo.", parent=self.winfo_toplevel())
            return
        self.clipboard_clear()
        self.clipboard_append(link)
        self.update()

    def _revoke_link(self, rol: str):
        if not self._current_id:
            return
        try:
            self._service.revocar_link(self._current_id, rol)
            self._links_by_expediente.get(self._current_id, {}).pop(rol, None)
            if rol == "vendedor":
                self.var_link_vendedor.set("Enlace revocado")
            else:
                self.var_link_comprador.set("Enlace revocado")
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _email(self, rol: str):
        link = self.var_link_vendedor.get() if rol == "vendedor" else self.var_link_comprador.get()
        email = self._vars[f"{rol}_email"].get()
        try:
            open_outlook_email(
                to=email,
                subject="Tramite DGT Gestinem",
                body=f"Hola,\n\nPuedes completar tus datos del expediente DGT en este enlace:\n{link}",
            )
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _whatsapp(self, rol: str):
        link = self.var_link_vendedor.get() if rol == "vendedor" else self.var_link_comprador.get()
        tel = self._vars[f"{rol}_telefono"].get()
        try:
            self._service.abrir_whatsapp(tel, f"Puedes completar tus datos del tramite DGT aqui: {link}")
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _payload(self) -> dict:
        return {key: var.get() for key, var in self._vars.items()}

    def _clear_form(self):
        self._current_id = None
        for key, var in self._vars.items():
            var.set(False if key == "modelo_620_presentado" else "")
        self.var_link_vendedor.set("")
        self.var_link_comprador.set("")
        self.var_firma_estado.set("Firma: sin solicitud")
        self.docs_tv.delete(*self.docs_tv.get_children())
        self.attach_tv.delete(*self.attach_tv.get_children())


class DatosParteDialog(simpledialog.Dialog):
    def __init__(self, parent, rol: str, expediente: dict):
        self.rol = rol
        self.expediente = expediente
        self.vars = {}
        self.result = None
        super().__init__(parent, f"Datos {rol}")

    def body(self, master):
        payload = dict(self.expediente.get(f"{self.rol}_payload") or {})
        defaults = dict(payload)
        for key in ("nombre", "email", "telefono"):
            defaults[key] = self.expediente.get(f"{self.rol}_{key}") or payload.get(key) or ""
        defaults["vehiculo_matricula"] = (
            payload.get("vehiculo_matricula") or self.expediente.get("vehiculo_matricula") or ""
        )
        defaults["vehiculo_bastidor"] = (
            payload.get("vehiculo_bastidor") or self.expediente.get("vehiculo_bastidor") or ""
        )
        defaults["precio_venta"] = payload.get("precio_venta") or self.expediente.get("precio_venta") or ""
        defaults["fecha_operacion"] = (
            payload.get("fecha_operacion") or self.expediente.get("fecha_operacion") or ""
        )
        aliases = {
            "primera_matriculacion": "vehiculo_primera_matriculacion",
            "kilometraje": "vehiculo_kilometros",
            "llaves_vehiculo": "numero_llaves",
            "direccion_envio": "envio_direccion",
            "cp_envio": "envio_cp",
            "poblacion_envio": "envio_poblacion",
            "provincia_envio": "envio_provincia",
        }
        for key, legacy in aliases.items():
            defaults[key] = payload.get(key) or payload.get(legacy) or ""

        self.geometry("760x690")
        notebook = ttk.Notebook(master)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)
        persona_tab = ttk.Frame(notebook, padding=8)
        detalle_tab = ttk.Frame(notebook, padding=8)
        notebook.add(persona_tab, text="Identificacion y contacto")
        notebook.add(
            detalle_tab,
            text="Vehiculo y operacion" if self.rol == "vendedor" else "Direccion de envio",
        )

        common_fields = (
            ("Tipo de persona", "tipo_persona"),
            ("Nombre o razon social", "nombre"),
            ("NIF, NIE o CIF", "nif"),
            ("Email", "email"),
            ("Telefono", "telefono"),
            ("Direccion", "direccion"),
            ("Codigo postal", "cp"),
            ("Poblacion", "poblacion"),
            ("Provincia", "provincia"),
            ("Representante (persona juridica)", "representante_nombre"),
            ("DNI/NIE representante", "representante_nif"),
            ("Observaciones", "observaciones"),
        )
        self._build_fields(persona_tab, common_fields, defaults)

        if self.rol == "vendedor":
            detail_fields = (
                ("Matricula", "vehiculo_matricula"),
                ("Bastidor", "vehiculo_bastidor"),
                ("Marca", "vehiculo_marca"),
                ("Modelo y version", "vehiculo_modelo"),
                ("Primera matriculacion (AAAA-MM-DD)", "primera_matriculacion"),
                ("Kilometraje", "kilometraje"),
                ("Precio de venta", "precio_venta"),
                ("Fecha de entrega (AAAA-MM-DD)", "fecha_operacion"),
                ("Hora de entrega", "hora_entrega"),
                ("Forma de pago", "forma_pago"),
                ("Numero de llaves", "llaves_vehiculo"),
            )
            self._build_fields(detalle_tab, detail_fields, defaults)
        else:
            ttk.Button(
                detalle_tab,
                text="Copiar domicilio principal",
                command=self._copiar_direccion_envio,
            ).grid(row=0, column=1, sticky="e", padx=8, pady=(0, 8))
            detail_fields = (
                ("Direccion de envio", "direccion_envio"),
                ("Codigo postal de envio", "cp_envio"),
                ("Poblacion de envio", "poblacion_envio"),
                ("Provincia de envio", "provincia_envio"),
            )
            self._build_fields(detalle_tab, detail_fields, defaults, start_row=1)
        return None

    def _build_fields(self, parent, fields, defaults, start_row=0):
        for offset, (label, key) in enumerate(fields):
            row = start_row + offset
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
            var = tk.StringVar(value=str(defaults.get(key) or ("fisica" if key == "tipo_persona" else "")))
            self.vars[key] = var
            if key == "tipo_persona":
                widget = ttk.Combobox(
                    parent,
                    textvariable=var,
                    values=("fisica", "juridica"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(parent, textvariable=var)
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        parent.columnconfigure(1, weight=1)

    def _copiar_direccion_envio(self):
        for source, target in (
            ("direccion", "direccion_envio"),
            ("cp", "cp_envio"),
            ("poblacion", "poblacion_envio"),
            ("provincia", "provincia_envio"),
        ):
            self.vars[target].set(self.vars[source].get())

    def apply(self):
        self.result = {key: var.get() for key, var in self.vars.items()}


class PlantillasDgtDialog(tk.Toplevel):
    def __init__(self, parent, service: TramitesDgtService):
        super().__init__(parent)
        self._service = service
        self.title("Plantillas DGT")
        self.transient(parent)
        self.grab_set()
        self.geometry("760x320")
        self._build()
        self.refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Button(top, text="Crear faltantes", style="Primary.TButton", command=self._crear_faltantes).pack(side=tk.LEFT)
        ttk.Button(top, text="Abrir carpeta", command=self._abrir_carpeta).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Actualizar", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(top, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

        self.tv = ttk.Treeview(
            self,
            columns=("titulo", "archivo", "estado", "ruta"),
            show="headings",
            height=8,
        )
        for col, text, width in (
            ("titulo", "Plantilla", 190),
            ("archivo", "Archivo", 210),
            ("estado", "Estado", 90),
            ("ruta", "Ruta editable", 250),
        ):
            self.tv.heading(col, text=text)
            self.tv.column(col, width=width, anchor="w")
        self.tv.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.tv.bind("<Double-1>", lambda _e: self._abrir_seleccionada())

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="Abrir plantilla", command=self._abrir_seleccionada).pack(side=tk.LEFT)

    def refresh(self):
        self.tv.delete(*self.tv.get_children())
        for item in self._service.listar_plantillas_editables():
            self.tv.insert(
                "",
                "end",
                iid=item["tipo_documento"],
                values=(
                    item["titulo"],
                    item["filename"],
                    "Existe" if item["exists"] else "Falta",
                    item["path"],
                ),
            )

    def _crear_faltantes(self):
        try:
            created = self._service.ensure_plantillas_editables(overwrite=False)
            messagebox.showinfo(
                "Gest2A3Eco",
                f"Plantillas creadas o verificadas: {len(created)}",
                parent=self,
            )
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)

    def _abrir_carpeta(self):
        try:
            self._service.abrir_carpeta_plantillas()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)

    def _abrir_seleccionada(self):
        sel = self.tv.selection()
        if not sel:
            return
        try:
            self._service.abrir_plantilla(str(sel[0]))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
