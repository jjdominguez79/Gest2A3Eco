# ui_procesos.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from controllers.ui_procesos_controller import ProcesosController



class UIProcesos(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.pack(fill=tk.BOTH, expand=True)
        self._build()
        self.controller = ProcesosController(gestor, codigo_empresa, ejercicio, self)
        self.controller.refresh_plantillas()

    # UI
    def _build(self):
        ttk.Label(self, text=f"Generar fichero - {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        form = ttk.Frame(self)
        form.pack(fill=tk.X, padx=10, pady=4)

        ttk.Label(form, text="Tipo de enlace:").grid(row=0, column=0, sticky="w")
        self.tipo = tk.StringVar(value="Bancos")
        ttk.Combobox(
            form,
            textvariable=self.tipo,
            values=["Bancos", "Facturas Emitidas", "Facturas Recibidas", "Terceros (alta masiva)"],
            width=25,
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(form, text="Plantilla:").grid(row=1, column=0, sticky="w")
        self.cb_plantilla = ttk.Combobox(form, width=40)
        self.cb_plantilla.grid(row=1, column=1, sticky="w")

        ttk.Button(form, text="Cargar Excel", style="Primary.TButton", command=lambda: self.controller.cargar_excel()).grid(row=2, column=0, pady=6)
        self.lbl_excel = ttk.Label(form, text="Ningun archivo seleccionado")
        self.lbl_excel.grid(row=2, column=1, sticky="w")

        ttk.Label(form, text="Seleccione Hoja:").grid(row=3, column=0, sticky="w")
        self.cb_sheet = ttk.Combobox(form, width=30)
        self.cb_sheet.grid(row=3, column=1, sticky="w")
        self.cb_sheet.bind("<<ComboboxSelected>>", lambda e: self.controller.preview_excel())

        self.btn_generar = ttk.Button(
            self,
            text="Generar Suenlace.dat",
            style="Primary.TButton",
            command=lambda: self.controller.generar(),
        )
        self.btn_generar.pack(side=tk.BOTTOM, pady=10)

        preview_wrap = ttk.Frame(self, height=320, width=900)
        preview_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        preview_wrap.pack_propagate(False)
        preview_wrap.grid_propagate(False)
        preview_wrap.rowconfigure(0, weight=1)
        preview_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(preview_wrap, show="headings", height=12)
        self.tv.grid(row=0, column=0, sticky="nsew")

        self.vsb = ttk.Scrollbar(preview_wrap, orient="vertical", command=self.tv.yview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb = ttk.Scrollbar(preview_wrap, orient="horizontal", command=self.tv.xview)
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.tv.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tipo.trace_add("write", lambda *_: self.controller.refresh_plantillas())

    def get_tipo(self):
        return self.tipo.get()

    def get_selected_plantilla(self):
        return self.cb_plantilla.get()

    def set_plantillas(self, values):
        self.cb_plantilla["values"] = values
        if values:
            self.cb_plantilla.current(0)
        else:
            self.cb_plantilla.set("")

    def set_plantilla_enabled(self, enabled: bool):
        self.cb_plantilla.configure(state=("normal" if enabled else "disabled"))

    def set_generar_text(self, text: str):
        self.btn_generar.configure(text=text)

    def ask_open_excel_path(self):
        return filedialog.askopenfilename(
            title="Seleccionar Excel",
            filetypes=[("Archivos Excel", "*.xlsx *.xls *.xlsm")],
        )

    def ask_save_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

    def set_excel_label(self, text):
        self.lbl_excel.config(text=text)

    def set_sheet_values(self, values):
        self.cb_sheet["values"] = values

    def clear_sheet_selection(self):
        self.cb_sheet.set("")

    def get_selected_sheet(self):
        return self.cb_sheet.get()

    def clear_preview(self):
        self.tv.delete(*self.tv.get_children())
        self.tv["columns"] = []

    def render_preview(self, df):
        self.tv.delete(*self.tv.get_children())
        self.tv["columns"] = list(df.columns)
        for c in df.columns:
            self.tv.heading(c, text=c)
            self.tv.column(c, width=120, minwidth=80, stretch=False)
        for row in df.itertuples(index=False):
            vals = [str(x) for x in row]
            self.tv.insert("", tk.END, values=vals)
        self.tv.xview_moveto(0)
        self.tv.yview_moveto(0)

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)
