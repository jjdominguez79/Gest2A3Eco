import tkinter as tk
from tkinter import ttk, messagebox
import json

def _mk_labeled_entry(parent, label, var, width=18):
    fr = ttk.Frame(parent); fr.pack(fill=tk.X, pady=2)
    ttk.Label(fr, text=label, width=22).pack(side=tk.LEFT)
    e = ttk.Entry(fr, textvariable=var, width=width); e.pack(side=tk.LEFT, fill=tk.X, expand=True)
    return e

class KVDialog(tk.Toplevel):
    def __init__(self, master, title, labels=("Clave","Valor"), initial=("", "")):
        super().__init__(master)
        self.title(title); self.resizable(False, False)
        self.result = None
        ttk.Label(self, text=labels[0]).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.e1 = ttk.Entry(self); self.e1.grid(row=0, column=1, padx=8, pady=6)
        ttk.Label(self, text=labels[1]).grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.e2 = ttk.Entry(self); self.e2.grid(row=1, column=1, padx=8, pady=6)
        self.e1.insert(0, initial[0]); self.e2.insert(0, initial[1])
        fr = ttk.Frame(self); fr.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(fr, text="Aceptar", command=self._ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(fr, text="Cancelar", command=self._cancel).pack(side=tk.LEFT)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.e1.focus()
        self.grab_set()
        self.wait_window(self)

    def _ok(self):
        a = self.e1.get().strip(); b = self.e2.get().strip()
        if not a:
            messagebox.showwarning("Gest2A3Eco","La clave no puede estar vacía."); return
        self.result = (a, b)
        self.destroy()

    def _cancel(self):
        self.result = None; self.destroy()

class KVEditor(ttk.Frame):
    def __init__(self, master, columns=("clave","valor"), headers=("Clave","Valor")):
        super().__init__(master)
        self.columns = columns
        self.tv = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for c,h in zip(columns, headers):
            self.tv.heading(c, text=h)
            self.tv.column(c, width=240 if c==columns[0] else 120)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        fr = ttk.Frame(self); fr.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(fr, text="Añadir", command=self.add).pack(side=tk.LEFT)
        ttk.Button(fr, text="Editar", command=self.edit).pack(side=tk.LEFT, padx=6)
        ttk.Button(fr, text="Eliminar", command=self.remove).pack(side=tk.LEFT)

    def load_dict(self, d):
        self.tv.delete(*self.tv.get_children())
        for k,v in (d or {}).items():
            self.tv.insert("", tk.END, values=(k, v))

    def to_dict(self):
        out = {}
        for iid in self.tv.get_children():
            k, v = self.tv.item(iid, "values")
            out[str(k)] = str(v)
        return out

    def add(self):
        d = KVDialog(self, "Añadir", ("Clave","Letra"), ("",""))
        if d.result:
            self.tv.insert("", tk.END, values=d.result)

    def edit(self):
        sel = self.tv.selection()
        if not sel: return
        k, v = self.tv.item(sel[0], "values")
        d = KVDialog(self, "Editar", ("Clave","Letra"), (k, v))
        if d.result:
            self.tv.item(sel[0], values=d.result)

    def remove(self):
        sel = self.tv.selection()
        if not sel: return
        self.tv.delete(sel[0])

class PatternEditor(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.tv = ttk.Treeview(self, columns=("patron","subcuenta"), show="headings", height=10)
        self.tv.heading("patron", text="Patrón"); self.tv.column("patron", width=280)
        self.tv.heading("subcuenta", text="Subcuenta"); self.tv.column("subcuenta", width=140)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        fr = ttk.Frame(self); fr.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(fr, text="Añadir", command=self.add).pack(side=tk.LEFT)
        ttk.Button(fr, text="Editar", command=self.edit).pack(side=tk.LEFT, padx=6)
        ttk.Button(fr, text="Eliminar", command=self.remove).pack(side=tk.LEFT)

    def load_list(self, arr):
        self.tv.delete(*self.tv.get_children())
        for it in (arr or []):
            self.tv.insert("", tk.END, values=(it.get("patron",""), it.get("subcuenta","")))

    def to_list(self):
        out = []
        for iid in self.tv.get_children():
            patron, sub = self.tv.item(iid, "values")
            out.append({"patron": str(patron), "subcuenta": str(sub)})
        return out

    def add(self):
        d = KVDialog(self, "Añadir patrón", ("Patrón","Subcuenta"), ("",""))
        if d.result: self.tv.insert("", tk.END, values=d.result)

    def edit(self):
        sel = self.tv.selection()
        if not sel: return
        patron, sub = self.tv.item(sel[0], "values")
        d = KVDialog(self, "Editar patrón", ("Patrón","Subcuenta"), (patron, sub))
        if d.result: self.tv.item(sel[0], values=d.result)

    def remove(self):
        sel = self.tv.selection()
        if not sel: return
        self.tv.delete(sel[0])

class IVAEditor(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.tv = ttk.Treeview(self, columns=("porcentaje","cuenta_iva"), show="headings", height=10)
        self.tv.heading("porcentaje", text="% IVA"); self.tv.column("porcentaje", width=120)
        self.tv.heading("cuenta_iva", text="Cuenta IVA"); self.tv.column("cuenta_iva", width=160)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        fr = ttk.Frame(self); fr.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(fr, text="Añadir", command=self.add).pack(side=tk.LEFT)
        ttk.Button(fr, text="Editar", command=self.edit).pack(side=tk.LEFT, padx=6)
        ttk.Button(fr, text="Eliminar", command=self.remove).pack(side=tk.LEFT)

    def load_list(self, arr):
        self.tv.delete(*self.tv.get_children())
        for it in (arr or []):
            self.tv.insert("", tk.END, values=(it.get("porcentaje",""), it.get("cuenta_iva","")))

    def to_list(self):
        out = []
        for iid in self.tv.get_children():
            pct, cta = self.tv.item(iid, "values")
            try:
                pct = float(str(pct).replace(",", "."))
            except Exception:
                pass
            out.append({"porcentaje": pct, "cuenta_iva": str(cta)})
        return out

    def add(self):
        d = KVDialog(self, "Añadir tipo IVA", ("% IVA","Cuenta IVA"), ("",""))
        if d.result: self.tv.insert("", tk.END, values=d.result)

    def edit(self):
        sel = self.tv.selection()
        if not sel: return
        pct, cta = self.tv.item(sel[0], "values")
        d = KVDialog(self, "Editar tipo IVA", ("% IVA","Cuenta IVA"), (pct, cta))
        if d.result: self.tv.item(sel[0], values=d.result)

    def remove(self):
        sel = self.tv.selection()
        if not sel: return
        self.tv.delete(sel[0])

class ConfigPlantillaDialog(tk.Toplevel):
    def __init__(self, master, gestor, empresa_codigo, tipo, plantilla):
        super().__init__(master)
        self.title(f"Configurar plantilla — {tipo.capitalize()}")
        self.gestor = gestor; self.codigo = empresa_codigo; self.tipo = tipo
        self.pl = json.loads(json.dumps(plantilla))  # copy
        self.pl.setdefault("excel", {})
        self.resizable(True, True)

        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Tab Excel override
        t_excel = ttk.Frame(nb); nb.add(t_excel, text="Excel (override)")
        self.var_override = tk.BooleanVar(value=bool(self.pl.get("excel_override", False)))
        ttk.Checkbutton(t_excel, text="Usar mapeo Excel propio", variable=self.var_override).pack(anchor=tk.W, padx=8, pady=(8,0))

        empresas = [e for e in self.gestor.listar_empresas() if e.get("codigo")==self.codigo]
        emp_excel = (empresas[0].get("excel") if empresas else {}) or {}

        def _excel_val(key, default=None):
            if key in self.pl["excel"]:
                return self.pl["excel"].get(key)
            return emp_excel.get(key, default)

        frm_excel_cfg = ttk.Frame(t_excel); frm_excel_cfg.pack(fill=tk.X, padx=8, pady=(8,4))
        frm_excel_cfg.columnconfigure(1, weight=1)

        ttk.Label(frm_excel_cfg, text="Primera fila a procesar").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.var_primera = tk.StringVar(value=str(_excel_val("primera_fila_procesar", 2) or "2"))
        ttk.Entry(frm_excel_cfg, textvariable=self.var_primera, width=10).grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(frm_excel_cfg, text="Ignorar filas (col=valor)").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.var_ignorar = tk.StringVar(value=_excel_val("ignorar_filas", "") or "")
        ttk.Entry(frm_excel_cfg, textvariable=self.var_ignorar).grid(row=1, column=1, sticky=tk.EW, pady=2)

        ttk.Label(frm_excel_cfg, text="Condición cuenta genérica").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.var_generica = tk.StringVar(value=_excel_val("condicion_cuenta_generica", "") or "")
        ttk.Entry(frm_excel_cfg, textvariable=self.var_generica).grid(row=2, column=1, sticky=tk.EW, pady=2)

        self.kv_excel = KVEditor(t_excel, ("clave","letra"), ("Clave","Letra")); self.kv_excel.pack(fill=tk.BOTH, expand=True)
        self.kv_excel.load_dict(((self.pl.get("excel") or {}).get("columnas")) or {})

        # Tab conceptos (bancos)
        if tipo == "bancos":
            t_conc = ttk.Frame(nb); nb.add(t_conc, text="Conceptos")
            self.pats = PatternEditor(t_conc); self.pats.pack(fill=tk.BOTH, expand=True)
            self.pats.load_list(self.pl.get("conceptos", []))

        # Tab IVA (emitidas/recibidas)
        if tipo in ("emitidas","recibidas"):
            t_iva = ttk.Frame(nb); nb.add(t_iva, text="Tipos IVA")
            self.iva = IVAEditor(t_iva); self.iva.pack(fill=tk.BOTH, expand=True)
            self.iva.load_list(self.pl.get("tipos_iva", []))

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(bar, text="Guardar", command=self._save).pack(side=tk.RIGHT, padx=6)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)

        self.grab_set()
        self.wait_window(self)

    def _save(self):
        self.pl["excel_override"] = bool(self.var_override.get())
        self.pl["excel"] = self.pl.get("excel", {})
        try:
            primera = int(str(self.var_primera.get()).strip() or "2")
        except ValueError:
            messagebox.showerror("Gest2A3Eco", "La primera fila debe ser un número entero.")
            return

        self.pl["excel"]["primera_fila_procesar"] = primera
        self.pl["excel"]["ignorar_filas"] = self.var_ignorar.get().strip()
        self.pl["excel"]["condicion_cuenta_generica"] = self.var_generica.get().strip()
        self.pl["excel"]["columnas"] = self.kv_excel.to_dict()
        if self.tipo == "bancos":
            self.pl["conceptos"] = self.pats.to_list()
            arr = self.gestor.listar_bancos(self.codigo)
            for i,p in enumerate(arr):
                if p.get("banco")==self.pl.get("banco"):
                    arr[i] = self.pl; break
            else:
                arr.append(self.pl)
        elif self.tipo == "emitidas":
            self.pl["tipos_iva"] = self.iva.to_list()
            arr = self.gestor.listar_emitidas(self.codigo)
            for i,p in enumerate(arr):
                if p.get("nombre")==self.pl.get("nombre"):
                    arr[i] = self.pl; break
            else:
                arr.append(self.pl)
        else:
            self.pl["tipos_iva"] = self.iva.to_list()
            arr = self.gestor.listar_recibidas(self.codigo)
            for i,p in enumerate(arr):
                if p.get("nombre")==self.pl.get("nombre"):
                    arr[i] = self.pl; break
            else:
                arr.append(self.pl)
        self.gestor.save()
        messagebox.showinfo("Gest2A3Eco","Configuración guardada.")
        self.destroy()

class UIPlantillasEmpresa(ttk.Frame):
    def __init__(self, master, gestor, empresa_codigo, empresa_nombre):
        super().__init__(master)
        self.gestor = gestor; self.codigo = empresa_codigo; self.nombre = empresa_nombre
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        ttk.Label(self, text=f"Plantillas de {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(pady=6, anchor=tk.W, padx=10)
        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        fr_excel = ttk.Frame(nb); nb.add(fr_excel, text="Excel (Empresa)"); self._build_excel_empresa(fr_excel)
        fr_ban = ttk.Frame(nb); nb.add(fr_ban, text="Bancos"); self._build_bancos(fr_ban)
        fr_em = ttk.Frame(nb); nb.add(fr_em, text="Facturas emitidas"); self._build_emitidas(fr_em)
        fr_re = ttk.Frame(nb); nb.add(fr_re, text="Facturas recibidas"); self._build_recibidas(fr_re)

    # ---- Excel Empresa
    def _build_excel_empresa(self, frame):
        left = ttk.Frame(frame); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        right = ttk.Frame(frame); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        ttk.Label(left, text="Primera Fila Procesar (1=primera fila)", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.emp_primera = tk.StringVar(value="2"); ttk.Entry(left, textvariable=self.emp_primera, width=8).pack(anchor=tk.W, pady=4)
        ttk.Label(left, text="Ignorar Filas (ej. Q=NOPROCESARFACTURA)").pack(anchor=tk.W); self.emp_ignorar = tk.StringVar(); ttk.Entry(left, textvariable=self.emp_ignorar, width=40).pack(anchor=tk.W, pady=4)
        ttk.Label(left, text="Condición cuenta genérica (ej. D=PARTICULAR)").pack(anchor=tk.W); self.emp_generica = tk.StringVar(); ttk.Entry(left, textvariable=self.emp_generica, width=40).pack(anchor=tk.W, pady=4)
        ttk.Label(right, text="Mapeo de columnas (Clave → Letra)").pack(anchor=tk.W)
        self.emp_map = KVEditor(right, ("clave","letra"), ("Clave","Letra")); self.emp_map.pack(fill=tk.BOTH, expand=True)

        empresas = [e for e in self.gestor.listar_empresas() if e.get("codigo")==self.codigo]
        conf = (empresas[0].get("excel") if empresas else {}) or {}
        self.emp_primera.set(str(conf.get("primera_fila_procesar", 2)))
        self.emp_ignorar.set(conf.get("ignorar_filas",""))
        self.emp_generica.set(conf.get("condicion_cuenta_generica",""))
        self.emp_map.load_dict(conf.get("columnas", {}))

        ttk.Button(frame, text="Guardar configuración de empresa", command=self._excel_empresa_save).pack(side=tk.BOTTOM, pady=6)

    def _excel_empresa_save(self):
        try:
            empresas = [e for e in self.gestor.listar_empresas() if e.get("codigo")==self.codigo]
            if not empresas: messagebox.showerror("Gest2A3Eco","Empresa no encontrada"); return
            emp = empresas[0]
            emp["excel"] = {
                "primera_fila_procesar": int(self.emp_primera.get() or "2"),
                "ignorar_filas": self.emp_ignorar.get().strip(),
                "condicion_cuenta_generica": self.emp_generica.get().strip(),
                "columnas": self.emp_map.to_dict()
            }
            self.gestor.save()
            messagebox.showinfo("Gest2A3Eco","Configuración Excel de empresa guardada.")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))

    # ---- Bancos
    def _build_bancos(self, frame):
        left = ttk.Frame(frame); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6,3), pady=6)
        right = ttk.Frame(frame); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3,6), pady=6)
        cols = ("banco","subcuenta_banco","subcuenta_por_defecto")
        self.tv_ban = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c,t in zip(cols, ["Banco","Subcta banco","Subcta por defecto"]):
            self.tv_ban.heading(c, text=t); self.tv_ban.column(c, width=160)
        self.tv_ban.pack(fill=tk.BOTH, expand=True)
        btns = ttk.Frame(left); btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="Nuevo", command=self._ban_nuevo).pack(side=tk.LEFT)
        ttk.Button(btns, text="Guardar", command=self._ban_guardar).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Eliminar", command=self._ban_eliminar).pack(side=tk.LEFT)
        ttk.Button(btns, text="Configurar…", command=self._ban_config).pack(side=tk.RIGHT)
        self._ban_refresh()

        self.b_banco = tk.StringVar(); self.b_sb = tk.StringVar(); self.b_sdef = tk.StringVar()
        self.b_dig = tk.StringVar(value="8"); self.b_eje = tk.StringVar(value="2025")
        ttk.Label(right, text="Editor de plantilla (Bancos)", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        _mk_labeled_entry(right, "Banco", self.b_banco)
        _mk_labeled_entry(right, "Subcuenta banco", self.b_sb)
        _mk_labeled_entry(right, "Subcuenta por defecto", self.b_sdef)
        _mk_labeled_entry(right, "Dígitos plan", self.b_dig)
        _mk_labeled_entry(right, "Ejercicio", self.b_eje)
        self.tv_ban.bind("<<TreeviewSelect>>", self._ban_load_selected)

    def _ban_refresh(self):
        self.tv_ban.delete(*self.tv_ban.get_children())
        for p in self.gestor.listar_bancos(self.codigo):
            self.tv_ban.insert("", tk.END, values=(p.get("banco"), p.get("subcuenta_banco"), p.get("subcuenta_por_defecto")))

    def _ban_load_selected(self, *_):
        sel = self.tv_ban.selection()
        if not sel: return
        banco, *_ = self.tv_ban.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==banco), None)
        if not p: return
        self.b_banco.set(p.get("banco","")); self.b_sb.set(p.get("subcuenta_banco","")); self.b_sdef.set(p.get("subcuenta_por_defecto",""))
        self.b_dig.set(str(p.get("digitos_plan",8))); self.b_eje.set(str(p.get("ejercicio",2025)))

    def _ban_nuevo(self):
        self.b_banco.set(""); self.b_sb.set(""); self.b_sdef.set("")
        self.b_dig.set("8"); self.b_eje.set("2025")

    def _ban_guardar(self):
        try:
            plantilla = {
                "codigo_empresa": self.codigo,
                "banco": self.b_banco.get().strip(),
                "subcuenta_banco": self.b_sb.get().strip(),
                "subcuenta_por_defecto": self.b_sdef.get().strip(),
                "digitos_plan": int(self.b_dig.get().strip() or "8"),
                "ejercicio": int(self.b_eje.get().strip() or "2025"),
            }
            ex = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==plantilla["banco"]), None)
            if ex:
                for k in ("conceptos","excel_override","excel"):
                    if k in ex: plantilla[k] = ex[k]
            self.gestor.upsert_banco(plantilla); self._ban_refresh()
            messagebox.showinfo("Gest2A3Eco","Plantilla guardada.")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))

    def _ban_eliminar(self):
        sel = self.tv_ban.selection()
        if not sel: return
        banco, *_ = self.tv_ban.item(sel[0], "values")
        self.gestor.eliminar_banco(self.codigo, banco); self._ban_refresh()

    def _ban_config(self):
        sel = self.tv_ban.selection()
        if not sel: messagebox.showinfo("Gest2A3Eco","Selecciona una plantilla de banco."); return
        banco, *_ = self.tv_ban.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==banco), None)
        if not p: return
        ConfigPlantillaDialog(self, self.gestor, self.codigo, "bancos", p)

    # ---- Emitidas
    def _build_emitidas(self, frame):
        left = ttk.Frame(frame); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6,3), pady=6)
        right = ttk.Frame(frame); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3,6), pady=6)

        cols = ("nombre","cliente_prefijo","iva_defecto")
        self.tv_em = ttk.Treeview(left, columns=cols, show="headings", height=12)
        self.tv_em.heading("nombre", text="Nombre"); self.tv_em.heading("cliente_prefijo", text="Prefijo 430"); self.tv_em.heading("iva_defecto", text="477 defecto")
        self.tv_em.column("nombre", width=180); self.tv_em.column("cliente_prefijo", width=120); self.tv_em.column("iva_defecto", width=120)
        self.tv_em.pack(fill=tk.BOTH, expand=True)
        btns = ttk.Frame(left); btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="Nuevo", command=self._em_nuevo).pack(side=tk.LEFT)
        ttk.Button(btns, text="Guardar", command=self._em_guardar).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Eliminar", command=self._em_eliminar).pack(side=tk.LEFT)
        ttk.Button(btns, text="Configurar…", command=self._em_config).pack(side=tk.RIGHT)
        self._em_refresh()

        self.em_nombre = tk.StringVar(); self.em_dig = tk.StringVar(value="8")
        self.em_cli_col = tk.BooleanVar(value=True); self.em_cli_codcol = tk.StringVar(value="NIF"); self.em_cli_pref = tk.StringVar(value="430")
        self.em_ing_def = tk.StringVar(value="70000000"); self.em_iva_def = tk.StringVar(value="47700000"); self.em_ret = tk.StringVar(value="47510000")
        ttk.Label(right, text="Editor (Emitidas)", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        _mk_labeled_entry(right, "Nombre", self.em_nombre, 24)
        _mk_labeled_entry(right, "Dígitos plan", self.em_dig)
        ttk.Checkbutton(right, text="Cliente por columna", variable=self.em_cli_col).pack(anchor=tk.W)
        _mk_labeled_entry(right, "Columna código cliente", self.em_cli_codcol)
        _mk_labeled_entry(right, "Prefijo cuenta cliente (430)", self.em_cli_pref)
        _mk_labeled_entry(right, "Ingreso por defecto (700)", self.em_ing_def)
        _mk_labeled_entry(right, "IVA repercutido defecto (477)", self.em_iva_def)
        _mk_labeled_entry(right, "Retenciones IRPF (4751)", self.em_ret)
        self.tv_em.bind("<<TreeviewSelect>>", self._em_load_selected)

    def _em_refresh(self):
        self.tv_em.delete(*self.tv_em.get_children())
        for p in self.gestor.listar_emitidas(self.codigo):
            self.tv_em.insert("", tk.END, values=(p.get("nombre"), p.get("cuenta_cliente_prefijo","430"), p.get("cuenta_iva_repercutido_defecto","47700000")))

    def _em_load_selected(self, *_):
        sel = self.tv_em.selection()
        if not sel: return
        nombre, *_ = self.tv_em.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==nombre), None)
        if not p: return
        self.em_nombre.set(p.get("nombre","")); self.em_dig.set(str(p.get("digitos_plan",8)))
        self.em_cli_col.set(bool(p.get("cliente_por_columna", True)))
        self.em_cli_codcol.set(p.get("col_cliente_codigo","NIF"))
        self.em_cli_pref.set(p.get("cuenta_cliente_prefijo","430"))
        self.em_ing_def.set(p.get("cuenta_ingreso_por_defecto","70000000"))
        self.em_iva_def.set(p.get("cuenta_iva_repercutido_defecto","47700000"))
        self.em_ret.set(p.get("cuenta_retenciones_irpf","47510000"))

    def _em_nuevo(self):
        self.em_nombre.set(""); self.em_dig.set("8"); self.em_cli_col.set(True); self.em_cli_codcol.set("NIF"); self.em_cli_pref.set("430"); self.em_ing_def.set("70000000"); self.em_iva_def.set("47700000"); self.em_ret.set("47510000")

    def _em_guardar(self):
        try:
            plantilla = {
                "codigo_empresa": self.codigo,
                "nombre": self.em_nombre.get().strip(),
                "digitos_plan": int(self.em_dig.get().strip() or "8"),
                "cliente_por_columna": bool(self.em_cli_col.get()),
                "col_cliente_codigo": self.em_cli_codcol.get().strip(),
                "cuenta_cliente_prefijo": self.em_cli_pref.get().strip(),
                "cuenta_ingreso_por_defecto": self.em_ing_def.get().strip(),
                "cuenta_iva_repercutido_defecto": self.em_iva_def.get().strip(),
                "cuenta_retenciones_irpf": self.em_ret.get().strip(),
            }
            ex = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==plantilla["nombre"]), None)
            if ex:
                for k in ("tipos_iva","excel_override","excel","soporta_retencion"):
                    if k in ex: plantilla[k] = ex[k]
            else:
                plantilla["tipos_iva"] = [{"porcentaje":21,"cuenta_iva":"47700000"}]
                plantilla["soporta_retencion"] = True
                plantilla["excel_override"] = False
                plantilla["excel"] = {"columnas":{}}
            self.gestor.upsert_emitida(plantilla); self._em_refresh()
            messagebox.showinfo("Gest2A3Eco","Plantilla guardada.")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))

    def _em_eliminar(self):
        sel = self.tv_em.selection()
        if not sel: return
        nombre, *_ = self.tv_em.item(sel[0], "values")
        self.gestor.eliminar_emitida(self.codigo, nombre); self._em_refresh()

    def _em_config(self):
        sel = self.tv_em.selection()
        if not sel: messagebox.showinfo("Gest2A3Eco","Selecciona una plantilla de emitidas."); return
        nombre, *_ = self.tv_em.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==nombre), None)
        if not p: return
        ConfigPlantillaDialog(self, self.gestor, self.codigo, "emitidas", p)

    # ---- Recibidas
    def _build_recibidas(self, frame):
        left = ttk.Frame(frame); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6,3), pady=6)
        right = ttk.Frame(frame); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3,6), pady=6)

        cols = ("nombre","proveedor_prefijo","iva_defecto")
        self.tv_re = ttk.Treeview(left, columns=cols, show="headings", height=12)
        self.tv_re.heading("nombre", text="Nombre"); self.tv_re.heading("proveedor_prefijo", text="Prefijo 400"); self.tv_re.heading("iva_defecto", text="472 defecto")
        self.tv_re.column("nombre", width=180); self.tv_re.column("proveedor_prefijo", width=120); self.tv_re.column("iva_defecto", width=120)
        self.tv_re.pack(fill=tk.BOTH, expand=True)
        btns = ttk.Frame(left); btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="Nuevo", command=self._re_nuevo).pack(side=tk.LEFT)
        ttk.Button(btns, text="Guardar", command=self._re_guardar).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Eliminar", command=self._re_eliminar).pack(side=tk.LEFT)
        ttk.Button(btns, text="Configurar…", command=self._re_config).pack(side=tk.RIGHT)
        self._re_refresh()

        self.re_nombre = tk.StringVar(); self.re_dig = tk.StringVar(value="8")
        self.re_prov_col = tk.BooleanVar(value=True); self.re_prov_codcol = tk.StringVar(value="NIF"); self.re_prov_pref = tk.StringVar(value="400")
        self.re_gasto_def = tk.StringVar(value="62900000"); self.re_iva_def = tk.StringVar(value="47200000"); self.re_ret = tk.StringVar(value="47510000")
        ttk.Label(right, text="Editor (Recibidas)", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        _mk_labeled_entry(right, "Nombre", self.re_nombre, 24)
        _mk_labeled_entry(right, "Dígitos plan", self.re_dig)
        ttk.Checkbutton(right, text="Proveedor por columna", variable=self.re_prov_col).pack(anchor=tk.W)
        _mk_labeled_entry(right, "Columna código proveedor", self.re_prov_codcol)
        _mk_labeled_entry(right, "Prefijo cuenta proveedor (400)", self.re_prov_pref)
        _mk_labeled_entry(right, "Gasto por defecto (6xx)", self.re_gasto_def)
        _mk_labeled_entry(right, "IVA soportado defecto (472)", self.re_iva_def)
        _mk_labeled_entry(right, "Retenciones IRPF (4751)", self.re_ret)
        self.tv_re.bind("<<TreeviewSelect>>", self._re_load_selected)

    def _re_refresh(self):
        self.tv_re.delete(*self.tv_re.get_children())
        for p in self.gestor.listar_recibidas(self.codigo):
            self.tv_re.insert("", tk.END, values=(p.get("nombre"), p.get("cuenta_proveedor_prefijo","400"), p.get("cuenta_iva_soportado_defecto","47200000")))

    def _re_load_selected(self, *_):
        sel = self.tv_re.selection()
        if not sel: return
        nombre, *_ = self.tv_re.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==nombre), None)
        if not p: return
        self.re_nombre.set(p.get("nombre","")); self.re_dig.set(str(p.get("digitos_plan",8)))
        self.re_prov_col.set(bool(p.get("proveedor_por_columna", True)))
        self.re_prov_codcol.set(p.get("col_proveedor_codigo","NIF"))
        self.re_prov_pref.set(p.get("cuenta_proveedor_prefijo","400"))
        self.re_gasto_def.set(p.get("cuenta_gasto_por_defecto","62900000"))
        self.re_iva_def.set(p.get("cuenta_iva_soportado_defecto","47200000"))
        self.re_ret.set(p.get("cuenta_retenciones_irpf","47510000"))

    def _re_nuevo(self):
        self.re_nombre.set(""); self.re_dig.set("8"); self.re_prov_col.set(True); self.re_prov_codcol.set("NIF"); self.re_prov_pref.set("400"); self.re_gasto_def.set("62900000"); self.re_iva_def.set("47200000"); self.re_ret.set("47510000")

    def _re_guardar(self):
        try:
            plantilla = {
                "codigo_empresa": self.codigo,
                "nombre": self.re_nombre.get().strip(),
                "digitos_plan": int(self.re_dig.get().strip() or "8"),
                "proveedor_por_columna": bool(self.re_prov_col.get()),
                "col_proveedor_codigo": self.re_prov_codcol.get().strip(),
                "cuenta_proveedor_prefijo": self.re_prov_pref.get().strip(),
                "cuenta_gasto_por_defecto": self.re_gasto_def.get().strip(),
                "cuenta_iva_soportado_defecto": self.re_iva_def.get().strip(),
                "cuenta_retenciones_irpf": self.re_ret.get().strip(),
            }
            ex = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==plantilla["nombre"]), None)
            if ex:
                for k in ("tipos_iva","excel_override","excel","soporta_retencion"):
                    if k in ex: plantilla[k] = ex[k]
            else:
                plantilla["tipos_iva"] = [{"porcentaje":21,"cuenta_iva":"47200000"}]
                plantilla["soporta_retencion"] = True
                plantilla["excel_override"] = False
                plantilla["excel"] = {"columnas":{}}
            self.gestor.upsert_recibida(plantilla); self._re_refresh()
            messagebox.showinfo("Gest2A3Eco","Plantilla guardada.")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))

    def _re_eliminar(self):
        sel = self.tv_re.selection()
        if not sel: return
        nombre, *_ = self.tv_re.item(sel[0], "values")
        self.gestor.eliminar_recibida(self.codigo, nombre); self._re_refresh()

    def _re_config(self):
        sel = self.tv_re.selection()
        if not sel: messagebox.showinfo("Gest2A3Eco","Selecciona una plantilla de recibidas."); return
        nombre, *_ = self.tv_re.item(sel[0], "values")
        p = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==nombre), None)
        if not p: return
        ConfigPlantillaDialog(self, self.gestor, self.codigo, "recibidas", p)
