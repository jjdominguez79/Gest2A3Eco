
import calendar
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import date, datetime
from utils.utilidades import aplicar_descuento_total_lineas

from controllers.ui_facturas_emitidas_controller import FacturasEmitidasController
from controllers.factura_dialog_controller import FacturaDialogController
from controllers.terceros_global_controller import TercerosGlobalController
from controllers.terceros_empresa_controller import TercerosEmpresaController

IVA_OPCIONES = [21, 10, 4, 0]
IRPF_RET_OPCIONES = [1, 7, 15, 19]

def _to_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0

def _parse_date_ui(val: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except Exception:
            continue
    return date.today()

def _to_fecha_ui(val: str) -> str:
    if not val:
        return date.today().strftime("%d/%m/%Y")
    try:
        d = _parse_date_ui(str(val))
        return d.strftime("%d/%m/%Y")
    except Exception:
        return date.today().strftime("%d/%m/%Y")

def _to_fecha_ui_or_blank(val: str) -> str:
    if not val:
        return ""
    return _to_fecha_ui(val)

def _round2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0

def _round4(x) -> float:
    try:
        return round(float(x), 4)
    except Exception:
        return 0.0

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
        for i, (lbl, key, width) in enumerate(fields):
            ttk.Label(self, text=lbl).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            v = tk.StringVar(value=str(t.get(key, "")))
            self.vars[key] = v
            ttk.Entry(self, textvariable=v, width=width).grid(row=i, column=1, sticky="w", padx=6, pady=3)
        btns = ttk.Frame(self)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _ok(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        self.result = data
        self.destroy()

class TercerosGlobalDialog(tk.Toplevel):
    def __init__(self, parent, gestor):
        super().__init__(parent)
        self.title("Terceros")
        self.resizable(True, True)
        self.gestor = gestor
        self.controller = TercerosGlobalController(gestor, self)
        self._empresas_cache = []
        self._empresas_index = {}
        self._empresas_list = []
        self._build()
        self.controller.refresh()
        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Nuevo", style="Primary.TButton", command=self.controller.nuevo).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Editar", command=self.controller.editar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar", command=self.controller.eliminar).pack(side=tk.LEFT, padx=4)

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

        ttk.Label(asignar, text="Ejercicios").grid(row=1, column=2, sticky="w", padx=6, pady=4)
        self.lb_ejercicios = tk.Listbox(asignar, height=5, selectmode="extended", exportselection=False)
        self.lb_ejercicios.grid(row=1, column=3, sticky="we", padx=6, pady=4)

        ttk.Button(asignar, text="Asignar", style="Primary.TButton", command=self.controller.asignar_a_empresa).grid(row=0, column=3, rowspan=1, padx=6, pady=4)
        asignar.columnconfigure(1, weight=1)
        asignar.columnconfigure(3, weight=1)

    # --- helpers de vista
    def set_terceros(self, rows):
        self.tv.delete(*self.tv.get_children())
        for t in rows:
            self.tv.insert(
                "",
                tk.END,
                iid=str(t.get("id")),
                values=(t.get("nif", ""), t.get("nombre", ""), t.get("poblacion", "")),
            )

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
        ejercicios = []
        for j in self.lb_ejercicios.curselection():
            try:
                ejercicios.append(int(self.lb_ejercicios.get(j)))
            except Exception:
                pass
        return emp.get("codigo"), ejercicios

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

    def set_empresas_asignadas(self, rows):
        self.lb_empresas_asignadas.delete(0, tk.END)
        for r in rows or []:
            codigo = r.get("codigo", "")
            nombre = r.get("nombre", "")
            ejercicio = r.get("ejercicio", "")
            texto = f"{codigo} - {nombre}"
            if ejercicio != "" and ejercicio is not None:
                texto = f"{texto} ({ejercicio})"
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
            self.lb_ejercicios.delete(0, tk.END)

    def _update_ejercicios(self):
        sel = self.lb_empresas.curselection()
        self.lb_ejercicios.delete(0, tk.END)
        if not sel:
            return
        emp = self._empresas_list[sel[0]]
        ejercicios = sorted(set(emp.get("ejercicios") or []))
        for ej in ejercicios:
            self.lb_ejercicios.insert(tk.END, str(ej))
        if ejercicios:
            self.lb_ejercicios.select_set(0, tk.END)


class TercerosEmpresaDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa, ejercicio, ndig_plan):
        super().__init__(parent)
        self.title("Terceros de empresa")
        self.resizable(True, True)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.ndig = ndig_plan
        self.controller = TercerosEmpresaController(gestor, codigo_empresa, ejercicio, ndig_plan, self)
        self._build()
        self.controller.refresh()
        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        bar = ttk.Frame(frm)
        bar.pack(fill="x")
        ttk.Button(bar, text="Copiar de ejercicio", command=self.controller.copiar_desde_ejercicio).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Suenlace terceros", command=self.controller.generar_suenlace_terceros).pack(side=tk.LEFT, padx=4)

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
        self.tv.delete(*self.tv.get_children())
        for t in rows:
            self.tv.insert(
                "",
                tk.END,
                iid=str(t.get("id")),
                values=(t.get("nif", ""), t.get("nombre", ""), t.get("poblacion", "")),
            )

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

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

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
    def __init__(self, parent, gestor, codigo_empresa, ejercicio, ndig_plan, factura=None, numero_sugerido="", titulo="Factura emitida"):
        super().__init__(parent)
        self.title(titulo)
        self.resizable(True, True)
        self.result = None
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.ndig = ndig_plan
        self.factura = dict(factura or {})
        self.factura.setdefault("codigo_empresa", codigo_empresa)
        self.factura.setdefault("ejercicio", ejercicio)
        if "ejercicio" not in self.factura:
            self.factura["ejercicio"] = ejercicio
        if numero_sugerido and not self.factura.get("numero"):
            self.factura["numero"] = numero_sugerido
        f = self.factura

        self.controller = FacturaDialogController(gestor, codigo_empresa, ejercicio, ndig_plan, self.factura, self)

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        def add_row(label, var, row_idx, width=16, col=0):
            ttk.Label(frm, text=label).grid(row=row_idx, column=col, sticky="w", padx=4, pady=3)
            ttk.Entry(frm, textvariable=var, width=width).grid(row=row_idx, column=col + 1, padx=4, pady=3, sticky="w")

        today = date.today().strftime("%d/%m/%Y")
        self.var_serie = tk.StringVar(value=f.get("serie", ""))
        self.var_numero = tk.StringVar(value=f.get("numero", ""))
        self.var_fecha_asiento = tk.StringVar(value=_to_fecha_ui(f.get("fecha_asiento", today)))
        self.var_fecha_exp = tk.StringVar(value=_to_fecha_ui(f.get("fecha_expedicion", f.get("fecha_asiento", today))))
        self.var_fecha_op = tk.StringVar(value=_to_fecha_ui(f.get("fecha_operacion", today)) if f.get("fecha_operacion") else "")
        self.var_nif = tk.StringVar(value=f.get("nif", ""))
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
                pct_ln = _to_float(ln.get("pct_irpf"))
                if pct_ln > 0:
                    ret_pct = pct_ln
                    ret_aplica = True
                    break
        if ret_importe in (None, "") and f.get("lineas"):
            ret_importe = sum(_to_float(ln.get("cuota_irpf")) for ln in f.get("lineas", []))
        base_lineas = sum(_to_float(ln.get("base")) for ln in f.get("lineas", []))
        if ret_base in (None, ""):
            pct_val = _to_float(ret_pct)
            if ret_importe not in (None, "") and pct_val:
                ret_base = abs(_to_float(ret_importe)) * 100.0 / pct_val
            else:
                ret_base = base_lineas if base_lineas else ""
        self.var_ret_aplica = tk.BooleanVar(value=ret_aplica)
        self.var_ret_pct = tk.StringVar(value=str(int(ret_pct)) if ret_pct not in (None, "", 0) else "")
        self.var_ret_base = tk.StringVar(
            value=f"{_round2(ret_base):.2f}" if ret_base not in (None, "") else ""
        )
        self._retencion_manual = False
        if ret_aplica:
            if ret_importe not in (None, ""):
                self._retencion_manual = True
            else:
                try:
                    if abs(_round2(ret_base) - _round2(base_lineas)) > 0.01:
                        self._retencion_manual = True
                except Exception:
                    pass
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
        self._plantillas_word = self._listar_plantillas_word()
        if not self.var_plantilla_word.get().strip():
            if "factura_emitida_template.docx" in self._plantillas_word:
                self.var_plantilla_word.set("factura_emitida_template.docx")
            elif self._plantillas_word:
                self.var_plantilla_word.set(self._plantillas_word[0])
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
        ttk.Button(frm, text="Terceros...", command=self._gestionar_terceros).grid(row=row, column=2, padx=4, pady=3)
        row += 1

        add_row("Serie", self.var_serie, row, width=8, col=0)
        row += 1
        
        add_row("Numero", self.var_numero, row, width=14, col=0)
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
        editor = ttk.Frame(frm)
        editor.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4)
        editor.columnconfigure(12, weight=1)
        ttk.Label(editor, text="Concepto").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["concepto"], width=26).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(editor, text="Unidades").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["unidades"], width=10).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(editor, text="Precio").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["precio"], width=10).grid(row=0, column=5, padx=4, pady=2)
        ttk.Label(editor, text="Desc.").grid(row=0, column=6, padx=4, pady=2, sticky="w")
        ttk.Combobox(editor, textvariable=self.line_vars["desc_tipo"], values=["", "%", "€"], width=4, state="readonly").grid(row=0, column=7, padx=4, pady=2)
        ttk.Entry(editor, textvariable=self.line_vars["desc_val"], width=8).grid(row=0, column=8, padx=4, pady=2)
        ttk.Label(editor, text="IVA %").grid(row=0, column=9, padx=4, pady=2, sticky="w")
        ttk.Combobox(editor, textvariable=self.line_vars["iva"], values=[str(x) for x in IVA_OPCIONES], width=6, state="readonly").grid(row=0, column=10, padx=4, pady=2)
        ttk.Button(editor, text="Añadir/Actualizar", style="Primary.TButton", command=self._add_update_linea).grid(row=0, column=11, padx=6)
        ttk.Button(editor, text="Limpiar", command=self._clear_line_editor).grid(row=0, column=12, padx=4)
        row += 1

        self.tv = ttk.Treeview(
            frm,
            columns=("concepto", "unidades", "precio", "desc", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf", "desc_tipo", "desc_val"),
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
        ttk.Button(bar, text="Eliminar linea", command=self._del_linea).pack(side=tk.LEFT, padx=4)
        row += 1

        tot = ttk.Frame(frm)
        tot.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        self.lbl_tot_base = ttk.Label(tot, text="Base: 0.00")
        self.lbl_tot_iva = ttk.Label(tot, text="IVA: 0.00")
        self.lbl_tot_ret = ttk.Label(tot, text="IRPF: 0.00")
        self.lbl_tot_total = ttk.Label(tot, text="Total: 0.00", font=("Segoe UI", 10, "bold"))
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
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
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

        self.grab_set()
        self.transient(parent)
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
        plantillas_dir = base_dir / "plantillas"
        if not plantillas_dir.exists():
            return []
        items = [p.name for p in plantillas_dir.glob("*.docx") if p.is_file()]
        return sorted(items, key=lambda s: s.lower())

    # --- controlador
    def _load_terceros(self):
        self.controller.load_terceros()

    def _preselect_tercero(self, tercero_id):
        self.controller.preselect_tercero(tercero_id)

    def _gestionar_terceros(self):
        self.controller.gestionar_terceros()

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

    def _refresh_totales(self):
        self.controller.refresh_totales()

    def _insert_linea(self, ln: dict):
        self.controller.insert_linea(ln)

    def _ok(self):
        self.controller.ok()

    def _on_select_linea(self, event=None):
        sel = self.tv.selection()
        if not sel:
            return
        vals = self.tv.item(sel[0], "values")
        if not vals:
            return
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
        self.var_nif.set(value)

    def set_nombre(self, value):
        self.var_nombre.set(value)

    def set_subcuenta(self, value):
        self.var_subcuenta.set(value)

    def set_cuenta_bancaria(self, value):
        self.var_cuenta_banco.set(value)

    def parse_date(self, text):
        return _parse_date_ui(text)

    def open_date_picker(self, initial):
        dlg = DatePicker(self, initial)
        return dlg.result if dlg.result else None

    def clear_line_editor(self):
        for v in self.line_vars.values():
            v.set("")
        self.tv.selection_remove(self.tv.selection())

    def get_line_editor_values(self):
        concepto = self.line_vars["concepto"].get().strip()
        unidades = _to_float(self.line_vars["unidades"].get())
        precio = _to_float(self.line_vars["precio"].get())
        iva_raw = self.line_vars["iva"].get()
        iva = _to_float(iva_raw)
        desc_tipo_ui = (self.line_vars["desc_tipo"].get() or "").strip()
        desc_tipo = "pct" if desc_tipo_ui == "%" else "imp" if desc_tipo_ui == "€" else ""
        desc_val = _to_float(self.line_vars["desc_val"].get())
        return concepto, unidades, precio, iva, iva_raw, desc_tipo, desc_val

    def upsert_line_row(self, ln: dict):
        desc_txt = self._format_desc(ln)
        vals = (
            ln["concepto"],
            f"{ln['unidades']:.2f}",
            f"{ln['precio']:.4f}",
            desc_txt,
            f"{ln['base']:.2f}",
            f"{ln['pct_iva']:.2f}",
            f"{ln['cuota_iva']:.2f}",
            f"{ln['pct_irpf']:.2f}",
            f"{ln['cuota_irpf']:.2f}",
            ln.get("descuento_tipo", ""),
            f"{_round2(ln.get('descuento_valor')):.2f}",
        )
        sel = self.tv.selection()
        if sel:
            self.tv.item(sel[0], values=vals)
        else:
            self.tv.insert("", tk.END, values=vals)

    def insert_line_row(self, ln: dict):
        desc_txt = self._format_desc(ln)
        vals = (
            ln.get("concepto", ""),
            f"{_round2(ln.get('unidades')):.2f}",
            f"{_round4(ln.get('precio')):.4f}",
            desc_txt,
            f"{_round2(ln.get('base')):.2f}",
            f"{_round2(ln.get('pct_iva')):.2f}",
            f"{_round2(ln.get('cuota_iva')):.2f}",
            f"{_round2(ln.get('pct_irpf')):.2f}",
            f"{_round2(ln.get('cuota_irpf')):.2f}",
            ln.get("descuento_tipo", ""),
            f"{_round2(ln.get('descuento_valor')):.2f}",
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

    def get_lineas(self):
        out = []
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values")
            if not vals:
                continue
            out.append(
                {
                    "concepto": vals[0],
                    "unidades": _round2(_to_float(vals[1])),
                    "precio": _round4(_to_float(vals[2])),
                    "base": _round2(_to_float(vals[4])),
                    "pct_iva": _round2(_to_float(vals[5])),
                    "cuota_iva": _round2(_to_float(vals[6])),
                    "pct_irpf": _round2(_to_float(vals[7])),
                    "cuota_irpf": _round2(_to_float(vals[8])),
                    "descuento_tipo": vals[9] if len(vals) > 9 else "",
                    "descuento_valor": _round2(_to_float(vals[10])) if len(vals) > 10 else 0.0,
                    "pct_re": 0.0,
                    "cuota_re": 0.0,
                }
            )
        return out

    def set_totales(self, base, iva, ret, total):
        self.lbl_tot_base.config(text=f"Base: {base:.2f}")
        self.lbl_tot_iva.config(text=f"IVA: {iva:.2f}")
        self.lbl_tot_ret.config(text=f"IRPF: {ret:.2f}")
        self.lbl_tot_total.config(text=f"Total: {total:.2f}")

    def set_iva_resumen(self, rows):
        self.tv_iva.delete(*self.tv_iva.get_children())
        for r in rows:
            self.tv_iva.insert(
                "",
                tk.END,
                values=(r.get("tipo", ""), f"{_round2(r.get('base')):.2f}", f"{_round2(r.get('cuota')):.2f}"),
            )

    def get_retencion_aplica(self):
        return bool(self.var_ret_aplica.get())

    def get_retencion_pct(self):
        return _to_float(self.var_ret_pct.get())

    def get_retencion_base(self):
        return _to_float(self.var_ret_base.get())

    def get_retencion_importe(self):
        base = self.get_retencion_base()
        pct = self.get_retencion_pct()
        return _round2(-abs(base * pct / 100.0)) if pct else 0.0

    def is_retencion_manual(self):
        return self._retencion_manual

    def set_retencion_manual(self, manual: bool):
        self._retencion_manual = bool(manual)

    def set_retencion_base(self, value: str):
        self._retencion_silent = True
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
            valor = _to_float(self.var_desc_total_valor.get())
        except Exception:
            valor = 0.0
        return tipo, valor

    def _format_desc(self, ln: dict) -> str:
        t = (ln.get("descuento_tipo") or "").strip().lower()
        v = _round2(ln.get("descuento_valor"))
        if not t or not v:
            return ""
        if t == "pct":
            return f"{v:.2f}%"
        return f"{v:.2f}"

    def get_numero_factura(self):
        return self.var_numero.get().strip()

    def get_subcuenta(self):
        return self.var_subcuenta.get().strip()

    def get_fecha_exp(self):
        return self.var_fecha_exp.get().strip()

    def get_serie(self):
        return self.var_serie.get().strip()

    def get_nif(self):
        return self.var_nif.get().strip()

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

    def get_plantilla_word(self):
        return self.var_plantilla_word.get().strip()

    def open_terceros_dialog(self, codigo_empresa, ejercicio, ndig):
        TercerosEmpresaDialog(self, self.gestor, codigo_empresa, ejercicio, ndig)

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
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        base = {
            "nombre": nombre_empresa,
            "digitos_plan": 8,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 1,
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
        self.controller = FacturasEmitidasController(gestor, codigo_empresa, ejercicio, self.empresa_conf, self)
        self._sort_state = {}
        self._build()

    # ------------------- UI -------------------
    def _build(self):
        ttk.Label(self, text=f"Facturas emitidas de {self.nombre} ({self.codigo} · {self.ejercicio})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        tab_facturas = ttk.Frame(nb)
        tab_albaranes = ttk.Frame(nb)
        nb.add(tab_facturas, text="Facturas")
        nb.add(tab_albaranes, text="Albaranes")

        self._build_facturas_tab(tab_facturas)
        self._build_albaranes_tab(tab_albaranes)

        self._refresh_facturas()
        self._refresh_albaranes()

    def _build_facturas_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=20, pady=(8, 0))
        ttk.Button(top, text="Nueva", style="Primary.TButton", command=self._nueva).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Editar", command=self._editar).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Copiar", command=self._copiar).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Eliminar", command=self._eliminar).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Terceros", command=self._terceros).pack(side=tk.LEFT, padx=12)
        ttk.Button(top, text="Exportar PDF", command=self._export_pdf).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Abrir PDF", command=self._abrir_pdf).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Compartir PDF", state="disabled").pack(side=tk.LEFT, padx=8)

        self.tv = ttk.Treeview(
            parent,
            columns=("serie", "numero", "fecha", "cliente", "total", "generada", "fecha_gen", "enviado", "fecha_envio"),
            show="headings",
            selectmode="extended",
            height=12,
        )
        cols = [
            ("serie", "Serie", 80, "w"),
            ("numero", "Numero", 120, "w"),
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
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._on_factura_select())

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
        ttk.Button(bottom, text="Generar Suenlace.dat", style="Primary.TButton", command=self._generar).pack(side=tk.RIGHT)

    def _build_albaranes_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Button(top, text="Nuevo", style="Primary.TButton", command=self._nuevo_albaran).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Editar", command=self._editar_albaran).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Copiar", command=self._copiar_albaran).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Eliminar", command=self._eliminar_albaran).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Facturar seleccionados", style="Primary.TButton", command=self._facturar_albaranes).pack(side=tk.RIGHT, padx=8)

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
                _to_float(ln.get("base"))
                + _to_float(ln.get("cuota_iva"))
                + _to_float(ln.get("cuota_re"))
            )
        total += self._retencion_importe(fac)
        return _round2(total)

    def _retencion_importe(self, fac: dict) -> float:
        if not fac:
            return 0.0
        if not bool(fac.get("retencion_aplica")):
            ret_lineas = 0.0
            for ln in fac.get("lineas", []):
                ret_lineas += _to_float(ln.get("cuota_irpf"))
            return _round2(ret_lineas)
        importe = fac.get("retencion_importe")
        if importe is None or importe == "":
            base = _to_float(fac.get("retencion_base"))
            pct = _to_float(fac.get("retencion_pct"))
            return _round2(-abs(base * pct / 100.0)) if pct else 0.0
        return _round2(_to_float(importe))

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
        self.tv.insert(
            "",
            tk.END,
            iid=str(fac.get("id")),
            values=(
                fac.get("serie", ""),
                fac.get("numero", ""),
                _to_fecha_ui_or_blank(fac.get("fecha_asiento", "")),
                fac.get("nombre", ""),
                f"{total:.2f}",
                "Si" if fac.get("generada") else "No",
                fac.get("fecha_generacion", ""),
                "Si" if fac.get("enviado") else "No",
                fac.get("fecha_envio", ""),
            ),
        )

    def insert_albaran_row(self, alb: dict, total: float):
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
                factura_txt = f"{fac.get('serie','')}{fac.get('numero','')}"
        self.tv_albaranes.insert(
            "",
            tk.END,
            iid=str(alb.get("id")),
            values=(
                alb.get("numero", ""),
                _to_fecha_ui_or_blank(alb.get("fecha_asiento", "")),
                alb.get("nombre", ""),
                f"{total:.2f}",
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
        if col == "total":
            return _to_float(val)
        if col == "fecha":
            return _parse_date_ui(val) if val else date.min
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
            return datetime.combine(_parse_date_ui(txt), datetime.min.time())
        except Exception:
            return datetime.min

    def _numero_sort_key(self, val):
        txt = str(val or "").strip()
        digits = "".join(ch for ch in txt if ch.isdigit())
        num = int(digits) if digits else -1
        return (txt[:1].lower() if txt else "", num, txt.lower())

    def set_detalle_lineas(self, lineas):
        self.tv_detalle.delete(*self.tv_detalle.get_children())
        for ln in lineas or []:
            self.tv_detalle.insert(
                "",
                tk.END,
                values=(
                    ln.get("concepto", ""),
                    f"{_round2(ln.get('unidades')):.2f}",
                    f"{_round4(ln.get('precio')):.4f}",
                    f"{_round2(ln.get('base')):.2f}",
                    f"{_round2(ln.get('pct_iva')):.2f}",
                    f"{_round2(ln.get('cuota_iva')):.2f}",
                    f"{_round2(ln.get('pct_irpf')):.2f}",
                    f"{_round2(ln.get('cuota_irpf')):.2f}",
                ),
            )

    def set_albaran_lineas(self, lineas):
        self.tv_alb_detalle.delete(*self.tv_alb_detalle.get_children())
        for ln in lineas or []:
            self.tv_alb_detalle.insert(
                "",
                tk.END,
                values=(
                    ln.get("concepto", ""),
                    f"{_round2(ln.get('unidades')):.2f}",
                    f"{_round4(ln.get('precio')):.4f}",
                    f"{_round2(ln.get('base')):.2f}",
                    f"{_round2(ln.get('pct_iva')):.2f}",
                    f"{_round2(ln.get('cuota_iva')):.2f}",
                    f"{_round2(ln.get('pct_irpf')):.2f}",
                    f"{_round2(ln.get('cuota_irpf')):.2f}",
                ),
            )

    def get_selected_ids(self):
        sel = list(self.tv.selection())
        if sel:
            return sel
        focus = self.tv.focus()
        return [focus] if focus else []

    def get_selected_albaran_ids(self):
        sel = list(self.tv_albaranes.selection())
        if sel:
            return sel
        focus = self.tv_albaranes.focus()
        return [focus] if focus else []

    def open_factura_dialog(self, factura, numero_sugerido=""):
        dlg = FacturaDialog(
            self,
            self.gestor,
            self.codigo,
            self.ejercicio,
            int(self.empresa_conf.get("digitos_plan", 8)),
            factura,
            numero_sugerido=numero_sugerido,
            titulo="Factura emitida",
        )
        return dlg.result

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
        )
        return dlg.result

    def open_terceros_dialog(self, codigo_empresa, ejercicio, ndig_plan):
        TercerosEmpresaDialog(self, self.gestor, codigo_empresa, ejercicio, ndig_plan)

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def _selected_ids(self):
        return self.get_selected_ids()

    def _nueva(self):
        self.controller.nueva()

    def _editar(self):
        self.controller.editar()

    def _copiar(self):
        self.controller.copiar()

    def _eliminar(self):
        self.controller.eliminar()

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

    def _terceros(self):
        self.controller.terceros()

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
