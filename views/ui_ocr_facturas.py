import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controllers.ui_ocr_facturas_controller import UIOcrFacturasController

# Bandejas: (clave_estado, titulo_tab)
BANDEJAS = [
    ("procesando",              "Procesando"),
    ("error",                   "Errores"),
    ("pendiente_revision",      "Pte. revision"),
    ("pendiente_contabilizar",  "Pte. contabilizar"),
    ("contabilizada",           "Contabilizadas"),
]

# Columnas de la tabla: (id, cabecera, ancho_px, anchor)
COLUMNAS = [
    ("fecha_subida",     "Subida",       90,  "w"),
    ("tipo_documento",   "Tipo",         130, "w"),
    ("proveedor_nombre", "Proveedor",    170, "w"),
    ("proveedor_nif",    "NIF",          90,  "w"),
    ("numero_factura",   "Factura",      100, "w"),
    ("fecha_factura",    "F.Factura",    85,  "w"),
    ("total",            "Total",        80,  "e"),
    ("estado_ocr",       "Estado OCR",   95,  "w"),
    ("error_mensaje",    "Aviso/Error",  200, "w"),
    ("confianza_ocr",    "Confianza",    70,  "e"),
]
COL_IDS = [c[0] for c in COLUMNAS]


class UIOcrFacturas(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa, session=None):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.session = session
        self._tvs: dict[str, ttk.Treeview] = {}
        self.controller = UIOcrFacturasController(gestor, codigo_empresa, ejercicio, self)
        self._build()
        self.after_idle(self.controller.refresh_all)

    # ── Construccion UI ───────────────────────────────────────────────────────

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(
            header,
            text=f"Captura documental  —  {self.nombre} ({self.codigo})",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        ttk.Button(
            header,
            text="Cargar documentos",
            style="Primary.TButton",
            command=self.controller.cargar_documentos,
        ).pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=4)
        for estado, titulo in BANDEJAS:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=titulo)
            self._build_bandeja(frame, estado)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        status_bar = ttk.Frame(self)
        status_bar.pack(fill="x", padx=10, pady=(0, 6))
        self._lbl_status = ttk.Label(status_bar, text="", foreground="#555555")
        self._lbl_status.pack(side="left")

    def _build_bandeja(self, parent: ttk.Frame, estado: str):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=6, pady=(6, 2))
        self._build_toolbar(bar, estado)

        tv_frame = ttk.Frame(parent)
        tv_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        tv = ttk.Treeview(
            tv_frame,
            columns=COL_IDS,
            show="headings",
            selectmode="extended",
        )
        for col_id, col_txt, col_w, anchor in COLUMNAS:
            tv.heading(col_id, text=col_txt)
            stretch = col_id in ("proveedor_nombre", "error_mensaje")
            tv.column(col_id, width=col_w, anchor=anchor, stretch=stretch)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True)

        tv.bind("<Double-1>", lambda _e, est=estado: self.controller.abrir_documento_seleccionado(est))
        tv.tag_configure("row_error", foreground="#c0392b")
        tv.tag_configure("row_pending", foreground="#7f8c8d")
        self._tvs[estado] = tv

    def _build_toolbar(self, bar: ttk.Frame, estado: str):
        if estado == "procesando":
            ttk.Label(bar, text="Los documentos se procesan automaticamente al cargar.").pack(side="left")
            return

        if estado == "error":
            ttk.Button(bar, text="Reintentar OCR",
                       command=lambda: self.controller.reintentar_seleccionados(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Abrir documento",
                       command=lambda: self.controller.abrir_documento_seleccionado(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Eliminar", style="Danger.TButton",
                       command=lambda: self.controller.eliminar_seleccionado(estado)).pack(side="left")

        elif estado == "pendiente_revision":
            ttk.Button(bar, text="Abrir y revisar", style="Primary.TButton",
                       command=lambda: self.controller.abrir_documento_seleccionado(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Marcar validada",
                       command=lambda: self.controller.marcar_validada_seleccionado(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Enviar a Errores",
                       command=lambda: self.controller.enviar_a_error_seleccionado(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Eliminar", style="Danger.TButton",
                       command=lambda: self.controller.eliminar_seleccionado(estado)).pack(side="left")

        elif estado == "pendiente_contabilizar":
            ttk.Button(bar, text="Generar suenlace seleccionadas", style="Primary.TButton",
                       command=self.controller.generar_suenlace_seleccionadas).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Abrir documento",
                       command=lambda: self.controller.abrir_documento_seleccionado(estado)).pack(side="left", padx=(0, 4))
            ttk.Button(bar, text="Enviar a Errores",
                       command=lambda: self.controller.enviar_a_error_seleccionado(estado)).pack(side="left")

        elif estado == "contabilizada":
            ttk.Button(bar, text="Abrir documento",
                       command=lambda: self.controller.abrir_documento_seleccionado(estado)).pack(side="left")

    # ── Poblado de bandejas ───────────────────────────────────────────────────

    def set_bandeja_docs(self, estado: str, docs: list[dict]):
        tv = self._tvs.get(estado)
        if not tv:
            return
        prev_sel = set(tv.selection())
        tv.delete(*tv.get_children())
        for doc in docs:
            fecha = str(doc.get("created_at") or "")[:10]
            total = doc.get("total") or 0.0
            confianza = doc.get("confianza_ocr") or 0.0
            vals = (
                fecha,
                doc.get("tipo_documento") or "factura_recibida",
                doc.get("proveedor_nombre") or "",
                doc.get("proveedor_nif") or "",
                doc.get("numero_factura") or "",
                doc.get("fecha_factura") or "",
                f"{total:.2f}",
                doc.get("estado_ocr") or "",
                doc.get("error_mensaje") or "",
                f"{confianza:.0%}" if confianza else "",
            )
            tags = ("row_error",) if doc.get("estado_ocr") == "error" else (
                ("row_pending",) if doc.get("estado_ocr") in ("pendiente", "procesando") else ()
            )
            tv.insert("", "end", iid=str(doc["id"]), values=vals, tags=tags)
        for iid in prev_sel:
            if tv.exists(iid):
                tv.selection_add(iid)
        self._update_tab_count(estado, len(docs))

    def _update_tab_count(self, estado: str, count: int):
        for idx, (est, titulo) in enumerate(BANDEJAS):
            if est == estado:
                badge = f" ({count})" if count else ""
                self.nb.tab(idx, text=titulo + badge)
                break

    # ── Navegacion ────────────────────────────────────────────────────────────

    def switch_to_bandeja(self, estado: str):
        for idx, (est, _) in enumerate(BANDEJAS):
            if est == estado:
                self.nb.select(idx)
                break

    def _current_estado(self) -> str:
        try:
            idx = self.nb.index(self.nb.select())
            return BANDEJAS[idx][0]
        except Exception:
            return "procesando"

    def _on_tab_changed(self, _e):
        estado = self._current_estado()
        self.controller.refresh_bandeja(estado)

    # ── Consulta de seleccion ─────────────────────────────────────────────────

    def get_selected_ids(self, estado: str) -> list[str]:
        tv = self._tvs.get(estado)
        return list(tv.selection()) if tv else []

    # ── Indicador de estado OCR ───────────────────────────────────────────────

    def set_ocr_running(self, running: bool, message: str = ""):
        self._lbl_status.configure(text=message if running else "")

    # ── Dialogos ─────────────────────────────────────────────────────────────

    def ask_open_document_paths(self):
        return filedialog.askopenfilenames(
            title="Seleccionar documentos de factura",
            filetypes=[
                ("Documentos soportados", "*.pdf *.png *.jpg *.jpeg"),
                ("PDF", "*.pdf"),
                ("Imagenes", "*.png *.jpg *.jpeg"),
            ],
        )

    def ask_save_path(self, initialfile: str):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

    def ask_yes_no(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message)

    def show_info(self, title: str, message: str):
        messagebox.showinfo(title, message)

    def show_warning(self, title: str, message: str):
        messagebox.showwarning(title, message)

    def show_error(self, title: str, message: str):
        messagebox.showerror(title, message)
