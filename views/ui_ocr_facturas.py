import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controllers.ui_ocr_facturas_controller import UIOcrFacturasController


class UIOcrFacturas(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa, session=None):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.session = session
        self._docs = []
        self.controller = UIOcrFacturasController(gestor, codigo_empresa, ejercicio, self)
        self._build()
        self.controller.refresh()

    def _build(self):
        ttk.Label(
            self,
            text=f"OCR de facturas recibidas - {self.nombre} ({self.codigo})",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=8)

        top = ttk.Frame(self)
        top.pack(fill="both", expand=True, padx=10, pady=8)
        top.columnconfigure(1, weight=1)
        top.rowconfigure(0, weight=1)

        left = ttk.Frame(top)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        ttk.Button(left, text="Cargar PDF", style="Primary.TButton", command=self.controller.cargar_documento).pack(fill="x")
        ttk.Button(left, text="Guardar", command=self.controller.guardar_actual).pack(fill="x", pady=(6, 0))
        ttk.Button(left, text="Marcar validada", command=self.controller.marcar_validada).pack(fill="x", pady=(6, 0))
        ttk.Button(left, text="Eliminar", style="Danger.TButton", command=self.controller.eliminar_actual).pack(fill="x", pady=(6, 0))

        self.tv = ttk.Treeview(
            left,
            columns=("proveedor", "numero", "estado"),
            show="headings",
            height=16,
        )
        for col, txt, width in (
            ("proveedor", "Proveedor", 180),
            ("numero", "Factura", 100),
            ("estado", "Estado", 100),
        ):
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor="w")
        self.tv.pack(fill="both", expand=True, pady=(10, 0))
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        right = ttk.Frame(top)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        self.vars = {
            "proveedor_nombre": tk.StringVar(),
            "proveedor_nif": tk.StringVar(),
            "numero_factura": tk.StringVar(),
            "fecha_factura": tk.StringVar(),
            "fecha_operacion": tk.StringVar(),
            "fecha_asiento": tk.StringVar(),
            "descripcion": tk.StringVar(),
            "base_imponible": tk.StringVar(),
            "cuota_iva": tk.StringVar(),
            "cuota_recargo": tk.StringVar(),
            "cuota_retencion": tk.StringVar(),
            "total": tk.StringVar(),
            "cuenta_gasto": tk.StringVar(),
            "cuenta_iva": tk.StringVar(),
            "cuenta_proveedor": tk.StringVar(),
            "estado_ocr": tk.StringVar(),
            "estado_validacion": tk.StringVar(),
        }
        fields = [
            ("Proveedor", "proveedor_nombre"),
            ("NIF", "proveedor_nif"),
            ("Numero factura", "numero_factura"),
            ("Fecha factura", "fecha_factura"),
            ("Fecha operacion", "fecha_operacion"),
            ("Fecha asiento", "fecha_asiento"),
            ("Descripcion", "descripcion"),
            ("Base", "base_imponible"),
            ("IVA", "cuota_iva"),
            ("Recargo", "cuota_recargo"),
            ("Retencion", "cuota_retencion"),
            ("Total", "total"),
            ("Cuenta gasto", "cuenta_gasto"),
            ("Cuenta IVA", "cuenta_iva"),
            ("Cuenta proveedor", "cuenta_proveedor"),
            ("Estado OCR", "estado_ocr"),
            ("Estado validacion", "estado_validacion"),
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(right, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(right, textvariable=self.vars[key]).grid(row=idx, column=1, sticky="ew", pady=4)

        ttk.Label(right, text="Texto OCR").grid(row=len(fields), column=0, sticky="nw", padx=(0, 8), pady=(10, 4))
        self.txt_ocr = tk.Text(right, height=16, wrap="word")
        self.txt_ocr.grid(row=len(fields), column=1, sticky="nsew", pady=(10, 4))
        right.rowconfigure(len(fields), weight=1)

    def set_documents(self, docs: list[dict]):
        self._docs = docs or []
        self.tv.delete(*self.tv.get_children())
        for doc in self._docs:
            estado = doc.get("estado_contable") or doc.get("estado_validacion") or doc.get("estado_ocr") or ""
            self.tv.insert(
                "",
                "end",
                iid=str(doc.get("id")),
                values=(doc.get("proveedor_nombre", ""), doc.get("numero_factura", ""), estado),
            )

    def load_document(self, doc: dict):
        for key, var in self.vars.items():
            value = doc.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            var.set("" if value is None else str(value))
        self.txt_ocr.delete("1.0", tk.END)
        self.txt_ocr.insert("1.0", str(doc.get("texto_ocr") or ""))
        iid = str(doc.get("id"))
        if iid in self.tv.get_children():
            self.tv.selection_set(iid)
            self.tv.focus(iid)

    def clear_form(self):
        for var in self.vars.values():
            var.set("")
        self.txt_ocr.delete("1.0", tk.END)

    def get_form_data(self):
        selected = self.tv.selection()
        if not selected:
            return None
        return {
            "proveedor_nombre": self.vars["proveedor_nombre"].get().strip(),
            "proveedor_nif": self.vars["proveedor_nif"].get().strip(),
            "numero_factura": self.vars["numero_factura"].get().strip(),
            "fecha_factura": self.vars["fecha_factura"].get().strip(),
            "fecha_operacion": self.vars["fecha_operacion"].get().strip(),
            "fecha_asiento": self.vars["fecha_asiento"].get().strip(),
            "descripcion": self.vars["descripcion"].get().strip(),
            "base_imponible": self._to_float(self.vars["base_imponible"].get()),
            "cuota_iva": self._to_float(self.vars["cuota_iva"].get()),
            "cuota_recargo": self._to_float(self.vars["cuota_recargo"].get()),
            "cuota_retencion": self._to_float(self.vars["cuota_retencion"].get()),
            "total": self._to_float(self.vars["total"].get()),
            "cuenta_gasto": self.vars["cuenta_gasto"].get().strip(),
            "cuenta_iva": self.vars["cuenta_iva"].get().strip(),
            "cuenta_proveedor": self.vars["cuenta_proveedor"].get().strip(),
            "estado_ocr": self.vars["estado_ocr"].get().strip(),
            "estado_validacion": self.vars["estado_validacion"].get().strip(),
            "texto_ocr": self.txt_ocr.get("1.0", tk.END).strip(),
        }

    def ask_open_document_path(self):
        return filedialog.askopenfilename(
            title="Seleccionar factura PDF",
            filetypes=[("PDF", "*.pdf")],
        )

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def _on_select(self):
        sel = self.tv.selection()
        if sel:
            self.controller.select_document(str(sel[0]))

    def _to_float(self, value: str) -> float:
        txt = str(value or "").strip().replace(".", "").replace(",", ".")
        if not txt:
            return 0.0
        try:
            return round(float(txt), 2)
        except Exception:
            return 0.0
