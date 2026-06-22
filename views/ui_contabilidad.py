import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controllers.ui_contabilidad_controller import UIContabilidadController
from controllers.ui_contabilidad_emitidas_controller import UIContabilidadEmitidasController

_ESTADO_LABELS = {"pendiente": "Pendiente", "generado": "Generado"}


class UIContabilidad(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa, session=None):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.session = session
        self._docs = []
        self._emitidas_docs = []
        self.controller = UIContabilidadController(gestor, codigo_empresa, ejercicio, self)
        self.emitidas_ctrl = UIContabilidadEmitidasController(gestor, codigo_empresa, ejercicio, self)
        self._build()
        self.controller.refresh()
        self.emitidas_ctrl.refresh()

    def _build(self):
        ttk.Label(
            self,
            text=f"Contabilidad - {self.nombre} ({self.codigo})",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        tab_recibidas = ttk.Frame(nb)
        nb.add(tab_recibidas, text="Facturas recibidas")
        self._build_recibidas(tab_recibidas)

        tab_emitidas = ttk.Frame(nb)
        nb.add(tab_emitidas, text="Facturas emitidas")
        self._build_emitidas(tab_emitidas)

    def _build_recibidas(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=10, pady=8)
        wrap.columnconfigure(1, weight=1)
        wrap.rowconfigure(1, weight=1)

        bar = ttk.Frame(wrap)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="Generar asiento", style="Primary.TButton", command=self.controller.generar_asiento).pack(side=tk.LEFT)
        ttk.Button(bar, text="Exportar suenlace.dat", command=self.controller.exportar_suenlace).pack(side=tk.LEFT, padx=6)
        ttk.Label(bar, text="Nº asiento").pack(side=tk.LEFT, padx=(14, 4))
        self.var_numero_asiento = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_numero_asiento, width=12).pack(side=tk.LEFT)
        ttk.Label(bar, text="Fecha asiento").pack(side=tk.LEFT, padx=(14, 4))
        self.var_fecha_asiento = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_fecha_asiento, width=12).pack(side=tk.LEFT)

        self.tv = ttk.Treeview(
            wrap,
            columns=("proveedor", "numero", "estado", "total"),
            show="headings",
            height=16,
        )
        for col, txt, width in (
            ("proveedor", "Proveedor", 220),
            ("numero", "Factura", 100),
            ("estado", "Estado", 110),
            ("total", "Total", 90),
        ):
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor="w")
        self.tv.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        right = ttk.Frame(wrap)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.lbl_resumen = ttk.Label(right, text="")
        self.lbl_resumen.grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.tv_asiento = ttk.Treeview(
            right,
            columns=("subcuenta", "dh", "importe", "concepto"),
            show="headings",
        )
        for col, txt, width in (
            ("subcuenta", "Subcuenta", 120),
            ("dh", "D/H", 50),
            ("importe", "Importe", 100),
            ("concepto", "Concepto", 360),
        ):
            self.tv_asiento.heading(col, text=txt)
            self.tv_asiento.column(col, width=width, anchor="w")
        self.tv_asiento.grid(row=1, column=0, sticky="nsew")

    def _build_emitidas(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Button(
            bar, text="Generar Suenlace.dat", style="Primary.TButton",
            command=self.emitidas_ctrl.generar_suenlace,
        ).pack(side=tk.LEFT)
        ttk.Label(
            bar,
            text="Selecciona facturas y genera el suenlace para importar en A3ECO.",
            foreground="#555",
        ).pack(side=tk.LEFT, padx=12)

        self.tv_emitidas = ttk.Treeview(
            parent,
            columns=("numero", "fecha", "cliente", "total", "estado"),
            show="headings",
            selectmode="extended",
            height=18,
        )
        for col, txt, width, anchor in (
            ("numero", "Nº Factura", 130, "w"),
            ("fecha", "Fecha", 100, "w"),
            ("cliente", "Cliente", 260, "w"),
            ("total", "Total", 100, "e"),
            ("estado", "Estado contable", 130, "center"),
        ):
            self.tv_emitidas.heading(col, text=txt)
            self.tv_emitidas.column(col, width=width, anchor=anchor)
        self.tv_emitidas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.tv_emitidas.tag_configure("generado", foreground="#2a7a2a")
        self.tv_emitidas.tag_configure("pendiente", foreground="#b85c00")

    # ── Emitidas tab interface ──────────────────────────────────────────────

    def set_emitidas(self, docs: list[dict]):
        self._emitidas_docs = docs or []
        self.tv_emitidas.delete(*self.tv_emitidas.get_children())
        for doc in self._emitidas_docs:
            estado = doc.get("estado_contable") or ""
            serie = str(doc.get("serie") or "").strip()
            numero = str(doc.get("numero") or "").strip()
            num_display = f"{serie}{numero}" if serie else numero
            try:
                total = float(doc.get("total") or 0)
            except Exception:
                total = 0.0
            tag = estado if estado in ("pendiente", "generado") else ""
            self.tv_emitidas.insert(
                "", tk.END,
                iid=str(doc.get("id")),
                tags=(tag,) if tag else (),
                values=(
                    num_display,
                    str(doc.get("fecha_asiento") or doc.get("fecha_expedicion") or ""),
                    str(doc.get("nombre") or ""),
                    f"{total:.2f}",
                    _ESTADO_LABELS.get(estado, estado),
                ),
            )

    def get_selected_emitida_ids(self) -> list[str]:
        return list(self.tv_emitidas.selection())

    def ask_yes_no(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message)

    def ask_save_dat_path(self, initialfile: str) -> str:
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

    # ── Recibidas tab interface (UIContabilidadController) ──────────────────

    def set_documents(self, docs: list[dict]):
        self._docs = docs or []
        self.tv.delete(*self.tv.get_children())
        for doc in self._docs:
            self.tv.insert(
                "", "end",
                iid=str(doc.get("id")),
                values=(
                    doc.get("proveedor_nombre", ""),
                    doc.get("numero_factura", ""),
                    doc.get("estado_contable", ""),
                    self._fmt_num(doc.get("total", 0)),
                ),
            )

    def load_document(self, doc: dict, asiento: dict | None):
        self.var_numero_asiento.set(str(doc.get("numero_asiento") or ""))
        self.var_fecha_asiento.set(str(doc.get("fecha_asiento") or doc.get("fecha_factura") or ""))
        self.lbl_resumen.configure(
            text=(
                f"Proveedor: {doc.get('proveedor_nombre', '')}    "
                f"Factura: {doc.get('numero_factura', '')}    "
                f"Total: {self._fmt_num(doc.get('total', 0))}    "
                f"Estado: {doc.get('estado_contable', '')}"
            )
        )
        self.tv_asiento.delete(*self.tv_asiento.get_children())
        if asiento:
            for idx, line in enumerate(asiento.get("lineas") or []):
                self.tv_asiento.insert(
                    "", "end",
                    iid=f"{doc.get('id')}::{idx}",
                    values=(
                        line.get("subcuenta", ""),
                        line.get("dh", ""),
                        self._fmt_num(line.get("importe", 0)),
                        line.get("concepto", ""),
                    ),
                )
        iid = str(doc.get("id"))
        if iid in self.tv.get_children():
            self.tv.selection_set(iid)
            self.tv.focus(iid)

    def clear_preview(self):
        self.var_numero_asiento.set("")
        self.var_fecha_asiento.set("")
        self.lbl_resumen.configure(text="")
        self.tv_asiento.delete(*self.tv_asiento.get_children())

    def get_numero_asiento(self):
        return self.var_numero_asiento.get().strip()

    def get_fecha_asiento(self):
        return self.var_fecha_asiento.get().strip()

    def ask_save_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

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

    def _fmt_num(self, value) -> str:
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "0.00"
