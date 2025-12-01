import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import Dialog
from utilidades import validar_subcuenta_longitud

DEFAULT_COLS_BANCOS = [
    "Fecha Asiento","Descripcion Asiento","Concepto","Importe",
]
DEFAULT_COLS_FACTURAS = [
    "Serie","Numero Factura","Numero Factura Largo SII",
    "Fecha Asiento","Fecha Expedicion","Fecha Operacion",
    "NIF Cliente Proveedor","Nombre Cliente Proveedor",
    "Descripcion Factura","Observaciones",
    "Cuenta Cliente Proveedor","Cuenta Compras Ventas","Cuenta IVA",
    "Cuenta Recargo","Cuenta Retenciones","Cuenta Proveedor Importacion",
    "Cuenta Tesoreria Cobro Pago",
    "Base","Porcentaje IVA","Cuota IVA","Porcentaje Recargo Equivalencia",
    "Cuota Recargo Equivalencia","Porcentaje Retencion IRPF","Cuota Retencion IRPF",
    "Marca Factura Rectificativa","Fecha Original Rectificativa","Fecha Registro SII",
    "Descripcion Ampliada Factura SII","Fecha Factura A Rectificar",
    "Numero Factura A Rectificar","DUA","Tipo Factura SII","Clave Tipo Factura SII",
    "NIF Representante","ISP Num Autofactura","Impreso",
    "Es Toda La Factura Percibida En Metalico","Importe Percibido Metalico",
    "Es Toda La Factura Transmision Inmueble Sujeto IVA","Importe Transmision Inmuebles Sujeto IVA",
    "Factura Tique Inicial SII","Factura Tique Final SII",
    "Numero Documentos Incluidos En La Serie","Emitida Por Terceros SII",
    "Emitida Varios Destinatarios SII","Emitida Cupones Bonificaciones SII",
    "Clave Retencion","Subclave Retencion","Naturaleza Retencion",
    "Tipo FACTURA Factura Abono Rectificativa","Va A Iva","Factura En Prorrata",
    "Afecta Modelo415","Marca Criterio Caja","Documento",
    "Departamento Analitica","Porcentaje Analitica","Importe Analitica"
]

def default_excel_columns_for(tipo: str) -> dict:
    return {k: "" for k in (DEFAULT_COLS_BANCOS if tipo=="bancos" else DEFAULT_COLS_FACTURAS)}

def _row(parent, label, var, w=24):
    fr = ttk.Frame(parent); fr.pack(fill=tk.X, pady=3)
    ttk.Label(fr, text=label, width=30).pack(side=tk.LEFT)
    ttk.Entry(fr, textvariable=var, width=w).pack(side=tk.LEFT, fill=tk.X, expand=True)

class InlineKVEditor(ttk.Frame):
    def __init__(self, master, columns=("clave","letra"), headers=("Clave","Letra")):
        super().__init__(master)
        self.columns = columns
        self.tv = ttk.Treeview(self, columns=columns, show="headings", height=12)
        for c,h in zip(columns, headers):
            self.tv.heading(c, text=h)
            self.tv.column(c, width=280 if c==columns[0] else 120, stretch=True)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.tv.bind("<Double-1>", self._begin_edit)
        self.tv.bind("<Return>", self._apply_edit)
        self.tv.bind("<Escape>", self._cancel_edit)
        self.tv.bind("<Up>", self._nav_up)
        self.tv.bind("<Down>", self._nav_down)
        self._edit_info = None
        self._last_col = None

    def load_dict(self, d):
        self.tv.delete(*self.tv.get_children())
        for k,v in (d or {}).items():
            self.tv.insert("", tk.END, values=(k, v))

    def to_dict(self):
        out = {}
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values")
            if len(vals) >= 2:
                out[str(vals[0])] = str(vals[1])
        return out

    def _begin_edit(self, event):
        region = self.tv.identify("region", event.x, event.y)
        if region != "cell":
            return
        rowid = self.tv.identify_row(event.y)
        if not rowid:
            return
        colid = self.tv.identify_column(event.x)
        if colid != "#2":
            return
        self._last_col = colid
        x, y, w, h = self.tv.bbox(rowid, colid)
        old = self.tv.set(rowid, self.columns[1])
        entry = ttk.Entry(self.tv)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, old or ""); entry.focus_set(); entry.select_range(0, tk.END)
        self._edit_info = (rowid, colid, entry)
        entry.bind("<Return>", self._apply_edit)
        entry.bind("<Escape>", self._cancel_edit)
        entry.bind("<Up>", self._nav_up)
        entry.bind("<Down>", self._nav_down)
        entry.bind("<FocusOut>", self._apply_edit)

    def _apply_edit(self, event=None):
        if not self._edit_info: return
        rowid, colid, entry = self._edit_info
        new_val = entry.get().strip().upper()
        entry.destroy()
        self.tv.set(rowid, self.columns[1], new_val)
        self._edit_info = None

    def _cancel_edit(self, event=None):
        if not self._edit_info: return
        _, _, entry = self._edit_info
        entry.destroy()
        self._edit_info = None

    def _move_selection(self, direction):
        items = self.tv.get_children()
        if not items: return
        sel = self.tv.selection()
        if not sel:
            target = items[0]
        else:
            idx = list(items).index(sel[0])
            idx = max(0, min(len(items)-1, idx + (1 if direction>0 else -1)))
            target = items[idx]
        self.tv.selection_set(target); self.tv.see(target)
        if self._last_col == "#2":
            x, y, w, h = self.tv.bbox(target, "#2")
            ev = tk.Event(); ev.x, ev.y = x + w//2, y + h//2
            self._begin_edit(ev)

    def _nav_up(self, event=None):
        self._apply_edit(); self._move_selection(-1); return "break"

    def _nav_down(self, event=None):
        self._apply_edit(); self._move_selection(+1); return "break"

class ConfigPlantillaDialog(Dialog):
    def __init__(self, parent, gestor, empresa, tipo, plantilla=None):
        self.gestor = gestor
        self.empresa = empresa
        self.tipo = tipo
        self.pl = dict(plantilla or {})
        super().__init__(parent, f"Configurar plantilla — {tipo.capitalize()}")

    def body(self, master):
        self.ndig = int(self.empresa.get("digitos_plan", 8))
        nb = ttk.Notebook(master)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        t_gen = ttk.Frame(nb)
        nb.add(t_gen, text="General")
        
        if self.tipo == "bancos":
            self.var_banco = tk.StringVar(value=self.pl.get("banco",""))
            self.var_sub_banco = tk.StringVar(value=self.pl.get("subcuenta_banco",""))
            self.var_sub_def = tk.StringVar(value=self.pl.get("subcuenta_por_defecto",""))
            _row(t_gen, "Banco", self.var_banco)
            _row(t_gen, "Subcuenta banco", self.var_sub_banco)
            _row(t_gen, "Subcuenta por defecto", self.var_sub_def)
        else:
            self.var_nombre = tk.StringVar(value=self.pl.get("nombre",""))
            if self.tipo == "emitidas":
                self.var_pref = tk.StringVar(value=self.pl.get("cuenta_cliente_prefijo","430"))
                self.var_ing = tk.StringVar(value=self.pl.get("cuenta_ingreso_por_defecto","70000000"))
                self.var_iva_def = tk.StringVar(value=self.pl.get("cuenta_iva_repercutido_defecto","47700000"))
                _row(t_gen, "Nombre plantilla", self.var_nombre)
                _row(t_gen, "Subcuenta clientes", self.var_pref)
                _row(t_gen, "Cuenta Ingreso", self.var_ing)
                _row(t_gen, "Cuenta IVA repercutido", self.var_iva_def)
            else:
                self.var_pref = tk.StringVar(value=self.pl.get("cuenta_proveedor_prefijo","400"))
                self.var_gasto = tk.StringVar(value=self.pl.get("cuenta_gasto_por_defecto","62900000"))
                self.var_iva_def = tk.StringVar(value=self.pl.get("cuenta_iva_soportado_defecto","47200000"))
                _row(t_gen, "Nombre plantilla", self.var_nombre)
                _row(t_gen, "Subcuenta proveedores", self.var_pref)
                _row(t_gen, "Cuenta Gasto", self.var_gasto)
                _row(t_gen, "Cuenta IVA soportado", self.var_iva_def)

        t_xl = ttk.Frame(nb); nb.add(t_xl, text="Excel")
        cols = (self.pl.get("excel") or {}).get("columnas") or default_excel_columns_for(self.tipo)
        self.var_primera = tk.StringVar(value=str((self.pl.get("excel") or {}).get("primera_fila_procesar", 2)))
        self.var_ignorar = tk.StringVar(value=(self.pl.get("excel") or {}).get("ignorar_filas",""))
        self.var_gen = tk.StringVar(value=(self.pl.get("excel") or {}).get("condicion_cuenta_generica",""))
        _row(t_xl, "Primera fila procesar", self.var_primera, w=8)
        _row(t_xl, "Ignorar filas (ej. Q=NOPROCESARFACTURA)", self.var_ignorar, w=28)
        _row(t_xl, "Condición cuenta genérica (ej. D=PARTICULAR)", self.var_gen, w=28)
        ttk.Label(t_xl, text="Mapeo de columnas (Clave → Letra)").pack(anchor="w", padx=6)
        self.kv = InlineKVEditor(t_xl, ("clave","letra"), ("Clave","Letra"))
        self.kv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.kv.load_dict(cols)

        if self.tipo == "bancos":
            t_con = ttk.Frame(nb); nb.add(t_con, text="Conceptos")
            self.pats = ttk.Treeview(t_con, columns=("patron","subcuenta"), show="headings", height=10)
            self.pats.heading("patron", text="Patrón (usa * comodín)")
            self.pats.heading("subcuenta", text="Subcuenta")
            self.pats.column("patron", width=360); self.pats.column("subcuenta", width=160)
            self.pats.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            bar = ttk.Frame(t_con); bar.pack(fill=tk.X, padx=4, pady=4)
            ttk.Button(bar, text="Añadir", command=lambda: self._pat_add()).pack(side=tk.LEFT)
            ttk.Button(bar, text="Editar", command=lambda: self._pat_edit()).pack(side=tk.LEFT, padx=6)
            ttk.Button(bar, text="Eliminar", command=lambda: self._pat_del()).pack(side=tk.LEFT)
            for it in (self.pl.get("conceptos") or []):
                self.pats.insert("", tk.END, values=(it.get("patron",""), it.get("subcuenta","")))
        return master

    def _pat_add(self):
        top = tk.Toplevel(self); top.title("Nuevo patrón"); top.resizable(False, False)
        v1 = tk.StringVar(); v2 = tk.StringVar()
        _row(top, "Patrón", v1); _row(top, "Subcuenta", v2)
        def ok():
            try:
                validar_subcuenta_longitud(v2.get(), self.ndig, "subcuenta")
                self.pats.insert("", tk.END, values=(v1.get().strip(), v2.get().strip()))
                top.destroy()
            except Exception as e:
                messagebox.showerror("Gest2A3Eco", str(e))
        ttk.Button(top, text="Aceptar", command=ok).pack(pady=6)

    def _pat_edit(self):
        sel = self.pats.selection()
        if not sel: return
        patron, sub = self.pats.item(sel[0], "values")
        top = tk.Toplevel(self); top.title("Editar patrón"); top.resizable(False, False)
        v1 = tk.StringVar(value=patron); v2 = tk.StringVar(value=sub)
        _row(top, "Patrón", v1); _row(top, "Subcuenta", v2)
        def ok():
            try:
                validar_subcuenta_longitud(v2.get(), self.ndig, "subcuenta")
                self.pats.item(sel[0], values=(v1.get().strip(), v2.get().strip()))
                top.destroy()
            except Exception as e:
                messagebox.showerror("Gest2A3Eco", str(e))
        ttk.Button(top, text="Aceptar", command=ok).pack(pady=6)

    def _pat_del(self):
        sel = self.pats.selection()
        if sel: self.pats.delete(sel[0])

    def validate(self):
        try:
            if self.tipo == "bancos":
                validar_subcuenta_longitud(self.var_sub_banco.get(), self.ndig, "subcuenta banco")
                validar_subcuenta_longitud(self.var_sub_def.get(), self.ndig, "subcuenta por defecto")
            else:
                if self.tipo == "emitidas":
                    validar_subcuenta_longitud(self.var_ing.get(), self.ndig, "cuenta ingreso")
                    validar_subcuenta_longitud(self.var_iva_def.get(), self.ndig, "cuenta IVA repercutido")
                else:
                    validar_subcuenta_longitud(self.var_gasto.get(), self.ndig, "cuenta gasto")
                    validar_subcuenta_longitud(self.var_iva_def.get(), self.ndig, "cuenta IVA soportado")
            return True
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e)); return False

    def apply(self):
        self.pl["codigo_empresa"] = self.empresa.get("codigo")
        if self.tipo == "bancos":
            self.pl["banco"] = self.var_banco.get().strip()
            self.pl["subcuenta_banco"] = self.var_sub_banco.get().strip()
            self.pl["subcuenta_por_defecto"] = self.var_sub_def.get().strip()
        else:
            self.pl["nombre"] = self.var_nombre.get().strip()
            if self.tipo == "emitidas":
                self.pl["cuenta_cliente_prefijo"] = self.var_pref.get().strip()
                self.pl["cuenta_ingreso_por_defecto"] = self.var_ing.get().strip()
                self.pl["cuenta_iva_repercutido_defecto"] = self.var_iva_def.get().strip()
            else:
                self.pl["cuenta_proveedor_prefijo"] = self.var_pref.get().strip()
                self.pl["cuenta_gasto_por_defecto"] = self.var_gasto.get().strip()
                self.pl["cuenta_iva_soportado_defecto"] = self.var_iva_def.get().strip()
        self.pl["excel"] = {
            "primera_fila_procesar": int(self.var_primera.get() or "2"),
            "ignorar_filas": self.var_ignorar.get().strip(),
            "condicion_cuenta_generica": self.var_gen.get().strip(),
            "columnas": self.kv.to_dict()
        }
        if self.tipo == "bancos":
            arr=[]
            for iid in getattr(self, "pats").get_children():
                patron, sub = self.pats.item(iid, "values")
                arr.append({"patron": str(patron), "subcuenta": str(sub)})
            self.pl["conceptos"] = arr
        # MUY IMPORTANTE: marcar que hay resultado para que el caller persista
        self.result = True

class UIPlantillasEmpresa(ttk.Frame):
    def __init__(self, parent, gestor, empresa_codigo, empresa_nombre):
        super().__init__(parent)
        self.gestor = gestor; self.codigo = empresa_codigo; self.nombre = empresa_nombre
        self.empresa = gestor.get_empresa(empresa_codigo) or {"codigo":empresa_codigo,"digitos_plan":8}
        self._build()

    def _build(self):
        ttk.Label(self, text=f"Plantillas de {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(pady=6, anchor="w", padx=10)
        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self._tab_bancos = self._build_tab(nb, "bancos", ("banco","subcuenta_banco","subcuenta_por_defecto"))
        self._tab_emitidas = self._build_tab(nb, "emitidas", ("nombre","cuenta_cliente_prefijo","cuenta_iva_repercutido_defecto"))
        self._tab_recibidas = self._build_tab(nb, "recibidas", ("nombre","cuenta_proveedor_prefijo","cuenta_iva_soportado_defecto"))
        self._refresh_all()

    def _build_tab(self, nb, title, cols):
        frame = ttk.Frame(nb); nb.add(frame, text=title)
        tv = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c in cols:
            tv.heading(c, text=c.replace("_"," ").title()); tv.column(c, width=220)
        tv.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        bar = ttk.Frame(frame); bar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(bar, text="Nueva Plantilla", style="Primary.TButton", command=lambda t=title: self._nuevo(t)).pack(side=tk.LEFT)
        ttk.Button(bar, text="Configurar…", style="Primary.TButton", command=lambda tv=tv, t=title: self._config(tv, t)).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Eliminar Plantilla", style="Primary.TButton", command=lambda tv=tv, t=title: self._eliminar(tv, t)).pack(side=tk.LEFT)
        return {"frame": frame, "tv": tv, "cols": cols}

    def _refresh_all(self):
        tv = self._tab_bancos["tv"]; tv.delete(*tv.get_children())
        for p in self.gestor.listar_bancos(self.codigo):
            tv.insert("", tk.END, values=(p.get("banco"), p.get("subcuenta_banco"), p.get("subcuenta_por_defecto")))
        tv = self._tab_emitidas["tv"]; tv.delete(*tv.get_children())
        for p in self.gestor.listar_emitidas(self.codigo):
            tv.insert("", tk.END, values=(p.get("nombre"), p.get("cuenta_cliente_prefijo","430"), p.get("cuenta_iva_repercutido_defecto","47700000")))
        tv = self._tab_recibidas["tv"]; tv.delete(*tv.get_children())
        for p in self.gestor.listar_recibidas(self.codigo):
            tv.insert("", tk.END, values=(p.get("nombre"), p.get("cuenta_proveedor_prefijo","400"), p.get("cuenta_iva_soportado_defecto","47200000")))

    def _nuevo(self, title):
        tipo = "bancos" if "Bancos" in title else ("emitidas" if "emitidas" in title else "recibidas")
        dlg = ConfigPlantillaDialog(self, self.gestor, self.empresa, tipo, {})
        if dlg.result:
            if tipo == "bancos":
                self.gestor.upsert_banco(dlg.pl)
            elif tipo == "emitidas":
                self.gestor.upsert_emitida(dlg.pl)
            else:
                self.gestor.upsert_recibida(dlg.pl)
            self._refresh_all()
            messagebox.showinfo("Gest2A3Eco", "Plantilla guardada.")

    def _sel_key(self, tv, tipo):
        sel = tv.selection()
        if not sel: return None
        v = tv.item(sel[0], "values")
        return v[0]

    def _config(self, tv, title):
        tipo = "bancos" if "Bancos" in title else ("emitidas" if "emitidas" in title else "recibidas")
        key = self._sel_key(tv, tipo)
        if not key:
            messagebox.showinfo("Gest2A3Eco","Selecciona una plantilla.")
            return
        if tipo == "bancos":
            pl = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==key), None)
        elif tipo == "emitidas":
            pl = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==key), None)
        else:
            pl = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==key), None)
        dlg = ConfigPlantillaDialog(self, self.gestor, self.empresa, tipo, pl)
        if dlg.result:
            if tipo == "bancos":
                self.gestor.upsert_banco(dlg.pl)
            elif tipo == "emitidas":
                self.gestor.upsert_emitida(dlg.pl)
            else:
                self.gestor.upsert_recibida(dlg.pl)
            self._refresh_all()
            messagebox.showinfo("Gest2A3Eco", "Cambios guardados.")

    def _eliminar(self, tv, title):
        tipo = "bancos" if "Bancos" in title else ("emitidas" if "emitidas" in title else "recibidas")
        key = self._sel_key(tv, tipo)
        if not key: return
        if not messagebox.askyesno("Gest2A3Eco","¿Eliminar la plantilla seleccionada?"): return
        if tipo == "bancos":
            self.gestor.eliminar_banco(self.codigo, key)
        elif tipo == "emitidas":
            self.gestor.eliminar_emitida(self.codigo, key)
        else:
            self.gestor.eliminar_recibida(self.codigo, key)
        self._refresh_all()
