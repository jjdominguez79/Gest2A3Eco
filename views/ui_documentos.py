import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from controllers.ui_documentos_controller import DocumentosController


class IntervinienteDialog(tk.Toplevel):
    def __init__(self, parent, data=None):
        super().__init__(parent)
        self.title("Interviniente")
        self.resizable(False, False)
        self.result = None
        base = dict(data or {})
        self.vars = {
            "tipo_persona": tk.StringVar(value=str(base.get("tipo_persona") or "fisica")),
            "nombre_razon_social": tk.StringVar(value=str(base.get("nombre_razon_social") or "")),
            "nif": tk.StringVar(value=str(base.get("nif") or "")),
            "domicilio": tk.StringVar(value=str(base.get("domicilio") or "")),
            "municipio": tk.StringVar(value=str(base.get("municipio") or "")),
            "provincia": tk.StringVar(value=str(base.get("provincia") or "")),
            "cp": tk.StringVar(value=str(base.get("cp") or "")),
            "telefono": tk.StringVar(value=str(base.get("telefono") or "")),
            "email": tk.StringVar(value=str(base.get("email") or "")),
            "representante": tk.StringVar(value=str(base.get("representante") or "")),
            "cargo": tk.StringVar(value=str(base.get("cargo") or "")),
            "rol_en_documento": tk.StringVar(value=str(base.get("rol_en_documento") or "interviniente")),
            "observaciones": tk.StringVar(value=str(base.get("observaciones") or "")),
        }
        self.var_habitual = tk.BooleanVar(value=bool(base.get("es_cliente_habitual")))
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        fields = [
            ("Tipo persona", "tipo_persona"),
            ("Nombre / razon social", "nombre_razon_social"),
            ("NIF", "nif"),
            ("Domicilio", "domicilio"),
            ("Municipio", "municipio"),
            ("Provincia", "provincia"),
            ("CP", "cp"),
            ("Telefono", "telefono"),
            ("Email", "email"),
            ("Representante", "representante"),
            ("Cargo", "cargo"),
            ("Rol en documento", "rol_en_documento"),
            ("Observaciones", "observaciones"),
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(frm, textvariable=self.vars[key], width=42).grid(row=idx, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(frm, text="Guardar como interviniente habitual", variable=self.var_habitual).grid(
            row=len(fields), column=1, sticky="w", pady=(6, 0)
        )
        btns = ttk.Frame(frm)
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)
        frm.columnconfigure(1, weight=1)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _ok(self):
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.result["es_cliente_habitual"] = bool(self.var_habitual.get())
        self.destroy()


class UIDocumentos(ttk.Frame):
    def __init__(self, parent, gestor, codigo_empresa, ejercicio, nombre_empresa, session=None, global_mode: bool = False):
        super().__init__(parent)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.session = session
        self.global_mode = bool(global_mode)
        self.controller = DocumentosController(gestor, codigo_empresa, ejercicio, self, global_mode=self.global_mode)
        self._build()
        self.controller.refresh()
        self.var_template_filter.trace_add("write", lambda *_: self.controller.apply_template_filter())
        self.var_cliente_filter.trace_add("write", lambda *_: self.controller.apply_cliente_filter())
        self.var_doc_filter.trace_add("write", lambda *_: self.controller.apply_document_filter())

    def _build(self):
        title = "Documentos globales" if self.global_mode else f"Documentos - {self.nombre} ({self.codigo})"
        ttk.Label(self, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        self.main_nb = ttk.Notebook(self)
        self.main_nb.pack(fill="both", expand=True, padx=8, pady=6)
        self.tab_templates = ttk.Frame(self.main_nb)
        self.tab_wizard = ttk.Frame(self.main_nb)
        self.tab_history = ttk.Frame(self.main_nb)
        self.tab_intervinientes = ttk.Frame(self.main_nb)
        self.main_nb.add(self.tab_templates, text="Plantillas")
        self.main_nb.add(self.tab_wizard, text="Asistente")
        self.main_nb.add(self.tab_history, text="Historico")
        self.main_nb.add(self.tab_intervinientes, text="Intervinientes")

        self._build_templates_tab()
        self._build_wizard_tab()
        self._build_history_tab()
        self._build_intervinientes_tab()

    def _build_templates_tab(self):
        top = ttk.Frame(self.tab_templates)
        top.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(top, text="Buscar").pack(side=tk.LEFT)
        self.var_template_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_template_filter, width=32).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Importar DOCX", style="Primary.TButton", command=self.controller.import_template).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Renombrar", command=self.controller.rename_template).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Abrir DOCX", command=self.controller.open_template_docx).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Releer variables", command=self.controller.refresh_template_variables).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Eliminar", command=self.controller.delete_template).pack(side=tk.LEFT)

        self.tv_templates = ttk.Treeview(
            self.tab_templates,
            columns=("nombre", "tipo", "ruta", "variables"),
            show="headings",
            height=14,
        )
        for col, title, width in (
            ("nombre", "Nombre", 220),
            ("tipo", "Tipo", 180),
            ("ruta", "Archivo", 380),
            ("variables", "Variables", 380),
        ):
            self.tv_templates.heading(col, text=title)
            self.tv_templates.column(col, width=width, anchor="w")
        self.tv_templates.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_wizard_tab(self):
        self.wizard_nb = ttk.Notebook(self.tab_wizard)
        self.wizard_nb.pack(fill="both", expand=True, padx=10, pady=10)
        tab1 = ttk.Frame(self.wizard_nb)
        tab2 = ttk.Frame(self.wizard_nb)
        tab3 = ttk.Frame(self.wizard_nb)
        tab4 = ttk.Frame(self.wizard_nb)
        self.wizard_nb.add(tab1, text="1. Plantilla")
        self.wizard_nb.add(tab2, text="2. Cliente")
        self.wizard_nb.add(tab3, text="3. Intervinientes")
        self.wizard_nb.add(tab4, text="4. Generar")

        ttk.Label(tab1, text="Plantilla").pack(anchor="w", pady=(0, 6))
        self.tv_wizard_templates = ttk.Treeview(tab1, columns=("nombre", "tipo", "variables"), show="headings", height=12)
        for col, title, width in (
            ("nombre", "Nombre", 260),
            ("tipo", "Tipo", 220),
            ("variables", "Variables detectadas", 500),
        ):
            self.tv_wizard_templates.heading(col, text=title)
            self.tv_wizard_templates.column(col, width=width, anchor="w")
        self.tv_wizard_templates.pack(fill="both", expand=True)
        ttk.Button(tab1, text="Usar plantilla seleccionada", style="Primary.TButton", command=self.controller.select_template_for_wizard).pack(
            anchor="e", pady=8
        )

        upper = ttk.LabelFrame(tab2, text="Cliente existente")
        upper.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        filter_row = ttk.Frame(upper)
        filter_row.pack(fill="x", padx=8, pady=6)
        ttk.Label(filter_row, text="Buscar").pack(side=tk.LEFT)
        self.var_cliente_filter = tk.StringVar()
        ttk.Entry(filter_row, textvariable=self.var_cliente_filter, width=32).pack(side=tk.LEFT, padx=6)
        ttk.Button(filter_row, text="Cargar cliente", style="Primary.TButton", command=self.controller.load_selected_cliente).pack(side=tk.LEFT, padx=6)
        self.tv_clientes = ttk.Treeview(upper, columns=("nombre", "nif", "municipio"), show="headings", height=8)
        for col, title, width in (
            ("nombre", "Nombre", 260),
            ("nif", "NIF", 140),
            ("municipio", "Municipio", 180),
        ):
            self.tv_clientes.heading(col, text=title)
            self.tv_clientes.column(col, width=width, anchor="w")
        self.tv_clientes.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        manual = ttk.LabelFrame(tab2, text="Datos manuales")
        manual.pack(fill="x", expand=False, padx=4, pady=(0, 8))
        self.manual_cliente_vars = {
            "nombre_razon_social": tk.StringVar(),
            "nif": tk.StringVar(),
            "domicilio": tk.StringVar(),
            "municipio": tk.StringVar(),
            "provincia": tk.StringVar(),
            "cp": tk.StringVar(),
            "telefono": tk.StringVar(),
            "email": tk.StringVar(),
            "representante": tk.StringVar(),
            "cargo": tk.StringVar(),
        }
        for idx, (key, label) in enumerate(
            (
                ("nombre_razon_social", "Nombre / razon social"),
                ("nif", "NIF"),
                ("domicilio", "Domicilio"),
                ("municipio", "Municipio"),
                ("provincia", "Provincia"),
                ("cp", "CP"),
                ("telefono", "Telefono"),
                ("email", "Email"),
                ("representante", "Representante"),
                ("cargo", "Cargo"),
            )
        ):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(manual, text=label).grid(row=row, column=col, sticky="w", padx=6, pady=4)
            ttk.Entry(manual, textvariable=self.manual_cliente_vars[key], width=36).grid(row=row, column=col + 1, sticky="ew", padx=6, pady=4)
        manual.columnconfigure(1, weight=1)
        manual.columnconfigure(3, weight=1)
        ttk.Button(tab2, text="Guardar datos del cliente en el borrador", style="Primary.TButton", command=self.controller.save_manual_cliente).pack(
            anchor="e"
        )

        split = ttk.Frame(tab3)
        split.pack(fill="both", expand=True)
        left = ttk.LabelFrame(split, text="Contactos")
        right = ttk.LabelFrame(split, text="Intervinientes del documento")
        left.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 6))
        right.pack(side=tk.LEFT, fill="both", expand=True)
        self.tv_saved_intervinientes = ttk.Treeview(left, columns=("nombre", "nif", "email"), show="headings", height=12)
        for col, title, width in (("nombre", "Nombre", 220), ("nif", "NIF", 120), ("email", "Email", 200)):
            self.tv_saved_intervinientes.heading(col, text=title)
            self.tv_saved_intervinientes.column(col, width=width, anchor="w")
        self.tv_saved_intervinientes.pack(fill="both", expand=True, padx=8, pady=8)
        bar_left = ttk.Frame(left)
        bar_left.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar_left, text="Anadir al documento", style="Primary.TButton", command=self.controller.add_saved_interviniente).pack(side=tk.LEFT)
        ttk.Button(bar_left, text="Nuevo habitual", command=self.controller.save_habitual_interviniente).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar_left, text="Editar", command=self.controller.edit_habitual_interviniente).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar_left, text="Eliminar", command=self.controller.delete_habitual_interviniente).pack(side=tk.LEFT)

        self.tv_draft_intervinientes = ttk.Treeview(right, columns=("orden", "rol", "nombre", "nif"), show="headings", height=12)
        for col, title, width in (("orden", "#", 50), ("rol", "Rol", 160), ("nombre", "Nombre", 240), ("nif", "NIF", 120)):
            self.tv_draft_intervinientes.heading(col, text=title)
            self.tv_draft_intervinientes.column(col, width=width, anchor="w")
        self.tv_draft_intervinientes.pack(fill="both", expand=True, padx=8, pady=8)
        bar_right = ttk.Frame(right)
        bar_right.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar_right, text="Nuevo manual", style="Primary.TButton", command=self.controller.add_manual_interviniente).pack(side=tk.LEFT)
        ttk.Button(bar_right, text="Editar", command=self.controller.edit_draft_interviniente).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar_right, text="Subir", command=self.controller.move_draft_interviniente_up).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar_right, text="Bajar", command=self.controller.move_draft_interviniente_down).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar_right, text="Quitar", command=self.controller.remove_draft_interviniente).pack(side=tk.LEFT)

        final = ttk.Frame(tab4)
        final.pack(fill="both", expand=True)
        ttk.Label(final, text="Titulo del documento").pack(anchor="w")
        self.var_document_title = tk.StringVar()
        ttk.Entry(final, textvariable=self.var_document_title, width=72).pack(fill="x", pady=(0, 8))
        ttk.Label(final, text="Campos detectados en la plantilla").pack(anchor="w")
        self.dynamic_fields_host = ttk.Frame(final)
        self.dynamic_fields_host.pack(fill="both", expand=True, pady=(0, 8))
        self._build_dynamic_fields_host()
        ttk.Label(final, text="Observaciones").pack(anchor="w")
        self.txt_observaciones = tk.Text(final, height=10)
        self.txt_observaciones.pack(fill="x", expand=False, pady=(0, 8))
        ttk.Button(final, text="Generar documento", style="Primary.TButton", command=self.controller.generate_document).pack(anchor="e")

    def _build_dynamic_fields_host(self):
        outer = self.dynamic_fields_host
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, height=260)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill="both", expand=True)
        scroll.pack(side=tk.RIGHT, fill="y")
        self.dynamic_fields_canvas = canvas
        self.dynamic_fields_body = body
        self.dynamic_field_vars = {}

    def _build_history_tab(self):
        top = ttk.Frame(self.tab_history)
        top.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(top, text="Buscar").pack(side=tk.LEFT)
        self.var_doc_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_doc_filter, width=32).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Abrir DOCX", style="Primary.TButton", command=self.controller.open_document_docx).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Abrir PDF", command=self.controller.open_document_pdf).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Cargar en asistente", command=self.controller.load_document_into_wizard).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Duplicar", command=self.controller.duplicate_document).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Eliminar", command=self.controller.delete_document).pack(side=tk.LEFT)

        self.tv_documents = ttk.Treeview(
            self.tab_history,
            columns=("titulo", "plantilla", "fecha", "estado", "docx", "pdf"),
            show="headings",
            height=14,
        )
        for col, title, width in (
            ("titulo", "Documento", 240),
            ("plantilla", "Plantilla", 220),
            ("fecha", "Fecha", 130),
            ("estado", "Estado", 140),
            ("docx", "DOCX", 340),
            ("pdf", "PDF", 340),
        ):
            self.tv_documents.heading(col, text=title)
            self.tv_documents.column(col, width=width, anchor="w")
        self.tv_documents.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_intervinientes_tab(self):
        top = ttk.Frame(self.tab_intervinientes)
        top.pack(fill="x", padx=10, pady=(10, 6))
        texto = "Gestiona aqui los contactos reutilizables y terceros disponibles para futuros documentos."
        ttk.Label(top, text=texto).pack(side=tk.LEFT)
        ttk.Button(top, text="Nuevo", style="Primary.TButton", command=self.controller.save_habitual_interviniente).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="Editar", command=self.controller.edit_habitual_interviniente).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="Eliminar", command=self.controller.delete_habitual_interviniente).pack(side=tk.RIGHT, padx=4)
        self.tv_habitual_detail = ttk.Treeview(
            self.tab_intervinientes,
            columns=("nombre", "nif", "municipio", "telefono", "email"),
            show="headings",
            height=14,
        )
        for col, title, width in (
            ("nombre", "Nombre", 240),
            ("nif", "NIF", 130),
            ("municipio", "Municipio", 160),
            ("telefono", "Telefono", 140),
            ("email", "Email", 220),
        ):
            self.tv_habitual_detail.heading(col, text=title)
            self.tv_habitual_detail.column(col, width=width, anchor="w")
        self.tv_habitual_detail.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def set_templates(self, rows, selected_id=None):
        filtro = (self.var_template_filter.get() or "").strip().lower()
        self.tv_templates.delete(*self.tv_templates.get_children())
        for row in rows or []:
            text = f"{row.get('nombre','')} {row.get('tipo_documento','')} {row.get('ruta_template','')}".lower()
            if filtro and filtro not in text:
                continue
            self.tv_templates.insert(
                "",
                tk.END,
                iid=str(row.get("id")),
                values=(
                    row.get("nombre", ""),
                    row.get("tipo_documento", ""),
                    row.get("ruta_template", ""),
                    ", ".join(row.get("variables", [])),
                ),
            )
        if selected_id and self.tv_templates.exists(str(selected_id)):
            self.tv_templates.selection_set(str(selected_id))

    def set_wizard_templates(self, rows, selected_id=None):
        self.tv_wizard_templates.delete(*self.tv_wizard_templates.get_children())
        for row in rows or []:
            self.tv_wizard_templates.insert(
                "",
                tk.END,
                iid=str(row.get("id")),
                values=(row.get("nombre", ""), row.get("tipo_documento", ""), ", ".join(row.get("variables", []))),
            )
        if selected_id and self.tv_wizard_templates.exists(str(selected_id)):
            self.tv_wizard_templates.selection_set(str(selected_id))

    def set_clientes(self, rows):
        filtro = (self.var_cliente_filter.get() or "").strip().lower()
        self.tv_clientes.delete(*self.tv_clientes.get_children())
        for row in rows or []:
            text = f"{row.get('nombre','')} {row.get('nif','')} {row.get('poblacion','')}".lower()
            if filtro and filtro not in text:
                continue
            self.tv_clientes.insert(
                "",
                tk.END,
                iid=str(row.get("id")),
                values=(
                    row.get("nombre", ""),
                    row.get("nif", ""),
                    row.get("poblacion", ""),
                ),
            )

    def set_saved_intervinientes(self, rows, selected_id=None):
        self.tv_saved_intervinientes.delete(*self.tv_saved_intervinientes.get_children())
        self.tv_habitual_detail.delete(*self.tv_habitual_detail.get_children())
        for row in rows or []:
            iid = str(row.get("id"))
            values = (row.get("nombre_razon_social", ""), row.get("nif", ""), row.get("email", ""))
            self.tv_saved_intervinientes.insert("", tk.END, iid=iid, values=values)
            self.tv_habitual_detail.insert(
                "",
                tk.END,
                iid=f"detail::{iid}",
                values=(
                    row.get("nombre_razon_social", ""),
                    row.get("nif", ""),
                    row.get("municipio", ""),
                    row.get("telefono", ""),
                    row.get("email", ""),
                ),
            )
        if selected_id and self.tv_saved_intervinientes.exists(str(selected_id)):
            self.tv_saved_intervinientes.selection_set(str(selected_id))

    def set_draft_intervinientes(self, rows):
        self.tv_draft_intervinientes.delete(*self.tv_draft_intervinientes.get_children())
        for idx, row in enumerate(rows or []):
            self.tv_draft_intervinientes.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    idx + 1,
                    row.get("rol_en_documento", "") or row.get("rol", ""),
                    row.get("nombre_razon_social", ""),
                    row.get("nif", ""),
                ),
            )

    def set_documents(self, rows, selected_id=None):
        filtro = (self.var_doc_filter.get() or "").strip().lower()
        self.tv_documents.delete(*self.tv_documents.get_children())
        for row in rows or []:
            text = f"{row.get('titulo_documento','')} {row.get('plantilla_nombre','')} {row.get('estado','')}".lower()
            if filtro and filtro not in text:
                continue
            self.tv_documents.insert(
                "",
                tk.END,
                iid=str(row.get("id")),
                values=(
                    row.get("titulo_documento", ""),
                    row.get("plantilla_nombre", ""),
                    row.get("fecha_generacion", ""),
                    row.get("estado", ""),
                    row.get("ruta_docx", ""),
                    row.get("ruta_pdf", ""),
                ),
            )
        if selected_id and self.tv_documents.exists(str(selected_id)):
            self.tv_documents.selection_set(str(selected_id))

    def get_selected_template_id(self):
        sel = self.tv_templates.selection()
        return sel[0] if sel else None

    def get_selected_wizard_template_id(self):
        sel = self.tv_wizard_templates.selection()
        return sel[0] if sel else None

    def get_selected_cliente_id(self):
        sel = self.tv_clientes.selection()
        return sel[0] if sel else None

    def get_selected_saved_interviniente_id(self):
        sel = self.tv_saved_intervinientes.selection()
        if sel:
            return sel[0]
        sel = self.tv_habitual_detail.selection()
        if not sel:
            return None
        iid = str(sel[0])
        return iid.replace("detail::", "", 1)

    def get_selected_draft_interviniente_index(self):
        sel = self.tv_draft_intervinientes.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except Exception:
            return None

    def get_selected_document_id(self):
        sel = self.tv_documents.selection()
        return sel[0] if sel else None

    def select_draft_interviniente(self, index: int):
        iid = str(index)
        if self.tv_draft_intervinientes.exists(iid):
            self.tv_draft_intervinientes.selection_set(iid)
            self.tv_draft_intervinientes.see(iid)

    def get_manual_cliente_form(self):
        return {key: var.get().strip() for key, var in self.manual_cliente_vars.items()}

    def set_manual_cliente_form(self, data):
        data = data or {}
        for key, var in self.manual_cliente_vars.items():
            var.set(str(data.get(key) or ""))

    def get_document_title(self):
        return self.var_document_title.get().strip()

    def set_document_title(self, value):
        self.var_document_title.set(str(value or ""))

    def get_document_observaciones(self):
        return self.txt_observaciones.get("1.0", tk.END).strip()

    def set_document_observaciones(self, value):
        self.txt_observaciones.delete("1.0", tk.END)
        self.txt_observaciones.insert("1.0", str(value or ""))

    def set_dynamic_fields(self, fields):
        for child in self.dynamic_fields_body.winfo_children():
            child.destroy()
        new_vars = {}
        for idx, field in enumerate(fields or []):
            key = str(field.get("key") or "")
            ttk.Label(self.dynamic_fields_body, text=str(field.get("label") or key)).grid(
                row=idx, column=0, sticky="w", padx=(0, 8), pady=3
            )
            var = tk.StringVar(value=str(field.get("value") or ""))
            state = "readonly" if field.get("readonly") else "normal"
            ttk.Entry(self.dynamic_fields_body, textvariable=var, width=72, state=state).grid(
                row=idx, column=1, sticky="ew", pady=3
            )
            new_vars[key] = {"var": var, "readonly": bool(field.get("readonly"))}
        self.dynamic_fields_body.columnconfigure(1, weight=1)
        self.dynamic_field_vars = new_vars
        self.dynamic_fields_canvas.yview_moveto(0)

    def get_dynamic_field_values(self):
        out = {}
        for key, item in (self.dynamic_field_vars or {}).items():
            if item.get("readonly"):
                continue
            out[key] = item["var"].get().strip()
        return out

    def goto_wizard_tab(self, index: int):
        self.wizard_nb.select(index)

    def goto_main_tab(self, index: int):
        self.main_nb.select(index)

    def ask_open_docx_path(self):
        return filedialog.askopenfilename(title="Selecciona plantilla DOCX", filetypes=[("Word", "*.docx")])

    def ask_template_name(self, current_name: str):
        return simpledialog.askstring("Plantilla", "Nuevo nombre de la plantilla:", initialvalue=current_name, parent=self)

    def open_interviniente_dialog(self, data):
        dlg = IntervinienteDialog(self, data)
        return dlg.result

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)
