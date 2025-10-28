import tkinter as tk
from tkinter import ttk, messagebox

DEFAULT_COLS_BANCOS = ["Fecha Asiento","Descripcion Factura","Concepto","Importe","NIF Cliente Proveedor","Nombre Cliente Proveedor"]
DEFAULT_COLS_FACTURAS = ["Serie","Numero Factura","Fecha Asiento","Fecha Expedicion","Fecha Operacion","NIF Cliente Proveedor","Nombre Cliente Proveedor","Descripcion Factura","Observaciones","Cuenta Cliente Proveedor","Cuenta Compras Ventas","Cuenta IVA","Cuenta Recargo","Cuenta Retenciones","Cuenta Proveedor Importacion","Cuenta Tesoreria Cobro Pago","Base","Porcentaje IVA","Cuota IVA","Porcentaje Recargo Equivalencia","Cuota Recargo Equivalencia","Porcentaje Retencion IRPF","Cuota Retencion IRPF","Marca Factura Rectificativa","Fecha Original Rectificativa","Fecha Registro SII","Numero Factura Largo SII","Descripcion Ampliada Factura SII","Fecha Factura A Rectificar","Numero Factura A Rectificar","DUA","Tipo Factura SII","Clave Tipo Factura SII","NIF Representante","ISP Num Autofactura","Impreso","Es Toda La Factura Percibida En Metalico","Importe Percibido Metalico","Es Toda La Factura Transmision Inmueble Sujeto IVA","Importe Transmision Inmuebles Sujeto IVA","Factura Tique Inicial SII","Factura Tique Final SII","Numero Documentos Incluidos En La Serie","Emitida Por Terceros SII","Emitida Varios Destinatarios SII","Emitida Cupones Bonificaciones SII","Clave Retencion","Subclave Retencion","Naturaleza Retencion","Tipo FACTURA Factura Abono Rectificativa","Va A Iva","Factura En Prorrata","Afecta Modelo415","Marca Criterio Caja","Documento","Departamento Analitica","Porcentaje Analitica","Importe Analitica"]

def default_excel_columns_for(tipo: str) -> dict:
    return {k: "" for k in (DEFAULT_COLS_BANCOS if tipo=='bancos' else DEFAULT_COLS_FACTURAS)}

def _mk_labeled_entry(parent, label, var, width=18):
    fr = ttk.Frame(parent); fr.pack(fill=tk.X, pady=2)
    ttk.Label(fr, text=label, width=26).pack(side=tk.LEFT)
    e = ttk.Entry(fr, textvariable=var, width=width); e.pack(side=tk.LEFT, fill=tk.X, expand=True)
    return e

class KVDialog(tk.Toplevel):
    def __init__(self, master, title, labels=("Clave","Valor"), initial=("", "")):
        super().__init__(master); self.title(title); self.resizable(False, False); self.result=None
        ttk.Label(self, text=labels[0]).grid(row=0, column=0, sticky='w', padx=8, pady=6); self.e1=ttk.Entry(self); self.e1.grid(row=0, column=1, padx=8, pady=6)
        ttk.Label(self, text=labels[1]).grid(row=1, column=0, sticky='w', padx=8, pady=6); self.e2=ttk.Entry(self); self.e2.grid(row=1, column=1, padx=8, pady=6)
        self.e1.insert(0, initial[0]); self.e2.insert(0, initial[1])
        fr=ttk.Frame(self); fr.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(fr, text="Aceptar", command=self._ok).pack(side=tk.LEFT, padx=6); ttk.Button(fr, text="Cancelar", command=self._cancel).pack(side=tk.LEFT)
        self.bind("<Return>", lambda e:self._ok()); self.bind("<Escape>", lambda e:self._cancel()); self.e1.focus(); self.grab_set(); self.wait_window(self)
    def _ok(self):
        a=self.e1.get().strip(); b=self.e2.get().strip()
        if not a: messagebox.showwarning("Gest2A3Eco","La clave no puede estar vacía."); return
        self.result=(a,b); self.destroy()
    def _cancel(self): self.result=None; self.destroy()

class KVEditor(ttk.Frame):
    def __init__(self, master, columns=("clave","valor"), headers=("Clave","Valor")):
        super().__init__(master); self.columns=columns
        self.tv=ttk.Treeview(self, columns=columns, show="headings", height=10)
        for c,h in zip(columns, headers): self.tv.heading(c, text=h); self.tv.column(c, width=260 if c==columns[0] else 140)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        fr=ttk.Frame(self); fr.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(fr, text="Añadir", command=self.add).pack(side=tk.LEFT); ttk.Button(fr, text="Editar", command=self.edit).pack(side=tk.LEFT, padx=6); ttk.Button(fr, text="Eliminar", command=self.remove).pack(side=tk.LEFT)
    def load_dict(self, d):
        self.tv.delete(*self.tv.get_children())
        for k,v in (d or {}).items(): self.tv.insert("", tk.END, values=(k, v))
    def to_dict(self):
        out={}; 
        for iid in self.tv.get_children():
            k,v=self.tv.item(iid,"values"); out[str(k)]=str(v)
        return out
    def add(self):
        d=KVDialog(self,"Añadir",("Clave","Letra"),("","")); 
        if d.result: self.tv.insert("", tk.END, values=d.result)
    def edit(self):
        sel=self.tv.selection(); 
        if not sel: return
        k,v=self.tv.item(sel[0],"values"); d=KVDialog(self,"Editar",("Clave","Letra"),(k,v))
        if d.result: self.tv.item(sel[0], values=d.result)
    def remove(self):
        sel=self.tv.selection(); 
        if not sel: return
        self.tv.delete(sel[0])

class UIPlantillasEmpresa(ttk.Frame):
    def __init__(self, master, gestor, empresa_codigo, empresa_nombre):
        super().__init__(master); self.gestor=gestor; self.codigo=empresa_codigo; self.nombre=empresa_nombre
        self.pack(fill=tk.BOTH, expand=True); self._build()

    # (Por brevedad, solo se incluye editor de Bancos con Configurar… que abre mapeo Excel)
    def _build(self):
        ttk.Label(self, text=f"Plantillas de {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(pady=6, anchor=tk.W, padx=10)
        fr = ttk.Frame(self); fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Bancos
        left = ttk.Frame(fr); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6,3), pady=6)
        right = ttk.Frame(fr); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3,6), pady=6)
        cols=("banco","subcuenta_banco","subcuenta_por_defecto")
        self.tv=ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c,t in zip(cols,["Banco","Subcta banco","Subcta por defecto"]): self.tv.heading(c, text=t); self.tv.column(c, width=180)
        self.tv.pack(fill=tk.BOTH, expand=True)
        btns=ttk.Frame(left); btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="Nuevo", command=self._nuevo).pack(side=tk.LEFT)
        ttk.Button(btns, text="Guardar", command=self._guardar).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Eliminar", command=self._eliminar).pack(side=tk.LEFT)
        ttk.Button(btns, text="Configurar…", command=self._config).pack(side=tk.RIGHT)
        self._refresh()

        self.b_banco=tk.StringVar(); self.b_sb=tk.StringVar(); self.b_sdef=tk.StringVar()
        self.b_dig=tk.StringVar(value="8"); self.b_eje=tk.StringVar(value="2025")
        ttk.Label(right, text="Editor de plantilla (Bancos)", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self._mk(right,"Banco",self.b_banco); self._mk(right,"Subcuenta banco",self.b_sb); self._mk(right,"Subcuenta por defecto",self.b_sdef); self._mk(right,"Dígitos plan",self.b_dig); self._mk(right,"Ejercicio",self.b_eje)
        self.tv.bind("<<TreeviewSelect>>", self._load_selected)

    def _mk(self, parent, label, var): _mk_labeled_entry(parent,label,var)

    def _refresh(self):
        self.tv.delete(*self.tv.get_children())
        for p in self.gestor.listar_bancos(self.codigo):
            self.tv.insert("", tk.END, values=(p.get("banco"), p.get("subcuenta_banco"), p.get("subcuenta_por_defecto")))

    def _load_selected(self, *_):
        sel=self.tv.selection()
        if not sel: return
        banco, *_ = self.tv.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==banco), None)
        if not p: return
        self.b_banco.set(p.get("banco","")); self.b_sb.set(p.get("subcuenta_banco","")); self.b_sdef.set(p.get("subcuenta_por_defecto",""))
        self.b_dig.set(str(p.get("digitos_plan",8))); self.b_eje.set(str(p.get("ejercicio",2025)))

    def _nuevo(self):
        self.b_banco.set(""); self.b_sb.set(""); self.b_sdef.set(""); self.b_dig.set("8"); self.b_eje.set("2025")

    def _guardar(self):
        try:
            plantilla={"codigo_empresa":self.codigo,"banco":self.b_banco.get().strip(),"subcuenta_banco":self.b_sb.get().strip(),"subcuenta_por_defecto":self.b_sdef.get().strip(),"digitos_plan":int(self.b_dig.get().strip() or "8"),"ejercicio":int(self.b_eje.get().strip() or "2025"),"excel":{"primera_fila_procesar":2,"ignorar_filas":"","condicion_cuenta_generica":"","columnas":{}}}
            ex = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==plantilla["banco"]), None)
            if ex and ex.get("excel"): plantilla["excel"]=ex["excel"]
            if not plantilla["excel"].get("columnas"):
                plantilla["excel"]["columnas"]=default_excel_columns_for("bancos")
            self.gestor.upsert_banco(plantilla); self._refresh(); messagebox.showinfo("Gest2A3Eco","Plantilla guardada.")
        except Exception as e: messagebox.showerror("Gest2A3Eco", str(e))

    def _eliminar(self):
        sel=self.tv.selection()
        if not sel: return
        banco, *_ = self.tv.item(sel[0], "values")
        self.gestor.eliminar_banco(self.codigo, banco); self._refresh()

    def _config(self):
        sel=self.tv.selection()
        if not sel: messagebox.showinfo("Gest2A3Eco","Selecciona una plantilla de banco."); return
        banco, *_ = self.tv.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==banco), None)
        if not p: return
        ConfigPlantillaDialog(self, self.gestor, self.codigo, "bancos", p)

class ConfigPlantillaDialog(tk.Toplevel):
    def __init__(self, master, gestor, empresa_codigo, tipo, plantilla):
        super().__init__(master)
        self.title(f"Configurar plantilla — {tipo.capitalize()}")
        self.gestor=gestor; self.codigo=empresa_codigo; self.tipo=tipo
        self.pl = dict(plantilla)
        self.resizable(True, True)

        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        t_excel = ttk.Frame(nb); nb.add(t_excel, text="Excel")
        frm_top = ttk.Frame(t_excel); frm_top.pack(fill=tk.X, padx=8, pady=(8,0))

        self.var_primera = tk.StringVar(value=str(((self.pl.get("excel") or {}).get("primera_fila_procesar", 2))))
        self.var_ignorar = tk.StringVar(value=(self.pl.get("excel") or {}).get("ignorar_filas", ""))
        self.var_gen = tk.StringVar(value=(self.pl.get("excel") or {}).get("condicion_cuenta_generica", ""))

        row1 = ttk.Frame(frm_top); row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Primera fila procesar", width=24).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.var_primera, width=8).pack(side=tk.LEFT)

        row2 = ttk.Frame(frm_top); row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Ignorar filas (ej. Q=NOPROCESARFACTURA)", width=36).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_ignorar, width=32).pack(side=tk.LEFT)

        row3 = ttk.Frame(frm_top); row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Cond. cuenta genérica (ej. D=PARTICULAR)", width=36).pack(side=tk.LEFT)
        ttk.Entry(row3, textvariable=self.var_gen, width=32).pack(side=tk.LEFT)

        ttk.Label(t_excel, text="Mapeo de columnas (Clave → Letra)").pack(anchor=tk.W, padx=8, pady=(8,0))
        self.kv = KVEditor(t_excel, ("clave","letra"), ("Clave","Letra")); self.kv.pack(fill=tk.BOTH, expand=True)
        current_map = ((self.pl.get("excel") or {}).get("columnas")) or {}
        if not current_map:
            current_map = default_excel_columns_for(tipo)
        self.kv.load_dict(current_map)

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(bar, text="Guardar", command=self._save).pack(side=tk.RIGHT, padx=6)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)

        self.grab_set(); self.wait_window(self)

    def _save(self):
        self.pl["excel"] = self.pl.get("excel", {})
        self.pl["excel"]["primera_fila_procesar"] = int(self.var_primera.get() or "2")
        self.pl["excel"]["ignorar_filas"] = self.var_ignorar.get().strip()
        self.pl["excel"]["condicion_cuenta_generica"] = self.var_gen.get().strip()
        self.pl["excel"]["columnas"] = self.kv.to_dict()
        # persist (solo bancos en este mini-editor)
        arr = self.gestor.listar_bancos(self.codigo)
        for i,p in enumerate(arr):
            if p.get("banco")==self.pl.get("banco"):
                arr[i] = self.pl; break
        else:
            arr.append(self.pl)
        self.gestor.save()
        messagebox.showinfo("Gest2A3Eco","Configuración guardada.")
        self.destroy()
