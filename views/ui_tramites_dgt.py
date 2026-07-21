from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.email_service import open_outlook_email
from services.tramites_dgt_service import TramitesDgtService


class UITramitesDgt(ttk.Frame):
    def __init__(self, parent, gestor, session=None, on_back=None):
        super().__init__(parent)
        self._service = TramitesDgtService(gestor, session=session)
        self._on_back = on_back
        self._expedientes = []
        self._current_id = None
        self._last_links = {}
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
            "observaciones": tk.StringVar(),
        }
        self._build()
        self.refresh()

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
            columns=("referencia", "estado", "matricula", "vendedor", "comprador"),
            show="headings",
            height=20,
        )
        for col, text, width in (
            ("referencia", "Referencia", 120),
            ("estado", "Estado", 95),
            ("matricula", "Matricula", 90),
            ("vendedor", "Vendedor", 160),
            ("comprador", "Comprador", 160),
        ):
            self.tv.heading(col, text=text)
            self.tv.column(col, width=width, anchor="w")
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())

        left_buttons = ttk.Frame(left)
        left_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(left_buttons, text="Nuevo", style="Primary.TButton", command=self._nuevo).pack(side=tk.LEFT)
        ttk.Button(left_buttons, text="Actualizar", command=self.refresh).pack(side=tk.LEFT, padx=6)

        form = ttk.LabelFrame(right, text="Expediente")
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
                ("Observaciones", "observaciones"),
            )
        ):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", padx=8, pady=3)
            ttk.Entry(form, textvariable=self._vars[key], width=48).grid(row=idx, column=1, sticky="ew", padx=8, pady=3)
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Guardar", style="Primary.TButton", command=self._guardar).pack(side=tk.LEFT)
        ttk.Button(actions, text="Datos vendedor", command=lambda: self._editar_parte("vendedor")).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Datos comprador", command=lambda: self._editar_parte("comprador")).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Adjuntar", command=self._adjuntar_documento).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Regenerar enlaces", command=self._regenerar_links).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Validar", command=self._validar).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Generar documentos", command=self._generar_documentos).pack(side=tk.LEFT, padx=5)

        links = ttk.LabelFrame(right, text="Enlaces seguros")
        links.pack(fill="x", pady=(0, 8))
        self.var_link_vendedor = tk.StringVar()
        self.var_link_comprador = tk.StringVar()
        self._link_row(links, "Vendedor", self.var_link_vendedor, self._email_vendedor, self._whatsapp_vendedor, 0)
        self._link_row(links, "Comprador", self.var_link_comprador, self._email_comprador, self._whatsapp_comprador, 1)

        attached = ttk.LabelFrame(right, text="Documentacion aportada")
        attached.pack(fill="both", expand=True, pady=(0, 8))
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

        docs = ttk.LabelFrame(right, text="Documentos generados")
        docs.pack(fill="both", expand=True)
        self.docs_tv = ttk.Treeview(docs, columns=("tipo", "ruta"), show="headings", height=7)
        self.docs_tv.heading("tipo", text="Tipo")
        self.docs_tv.heading("ruta", text="Ruta")
        self.docs_tv.column("tipo", width=180, anchor="w")
        self.docs_tv.column("ruta", width=420, anchor="w")
        self.docs_tv.pack(fill="both", expand=True)
        self.docs_tv.bind("<Double-1>", lambda _e: self._abrir_documento())

    def _link_row(self, parent, label, var, email_cmd, whatsapp_cmd, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, padx=8, pady=4, sticky="ew")
        ttk.Button(parent, text="Email", command=email_cmd).grid(row=row, column=2, padx=3)
        ttk.Button(parent, text="WhatsApp", command=whatsapp_cmd).grid(row=row, column=3, padx=3)
        parent.columnconfigure(1, weight=1)

    def refresh(self):
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
                    item.get("vehiculo_matricula", ""),
                    item.get("vendedor_nombre", ""),
                    item.get("comprador_nombre", ""),
                ),
            )
        children = self.tv.get_children()
        if children:
            self.tv.selection_set(children[0])
            self.tv.focus(children[0])
            self._load_selected()
        else:
            self._clear_form()

    def _nuevo(self):
        payload = self._payload()
        expediente_id = self._service.crear_expediente_minimo(payload)
        self._last_links = self._service.regenerar_links(expediente_id)
        self.refresh()
        self.tv.selection_set(expediente_id)
        self.tv.focus(expediente_id)
        self._load_selected()
        self.var_link_vendedor.set(self._last_links.get("vendedor", ""))
        self.var_link_comprador.set(self._last_links.get("comprador", ""))

    def _guardar(self):
        if not self._current_id:
            self._nuevo()
            return
        try:
            self._service.guardar_expediente(self._current_id, self._payload())
            self.refresh()
            self.tv.selection_set(self._current_id)
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

    def _regenerar_links(self):
        if not self._current_id:
            return
        try:
            self._last_links = self._service.regenerar_links(self._current_id)
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
        links = self._service.get_links(expediente)
        self.var_link_vendedor.set(links.get("vendedor", ""))
        self.var_link_comprador.set(links.get("comprador", ""))
        self._load_docs()
        self._load_adjuntos(expediente)

    def _load_docs(self):
        self.docs_tv.delete(*self.docs_tv.get_children())
        if not self._current_id:
            return
        for doc in self._service.listar_documentos(self._current_id):
            path = doc.get("ruta_pdf") or doc.get("ruta_docx") or doc.get("ruta_txt") or ""
            self.docs_tv.insert("", "end", iid=str(doc.get("id")), values=(doc.get("tipo_documento", ""), path))

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
        path = self.docs_tv.item(sel[0], "values")[1]
        if path:
            webbrowser.open(path)

    def _abrir_adjunto(self):
        sel = self.attach_tv.selection()
        if not sel or not self._current_id:
            return
        expediente = self._service.get_expediente(self._current_id) or {}
        selected_id = str(sel[0])
        for doc in expediente.get("documentos") or []:
            if str(doc.get("id")) == selected_id and doc.get("ruta"):
                webbrowser.open(doc["ruta"])
                return

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
        for var in self._vars.values():
            var.set("")
        self.var_link_vendedor.set("")
        self.var_link_comprador.set("")
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
        defaults = {
            "nombre": self.expediente.get(f"{self.rol}_nombre") or "",
            "email": self.expediente.get(f"{self.rol}_email") or "",
            "telefono": self.expediente.get(f"{self.rol}_telefono") or "",
            "nif": payload.get("nif") or "",
            "direccion": payload.get("direccion") or "",
            "cp": payload.get("cp") or "",
            "poblacion": payload.get("poblacion") or "",
            "provincia": payload.get("provincia") or "",
            "representante": payload.get("representante") or "",
            "observaciones": payload.get("observaciones") or "",
            "vehiculo_matricula": self.expediente.get("vehiculo_matricula") or "",
            "vehiculo_bastidor": self.expediente.get("vehiculo_bastidor") or "",
            "precio_venta": self.expediente.get("precio_venta") or "",
            "fecha_operacion": self.expediente.get("fecha_operacion") or "",
        }
        fields = [
            ("Nombre/Razon social", "nombre"),
            ("NIF/NIE/CIF", "nif"),
            ("Email", "email"),
            ("Telefono", "telefono"),
            ("Direccion", "direccion"),
            ("CP", "cp"),
            ("Poblacion", "poblacion"),
            ("Provincia", "provincia"),
            ("Representante", "representante"),
            ("Observaciones", "observaciones"),
        ]
        if self.rol == "vendedor":
            fields.extend(
                [
                    ("Matricula", "vehiculo_matricula"),
                    ("Bastidor", "vehiculo_bastidor"),
                    ("Precio venta", "precio_venta"),
                    ("Fecha operacion", "fecha_operacion"),
                ]
            )
        for row, (label, key) in enumerate(fields):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=str(defaults.get(key) or ""))
            self.vars[key] = var
            ttk.Entry(master, textvariable=var, width=46).grid(row=row, column=1, sticky="ew", padx=8, pady=3)
        master.columnconfigure(1, weight=1)
        return None

    def apply(self):
        self.result = {key: var.get() for key, var in self.vars.items()}
