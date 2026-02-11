import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime
from tkinter.simpledialog import Dialog, askstring

from views.ui_facturas_emitidas import TercerosGlobalDialog
from utils.utilidades import format_num_es, load_monedas
from controllers.ui_seleccion_controller import SeleccionEmpresaController

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

def _to_float_es(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0

def _fmt2(x) -> str:
    return format_num_es(x, 2)

def _parse_datetime_ui(val: str) -> datetime:
    txt = str(val or "").strip()
    if not txt:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(txt, fmt)
        except Exception:
            continue
    try:
        d = _parse_date_ui(txt)
        return datetime(d.year, d.month, d.day)
    except Exception:
        return datetime.min

class EmpresaDialog(Dialog):
    def __init__(self, parent, titulo, empresa=None):
        base = {
            "codigo": "",
            "nombre": "",
            "digitos_plan": 8,
            "ejercicio": 2025,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 1,
            "serie_emitidas_rect": "R",
            "siguiente_num_emitidas_rect": 1,
            "cuenta_bancaria": "",
            "cuentas_bancarias": "",
            "cif": "",
            "direccion": "",
            "cp": "",
            "poblacion": "",
            "provincia": "",
            "telefono": "",
            "email": "",
            "logo_path": "",
            "activo": True,
        }
        if empresa:
            base.update(empresa)
        # Normaliza valores None a "" para evitar errores de conversión
        for k in ("digitos_plan", "ejercicio", "serie_emitidas", "siguiente_num_emitidas", "serie_emitidas_rect", "siguiente_num_emitidas_rect"):
            if base.get(k) is None:
                base[k] = ""
        self.empresa = base
        super().__init__(parent, titulo)

    def body(self, master):
        self.var_codigo = tk.StringVar(value=str(self.empresa.get("codigo","")))
        self.var_nombre = tk.StringVar(value=str(self.empresa.get("nombre","")))
        self.var_dig = tk.StringVar(value=str(self.empresa.get("digitos_plan") or ""))
        self.var_eje = tk.StringVar(value=str(self.empresa.get("ejercicio") or ""))
        self.var_serie = tk.StringVar(value=str(self.empresa.get("serie_emitidas") or ""))
        self.var_next = tk.StringVar(value=str(self.empresa.get("siguiente_num_emitidas") or ""))
        self.var_serie_rect = tk.StringVar(value=str(self.empresa.get("serie_emitidas_rect") or ""))
        self.var_next_rect = tk.StringVar(value=str(self.empresa.get("siguiente_num_emitidas_rect") or ""))
        cuentas_raw = self.empresa.get("cuentas_bancarias") or self.empresa.get("cuenta_bancaria") or ""
        self.var_cuentas = tk.StringVar(value=str(cuentas_raw))
        self.var_cif = tk.StringVar(value=str(self.empresa.get("cif","")))
        self.var_dir = tk.StringVar(value=str(self.empresa.get("direccion","")))
        self.var_cp = tk.StringVar(value=str(self.empresa.get("cp","")))
        self.var_pob = tk.StringVar(value=str(self.empresa.get("poblacion","")))
        self.var_prov = tk.StringVar(value=str(self.empresa.get("provincia","")))
        self.var_tel = tk.StringVar(value=str(self.empresa.get("telefono","")))
        self.var_mail = tk.StringVar(value=str(self.empresa.get("email","")))
        self.var_logo = tk.StringVar(value=str(self.empresa.get("logo_path","")))
        self.var_activo = tk.BooleanVar(value=bool(self.empresa.get("activo", True)))

        ttk.Label(master, text="Codigo").grid(row=0, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_codigo).grid(row=0, column=1)
        ttk.Label(master, text="Nombre").grid(row=1, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_nombre, width=40).grid(row=1, column=1)
        ttk.Label(master, text="Digitos plan").grid(row=2, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dig, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(master, text="Ejercicio").grid(row=3, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_eje, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(master, text="Serie emitidas").grid(row=4, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_serie, width=10).grid(row=4, column=1, sticky="w")
        ttk.Label(master, text="Siguiente numero").grid(row=5, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_next, width=10).grid(row=5, column=1, sticky="w")
        ttk.Label(master, text="Serie rectificativas").grid(row=6, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_serie_rect, width=10).grid(row=6, column=1, sticky="w")
        ttk.Label(master, text="Siguiente num. rectificativas").grid(row=7, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_next_rect, width=10).grid(row=7, column=1, sticky="w")
        ttk.Label(master, text="Cuentas bancarias (coma)").grid(row=8, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_cuentas, width=40).grid(row=8, column=1, sticky="w")
        ttk.Label(master, text="CIF/NIF").grid(row=9, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_cif, width=18).grid(row=9, column=1, sticky="w")
        ttk.Label(master, text="Direccion").grid(row=10, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dir, width=40).grid(row=10, column=1, sticky="w")
        ttk.Label(master, text="CP").grid(row=11, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_cp, width=8).grid(row=11, column=1, sticky="w")
        ttk.Label(master, text="Poblacion").grid(row=12, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_pob, width=32).grid(row=12, column=1, sticky="w")
        ttk.Label(master, text="Provincia").grid(row=13, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_prov, width=24).grid(row=13, column=1, sticky="w")
        ttk.Label(master, text="Telefono").grid(row=14, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_tel, width=20).grid(row=14, column=1, sticky="w")
        ttk.Label(master, text="Email").grid(row=15, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_mail, width=30).grid(row=15, column=1, sticky="w")
        ttk.Label(master, text="Logo (JPG)").grid(row=16, column=0, sticky="w")
        row_logo = ttk.Frame(master)
        row_logo.grid(row=16, column=1, sticky="we")
        ttk.Entry(row_logo, textvariable=self.var_logo, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_logo, text="Buscar", command=self._choose_logo).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(master, text="Activo", variable=self.var_activo).grid(row=17, column=0, sticky="w", pady=(6, 0))
        return master

    def _cuenta_bancaria_default(self):
        cuentas = self.var_cuentas.get().strip()
        if not cuentas:
            return ""
        for sep in ["\n", ";", ","]:
            cuentas = cuentas.replace(sep, ",")
        for p in cuentas.split(","):
            p = p.strip()
            if p:
                return p
        return ""

    def _choose_logo(self):
        path = filedialog.askopenfilename(title="Seleccionar logo (JPG)", filetypes=[("JPEG", "*.jpg;*.jpeg"), ("Todos", "*.*")])
        if path:
            self.var_logo.set(path)

    def apply(self):
        try:
            self.result = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "ejercicio": int(self.var_eje.get().strip() or "2025"),
                "serie_emitidas": self.var_serie.get().strip() or "A",
                "siguiente_num_emitidas": int(self.var_next.get().strip() or "1"),
                "serie_emitidas_rect": self.var_serie_rect.get().strip() or "R",
                "siguiente_num_emitidas_rect": int(self.var_next_rect.get().strip() or "1"),
                "cuenta_bancaria": self._cuenta_bancaria_default(),
                "cuentas_bancarias": self.var_cuentas.get().strip(),
                "cif": self.var_cif.get().strip(),
                "direccion": self.var_dir.get().strip(),
                "cp": self.var_cp.get().strip(),
                "poblacion": self.var_pob.get().strip(),
                "provincia": self.var_prov.get().strip(),
                "telefono": self.var_tel.get().strip(),
                "email": self.var_mail.get().strip(),
                "logo_path": self.var_logo.get().strip(),
                "activo": bool(self.var_activo.get()),
            }
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            self.result = None

class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, parent, gestor, on_ok):
        super().__init__(parent)
        self.gestor = gestor
        self.on_ok = on_ok
        self._fact_sort_state = {}
        self._empresa_default_ej = {}
        monedas = load_monedas()
        self._default_moneda_simbolo = str(monedas[0].get("simbolo")) if monedas else ""
        self.pack(fill=tk.BOTH, expand=True)
        self.controller = SeleccionEmpresaController(gestor, on_ok, self)
        self._build()
        self.controller.refresh()

    def _build(self):
        ttk.Label(self, text="Selecciona empresa", font=("Segoe UI", 12, "bold")).pack(pady=8)

        search_row = ttk.Frame(self)
        search_row.pack(fill=tk.X, padx=10, pady=(4, 0))
        self.var_ver_bajas = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_row, text="Ver bajas", variable=self.var_ver_bajas, command=self.controller.apply_filter).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(search_row, text="Buscar").pack(side=tk.LEFT)
        self.var_buscar = tk.StringVar()
        entry_buscar = ttk.Entry(search_row, textvariable=self.var_buscar, width=40)
        entry_buscar.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(search_row, text="Limpiar", command=lambda: self.var_buscar.set("")).pack(side=tk.LEFT)
        self.var_buscar.trace_add("write", lambda *_: self.controller.apply_filter())

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self.tv = ttk.Treeview(tree_frame, columns=("codigo","nombre","cif","digitos","ejercicios","serie","next"), show="headings", height=12)
        for c,t,w in (
            ("codigo","Codigo",120),
            ("nombre","Nombre",320),
            ("cif","CIF",120),
            ("digitos","Digitos",70),
            ("ejercicios","Ejercicios",120),
            ("serie","Serie",80),
            ("next","Siguiente",90),
        ):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tv.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tv.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(bar, text="Importar CSV empresas", style="Primary.TButton", command=self.controller.importar_csv).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(bar, text="Nueva empresa", style="Primary.TButton", command=self.controller.nueva).pack(side=tk.LEFT)
        ttk.Button(bar, text="Editar empresa", style="Primary.TButton", command=self.controller.editar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Copiar empresa", style="Primary.TButton", command=self.controller.copiar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Eliminar empresa", style="Danger.TButton", command=self.controller.eliminar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Terceros", style="Primary.TButton", command=self.controller.terceros).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Contabilidad", style="Primary.TButton", command=self.controller.continuar_contabilidad).pack(side=tk.RIGHT, padx=(6,0))
        ttk.Button(bar, text="Facturacion", style="Primary.TButton", command=self.controller.continuar_facturacion).pack(side=tk.RIGHT)

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill=tk.X, padx=10, pady=(6, 4))

        ttk.Label(self, text="Facturas (todas las empresas)", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 0))

        fact_filter = ttk.Frame(self)
        fact_filter.pack(fill=tk.X, padx=10, pady=(4, 0))
        ttk.Label(fact_filter, text="Ejercicio").pack(side=tk.LEFT)
        self.var_fact_ejercicio = tk.StringVar(value="Todos")
        self.cb_fact_ejercicio = ttk.Combobox(fact_filter, textvariable=self.var_fact_ejercicio, width=8, state="readonly")
        self.cb_fact_ejercicio.pack(side=tk.LEFT, padx=6)
        self.cb_fact_ejercicio.bind("<<ComboboxSelected>>", lambda e: self.controller.apply_facturas_filter())

        ttk.Label(fact_filter, text="Buscar empresa").pack(side=tk.LEFT, padx=(12, 0))
        self.var_fact_empresa_text = tk.StringVar()
        entry_fact_empresa_text = ttk.Entry(fact_filter, textvariable=self.var_fact_empresa_text, width=36)
        entry_fact_empresa_text.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        self.var_fact_empresa_text.trace_add("write", lambda *_: self.controller.apply_facturas_filter())
        ttk.Button(fact_filter, text="Limpiar", command=lambda: self.var_fact_empresa_text.set("")).pack(side=tk.LEFT, padx=6)
        ttk.Button(fact_filter, text="Actualizar listado", style="Primary.TButton", command=self.controller.refresh_facturas_global).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(fact_filter, text="Copiar factura", style="Primary.TButton", command=self.controller.copiar_factura_global).pack(side=tk.LEFT, padx=(6, 0))

        fact_frame = ttk.Frame(self)
        fact_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.tv_facturas = ttk.Treeview(
            fact_frame,
            columns=("empresa", "empresa_nombre", "ejercicio", "serie", "numero", "fecha", "cliente", "total", "generada", "fecha_gen", "enviado", "fecha_envio"),
            show="headings",
            height=10,
        )
        for c, t, w, align in (
            ("empresa", "Codigo", 90, "w"),
            ("empresa_nombre", "Empresa", 200, "w"),
            ("ejercicio", "Ejercicio", 80, "center"),
            ("serie", "Serie", 70, "w"),
            ("numero", "Numero", 120, "w"),
            ("fecha", "Fecha", 100, "w"),
            ("cliente", "Cliente", 240, "w"),
            ("total", "Total", 100, "e"),
            ("generada", "Generada", 90, "center"),
            ("fecha_gen", "Fecha gen.", 110, "w"),
            ("enviado", "Enviado", 90, "center"),
            ("fecha_envio", "Fecha envio", 110, "w"),
        ):
            self.tv_facturas.heading(c, text=t, command=lambda col=c: self._sort_facturas_global(col))
            self.tv_facturas.column(c, width=w, anchor=align)

        f_ys = ttk.Scrollbar(fact_frame, orient="vertical", command=self.tv_facturas.yview)
        self.tv_facturas.configure(yscrollcommand=f_ys.set)
        self.tv_facturas.grid(row=0, column=0, sticky="nsew")
        f_ys.grid(row=0, column=1, sticky="ns")
        fact_frame.columnconfigure(0, weight=1)
        fact_frame.rowconfigure(0, weight=1)

        # Monedas: se gestionan desde el menu contextual de configuracion

    def get_filter_text(self):
        return self.var_buscar.get()

    def get_ejercicio_filter(self):
        return None

    def get_ver_bajas(self):
        return bool(self.var_ver_bajas.get())

    def clear_empresas(self):
        self.tv.delete(*self.tv.get_children())
        self._empresa_default_ej = {}

    def insert_empresa(self, empresa):
        codigo = str(empresa.get("codigo") or "")
        self._empresa_default_ej[codigo] = empresa.get("ejercicio_default")
        ejercicios_txt = empresa.get("ejercicios_txt") or ""
        self.tv.insert("", tk.END, iid=codigo, values=(
            empresa.get("codigo"),
            empresa.get("nombre"),
            empresa.get("cif", ""),
            empresa.get("digitos_plan", 8),
            ejercicios_txt,
            empresa.get("serie_emitidas", "A"),
            empresa.get("siguiente_num_emitidas", 1),
        ))

    def get_selected_empresa_key(self):
        sel = self.tv.selection()
        if not sel:
            return None, None
        codigo = self.tv.item(sel[0], "values")[0]
        return codigo, self._empresa_default_ej.get(codigo)

    def select_empresa_by_codigo(self, codigo):
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values") or []
            if vals and vals[0] == codigo:
                self.tv.selection_set(iid)
                self.tv.see(iid)
                break

    def ask_csv_path(self):
        return filedialog.askopenfilename(
            title="Selecciona CSV de empresas",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )

    # ----- Facturas globales -----
    def set_facturas_filters(self, ejercicios):
        vals_ej = ["Todos"] + [str(e) for e in ejercicios]
        self.cb_fact_ejercicio["values"] = vals_ej
        if self.var_fact_ejercicio.get() not in vals_ej:
            self.var_fact_ejercicio.set(vals_ej[0])

    def get_facturas_filters(self):
        eje_txt = (self.var_fact_ejercicio.get() or "").strip()
        eje = None
        if eje_txt and eje_txt.lower() != "todos":
            try:
                eje = int(eje_txt)
            except Exception:
                eje = None
        empresa_txt = (self.var_fact_empresa_text.get() or "").strip().lower()
        return eje, empresa_txt

    def clear_facturas(self):
        self.tv_facturas.delete(*self.tv_facturas.get_children())

    def insert_factura_row(self, fac, total, empresa_nombre=""):
        sym = fac.get("moneda_simbolo") or self._default_moneda_simbolo
        self.tv_facturas.insert(
            "",
            tk.END,
            iid=f"{fac.get('codigo_empresa','')}::{fac.get('ejercicio','')}::{fac.get('id','')}",
            values=(
                fac.get("codigo_empresa", ""),
                empresa_nombre,
                fac.get("ejercicio", ""),
                fac.get("serie", ""),
                fac.get("numero", ""),
                _to_fecha_ui_or_blank(fac.get("fecha_asiento", "")),
                fac.get("nombre", ""),
                f"{_fmt2(total)} {sym}".strip() if sym else _fmt2(total),
                "Si" if fac.get("generada") else "No",
                fac.get("fecha_generacion", ""),
                "Si" if fac.get("enviado") else "No",
                fac.get("fecha_envio", ""),
            ),
        )

    def _sort_facturas_global(self, col):
        items = []
        for iid in self.tv_facturas.get_children(""):
            val = self.tv_facturas.set(iid, col)
            items.append((self._fact_sort_key(col, val), iid))
        reverse = self._fact_sort_state.get(col) == "asc"
        items.sort(key=lambda x: x[0], reverse=reverse)
        for idx, (_, iid) in enumerate(items):
            self.tv_facturas.move(iid, "", idx)
        self._fact_sort_state[col] = "desc" if reverse else "asc"

    def _fact_sort_key(self, col, val):
        if col in ("ejercicio",):
            try:
                return int(val)
            except Exception:
                return -1
        if col in ("total",):
            try:
                return _to_float_es(val)
            except Exception:
                return 0.0
        if col in ("fecha",):
            try:
                d = _parse_date_ui(str(val))
                return d.toordinal()
            except Exception:
                return 0
        if col in ("fecha_gen", "fecha_envio"):
            return _parse_datetime_ui(str(val)).timestamp()
        if col in ("enviado", "generada"):
            return 1 if str(val).lower() == "si" else 0
        return str(val).lower()

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)

    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def ask_admin_password(self):
        return askstring("Gest2A3Eco", "Contraseña de administrador:", show="*")

    def get_selected_factura_key(self):
        sel = self.tv_facturas.selection()
        if not sel:
            return None, None, None
        iid = sel[0]
        parts = str(iid).split("::")
        if len(parts) >= 3:
            codigo = parts[0]
            try:
                ejercicio = int(parts[1])
            except Exception:
                ejercicio = parts[1]
            fid = parts[2]
            return codigo, ejercicio, fid
        vals = self.tv_facturas.item(iid, "values") or []
        if len(vals) >= 3:
            return vals[0], vals[2], None
        return None, None, None

    def ask_copiar_factura_destino(self, empresas):
        dlg = tk.Toplevel(self)
        dlg.title("Copiar factura")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Selecciona empresa y ejercicio destino").pack(anchor="w")

        lb = tk.Listbox(frm, height=min(10, len(empresas)), exportselection=False)
        for e in empresas:
            texto = f"{e.get('codigo','')} - {e.get('nombre','')} ({e.get('ejercicio','')})"
            lb.insert(tk.END, texto)
        lb.pack(fill="both", expand=True, pady=6)
        if empresas:
            lb.selection_set(0)

        result = {"value": None}

        def _ok():
            sel = lb.curselection()
            if sel:
                idx = sel[0]
                emp = empresas[idx]
                result["value"] = (emp.get("codigo"), emp.get("ejercicio"))
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Copiar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=_cancel).pack(side=tk.LEFT, padx=4)

        dlg.wait_window(dlg)
        return result["value"]

    def open_empresa_dialog(self, titulo, empresa=None):
        dlg = EmpresaDialog(self, titulo, empresa)
        return dlg.result

    def open_terceros_dialog(self, gestor):
        TercerosGlobalDialog(self, gestor)

    # ----- Monedas -----
    # Configuracion de monedas se maneja fuera de esta pantalla
