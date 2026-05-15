
import calendar
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import date, datetime
from utils.utilidades import aplicar_descuento_total_lineas, format_num_es, load_monedas
from utils.ui_facturas_emitidas_helpers import (
    fmt2,
    fmt2s,
    fmt4,
    normalizar_telefono,
    parse_date_ui,
    round2,
    round4,
    to_fecha_ui,
    to_fecha_ui_or_blank,
    to_float,
)
from utils.validaciones import normalizar_nif_cif

from controllers.ui_facturas_emitidas_controller import FacturasEmitidasController
from controllers.factura_dialog_controller import FacturaDialogController
from controllers.terceros_global_controller import TercerosGlobalController
from controllers.terceros_empresa_controller import TercerosEmpresaController

IVA_OPCIONES = [21, 10, 4, 0]
IRPF_RET_OPCIONES = [1, 7, 15, 19]
TIPOS_OPERACION_EMITIDAS = [
    ("01", "01: Operaciones interiores sujetas a IVA"),
    ("02", "02: Operaciones exentas sin derecho a deduccion"),
    ("03", "03: Entregas intracomunitarias"),
    ("04", "04: Entregas intracomunitarias Ops. Triangulares"),
    ("05", "05: Operaciones con Canarias, Ceuta y Melilla"),
    ("06", "06: Exportaciones"),
    ("07", "07: Operacion no sujeta a IVA, reservada a a3ges"),
    ("08", "08: No sujetas o inversion de sujeto pasivo con derecho a deduccion"),
    ("09", "09: Otras operaciones exentas con derecho a deduccion"),
]
MODELOS_FISCALES_EMITIDAS = [
    ("", "Sin modelo asignado"),
    ("01", "01: 347, subclave A-B, Compras-Ventas"),
    ("02", "02: 349, B, Bienes"),
    ("03", "03: 180, A, Dinerarias"),
    ("04", "04: 180, B, Especie"),
    ("05", "05: 190, G01, Profesionales dinerarias"),
    ("06", "06: 190, G02, Profesionales en especie"),
    ("07", "07: 190, H01, Agrarios dinerarias"),
    ("08", "08: 190, H01, Agrarios en especie"),
    ("09", "09: 190, H04, Modulos empresariales dinerarias"),
    ("10", "10: 190, H04, Modulos empresariales en especie"),
    ("11", "11: 349, S, Servicios"),
    ("12", "12: 190, G02, Tabacaleras ag.seguros LAE dinerarias"),
    ("13", "13: 190, G02, Tabacaleras ag.seguros LAE en especie"),
    ("14", "14: 190, G03, Inicio actividad profesional dinerarias"),
]


def _bind_nif_normalizer(var: tk.StringVar):
    def _normalize(*_args):
        current = var.get()
        normalized = normalizar_nif_cif(current)
        if current != normalized:
            var.set(normalized)

    var.trace_add("write", _normalize)


def _center_window(win, parent=None):
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if parent is None:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        else:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        win.geometry(f"+{max(x,0)}+{max(y,0)}")
    except Exception:
        pass

class DatePicker(tk.Toplevel):
    def __init__(self, parent, initial: date | None = None):
        super().__init__(parent)
        self.title("Selecciona fecha")
        self.resizable(False, False)
        self.result = None
        self._current = initial or date.today()
        self._build()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        nav = ttk.Frame(frm)
        nav.pack(fill="x")
        ttk.Button(nav, text="<", width=3, command=self._prev_month).pack(side=tk.LEFT)
        self.lbl_month = ttk.Label(nav, width=18, anchor="center")
        self.lbl_month.pack(side=tk.LEFT, expand=True)
        ttk.Button(nav, text=">", width=3, command=self._next_month).pack(side=tk.LEFT)

        self.days_frame = ttk.Frame(frm)
        self.days_frame.pack(pady=4)
        for i, dname in enumerate(["Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"]):
            ttk.Label(self.days_frame, text=dname, width=3, anchor="center").grid(row=0, column=i, padx=1, pady=1)

        self._paint_calendar()

    def _paint_calendar(self):
        for w in self.days_frame.grid_slaves():
            info = w.grid_info()
            if int(info.get("row", 0)) > 0:
                w.destroy()
        y, m = self._current.year, self._current.month
        meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        self.lbl_month.config(text=f"{meses[m]} {y}")
        month_days = calendar.monthcalendar(y, m)
        for r, week in enumerate(month_days, start=1):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                btn = ttk.Button(
                    self.days_frame,
                    text=str(day),
                    width=3,
                    command=lambda dd=day: self._select(dd),
                )
                btn.grid(row=r, column=c, padx=1, pady=1)

    def _select(self, day: int):
        try:
            self.result = self._current.replace(day=day)
        except ValueError:
            self.result = None
        self.destroy()

    def _prev_month(self):
        y, m = self._current.year, self._current.month
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
        self._current = self._current.replace(year=y, month=m, day=1)
        self._paint_calendar()

    def _next_month(self):
        y, m = self._current.year, self._current.month
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
        self._current = self._current.replace(year=y, month=m, day=1)
        self._paint_calendar()

class TerceroFicha(tk.Toplevel):
    def __init__(self, parent, tercero=None):
        super().__init__(parent)
        self.title("Tercero")
        self.resizable(False, False)
        self.result = None
        t = tercero or {}
        fields = [
            ("NIF", "nif", 18),
            ("Nombre", "nombre", 40),
            ("Direccion", "direccion", 40),
            ("CP", "cp", 10),
            ("Poblacion", "poblacion", 28),
            ("Provincia", "provincia", 28),
            ("Telefono", "telefono", 20),
            ("Email", "email", 28),
            ("Contacto", "contacto", 28),
        ]
        self.vars = {}
        self._nif_entry = None
        self._nif_normalizer_id = None
        for i, (lbl, key, width) in enumerate(fields):
            ttk.Label(self, text=lbl).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            v = tk.StringVar(value=str(t.get(key, "")))
            self.vars[key] = v
            entry = ttk.Entry(self, textvariable=v, width=width)
            entry.grid(row=i, column=1, sticky="w", padx=6, pady=3)
            if key == "nif":
                self._nif_entry = entry
                self._nif_normalizer_id = v.trace_add("write", lambda *_: self._on_nif_change())
        # Casilla para NIF extranjero (omitir validacion española)
        nif_actual = str(t.get("nif") or "")
        from utils.validaciones import validar_nif_cif_nie as _val
        nif_no_valido = bool(nif_actual) and not _val(normalizar_nif_cif(nif_actual))
        self.var_nif_extranjero = tk.BooleanVar(value=nif_no_valido)
        row_extra = len(fields)
        cb_ext = ttk.Checkbutton(
            self,
            text="NIF/CIF extranjero (omitir validacion española)",
            variable=self.var_nif_extranjero,
            command=self._on_extranjero_toggle,
        )
        cb_ext.grid(row=row_extra, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 4))
        btns = ttk.Frame(self)
        btns.grid(row=row_extra + 1, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _on_extranjero_toggle(self):
        """Activa/desactiva la normalizacion automatica del NIF segun la casilla."""
        v = self.vars["nif"]
        if self.var_nif_extranjero.get():
            # Quitar normalizador para no alterar NIFs extranjeros
            try:
                v.trace_remove("write", self._nif_normalizer_id)
            except Exception:
                pass
        else:
            # Restaurar normalizador y normalizar el valor actual
            self._nif_normalizer_id = v.trace_add("write", lambda *_: self._on_nif_change())
            v.set(normalizar_nif_cif(v.get()))

    def _on_nif_change(self):
        if self.var_nif_extranjero.get():
            return
        v = self.vars["nif"]
        current = v.get()
        normalized = normalizar_nif_cif(current)
        if current != normalized:
            v.set(normalized)

    def _ok(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        if not self.var_nif_extranjero.get():
            data["nif"] = normalizar_nif_cif(data.get("nif"))
        else:
            data["nif"] = str(data.get("nif") or "").strip().upper()
        data["_nif_extranjero"] = bool(self.var_nif_extranjero.get())
        self.result = data
        self.destroy()

class TercerosGlobalDialog(tk.Toplevel):
    def __init__(self, parent, gestor):
        super().__init__(parent)
        self.title("Terceros")
        self.geometry("1320x860")
        self.minsize(1120, 720)
        self.resizable(True, True)
        self.gestor = gestor
        self.controller = TercerosGlobalController(gestor, self)
        self._terceros_cache = []
        self._empresas_cache = []
        self._empresas_index = {}
        self._empresas_list = []
        self._build()
        self.controller.refresh()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _build(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill="both", expand=True)
        vscroll.pack(side=tk.RIGHT, fill="y")
        frm = ttk.Frame(canvas, padding=10)
        canvas_window = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(_event):
            canvas.itemconfigure(canvas_window, width=_event.width)

        def _on_mousewheel(_event):
            try:
                delta = int(-_event.delta / 120)
                if delta:
                    canvas.yview_scroll(delta, "units")
            except Exception:
                pass

        frm.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Nuevo", style="Primary.TButton", command=self.controller.nuevo).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Editar", command=self.controller.editar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar", command=self.controller.eliminar).pack(side=tk.LEFT, padx=4)

        filtro = ttk.Frame(frm)
        filtro.pack(fill="x", pady=(0, 6))
        ttk.Label(filtro, text="Buscar").pack(side=tk.LEFT, padx=(0, 6))
        self.var_buscar_tercero = tk.StringVar()
        entry_buscar = ttk.Entry(filtro, textvariable=self.var_buscar_tercero, width=30)
        entry_buscar.pack(side=tk.LEFT, padx=(0, 6))
        self.var_buscar_tercero.trace_add("write", lambda *_: self._apply_filtro_terceros())

        cols = ("nif", "nombre", "poblacion")
        self.tv = ttk.Treeview(frm, columns=cols, show="headings", height=12, selectmode="browse")
        self.tv.heading("nif", text="NIF")
        self.tv.column("nif", width=120)
        self.tv.heading("nombre", text="Nombre")
        self.tv.column("nombre", width=240)
        self.tv.heading("poblacion", text="Poblacion")
        self.tv.column("poblacion", width=160)
        self.tv.pack(fill="both", expand=True, pady=6)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.controller.load_empresas_asignadas())

        asignadas = ttk.LabelFrame(frm, text="Empresas asignadas")
        asignadas.pack(fill="x", pady=(0, 6))
        self.lb_empresas_asignadas = tk.Listbox(asignadas, height=4, exportselection=False)
        self.lb_empresas_asignadas.pack(fill="x", padx=6, pady=4)

        asignar = ttk.LabelFrame(frm, text="Asignar a empresa")
        asignar.pack(fill="x", pady=(4, 0))
        ttk.Label(asignar, text="Buscar").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.var_buscar_empresa = tk.StringVar()
        entry_buscar = ttk.Entry(asignar, textvariable=self.var_buscar_empresa, width=30)
        entry_buscar.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self.var_buscar_empresa.trace_add("write", lambda *_: self._apply_filtro_empresas())

        ttk.Label(asignar, text="Empresa").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.lb_empresas = tk.Listbox(asignar, height=5, exportselection=False)
        self.lb_empresas.grid(row=1, column=1, sticky="we", padx=6, pady=4)
        self.lb_empresas.bind("<<ListboxSelect>>", lambda e: self._update_ejercicios())

        ttk.Button(asignar, text="Asignar", style="Primary.TButton", command=self.controller.asignar_a_empresa).grid(row=0, column=3, rowspan=1, padx=6, pady=4)
        asignar.columnconfigure(1, weight=1)
        asignar.columnconfigure(3, weight=1)

    # --- helpers de vista
    def set_terceros(self, rows):
        self._terceros_cache = list(rows or [])
        self._apply_filtro_terceros()

    def set_empresas(self, empresas):
        self._empresas_cache = [e for e in (empresas or []) if e.get("ejercicio") is not None]
        self._empresas_index = {}
        for e in self._empresas_cache:
            key = str(e.get("codigo", ""))
            item = self._empresas_index.setdefault(key, {"codigo": key, "nombre": e.get("nombre", ""), "ejercicios": []})
            item["ejercicios"].append(e.get("ejercicio"))
        self._apply_filtro_empresas()

    def get_selected_tercero_id(self):
        sel = self.tv.selection()
        return sel[0] if sel else None

    def get_selected_empresa(self):
        sel = self.lb_empresas.curselection()
        if not sel:
            return None, []
        idx = sel[0]
        if idx < 0 or idx >= len(self._empresas_list):
            return None, []
        emp = self._empresas_list[idx]
        return emp.get("codigo"), []

    def select_tercero(self, tid):
        self.tv.selection_set(str(tid))

    def open_tercero_ficha(self, tercero):
        dlg = TerceroFicha(self, tercero)
        return dlg.result

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def set_empresas_asignadas(self, rows):
        self.lb_empresas_asignadas.delete(0, tk.END)
        for r in rows or []:
            codigo = r.get("codigo", "")
            nombre = r.get("nombre", "")
            texto = f"{codigo} - {nombre}"
            self.lb_empresas_asignadas.insert(tk.END, texto)

    def _apply_filtro_empresas(self):
        filtro = (self.var_buscar_empresa.get() or "").strip().lower()
        self.lb_empresas.delete(0, tk.END)
        self._empresas_list = []
        for emp in self._empresas_index.values():
            texto = f"{emp.get('codigo','')} {emp.get('nombre','')}".lower()
            if filtro and filtro not in texto:
                continue
            self._empresas_list.append(emp)
            self.lb_empresas.insert(tk.END, f"{emp.get('codigo','')} - {emp.get('nombre','')}")
        if self._empresas_list:
            self.lb_empresas.selection_set(0)
            self._update_ejercicios()
        else:
            pass

    def _update_ejercicios(self):
        return

    def _apply_filtro_terceros(self):
        filtro = (self.var_buscar_tercero.get() or "").strip().lower()
        selected = self.get_selected_tercero_id()
        self.tv.delete(*self.tv.get_children())
        for t in self._terceros_cache:
            nif = str(t.get("nif", ""))
            nombre = str(t.get("nombre", ""))
            poblacion = str(t.get("poblacion", ""))
            texto = f"{nif} {nombre} {poblacion}".lower()
            if filtro and filtro not in texto:
                continue
            self.tv.insert(
                "",
                tk.END,
                iid=str(t.get("id")),
                values=(nif, nombre, poblacion),
            )
        if selected and self.tv.exists(selected):
            self.tv.selection_set(selected)


class TercerosEmpresaDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa, ejercicio, ndig_plan):
        super().__init__(parent)
        self.title("Terceros de empresa")
        self.geometry("1240x820")
        self.minsize(1040, 680)
        self.resizable(True, True)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.ndig = ndig_plan
        self.controller = TercerosEmpresaController(gestor, codigo_empresa, ejercicio, ndig_plan, self)
        self._terceros_cache = []
        self._build()
        self.controller.refresh()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        bar = ttk.Frame(frm)
        bar.pack(fill="x")
        ttk.Button(bar, text="Suenlace terceros", command=self.controller.generar_suenlace_terceros).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar asignacion", command=self.controller.eliminar_asignacion).pack(side=tk.LEFT, padx=4)

        filtro = ttk.Frame(frm)
        filtro.pack(fill="x", pady=(6, 0))
        ttk.Label(filtro, text="Buscar").pack(side=tk.LEFT, padx=(0, 6))
        self.var_buscar_tercero = tk.StringVar()
        entry_buscar = ttk.Entry(filtro, textvariable=self.var_buscar_tercero, width=30)
        entry_buscar.pack(side=tk.LEFT, padx=(0, 6))
        self.var_buscar_tercero.trace_add("write", lambda *_: self._apply_filtro_terceros())

        cols = ("nif", "nombre", "poblacion")
        self.tv = ttk.Treeview(frm, columns=cols, show="headings", height=12, selectmode="browse")
        self.tv.heading("nif", text="NIF")
        self.tv.column("nif", width=120)
        self.tv.heading("nombre", text="Nombre")
        self.tv.column("nombre", width=240)
        self.tv.heading("poblacion", text="Poblacion")
        self.tv.column("poblacion", width=160)
        self.tv.pack(fill="both", expand=True, pady=6)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.controller.load_subcuentas())

        sub = ttk.LabelFrame(frm, text=f"Subcuentas en empresa {self.codigo}")
        sub.pack(fill="x", pady=(4, 0))
        ttk.Label(sub, text="Subcta cliente").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(sub, text="Subcta proveedor").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(sub, text="Subcta ingreso").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(sub, text="Subcta gasto").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.var_sub_cli = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_cli, width=18).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self.var_sub_pro = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_pro, width=18).grid(row=1, column=1, sticky="w", padx=6, pady=4)
        self.var_sub_ing = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_ing, width=18).grid(row=2, column=1, sticky="w", padx=6, pady=4)
        self.var_sub_gas = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_gas, width=18).grid(row=3, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(sub, text="Guardar", style="Primary.TButton", command=self.controller.guardar_subcuentas).grid(row=0, column=2, rowspan=4, padx=6, pady=4)

    # --- helpers de vista
    def set_terceros(self, rows):
        self._terceros_cache = list(rows or [])
        self._apply_filtro_terceros()

    def clear_subcuentas(self):
        self.var_sub_cli.set("")
        self.var_sub_pro.set("")
        self.var_sub_ing.set("")
        self.var_sub_gas.set("")

    def get_selected_id(self):
        sel = self.tv.selection()
        return sel[0] if sel else None

    def get_subcuenta_cliente(self):
        return self.var_sub_cli.get()

    def get_subcuenta_proveedor(self):
        return self.var_sub_pro.get()

    def get_subcuenta_ingreso(self):
        return self.var_sub_ing.get()

    def get_subcuenta_gasto(self):
        return self.var_sub_gas.get()

    def set_subcuentas(self, sc, sp, si, sg):
        self.var_sub_cli.set(sc)
        self.var_sub_pro.set(sp)
        self.var_sub_ing.set(si)
        self.var_sub_gas.set(sg)

    def _apply_filtro_terceros(self):
        filtro = (self.var_buscar_tercero.get() or "").strip().lower()
        selected = self.get_selected_id()
        self.tv.delete(*self.tv.get_children())
        for t in self._terceros_cache:
            nif = str(t.get("nif", ""))
            nombre = str(t.get("nombre", ""))
            poblacion = str(t.get("poblacion", ""))
            texto = f"{nif} {nombre} {poblacion}".lower()
            if filtro and filtro not in texto:
                continue
            self.tv.insert(
                "",
                tk.END,
                iid=str(t.get("id")),
                values=(nif, nombre, poblacion),
            )
        if selected and self.tv.exists(selected):
            self.tv.selection_set(selected)

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_save_dat_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default, parent=self)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_copiar_ejercicio(self, ejercicios):
        dlg = tk.Toplevel(self)
        dlg.title("Copiar terceros")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona el ejercicio de origen").pack(anchor="w")

        lb = tk.Listbox(frm, height=min(8, len(ejercicios)), exportselection=False)
        for ej in ejercicios:
            lb.insert(tk.END, str(ej))
        lb.pack(fill="both", expand=True, pady=6)
        if ejercicios:
            lb.selection_set(0)

        result = {"value": None}

        def _ok():
            sel = lb.curselection()
            if sel:
                try:
                    result["value"] = int(lb.get(sel[0]))
                except Exception:
                    result["value"] = None
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Copiar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=_cancel).pack(side=tk.LEFT, padx=4)

        dlg.wait_window(dlg)
        return result["value"]


class FacturaDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        gestor,
        codigo_empresa,
        ejercicio,
        ndig_plan,
        factura=None,
        numero_sugerido="",
        titulo="Factura emitida",
        on_open_company_config=None,
    ):
        super().__init__(parent)
        self.title(titulo)
        self.resizable(True, True)
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            dialog_w = max(1080, int(screen_w * 0.72))
            dialog_h = max(820, int(screen_h * 0.82))
            dialog_w = min(dialog_w, max(900, screen_w - 80))
            dialog_h = min(dialog_h, max(700, screen_h - 80))
            self.geometry(f"{dialog_w}x{dialog_h}")
            self.minsize(980, 720)
        except Exception:
            pass
        self.result = None
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.ndig = ndig_plan
        self._on_open_company_config = on_open_company_config
        self.factura = dict(factura or {})
        self.factura.setdefault("codigo_empresa", codigo_empresa)
        self.factura.setdefault("ejercicio", ejercicio)
        if "ejercicio" not in self.factura:
            self.factura["ejercicio"] = ejercicio
        if numero_sugerido and not self.factura.get("numero"):
            self.factura["numero"] = numero_sugerido
        f = self.factura

        self.controller = FacturaDialogController(gestor, codigo_empresa, ejercicio, ndig_plan, self.factura, self)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill="both", expand=True)
        vscroll.pack(side=tk.RIGHT, fill="y")
        frm = ttk.Frame(canvas, padding=10)
        canvas_window = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(_event):
            canvas.itemconfigure(canvas_window, width=_event.width)

        def _on_mousewheel(_event):
            try:
                delta = int(-_event.delta / 120)
                if delta:
                    canvas.yview_scroll(delta, "units")
            except Exception:
                pass

        frm.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        def add_row(label, var, row_idx, width=16, col=0):
            ttk.Label(frm, text=label).grid(row=row_idx, column=col, sticky="w", padx=4, pady=3)
            ttk.Entry(frm, textvariable=var, width=width).grid(row=row_idx, column=col + 1, padx=4, pady=3, sticky="w")

        today = date.today().strftime("%d/%m/%Y")
        self.var_serie = tk.StringVar(value=f.get("serie", ""))
        self.var_numero = tk.StringVar(value=f.get("numero", ""))
        self.var_numero_asiento = tk.StringVar(value=f.get("numero_asiento", ""))
        self.var_fecha_asiento = tk.StringVar(value=to_fecha_ui(f.get("fecha_asiento", today)))
        self.var_fecha_exp = tk.StringVar(value=to_fecha_ui(f.get("fecha_expedicion", f.get("fecha_asiento", today))))
        self.var_fecha_op = tk.StringVar(value=to_fecha_ui(f.get("fecha_operacion", today)) if f.get("fecha_operacion") else "")
        self._tipo_operacion_labels = [lbl for _, lbl in TIPOS_OPERACION_EMITIDAS]
        self._tipo_operacion_by_label = {lbl: cod for cod, lbl in TIPOS_OPERACION_EMITIDAS}
        self._tipo_operacion_by_code = {cod: lbl for cod, lbl in TIPOS_OPERACION_EMITIDAS}
        tipo_operacion_code = str(f.get("tipo_operacion") or "01").zfill(2)[-2:]
        self.var_tipo_operacion = tk.StringVar(
            value=self._tipo_operacion_by_code.get(tipo_operacion_code, TIPOS_OPERACION_EMITIDAS[0][1])
        )
        self._modelo_fiscal_labels = [lbl for _, lbl in MODELOS_FISCALES_EMITIDAS]
        self._modelo_fiscal_by_label = {lbl: cod for cod, lbl in MODELOS_FISCALES_EMITIDAS}
        self._modelo_fiscal_by_code = {cod: lbl for cod, lbl in MODELOS_FISCALES_EMITIDAS}
        modelo_fiscal_code = str(f.get("modelo_fiscal") or "").strip()
        self.var_modelo_fiscal = tk.StringVar(
            value=self._modelo_fiscal_by_code.get(modelo_fiscal_code, MODELOS_FISCALES_EMITIDAS[0][1])
        )
        self.var_nif = tk.StringVar(value=normalizar_nif_cif(f.get("nif", "")))
        _bind_nif_normalizer(self.var_nif)
        self.var_nombre = tk.StringVar(value=f.get("nombre", ""))
        self.var_desc = tk.StringVar(value=f.get("descripcion", ""))
        obs_val = f.get("observaciones")
        if obs_val in (None, ""):
            obs_val = f.get("descripcion", "")
        self.var_obs = tk.StringVar(value=obs_val)
        has_ret_flag = "retencion_aplica" in f
        ret_aplica = bool(f.get("retencion_aplica")) if has_ret_flag else False
        ret_pct = f.get("retencion_pct", "")
        ret_importe = f.get("retencion_importe", "")
        ret_base = f.get("retencion_base", "")
        if not has_ret_flag:
            for ln in f.get("lineas", []):
                pct_ln = to_float(ln.get("pct_irpf"))
                if pct_ln > 0:
                    ret_pct = pct_ln
                    ret_aplica = True
                    break
        if ret_importe in (None, "") and f.get("lineas"):
            ret_importe = sum(to_float(ln.get("cuota_irpf")) for ln in f.get("lineas", []))
        base_lineas = sum(to_float(ln.get("base")) for ln in f.get("lineas", []))
        if ret_base in (None, ""):
            pct_val = to_float(ret_pct)
            if ret_importe not in (None, "") and pct_val:
                ret_base = abs(to_float(ret_importe)) * 100.0 / pct_val
            else:
                ret_base = base_lineas if base_lineas else ""
        self.var_ret_aplica = tk.BooleanVar(value=ret_aplica)
        self.var_ret_pct = tk.StringVar(value=str(int(ret_pct)) if ret_pct not in (None, "", 0) else "")
        self.var_ret_base = tk.StringVar(
            value=fmt2(round2(ret_base)) if ret_base not in (None, "") else ""
        )
        self._retencion_manual = False
        self.var_ret_manual = tk.BooleanVar(value=self._retencion_manual)
        self._retencion_silent = False
        dtipo = (f.get("descuento_total_tipo") or "").strip().lower()
        dval = f.get("descuento_total_valor", "")
        self.var_desc_total_tipo = tk.StringVar(value="Ninguno")
        if dtipo == "pct":
            self.var_desc_total_tipo.set("%")
        elif dtipo == "imp":
            self.var_desc_total_tipo.set("€")
        self.var_desc_total_valor = tk.StringVar(value=str(dval) if dval not in (None, "") else "")
        self.var_subcuenta = tk.StringVar(value=f.get("subcuenta_cliente", ""))
        self.var_forma_pago = tk.StringVar(value=f.get("forma_pago", ""))
        self.var_cuenta_banco = tk.StringVar(value=f.get("cuenta_bancaria", ""))
        self.var_plantilla_word = tk.StringVar(value=f.get("plantilla_word", ""))
        self.var_plantilla_emitidas = tk.StringVar(value=f.get("plantilla_emitidas", ""))
        self._monedas = load_monedas()
        self._moneda_labels = []
        self._moneda_by_label = {}
        for m in self._monedas:
            codigo = str(m.get("codigo") or "").upper()
            simbolo = str(m.get("simbolo") or "")
            nombre = str(m.get("nombre") or "")
            label = f"{codigo} {simbolo}".strip()
            if nombre:
                label = f"{label} - {nombre}"
            self._moneda_labels.append(label)
            self._moneda_by_label[label] = {"codigo": codigo, "simbolo": simbolo, "nombre": nombre}
        moneda_default = ""
        if self._monedas:
            moneda_default = str(self._monedas[0].get("codigo") or "").upper()
        moneda_code = str(f.get("moneda_codigo") or moneda_default).upper()
        moneda_label = next((l for l in self._moneda_labels if l.startswith(moneda_code)), (self._moneda_labels[0] if self._moneda_labels else ""))
        self.var_moneda = tk.StringVar(value=moneda_label)
        self._moneda_simbolo = (self._moneda_by_label.get(moneda_label) or {}).get("simbolo", "")
        self._plantillas_word = self._listar_plantillas_word()
        if not self.var_plantilla_word.get().strip():
            if "factura_emitida_template.docx" in self._plantillas_word:
                self.var_plantilla_word.set("factura_emitida_template.docx")
            elif self._plantillas_word:
                self.var_plantilla_word.set(self._plantillas_word[0])
        self._plantillas_emitidas = self._listar_plantillas_emitidas()
        if not self.var_plantilla_emitidas.get().strip() and self._plantillas_emitidas:
            self.var_plantilla_emitidas.set(self._plantillas_emitidas[0])
        self._cuentas_banco = self._parse_cuentas_banco()
        if self.var_cuenta_banco.get().strip() and self.var_cuenta_banco.get().strip() not in self._cuentas_banco:
            self._cuentas_banco.append(self.var_cuenta_banco.get().strip())
        if not self.var_cuenta_banco.get().strip() and self._cuentas_banco:
            self.var_cuenta_banco.set(self._cuentas_banco[0])

        row = 0
        ttk.Label(frm, text="Seleccione Cliente").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_tercero = tk.StringVar()
        self.cb_tercero = ttk.Combobox(frm, textvariable=self.var_tercero, width=40, state="readonly")
        self.cb_tercero.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        ttk.Button(frm, text="Config. empresa", command=self._configurar_empresa).grid(row=row, column=2, padx=4, pady=3)
        row += 1

        ttk.Label(frm, text="Serie").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        series_disponibles = list(f.get("_series_disponibles") or [])
        self._series_nombres = [s["nombre"] for s in series_disponibles] if series_disponibles else [str(f.get("serie", ""))]
        self.cb_serie = ttk.Combobox(frm, textvariable=self.var_serie, values=self._series_nombres, width=10, state="readonly" if self._series_nombres else "normal")
        self.cb_serie.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        self.cb_serie.bind("<<ComboboxSelected>>", lambda e: self._on_serie_changed())
        row += 1

        add_row("Numero", self.var_numero, row, width=14, col=0)
        row += 1

        add_row("Nº asiento", self.var_numero_asiento, row, width=14, col=0)
        row += 1
        
        add_row("Subcuenta cliente", self.var_subcuenta, row, col=0, width=18)
        row += 1

        ttk.Label(frm, text="Forma de pago").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(frm, textvariable=self.var_forma_pago, values=["Transferencia","Confirming","Cheque","Contado"], width=18, state="readonly").grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Cuenta bancaria").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.cb_cuenta_banco = ttk.Combobox(frm, textvariable=self.var_cuenta_banco, values=self._cuentas_banco, width=28, state="readonly")
        self.cb_cuenta_banco.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Moneda").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.cb_moneda = ttk.Combobox(frm, textvariable=self.var_moneda, values=self._moneda_labels, width=28, state="readonly")
        self.cb_moneda.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        self.cb_moneda.bind("<<ComboboxSelected>>", lambda e: self._on_moneda_change())
        row += 1

        ttk.Label(frm, text="Plantilla Word").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.cb_plantilla_word = ttk.Combobox(
            frm,
            textvariable=self.var_plantilla_word,
            values=self._plantillas_word,
            width=28,
            state="readonly",
        )
        self.cb_plantilla_word.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        def add_date_cell(label, var, row_idx):
            ttk.Label(frm, text=label).grid(row=row_idx, column=0, sticky="w", padx=4, pady=3)
            cont = ttk.Frame(frm)
            cont.grid(row=row_idx, column=1, columnspan=2, sticky="w", padx=4, pady=3)
            ttk.Entry(cont, textvariable=var, width=14).pack(side=tk.LEFT)
            ttk.Button(cont, text="Cal", width=4, command=lambda v=var: self._pick_date(v)).pack(side=tk.LEFT, padx=(4, 0))

        add_date_cell("Fecha Factura", self.var_fecha_exp, row)
        #add_date_cell("Fecha Expedicion", self.var_fecha_exp, row, 2)
        #add_date_cell("Fecha Operacion", self.var_fecha_op, row, 3)
        row += 1
        ttk.Label(frm, text="Tipo operacion").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.cb_tipo_operacion = ttk.Combobox(
            frm,
            textvariable=self.var_tipo_operacion,
            values=self._tipo_operacion_labels,
            width=46,
            state="readonly",
        )
        self.cb_tipo_operacion.grid(row=row, column=1, columnspan=2, padx=4, pady=3, sticky="w")
        row += 1
        ttk.Label(frm, text="Modelo fiscal").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.cb_modelo_fiscal = ttk.Combobox(
            frm,
            textvariable=self.var_modelo_fiscal,
            values=self._modelo_fiscal_labels,
            width=46,
            state="readonly",
        )
        self.cb_modelo_fiscal.grid(row=row, column=1, columnspan=2, padx=4, pady=3, sticky="w")
        row += 1
        add_row("NIF Cliente", self.var_nif, row)
        row += 1
        add_row("Nombre Cliente", self.var_nombre, row, width=34)
        row += 1
        add_row("Observaciones", self.var_obs, row, width=46)
        row += 1

        ret_row = ttk.Frame(frm)
        ret_row.grid(row=row, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 2))
        ttk.Checkbutton(
            ret_row,
            text="Factura con retencion",
            variable=self.var_ret_aplica,
            command=self._on_retencion_toggle,
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.cb_ret_manual = ttk.Checkbutton(
            ret_row,
            text="Base IRPF manual",
            variable=self.var_ret_manual,
            command=self._on_retencion_manual_toggle,
        )
        self.cb_ret_manual.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(ret_row, text="Tipo %").pack(side=tk.LEFT)
        self.cb_ret_pct = ttk.Combobox(
            ret_row,
            textvariable=self.var_ret_pct,
            values=[str(x) for x in IRPF_RET_OPCIONES],
            width=6,
            state="readonly",
        )
        self.cb_ret_pct.pack(side=tk.LEFT, padx=4)
        ttk.Label(ret_row, text="Base IRPF").pack(side=tk.LEFT, padx=(8, 0))
        self.entry_ret_base = ttk.Entry(ret_row, textvariable=self.var_ret_base, width=12)
        self.entry_ret_base.pack(side=tk.LEFT, padx=4)
        row += 1

        desc_row = ttk.Frame(frm)
        desc_row.grid(row=row, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 2))
        ttk.Label(desc_row, text="Descuento total").pack(side=tk.LEFT, padx=(0, 6))
        self.cb_desc_total = ttk.Combobox(
            desc_row,
            textvariable=self.var_desc_total_tipo,
            values=["Ninguno", "%", "€"],
            width=10,
            state="readonly",
        )
        self.cb_desc_total.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_desc_total = ttk.Entry(desc_row, textvariable=self.var_desc_total_valor, width=12)
        self.entry_desc_total.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(desc_row, text="(aplica sobre base)").pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Lineas").grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        row += 1

        self.line_vars = {
            "concepto": tk.StringVar(),
            "unidades": tk.StringVar(),
            "precio": tk.StringVar(),
            "iva": tk.StringVar(),
            "desc_tipo": tk.StringVar(),
            "desc_val": tk.StringVar(),
        }
        self.var_line_obs = tk.BooleanVar(value=False)
        editor = ttk.Frame(frm)
        editor.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4)
        editor.columnconfigure(13, weight=1)
        ttk.Label(editor, text="Concepto").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["concepto"], width=26).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(editor, text="Unidades").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        self.entry_unidades = ttk.Entry(editor, textvariable=self.line_vars["unidades"], width=10)
        self.entry_unidades.grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(editor, text="Precio").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        self.entry_precio = ttk.Entry(editor, textvariable=self.line_vars["precio"], width=10)
        self.entry_precio.grid(row=0, column=5, padx=4, pady=2)
        ttk.Label(editor, text="Desc.").grid(row=0, column=6, padx=4, pady=2, sticky="w")
        self.cb_desc_tipo = ttk.Combobox(editor, textvariable=self.line_vars["desc_tipo"], values=["", "%", "€"], width=4, state="readonly")
        self.cb_desc_tipo.grid(row=0, column=7, padx=4, pady=2)
        self.entry_desc_val = ttk.Entry(editor, textvariable=self.line_vars["desc_val"], width=8)
        self.entry_desc_val.grid(row=0, column=8, padx=4, pady=2)
        ttk.Label(editor, text="IVA %").grid(row=0, column=9, padx=4, pady=2, sticky="w")
        self.cb_iva = ttk.Combobox(editor, textvariable=self.line_vars["iva"], values=[str(x) for x in IVA_OPCIONES], width=6, state="readonly")
        self.cb_iva.grid(row=0, column=10, padx=4, pady=2)
        ttk.Checkbutton(editor, text="Observacion", variable=self.var_line_obs, command=self._on_line_obs_toggle).grid(row=0, column=11, padx=6)
        ttk.Button(editor, text="Añadir/Actualizar", style="Primary.TButton", command=self._add_update_linea).grid(row=0, column=12, padx=6)
        ttk.Button(editor, text="Limpiar", command=self._clear_line_editor).grid(row=0, column=13, padx=4)
        row += 1

        self.tv = ttk.Treeview(
            frm,
            columns=("concepto", "unidades", "precio", "desc", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf", "desc_tipo", "desc_val", "tipo_linea"),
            displaycolumns=("concepto", "unidades", "precio", "desc", "base", "pct_iva", "cuota_iva"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        headers = {
            "concepto": "Concepto",
            "unidades": "Unid",
            "precio": "P. unit",
            "desc": "Desc.",
            "base": "Base",
            "pct_iva": "% IVA",
            "cuota_iva": "Cuota IVA",
        }
        for c, h in headers.items():
            self.tv.heading(c, text=h)
            self.tv.column(c, width=90 if c == "concepto" else 70, anchor="e" if c != "concepto" else "w")
        self.tv.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)
        self.tv.bind("<<TreeviewSelect>>", self._on_select_linea)
        row += 1

        bar = ttk.Frame(frm)
        bar.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Button(bar, text="Subir linea", command=self._move_linea_up).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Bajar linea", command=self._move_linea_down).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar linea", command=self._del_linea).pack(side=tk.LEFT, padx=4)
        row += 1

        tot = ttk.Frame(frm)
        tot.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        self.lbl_tot_base = ttk.Label(tot, text="Base: 0,00")
        self.lbl_tot_iva = ttk.Label(tot, text="IVA: 0,00")
        self.lbl_tot_ret = ttk.Label(tot, text="IRPF: 0,00")
        self.lbl_tot_total = ttk.Label(tot, text="Total: 0,00", font=("Segoe UI", 10, "bold"))
        for i, lbl in enumerate([self.lbl_tot_base, self.lbl_tot_iva, self.lbl_tot_ret, self.lbl_tot_total]):
            lbl.grid(row=0, column=i, padx=6)
        row += 1

        iva_frame = ttk.LabelFrame(frm, text="Detalle IVA")
        iva_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4, pady=(0, 8))
        self.tv_iva = ttk.Treeview(
            iva_frame,
            columns=("tipo", "base", "cuota"),
            show="headings",
            height=4,
        )
        self.tv_iva.heading("tipo", text="Tipo IVA")
        self.tv_iva.heading("base", text="Base")
        self.tv_iva.heading("cuota", text="Cuota IVA")
        self.tv_iva.column("tipo", width=90, anchor="w")
        self.tv_iva.column("base", width=100, anchor="e")
        self.tv_iva.column("cuota", width=100, anchor="e")
        self.tv_iva.pack(fill="x", expand=True, padx=6, pady=4)
        row += 1

        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=3, pady=(6, 2))
        ttk.Button(btns, text="Guardar factura", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Guardar borrador", command=self._ok_borrador).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self._load_terceros()
        self._preselect_tercero(f.get("tercero_id"))

        for ln in f.get("lineas", []):
            self._insert_linea(ln)
        self.var_ret_pct.trace_add("write", lambda *_: self._on_retencion_pct_change())
        self.var_ret_base.trace_add("write", lambda *_: self._on_retencion_base_change())
        self.var_desc_total_tipo.trace_add("write", lambda *_: self._refresh_totales())
        self.var_desc_total_valor.trace_add("write", lambda *_: self._refresh_totales())
        self._update_retencion_state()
        if self.var_ret_aplica.get():
            self.controller.apply_retencion_header()
        self._refresh_totales()
        self._update_line_obs_state()

        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _parse_cuentas_banco(self):
        emp = self.gestor.get_empresa(self.codigo, self.ejercicio) or {}
        raw = emp.get("cuentas_bancarias") or ""
        if not str(raw).strip():
            raw = emp.get("cuenta_bancaria") or ""
        parts = []
        for sep in ["\n", ";", ","]:
            raw = str(raw).replace(sep, ",")
        for p in str(raw).split(","):
            p = p.strip()
            if p:
                parts.append(p)
        out = []
        for p in parts:
            if p not in out:
                out.append(p)
        return out

    def _listar_plantillas_word(self):
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parents[1]
        from utils.utilidades import get_word_templates_dir
        plantillas_dir = Path(get_word_templates_dir(str(base_dir / "plantillas")))
        if not plantillas_dir.exists():
            return []
        items = [p.name for p in plantillas_dir.glob("*.docx") if p.is_file()]
        return sorted(items, key=lambda s: s.lower())

    def _listar_plantillas_emitidas(self):
        try:
            items = [p.get("nombre") for p in self.gestor.listar_emitidas(self.codigo, self.ejercicio)]
        except Exception:
            items = []
        return [x for x in items if str(x or "").strip()]

    # --- controlador
    def _load_terceros(self):
        self.controller.load_terceros()

    def _preselect_tercero(self, tercero_id):
        self.controller.preselect_tercero(tercero_id)

    def _configurar_empresa(self):
        self.controller.configurar_empresa()

    def _on_tercero_selected(self):
        self.controller.on_tercero_selected()

    def _pick_date(self, target_var: tk.StringVar):
        self.controller.pick_date(target_var)

    def _clear_line_editor(self):
        self.controller.clear_line_editor()

    def _add_update_linea(self):
        self.controller.add_update_linea()

    def _del_linea(self):
        self.controller.del_linea()

    def _move_linea_up(self):
        self.controller.move_linea_up()

    def _move_linea_down(self):
        self.controller.move_linea_down()

    def _refresh_totales(self):
        self.controller.refresh_totales()

    def _insert_linea(self, ln: dict):
        self.controller.insert_linea(ln)

    def _ok(self):
        self.controller.ok()

    def _ok_borrador(self):
        self.controller.ok_borrador()

    def _on_serie_changed(self):
        nombre = self.var_serie.get().strip()
        if nombre:
            self.controller.on_serie_selected(nombre)

    def set_numero(self, numero: str):
        self.var_numero.set(numero)

    def _on_select_linea(self, event=None):
        sel = self.tv.selection()
        if not sel:
            return
        vals = self.tv.item(sel[0], "values")
        if not vals:
            return
        tipo = vals[11] if len(vals) > 11 else ""
        self.var_line_obs.set(str(tipo).strip().lower() == "obs")
        self._update_line_obs_state()
        self.line_vars["concepto"].set(vals[0])
        self.line_vars["unidades"].set(vals[1])
        self.line_vars["precio"].set(vals[2])
        if len(vals) > 3:
            dt = vals[9] if len(vals) > 9 else ""
            if dt == "pct":
                dt = "%"
            elif dt == "imp":
                dt = "€"
            self.line_vars["desc_tipo"].set(dt)
            self.line_vars["desc_val"].set(vals[10] if len(vals) > 10 else "")
        if len(vals) > 5:
            self.line_vars["iva"].set(vals[5])

    def _on_line_obs_toggle(self):
        self._update_line_obs_state()

    def _update_line_obs_state(self):
        is_obs = bool(self.var_line_obs.get())
        self.entry_unidades.config(state="disabled" if is_obs else "normal")
        self.entry_precio.config(state="disabled" if is_obs else "normal")
        self.entry_desc_val.config(state="disabled" if is_obs else "normal")
        self.cb_desc_tipo.config(state="disabled" if is_obs else "readonly")
        self.cb_iva.config(state="disabled" if is_obs else "readonly")
        if is_obs:
            self.line_vars["unidades"].set("")
            self.line_vars["precio"].set("")
            self.line_vars["iva"].set("")
            self.line_vars["desc_tipo"].set("")
            self.line_vars["desc_val"].set("")

    def _on_retencion_toggle(self):
        self._update_retencion_state()
        self.controller.retencion_toggled()

    def _on_retencion_manual_toggle(self):
        self._retencion_manual = bool(self.var_ret_manual.get())
        self._update_retencion_state()
        if not self._retencion_manual:
            self.controller.retencion_base_changed()

    def _on_retencion_pct_change(self):
        if self._retencion_silent:
            return
        self._update_retencion_state()
        self.controller.retencion_pct_changed()

    def _on_retencion_base_change(self):
        if self._retencion_silent:
            return
        if not self._retencion_manual:
            return
        self.controller.retencion_base_changed()

    def _on_moneda_change(self):
        label = self.var_moneda.get()
        self._moneda_simbolo = (self._moneda_by_label.get(label) or {}).get("simbolo", "")
        self.set_lineas(self.get_lineas())
        self._refresh_totales()

    def _update_retencion_state(self):
        aplica = bool(self.var_ret_aplica.get())
        if aplica and not (self.var_ret_pct.get() or "").strip():
            self.set_retencion_pct(str(IRPF_RET_OPCIONES[0]))
        self.cb_ret_pct.config(state="readonly" if aplica else "disabled")
        self.cb_ret_manual.config(state="normal" if aplica else "disabled")
        if not aplica:
            self._retencion_manual = False
            self.var_ret_manual.set(False)
        self.entry_ret_base.config(state="normal" if (aplica and self._retencion_manual) else "disabled")

    # --- helpers de vista para el controlador
    def set_terceros(self, values):
        self.cb_tercero["values"] = values
        self.cb_tercero.bind("<<ComboboxSelected>>", lambda e: self._on_tercero_selected())

    def select_tercero_index(self, idx):
        self.cb_tercero.current(idx)

    def get_selected_tercero_index(self):
        return self.cb_tercero.current()

    def set_nif(self, value):
        self.var_nif.set(normalizar_nif_cif(value))

    def set_nombre(self, value):
        self.var_nombre.set(value)

    def set_subcuenta(self, value):
        self.var_subcuenta.set(value)

    def set_cuenta_bancaria(self, value):
        self.var_cuenta_banco.set(value)

    def parse_date(self, text):
        return parse_date_ui(text)

    def open_date_picker(self, initial):
        dlg = DatePicker(self, initial)
        return dlg.result if dlg.result else None

    def clear_line_editor(self):
        for v in self.line_vars.values():
            v.set("")
        self.var_line_obs.set(False)
        self._update_line_obs_state()
        self.tv.selection_remove(self.tv.selection())

    def get_line_editor_values(self):
        concepto = self.line_vars["concepto"].get().strip()
        unidades = to_float(self.line_vars["unidades"].get())
        precio = to_float(self.line_vars["precio"].get())
        iva_raw = self.line_vars["iva"].get()
        iva = to_float(iva_raw)
        desc_tipo_ui = (self.line_vars["desc_tipo"].get() or "").strip()
        desc_tipo = "pct" if desc_tipo_ui == "%" else "imp" if desc_tipo_ui == "€" else ""
        desc_val = to_float(self.line_vars["desc_val"].get())
        return concepto, unidades, precio, iva, iva_raw, desc_tipo, desc_val

    def is_line_observacion(self):
        return bool(self.var_line_obs.get())

    def upsert_line_row(self, ln: dict):
        desc_txt = self._format_desc(ln)
        is_obs = str(ln.get("tipo") or "").strip().lower() == "obs"
        sym = self._moneda_simbolo
        vals = (
            ln["concepto"],
            "" if is_obs else fmt2(ln["unidades"]),
            "" if is_obs else fmt4(ln["precio"]),
            desc_txt,
            "" if is_obs else fmt2s(ln["base"], sym),
            "" if is_obs else fmt2(ln["pct_iva"]),
            "" if is_obs else fmt2s(ln["cuota_iva"], sym),
            "" if is_obs else fmt2(ln["pct_irpf"]),
            "" if is_obs else fmt2s(ln["cuota_irpf"], sym),
            ln.get("descuento_tipo", ""),
            "" if is_obs else fmt2(round2(ln.get("descuento_valor"))),
            ln.get("tipo", ""),
        )
        sel = self.tv.selection()
        if sel:
            self.tv.item(sel[0], values=vals)
        else:
            self.tv.insert("", tk.END, values=vals)

    def insert_line_row(self, ln: dict):
        desc_txt = self._format_desc(ln)
        is_obs = str(ln.get("tipo") or "").strip().lower() == "obs"
        sym = self._moneda_simbolo
        vals = (
            ln.get("concepto", ""),
            "" if is_obs else fmt2(round2(ln.get("unidades"))),
            "" if is_obs else fmt4(round4(ln.get("precio"))),
            desc_txt,
            "" if is_obs else fmt2s(round2(ln.get("base")), sym),
            "" if is_obs else fmt2(round2(ln.get("pct_iva"))),
            "" if is_obs else fmt2s(round2(ln.get("cuota_iva")), sym),
            "" if is_obs else fmt2(round2(ln.get("pct_irpf"))),
            "" if is_obs else fmt2s(round2(ln.get("cuota_irpf")), sym),
            ln.get("descuento_tipo", ""),
            "" if is_obs else fmt2(round2(ln.get("descuento_valor"))),
            ln.get("tipo", ""),
        )
        self.tv.insert("", tk.END, values=vals)

    def set_lineas(self, lineas):
        self.tv.delete(*self.tv.get_children())
        for ln in lineas or []:
            self.insert_line_row(ln)

    def delete_selected_line(self):
        sel = self.tv.selection()
        if sel:
            self.tv.delete(sel[0])
            return True
        return False

    def move_selected_line(self, offset: int) -> bool:
        sel = self.tv.selection()
        if not sel:
            return False
        iid = sel[0]
        items = list(self.tv.get_children())
        try:
            idx = items.index(iid)
        except ValueError:
            return False
        new_idx = idx + int(offset)
        if new_idx < 0 or new_idx >= len(items) or new_idx == idx:
            return False
        self.tv.move(iid, "", new_idx)
        self.tv.selection_set(iid)
        self.tv.focus(iid)
        self.tv.see(iid)
        return True

    def get_lineas(self):
        out = []
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values")
            if not vals:
                continue
            tipo = vals[11] if len(vals) > 11 else ""
            out.append(
                {
                    "concepto": vals[0],
                    "unidades": round2(to_float(vals[1])),
                    "precio": round4(to_float(vals[2])),
                    "base": round2(to_float(vals[4])),
                    "pct_iva": round2(to_float(vals[5])),
                    "cuota_iva": round2(to_float(vals[6])),
                    "pct_irpf": round2(to_float(vals[7])),
                    "cuota_irpf": round2(to_float(vals[8])),
                    "descuento_tipo": vals[9] if len(vals) > 9 else "",
                    "descuento_valor": round2(to_float(vals[10])) if len(vals) > 10 else 0.0,
                    "pct_re": 0.0,
                    "cuota_re": 0.0,
                    "tipo": tipo,
                }
            )
        return out

    def set_totales(self, base, iva, ret, total):
        sym = self._moneda_simbolo
        self.lbl_tot_base.config(text=f"Base: {fmt2s(base, sym)}")
        self.lbl_tot_iva.config(text=f"IVA: {fmt2s(iva, sym)}")
        self.lbl_tot_ret.config(text=f"IRPF: {fmt2s(ret, sym)}")
        self.lbl_tot_total.config(text=f"Total: {fmt2s(total, sym)}")

    def set_iva_resumen(self, rows):
        self.tv_iva.delete(*self.tv_iva.get_children())
        sym = self._moneda_simbolo
        for r in rows:
            self.tv_iva.insert(
                "",
                tk.END,
                values=(r.get("tipo", ""), fmt2s(round2(r.get("base")), sym), fmt2s(round2(r.get("cuota")), sym)),
            )

    def get_retencion_aplica(self):
        return bool(self.var_ret_aplica.get())

    def get_retencion_pct(self):
        return to_float(self.var_ret_pct.get())

    def get_retencion_base(self):
        return to_float(self.var_ret_base.get())

    def get_retencion_importe(self):
        base = self.get_retencion_base()
        pct = self.get_retencion_pct()
        signo = 1.0 if base < 0 else -1.0
        return round2(signo * abs(base * pct / 100.0)) if pct else 0.0

    def is_retencion_manual(self):
        return self._retencion_manual

    def set_retencion_manual(self, manual: bool):
        self._retencion_manual = bool(manual)

    def set_retencion_base(self, value: str):
        self._retencion_silent = True
        try:
            val = to_float(value)
            self.var_ret_base.set(fmt2(val) if value not in ("", None) else "")
        except Exception:
            self.var_ret_base.set(value)
        self._retencion_silent = False

    def set_retencion_pct(self, value: str):
        self._retencion_silent = True
        self.var_ret_pct.set(value)
        self._retencion_silent = False

    def get_descuento_total(self):
        tipo_ui = (self.var_desc_total_tipo.get() or "").strip()
        tipo = "pct" if tipo_ui == "%" else "imp" if tipo_ui == "€" else ""
        try:
            valor = to_float(self.var_desc_total_valor.get())
        except Exception:
            valor = 0.0
        return tipo, valor

    def _format_desc(self, ln: dict) -> str:
        if str(ln.get("tipo") or "").strip().lower() == "obs":
            return ""
        t = (ln.get("descuento_tipo") or "").strip().lower()
        v = round2(ln.get("descuento_valor"))
        if not t or not v:
            return ""
        if t == "pct":
            return f"{fmt2(v)}%"
        return fmt2(v)

    def get_numero_factura(self):
        return self.var_numero.get().strip()

    def get_numero_asiento(self):
        return self.var_numero_asiento.get().strip()

    def get_subcuenta(self):
        return self.var_subcuenta.get().strip()

    def get_fecha_exp(self):
        return self.var_fecha_exp.get().strip()

    def get_serie(self):
        return self.var_serie.get().strip()

    def get_tipo_operacion(self):
        label = self.var_tipo_operacion.get()
        return self._tipo_operacion_by_label.get(label, "01")

    def get_modelo_fiscal(self):
        label = self.var_modelo_fiscal.get()
        return self._modelo_fiscal_by_label.get(label, "")

    def get_nif(self):
        return normalizar_nif_cif(self.var_nif.get())

    def get_nombre(self):
        return self.var_nombre.get().strip()

    def get_descripcion(self):
        return self.var_desc.get().strip()

    def get_observaciones(self):
        return self.var_obs.get().strip()

    def get_forma_pago(self):
        return self.var_forma_pago.get().strip()

    def get_cuenta_bancaria(self):
        return self.var_cuenta_banco.get().strip()

    def get_moneda(self):
        label = self.var_moneda.get()
        data = self._moneda_by_label.get(label) or {}
        return data.get("codigo", ""), data.get("simbolo", "")

    def get_plantilla_word(self):
        return self.var_plantilla_word.get().strip()

    def get_plantilla_emitidas(self):
        return self.var_plantilla_emitidas.get().strip()

    def open_company_config(self):
        if not self._on_open_company_config:
            self.show_warning("Gest2A3Eco", "La configuracion de empresa no esta disponible.")
            return False
        return bool(self._on_open_company_config())

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def set_result_and_close(self, result):
        self.result = result
        self.destroy()
class UIFacturasEmitidas(ttk.Frame):
    def __init__(
        self,
        master,
        gestor,
        codigo_empresa,
        ejercicio,
        nombre_empresa,
        allow_all_years: bool = False,
        session=None,
        on_open_company_config=None,
    ):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.allow_all_years = bool(allow_all_years)
        self.session = session
        self._on_open_company_config = on_open_company_config
        self._marked_factura_ids = set()
        monedas = load_monedas()
        self._default_moneda_simbolo = str(monedas[0].get("simbolo")) if monedas else ""
        base = {
            "nombre": nombre_empresa,
            "digitos_plan": 8,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 1,
            "serie_emitidas_rect": "R",
            "siguiente_num_emitidas_rect": 1,
            "cuenta_bancaria": "",
            "cuentas_bancarias": "",
            "ejercicio": "",
            "cif": "",
            "direccion": "",
            "poblacion": "",
            "provincia": "",
            "cp": "",
            "telefono": "",
            "email": "",
            "logo_path": "",
        }
        emp_conf = gestor.get_empresa(codigo_empresa, ejercicio) or {}
        base.update(emp_conf)
        self.empresa_conf = base
        self.controller = FacturasEmitidasController(gestor, codigo_empresa, ejercicio, self.empresa_conf, self, allow_all_years=self.allow_all_years)
        self._sort_state = {}
        self._build()

    # ------------------- UI -------------------
    def _build(self):
        ttk.Label(self, text=f"Facturas emitidas de {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        tab_facturas = ttk.Frame(nb)
        tab_albaranes = ttk.Frame(nb)
        nb.add(tab_facturas, text="Facturas")
        is_cliente = bool(self.session and self.session.role.value == "cliente")
        if not is_cliente:
            nb.add(tab_albaranes, text="Albaranes")

        self._build_facturas_tab(tab_facturas)
        if not is_cliente:
            self._build_albaranes_tab(tab_albaranes)

        self._refresh_facturas()
        if not is_cliente:
            self._refresh_albaranes()

    def _build_facturas_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=20, pady=(8, 0))
        can_write = getattr(getattr(self.gestor, "security", None), "can_write_company", lambda _c: True)(self.codigo)
        is_cliente = bool(self.session and self.session.role.value == "cliente")
        self.btn_fact_nueva = ttk.Button(top, text="Nueva", style="Primary.TButton", command=self._nueva)
        self.btn_fact_nueva.pack(side=tk.LEFT, padx=8)
        self.btn_fact_nueva_rect = ttk.Button(top, text="Nueva Rectif.", command=self._nueva_rectificativa)
        self.btn_fact_nueva_rect.pack(side=tk.LEFT, padx=8)
        self.btn_fact_editar = ttk.Button(top, text="Editar", command=self._editar)
        self.btn_fact_editar.pack(side=tk.LEFT, padx=8)
        self.btn_fact_copiar = ttk.Button(top, text="Copiar", command=self._copiar)
        self.btn_fact_copiar.pack(side=tk.LEFT, padx=8)
        self.btn_fact_rectificar = ttk.Button(top, text="Rectificar", command=self._rectificar)
        self.btn_fact_rectificar.pack(side=tk.LEFT, padx=8)
        self.btn_fact_eliminar = ttk.Button(top, text="Eliminar", command=self._eliminar)
        self.btn_fact_eliminar.pack(side=tk.LEFT, padx=8)
        self.btn_fact_confirmar = ttk.Button(top, text="Confirmar borrador", command=self._confirmar_borrador)
        self.btn_fact_confirmar.pack(side=tk.LEFT, padx=8)
        self.btn_fact_desmarcar = ttk.Button(top, text="Desmarcar enlazadas", command=self._desmarcar_generadas)
        self.btn_fact_desmarcar.pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Exportar PDF", command=self._export_pdf).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Abrir PDF", command=self._abrir_pdf).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Compartir PDF", command=self._compartir_pdf).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="PDF seleccion", command=self._export_pdf_multiple).pack(side=tk.LEFT, padx=8)
        if not can_write:
            for btn in (
                self.btn_fact_nueva,
                self.btn_fact_nueva_rect,
                self.btn_fact_editar,
                self.btn_fact_copiar,
                self.btn_fact_rectificar,
                self.btn_fact_eliminar,
                self.btn_fact_confirmar,
                self.btn_fact_desmarcar,
            ):
                btn.configure(state="disabled")

        filtros = ttk.Frame(parent)
        filtros.pack(fill="x", padx=20, pady=(6, 0))
        if self.allow_all_years:
            ttk.Label(filtros, text="Año").pack(side=tk.LEFT)
            self.var_fact_year = tk.StringVar(value="Todos")
            self.cb_fact_year = ttk.Combobox(filtros, textvariable=self.var_fact_year, width=8, state="readonly")
            self.cb_fact_year.pack(side=tk.LEFT, padx=6)
            self.cb_fact_year.bind("<<ComboboxSelected>>", lambda e: self.controller.apply_facturas_filter())
        ttk.Label(filtros, text="Serie:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_fact_serie_filter = tk.StringVar(value="Todas")
        self.cb_fact_serie = ttk.Combobox(filtros, textvariable=self.var_fact_serie_filter, width=8, state="readonly")
        self.cb_fact_serie.pack(side=tk.LEFT, padx=6)
        self.cb_fact_serie.bind("<<ComboboxSelected>>", lambda e: self.controller.apply_facturas_filter())
        ttk.Label(filtros, text="Cliente:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_fact_cliente_filter = tk.StringVar()
        self.var_fact_cliente_filter.trace_add("write", lambda *_: self.controller.apply_facturas_filter())
        ttk.Entry(filtros, textvariable=self.var_fact_cliente_filter, width=28).pack(side=tk.LEFT, padx=6)

        self.tv = ttk.Treeview(
            parent,
            columns=("marcar", "ejercicio", "serie", "numero", "asiento", "fecha", "cliente", "total", "generada", "fecha_gen", "enviado", "fecha_envio"),
            show="headings",
            selectmode="extended",
            height=12,
        )
        cols = [
            ("marcar", "Generar", 70, "center"),
            ("ejercicio", "Ejercicio", 90, "center"),
            ("serie", "Serie", 70, "center"),
            ("numero", "Numero", 110, "w"),
            ("asiento", "Asiento", 100, "w"),
            ("fecha", "Fecha", 100, "w"),
            ("cliente", "Cliente", 240, "w"),
            ("total", "Total", 100, "e"),
            ("generada", "Generada", 90, "center"),
            ("fecha_gen", "Fecha gen.", 110, "w"),
            ("enviado", "Enviado", 90, "center"),
            ("fecha_envio", "Fecha envio", 110, "w"),
        ]
        for c, h, w, align in cols:
            self.tv.heading(c, text=h, command=lambda col=c: self._sort_facturas(col))
            self.tv.column(c, width=w, anchor=align)
        self.tv.pack(fill="both", expand=True, padx=10, pady=8)
        self.tv.tag_configure("borrador", foreground="#888888", font=("", 9, "italic"))
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._on_factura_select())
        self.tv.bind("<Button-1>", self._on_factura_click, add="+")

        detalle = ttk.LabelFrame(parent, text="Detalle de factura")
        detalle.pack(fill="x", padx=10, pady=(0, 6))
        self.tv_detalle = ttk.Treeview(
            detalle,
            columns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf"),
            displaycolumns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        headers_det = {
            "concepto": "Concepto",
            "unidades": "Unid",
            "precio": "P. unit",
            "base": "Base",
            "pct_iva": "% IVA",
            "cuota_iva": "Cuota IVA",
        }
        for c, h in headers_det.items():
            self.tv_detalle.heading(c, text=h)
            self.tv_detalle.column(c, width=90 if c == "concepto" else 70, anchor="e" if c != "concepto" else "w")
        self.tv_detalle.pack(fill="x", expand=True, padx=6, pady=4)

        bottom = ttk.Frame(parent)
        bottom.pack(fill="x", padx=10, pady=6)
        self.btn_marcar_facturas = ttk.Button(bottom, text="Marcar seleccionadas", command=self._marcar_facturas_seleccionadas)
        self.btn_marcar_facturas.pack(side=tk.LEFT)
        self.btn_desmarcar_facturas = ttk.Button(bottom, text="Desmarcar todas", command=self._desmarcar_todas_facturas)
        self.btn_desmarcar_facturas.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_generar_suenlace = ttk.Button(bottom, text="Generar Suenlace.dat", style="Primary.TButton", command=self._generar)
        self.btn_generar_suenlace.pack(side=tk.RIGHT)
        if not can_write or is_cliente:
            self.btn_marcar_facturas.configure(state="disabled")
            self.btn_desmarcar_facturas.configure(state="disabled")
            self.btn_generar_suenlace.configure(state="disabled")

    def _build_albaranes_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=10, pady=(8, 0))
        can_write = getattr(getattr(self.gestor, "security", None), "can_write_company", lambda _c: True)(self.codigo)
        self.btn_alb_nuevo = ttk.Button(top, text="Nuevo", style="Primary.TButton", command=self._nuevo_albaran)
        self.btn_alb_nuevo.pack(side=tk.LEFT, padx=8)
        self.btn_alb_editar = ttk.Button(top, text="Editar", command=self._editar_albaran)
        self.btn_alb_editar.pack(side=tk.LEFT, padx=8)
        self.btn_alb_copiar = ttk.Button(top, text="Copiar", command=self._copiar_albaran)
        self.btn_alb_copiar.pack(side=tk.LEFT, padx=8)
        self.btn_alb_eliminar = ttk.Button(top, text="Eliminar", command=self._eliminar_albaran)
        self.btn_alb_eliminar.pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Imprimir", command=self._imprimir_albaran).pack(side=tk.LEFT, padx=8)
        self.btn_alb_facturar = ttk.Button(top, text="Facturar seleccionados", style="Primary.TButton", command=self._facturar_albaranes)
        self.btn_alb_facturar.pack(side=tk.RIGHT, padx=8)
        if not can_write:
            for btn in (self.btn_alb_nuevo, self.btn_alb_editar, self.btn_alb_copiar, self.btn_alb_eliminar, self.btn_alb_facturar):
                btn.configure(state="disabled")

        self.tv_albaranes = ttk.Treeview(
            parent,
            columns=("numero", "fecha", "cliente", "total", "facturado", "factura"),
            show="headings",
            selectmode="extended",
            height=12,
        )
        cols = [
            ("numero", "Numero", 160, "w"),
            ("fecha", "Fecha", 100, "w"),
            ("cliente", "Cliente", 240, "w"),
            ("total", "Total", 100, "e"),
            ("facturado", "Facturado", 90, "center"),
            ("factura", "Factura", 140, "w"),
        ]
        for c, h, w, align in cols:
            self.tv_albaranes.heading(c, text=h)
            self.tv_albaranes.column(c, width=w, anchor=align)
        self.tv_albaranes.pack(fill="both", expand=True, padx=10, pady=8)
        self.tv_albaranes.bind("<<TreeviewSelect>>", lambda e: self._on_albaran_select())

        detalle = ttk.LabelFrame(parent, text="Detalle de albaran")
        detalle.pack(fill="x", padx=10, pady=(0, 6))
        self.tv_alb_detalle = ttk.Treeview(
            detalle,
            columns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf"),
            displaycolumns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        headers_det = {
            "concepto": "Concepto",
            "unidades": "Unid",
            "precio": "P. unit",
            "base": "Base",
            "pct_iva": "% IVA",
            "cuota_iva": "Cuota IVA",
        }
        for c, h in headers_det.items():
            self.tv_alb_detalle.heading(c, text=h)
            self.tv_alb_detalle.column(c, width=90 if c == "concepto" else 70, anchor="e" if c != "concepto" else "w")
        self.tv_alb_detalle.pack(fill="x", expand=True, padx=6, pady=4)


    # ------------------- Datos -------------------
    def _compute_total(self, fac: dict) -> float:
        total = 0.0
        lineas = aplicar_descuento_total_lineas(
            fac.get("lineas", []),
            fac.get("descuento_total_tipo"),
            fac.get("descuento_total_valor"),
        )
        for ln in lineas:
            total += (
                to_float(ln.get("base"))
                + to_float(ln.get("cuota_iva"))
                + to_float(ln.get("cuota_re"))
            )
        total += self._retencion_importe(fac)
        return round2(total)

    def _retencion_importe(self, fac: dict) -> float:
        if not fac:
            return 0.0
        if not bool(fac.get("retencion_aplica")):
            ret_lineas = 0.0
            for ln in fac.get("lineas", []):
                ret_lineas += to_float(ln.get("cuota_irpf"))
            return round2(ret_lineas)
        signo_ret = self._signo_retencion_por_factura(fac)
        importe = fac.get("retencion_importe")
        if importe is None or importe == "":
            base = to_float(fac.get("retencion_base"))
            pct = to_float(fac.get("retencion_pct"))
            return round2(signo_ret * abs(base * pct / 100.0)) if pct else 0.0
        return round2(signo_ret * abs(to_float(importe)))

    def _signo_retencion_por_factura(self, fac: dict) -> float:
        base = to_float(fac.get("retencion_base"))
        if base == 0.0:
            lineas = aplicar_descuento_total_lineas(
                fac.get("lineas", []),
                fac.get("descuento_total_tipo"),
                fac.get("descuento_total_valor"),
            )
            base = sum(to_float(ln.get("base")) for ln in lineas)
        return 1.0 if base < 0 else -1.0

    def _refresh_facturas(self):
        self.controller.refresh_facturas()

    def _refresh_albaranes(self):
        self.controller.refresh_albaranes()


    def clear_facturas(self):
        self.tv.delete(*self.tv.get_children())
        self.tv_detalle.delete(*self.tv_detalle.get_children())

    def clear_albaranes(self):
        self.tv_albaranes.delete(*self.tv_albaranes.get_children())
        self.tv_alb_detalle.delete(*self.tv_alb_detalle.get_children())

    def insert_factura_row(self, fac: dict, total: float):
        sym = fac.get("moneda_simbolo") or self._default_moneda_simbolo
        fid = str(fac.get("id"))
        es_borrador = bool(fac.get("borrador"))
        serie_val  = str(fac.get("serie", "") or "").strip()
        numero_raw = str(fac.get("numero", "") or "").strip()
        # Eliminar prefijo de serie si el numero lo lleva aún (compatibilidad BD antigua)
        if serie_val and numero_raw.upper().startswith(serie_val.upper()):
            numero_raw = numero_raw[len(serie_val):]
        numero_display = "BORRADOR" if es_borrador else numero_raw
        self.tv.insert(
            "",
            tk.END,
            iid=fid,
            tags=("borrador",) if es_borrador else (),
            values=(
                "Si" if fid in self._marked_factura_ids else "",
                fac.get("ejercicio", ""),
                serie_val,
                numero_display,
                fac.get("numero_asiento", ""),
                to_fecha_ui_or_blank(fac.get("fecha_asiento", "")),
                fac.get("nombre", ""),
                fmt2s(total, sym),
                "Si" if fac.get("generada") else "No",
                fac.get("fecha_generacion", ""),
                "Si" if fac.get("enviado") else "No",
                fac.get("fecha_envio", ""),
            ),
        )

    def insert_albaran_row(self, alb: dict, total: float):
        sym = alb.get("moneda_simbolo") or self._default_moneda_simbolo
        factura_txt = alb.get("factura_id", "") or ""
        if factura_txt:
            fac = next(
                (
                    f
                    for f in self.gestor.listar_facturas_emitidas(self.codigo, self.ejercicio)
                    if str(f.get("id")) == str(factura_txt)
                ),
                None,
            )
            if fac:
                factura_txt = fac.get('numero', '')
        self.tv_albaranes.insert(
            "",
            tk.END,
            iid=str(alb.get("id")),
            values=(
                alb.get("numero", ""),
                to_fecha_ui_or_blank(alb.get("fecha_asiento", "")),
                alb.get("nombre", ""),
                fmt2s(total, sym),
                "Si" if alb.get("facturado") else "No",
                factura_txt,
            ),
        )

    def _sort_facturas(self, col):
        items = []
        for iid in self.tv.get_children(""):
            val = self.tv.set(iid, col)
            items.append((self._sort_key(col, val), iid))
        reverse = self._sort_state.get(col, False)
        items.sort(key=lambda x: x[0], reverse=reverse)
        for idx, (_, iid) in enumerate(items):
            self.tv.move(iid, "", idx)
        self._sort_state[col] = not reverse

    def _sort_key(self, col, val):
        if col == "ejercicio":
            try:
                return int(val)
            except Exception:
                return -1
        if col == "total":
            return to_float(val)
        if col == "fecha":
            return parse_date_ui(val) if val else date.min
        if col in ("fecha_gen", "fecha_envio"):
            return self._parse_datetime(val)
        if col in ("generada", "enviado"):
            return 1 if str(val).strip().lower() == "si" else 0
        if col == "numero":
            return self._numero_sort_key(val)
        return str(val or "").strip().lower()

    def _parse_datetime(self, val):
        txt = str(val or "").strip()
        if not txt:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(txt, fmt)
            except Exception:
                continue
        try:
            return datetime.combine(parse_date_ui(txt), datetime.min.time())
        except Exception:
            return datetime.min

    def _numero_sort_key(self, val):
        txt = str(val or "").strip()
        digits = "".join(ch for ch in txt if ch.isdigit())
        num = int(digits) if digits else -1
        return (txt[:1].lower() if txt else "", num, txt.lower())

    def set_detalle_lineas(self, lineas, simbolo: str = ""):
        self.tv_detalle.delete(*self.tv_detalle.get_children())
        sym = simbolo or self._default_moneda_simbolo
        for ln in lineas or []:
            is_obs = str(ln.get("tipo") or "").strip().lower() == "obs"
            self.tv_detalle.insert(
                "",
                tk.END,
                values=(
                    ln.get("concepto", ""),
                    "" if is_obs else fmt2(round2(ln.get("unidades"))),
                    "" if is_obs else fmt4(round4(ln.get("precio"))),
                    "" if is_obs else fmt2s(round2(ln.get("base")), sym),
                    "" if is_obs else fmt2(round2(ln.get("pct_iva"))),
                    "" if is_obs else fmt2s(round2(ln.get("cuota_iva")), sym),
                    "" if is_obs else fmt2(round2(ln.get("pct_irpf"))),
                    "" if is_obs else fmt2s(round2(ln.get("cuota_irpf")), sym),
                ),
            )

    def set_albaran_lineas(self, lineas, simbolo: str = ""):
        self.tv_alb_detalle.delete(*self.tv_alb_detalle.get_children())
        sym = simbolo or self._default_moneda_simbolo
        for ln in lineas or []:
            is_obs = str(ln.get("tipo") or "").strip().lower() == "obs"
            self.tv_alb_detalle.insert(
                "",
                tk.END,
                values=(
                    ln.get("concepto", ""),
                    "" if is_obs else fmt2(round2(ln.get("unidades"))),
                    "" if is_obs else fmt4(round4(ln.get("precio"))),
                    "" if is_obs else fmt2s(round2(ln.get("base")), sym),
                    "" if is_obs else fmt2(round2(ln.get("pct_iva"))),
                    "" if is_obs else fmt2s(round2(ln.get("cuota_iva")), sym),
                    "" if is_obs else fmt2(round2(ln.get("pct_irpf"))),
                    "" if is_obs else fmt2s(round2(ln.get("cuota_irpf")), sym),
                ),
            )

    def get_selected_ids(self):
        sel = list(self.tv.selection())
        if sel:
            return sel
        focus = self.tv.focus()
        return [focus] if focus else []

    def get_marked_ids(self):
        return [iid for iid in self.tv.get_children() if str(iid) in self._marked_factura_ids]

    def clear_marked_ids(self, ids=None):
        if ids is None:
            self._marked_factura_ids.clear()
        else:
            for iid in ids:
                self._marked_factura_ids.discard(str(iid))

    def _sync_mark_visual(self, iid):
        if not self.tv.exists(iid):
            return
        self.tv.set(iid, "marcar", "Si" if str(iid) in self._marked_factura_ids else "")

    def _toggle_mark_factura(self, iid):
        iid = str(iid)
        if iid in self._marked_factura_ids:
            self._marked_factura_ids.discard(iid)
        else:
            self._marked_factura_ids.add(iid)
        self._sync_mark_visual(iid)

    def _on_factura_click(self, event):
        region = self.tv.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tv.identify_column(event.x)
        row = self.tv.identify_row(event.y)
        if col == "#1" and row:
            self._toggle_mark_factura(row)
            return "break"

    def _marcar_facturas_seleccionadas(self):
        for iid in self.get_selected_ids():
            self._marked_factura_ids.add(str(iid))
            self._sync_mark_visual(str(iid))

    def _desmarcar_todas_facturas(self):
        ids = list(self._marked_factura_ids)
        self._marked_factura_ids.clear()
        for iid in ids:
            self._sync_mark_visual(str(iid))

    def get_selected_albaran_ids(self):
        sel = list(self.tv_albaranes.selection())
        if sel:
            return sel
        focus = self.tv_albaranes.focus()
        return [focus] if focus else []

    def open_factura_dialog(self, factura, numero_sugerido=""):
        ejercicio = self.ejercicio
        if self.allow_all_years and factura.get("ejercicio") is not None:
            ejercicio = factura.get("ejercicio")
        if self.allow_all_years:
            factura = dict(factura or {})
            factura["_allow_fecha_fuera_ejercicio"] = True
            factura["_auto_ejercicio_por_fecha"] = True
        dlg = FacturaDialog(
            self,
            self.gestor,
            self.codigo,
            ejercicio,
            int(self.empresa_conf.get("digitos_plan", 8)),
            factura,
            numero_sugerido=numero_sugerido,
            titulo="Factura emitida",
            on_open_company_config=self._on_open_company_config,
        )
        return dlg.result

    def set_facturas_years(self, years):
        if not self.allow_all_years:
            return
        vals = ["Todos"] + [str(y) for y in years]
        self.cb_fact_year["values"] = vals
        if self.var_fact_year.get() not in vals:
            self.var_fact_year.set(vals[0])

    def get_facturas_year_filter(self):
        if not self.allow_all_years:
            return None
        txt = (self.var_fact_year.get() or "").strip()
        if not txt or txt.lower() == "todos":
            return None
        try:
            return int(txt)
        except Exception:
            return None

    def get_facturas_cliente_filter(self):
        return (self.var_fact_cliente_filter.get() or "").strip().lower()

    def set_facturas_series(self, series: list[str]):
        vals = ["Todas"] + sorted(set(series))
        self.cb_fact_serie["values"] = vals
        if self.var_fact_serie_filter.get() not in vals:
            self.var_fact_serie_filter.set("Todas")

    def get_facturas_serie_filter(self) -> str | None:
        txt = (self.var_fact_serie_filter.get() or "").strip()
        return None if not txt or txt.lower() == "todas" else txt

    def open_albaran_dialog(self, albaran, numero_sugerido=""):
        dlg = FacturaDialog(
            self,
            self.gestor,
            self.codigo,
            self.ejercicio,
            int(self.empresa_conf.get("digitos_plan", 8)),
            albaran,
            numero_sugerido=numero_sugerido,
            titulo="Albaran emitido",
            on_open_company_config=self._on_open_company_config,
        )
        return dlg.result

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def ask_desmarcar_generadas_password(self):
        return simpledialog.askstring(
            "Gest2A3Eco",
            "Contraseña para desmarcar generadas:",
            show="*",
            parent=self,
        )

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def ask_share_channel(self):
        dlg = tk.Toplevel(self)
        dlg.title("Compartir factura")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona canal para compartir:").pack(anchor="w", pady=(0, 8))

        def _set(val):
            result["value"] = val
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Email", style="Primary.TButton", command=lambda: _set("email")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="WhatsApp", style="Primary.TButton", command=lambda: _set("whatsapp")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"+{x}+{y}")

        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email(self, default=""):
        return simpledialog.askstring("Gest2A3Eco", "Email de envio:", initialvalue=default, parent=self)

    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            pass

    def ask_smtp_config(self, current_cfg: dict) -> dict | None:
        dlg = tk.Toplevel(self)
        dlg.title("Configuracion SMTP")
        dlg.resizable(False, False)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        fields = [
            ("Servidor SMTP:", "host", str(current_cfg.get("host") or ""), False),
            ("Puerto:", "port", str(current_cfg.get("port") or "587"), False),
            ("Usuario:", "user", str(current_cfg.get("user") or ""), False),
            ("Contrasena:", "password", str(current_cfg.get("password") or ""), True),
            ("Email remitente:", "from_addr", str(current_cfg.get("from_addr") or ""), False),
        ]

        vars_ = {}
        for row, (label, key, default, is_password) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            vars_[key] = var
            ttk.Entry(frm, textvariable=var, width=35, show="*" if is_password else "").grid(
                row=row, column=1, sticky="ew", pady=4
            )

        chk_row = len(fields)
        use_tls = tk.BooleanVar(value=bool(current_cfg.get("use_tls", True)))
        use_ssl = tk.BooleanVar(value=bool(current_cfg.get("use_ssl", False)))
        ttk.Checkbutton(frm, text="Usar STARTTLS (puerto 587)", variable=use_tls).grid(
            row=chk_row, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(frm, text="Usar SSL (puerto 465)", variable=use_ssl).grid(
            row=chk_row + 1, column=0, columnspan=2, sticky="w", pady=2
        )

        lbl_test = ttk.Label(frm, text="", foreground="gray", wraplength=320, justify="left")
        lbl_test.grid(row=chk_row + 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def _build_cfg():
            try:
                port_val = int(vars_["port"].get().strip() or "587")
            except ValueError:
                port_val = 587
            return {
                "host": vars_["host"].get().strip(),
                "port": port_val,
                "user": vars_["user"].get().strip(),
                "password": vars_["password"].get(),
                "from_addr": vars_["from_addr"].get().strip(),
                "use_tls": use_tls.get(),
                "use_ssl": use_ssl.get(),
            }

        def _probar():
            import smtplib, ssl as _ssl
            cfg = _build_cfg()
            host = cfg["host"]
            port = cfg["port"]
            if not host:
                lbl_test.configure(text="Error: el servidor SMTP esta vacio.", foreground="#c0392b")
                return
            lbl_test.configure(text=f"Conectando a {host}:{port} ...", foreground="gray")
            dlg.update()
            try:
                if cfg["use_ssl"]:
                    ctx = _ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=8) as s:
                        if cfg["user"]:
                            s.login(cfg["user"], cfg["password"])
                else:
                    with smtplib.SMTP(host, port, timeout=8) as s:
                        s.ehlo()
                        if cfg["use_tls"]:
                            s.starttls()
                            s.ehlo()
                        if cfg["user"]:
                            s.login(cfg["user"], cfg["password"])
                lbl_test.configure(text=f"Conexion correcta con {host}:{port}", foreground="#27ae60")
            except Exception as exc:
                lbl_test.configure(text=f"Error: {exc}", foreground="#c0392b")

        def _save():
            result["value"] = _build_cfg()
            dlg.destroy()

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=chk_row + 3, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frm, text="Probar conexion", command=_probar).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frm, text="Guardar", style="Primary.TButton", command=_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frm, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_email_compose(
        self,
        email_cliente: str,
        asunto: str,
        cuerpo: str,
        pdf_path: str,
        smtp_cfg: dict,
        *,
        email_empresa: str = "",
    ) -> dict | None:
        dlg = tk.Toplevel(self)
        dlg.title("Enviar factura por email")
        dlg.resizable(True, True)
        result = {"value": None}
        current_smtp = [dict(smtp_cfg)]

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # PDF info + boton SMTP
        pdf_name = Path(pdf_path).name if pdf_path else ""
        ttk.Label(frm, text="PDF:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=4)
        ttk.Label(frm, text=pdf_name, foreground="gray").grid(row=0, column=1, sticky="w", pady=4)

        def _abrir_smtp():
            new_cfg = self.ask_smtp_config(current_smtp[0])
            if new_cfg:
                current_smtp[0] = new_cfg

        def _editar_plantilla_html():
            from services.email_service import ensure_template_file
            import subprocess
            path = ensure_template_file()
            try:
                subprocess.Popen(["notepad.exe", str(path)])
                messagebox.showinfo(
                    "Plantilla HTML",
                    f"Fichero abierto en el Bloc de notas:\n{path}\n\n"
                    "Guarda los cambios y vuelve a enviar la factura para aplicarlos.\n"
                    "Los cambios se aplican en el siguiente envio sin reiniciar la aplicacion.",
                    parent=dlg,
                )
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", f"No se pudo abrir el editor:\n{exc}", parent=dlg)

        btn_row_top = ttk.Frame(frm)
        btn_row_top.grid(row=0, column=2, padx=(8, 0), pady=4, sticky="e")
        ttk.Button(btn_row_top, text="Configurar SMTP", command=_abrir_smtp).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row_top, text="Editar plantilla HTML", command=_editar_plantilla_html).pack(side=tk.LEFT)

        # --- Destinatarios ---
        ttk.Label(frm, text="Destinatarios:").grid(row=1, column=0, sticky="ne", padx=(0, 8), pady=(8, 2))
        dest_frm = ttk.Frame(frm)
        dest_frm.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 2))
        dest_frm.columnconfigure(1, weight=1)

        # Checkboxes empresa / cliente
        var_empresa = tk.BooleanVar(value=False)
        var_cliente = tk.BooleanVar(value=bool(email_cliente))

        chk_empresa = ttk.Checkbutton(dest_frm, text="Empresa:", variable=var_empresa)
        chk_empresa.grid(row=0, column=0, sticky="w")
        lbl_empresa_mail = ttk.Label(
            dest_frm,
            text=email_empresa or "(sin email de empresa)",
            foreground="gray" if not email_empresa else "#333",
        )
        lbl_empresa_mail.grid(row=0, column=1, sticky="w", padx=(4, 0))

        chk_cliente = ttk.Checkbutton(dest_frm, text="Cliente:", variable=var_cliente)
        chk_cliente.grid(row=1, column=0, sticky="w", pady=(4, 0))
        lbl_cliente_mail = ttk.Label(
            dest_frm,
            text=email_cliente or "(sin email de cliente)",
            foreground="gray" if not email_cliente else "#333",
        )
        lbl_cliente_mail.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        if not email_empresa:
            chk_empresa.configure(state="disabled")
        if not email_cliente:
            chk_cliente.configure(state="disabled")

        # Campo para añadir correos adicionales
        ttk.Label(dest_frm, text="Añadir:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        var_extra = tk.StringVar()
        ttk.Entry(dest_frm, textvariable=var_extra, width=36).grid(
            row=2, column=1, sticky="ew", pady=(6, 0)
        )
        ttk.Label(dest_frm, text="(separar varios con ; o ,)", foreground="gray", font=("", 8)).grid(
            row=3, column=1, sticky="w"
        )

        # Asunto
        ttk.Label(frm, text="Asunto:").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=(8, 4))
        asunto_var = tk.StringVar(value=asunto)
        ttk.Entry(frm, textvariable=asunto_var, width=50).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=(8, 4)
        )

        # Cuerpo
        ttk.Label(frm, text="Mensaje:").grid(row=3, column=0, sticky="ne", padx=(0, 8), pady=4)
        cuerpo_text = tk.Text(frm, height=7, width=50, wrap="word")
        cuerpo_text.insert("1.0", cuerpo)
        cuerpo_text.grid(row=3, column=1, columnspan=2, sticky="nsew", pady=4)
        frm.rowconfigure(3, weight=1)

        # Botones
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=4, column=0, columnspan=3, pady=(12, 0))

        def _enviar():
            emails = []
            if var_empresa.get() and email_empresa:
                emails.append(email_empresa)
            if var_cliente.get() and email_cliente:
                emails.append(email_cliente)
            extra_raw = var_extra.get()
            for e in extra_raw.replace(";", ",").split(","):
                e = e.strip()
                if e:
                    emails.append(e)
            if not emails:
                messagebox.showwarning(
                    "Gest2A3Eco", "Selecciona al menos un destinatario o introduce un correo.", parent=dlg
                )
                return
            result["value"] = {
                "emails": emails,
                "asunto": asunto_var.get().strip(),
                "cuerpo": cuerpo_text.get("1.0", "end").strip(),
                "smtp_cfg": current_smtp[0],
            }
            dlg.destroy()

        ttk.Button(btn_frm, text="Enviar", style="Primary.TButton", command=_enviar).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frm, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.update_idletasks()
        w = max(dlg.winfo_width(), 540)
        h = max(dlg.winfo_height(), 420)
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def ask_whatsapp_compose(
        self,
        telefono_cliente: str,
        mensaje: str,
        pdf_path: str,
        *,
        telefono_empresa: str = "",
    ) -> dict | None:
        """Dialogo para preparar y lanzar el envio por WhatsApp."""
        from pathlib import Path

        dlg = tk.Toplevel(self)
        dlg.title("Enviar por WhatsApp")
        dlg.resizable(True, True)
        result = {"value": None}

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # PDF
        pdf_name = Path(pdf_path).name if pdf_path else "(sin PDF)"
        ttk.Label(frm, text="PDF:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=4)
        ttk.Label(frm, text=pdf_name, foreground="gray").grid(row=0, column=1, sticky="w", pady=4)

        # --- Destinatario (radio: cliente / empresa / otro) ---
        ttk.Label(frm, text="Destinatario:").grid(row=1, column=0, sticky="ne", padx=(0, 8), pady=(8, 2))

        dest_frm = ttk.Frame(frm)
        dest_frm.grid(row=1, column=1, sticky="ew", pady=(8, 2))
        dest_frm.columnconfigure(1, weight=1)

        # radio variable: "cliente" | "empresa" | "otro"
        default_radio = "cliente" if telefono_cliente else ("empresa" if telefono_empresa else "otro")
        var_radio = tk.StringVar(value=default_radio)

        # --- fila cliente ---
        rb_cliente = ttk.Radiobutton(dest_frm, text="Cliente:", variable=var_radio, value="cliente")
        rb_cliente.grid(row=0, column=0, sticky="w")
        lbl_tel_cliente = ttk.Label(
            dest_frm,
            text=telefono_cliente or "(sin telefono de cliente)",
            foreground="gray" if not telefono_cliente else "#333",
        )
        lbl_tel_cliente.grid(row=0, column=1, sticky="w", padx=(4, 0))
        if not telefono_cliente:
            rb_cliente.configure(state="disabled")

        # --- fila empresa ---
        rb_empresa = ttk.Radiobutton(dest_frm, text="Empresa:", variable=var_radio, value="empresa")
        rb_empresa.grid(row=1, column=0, sticky="w", pady=(4, 0))
        lbl_tel_empresa = ttk.Label(
            dest_frm,
            text=telefono_empresa or "(sin telefono de empresa)",
            foreground="gray" if not telefono_empresa else "#333",
        )
        lbl_tel_empresa.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        if not telefono_empresa:
            rb_empresa.configure(state="disabled")

        # --- fila otro ---
        rb_otro = ttk.Radiobutton(dest_frm, text="Otro:", variable=var_radio, value="otro")
        rb_otro.grid(row=2, column=0, sticky="w", pady=(4, 0))
        var_otro_tel = tk.StringVar()
        ent_otro = ttk.Entry(dest_frm, textvariable=var_otro_tel, width=22)
        ent_otro.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(
            dest_frm,
            text="Formato internacional sin '+': ej. 34612345678",
            foreground="gray",
            font=("Segoe UI", 8),
        ).grid(row=3, column=1, sticky="w")

        # Mensaje
        ttk.Label(frm, text="Mensaje:").grid(row=2, column=0, sticky="ne", padx=(0, 8), pady=(8, 4))
        msg_text = tk.Text(frm, width=46, height=6, wrap="word", font=("Segoe UI", 10))
        msg_text.grid(row=2, column=1, sticky="nsew", pady=(8, 4))
        msg_text.insert("1.0", mensaje)
        frm.rowconfigure(2, weight=1)

        # Nota informativa
        nota = (
            "Al pulsar 'Abrir WhatsApp':\n"
            "  1. Se abre WhatsApp Web/Escritorio con el numero y mensaje ya escritos.\n"
            "  2. La carpeta del PDF se abre en el Explorador para adjuntarlo manualmente.\n"
            "  3. Envia el mensaje de texto y luego adjunta el PDF desde WhatsApp."
        )
        ttk.Label(frm, text=nota, foreground="#555", font=("Segoe UI", 8), justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=4, column=0, columnspan=2, pady=(12, 0))

        def _abrir():
            opcion = var_radio.get()
            if opcion == "cliente":
                raw = telefono_cliente
            elif opcion == "empresa":
                raw = telefono_empresa
            else:
                raw = var_otro_tel.get()
            tel = normalizar_telefono(raw)
            if not tel:
                messagebox.showwarning(
                    "Gest2A3Eco", "Introduce o selecciona un numero de telefono.", parent=dlg
                )
                return
            msg = msg_text.get("1.0", "end").strip()
            result["value"] = {"telefono": tel, "mensaje": msg}
            dlg.destroy()

        ttk.Button(btn_frm, text="Abrir WhatsApp", style="Primary.TButton", command=_abrir).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frm, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.update_idletasks()
        w = max(dlg.winfo_width(), 520)
        h = max(dlg.winfo_height(), 420)
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.grab_set()
        dlg.transient(self)
        dlg.wait_window(dlg)
        return result["value"]

    def _selected_ids(self):
        return self.get_selected_ids()

    def _nueva(self):
        self.controller.nueva()

    def _editar(self):
        self.controller.editar()

    def _copiar(self):
        self.controller.copiar()

    def _nueva_rectificativa(self):
        self.controller.nueva_rectificativa()

    def _rectificar(self):
        self.controller.rectificar()

    def _eliminar(self):
        self.controller.eliminar()

    def _confirmar_borrador(self):
        self.controller.confirmar_borrador()

    def _desmarcar_generadas(self):
        self.controller.desmarcar_generadas()

    def _nuevo_albaran(self):
        self.controller.nuevo_albaran()

    def _editar_albaran(self):
        self.controller.editar_albaran()

    def _copiar_albaran(self):
        self.controller.copiar_albaran()

    def _eliminar_albaran(self):
        self.controller.eliminar_albaran()

    def _facturar_albaranes(self):
        self.controller.facturar_albaranes()

    def _imprimir_albaran(self):
        self.controller.imprimir_albaran()

    def _on_factura_select(self):
        self.controller.factura_seleccionada()

    def _on_albaran_select(self):
        self.controller.albaran_seleccionado()

    # ------------------- Exportar PDF -------------------
    def _export_pdf(self):
        self.controller.export_pdf()

    def _abrir_pdf(self):
        self.controller.abrir_pdf()

    def _compartir_pdf(self):
        self.controller.compartir_pdf()

    def _export_pdf_multiple(self):
        self.controller.export_pdf_multiple()

    def _generar(self):
        self.controller.generar_suenlace()

    def ask_save_pdf_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Exportar PDF",
            defaultextension=".pdf",
            initialfile=initialfile,
            filetypes=[("PDF", "*.pdf")],
        )

    def ask_save_dat_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )
