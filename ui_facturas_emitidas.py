

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime

from procesos.facturas_emitidas import generar_emitidas
from utilidades import validar_subcuenta_longitud

IVA_OPCIONES = [21, 10, 4, 0]
IRPF_OPCIONES = [0, 1, 7, 15]


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
        ttk.Label(self, text="Tipo").grid(row=len(fields), column=0, sticky="w", padx=6, pady=3)
        self.var_tipo = tk.StringVar(value=t.get("tipo", "cliente"))
        ttk.Combobox(self, textvariable=self.var_tipo, values=["cliente","proveedor","ambos"], state="readonly", width=18).grid(row=len(fields), column=1, sticky="w", padx=6, pady=3)
        btns = ttk.Frame(self)
        btns.grid(row=len(fields)+1, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _ok(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        data["tipo"] = self.var_tipo.get() or "cliente"
        self.result = data
        self.destroy()


class TercerosDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa, ndig_plan):
        super().__init__(parent)
        self.title("Terceros")
        self.resizable(True, True)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ndig = ndig_plan
        self._build()
        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Nuevo", style="Primary.TButton", command=self._nuevo).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Editar", command=self._editar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar", command=self._eliminar).pack(side=tk.LEFT, padx=4)

        cols = ("nif", "nombre", "tipo", "poblacion")
        self.tv = ttk.Treeview(frm, columns=cols, show="headings", height=12, selectmode="browse")
        self.tv.heading("nif", text="NIF")
        self.tv.column("nif", width=120)
        self.tv.heading("nombre", text="Nombre")
        self.tv.column("nombre", width=240)
        self.tv.heading("tipo", text="Tipo")
        self.tv.column("tipo", width=100)
        self.tv.heading("poblacion", text="Poblacion")
        self.tv.column("poblacion", width=160)
        self.tv.pack(fill="both", expand=True, pady=6)
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._load_subcuentas())

        sub = ttk.LabelFrame(frm, text=f"Subcuentas en empresa {self.codigo}")
        sub.pack(fill="x", pady=(4, 0))
        ttk.Label(sub, text="Subcta cliente").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(sub, text="Subcta proveedor").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.var_sub_cli = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_cli, width=18).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self.var_sub_pro = tk.StringVar()
        ttk.Entry(sub, textvariable=self.var_sub_pro, width=18).grid(row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(sub, text="Guardar", style="Primary.TButton", command=self._guardar_sub).grid(row=0, column=2, rowspan=2, padx=6, pady=4)

        self._refresh()

    def _refresh(self):
        self.tv.delete(*self.tv.get_children())
        for t in self.gestor.listar_terceros():
            self.tv.insert(
                "",
                tk.END,
                iid=str(t.get("id")),
                values=(t.get("nif", ""), t.get("nombre", ""), t.get("tipo", "cliente"), t.get("poblacion", "")),
            )
        self.var_sub_cli.set("")
        self.var_sub_pro.set("")

    def _sel_id(self):
        sel = self.tv.selection()
        return sel[0] if sel else None

    def _nuevo(self):
        dlg = TerceroFicha(self)
        if dlg.result:
            tid = self.gestor.upsert_tercero(dlg.result)
            self._refresh()
            self.tv.selection_set(str(tid))

    def _editar(self):
        tid = self._sel_id()
        if not tid:
            return
        ter = next((t for t in self.gestor.listar_terceros() if str(t.get("id")) == str(tid)), None)
        dlg = TerceroFicha(self, ter)
        if dlg.result:
            dlg.result["id"] = tid
            self.gestor.upsert_tercero(dlg.result)
            self._refresh()

    def _eliminar(self):
        tid = self._sel_id()
        if not tid:
            return
        if not messagebox.askyesno("Gest2A3Eco", "Eliminar el tercero seleccionado?"):
            return
        self.gestor.eliminar_tercero(tid)
        self._refresh()

    def _load_subcuentas(self):
        tid = self._sel_id()
        if not tid:
            self.var_sub_cli.set("")
            self.var_sub_pro.set("")
            return
        rel = self.gestor.get_tercero_empresa(self.codigo, tid) or {}
        self.var_sub_cli.set(rel.get("subcuenta_cliente", ""))
        self.var_sub_pro.set(rel.get("subcuenta_proveedor", ""))

    def _guardar_sub(self):
        tid = self._sel_id()
        if not tid:
            messagebox.showinfo("Gest2A3Eco", "Selecciona un tercero.")
            return
        sc = self.var_sub_cli.get().strip()
        sp = self.var_sub_pro.get().strip()
        if sc:
            validar_subcuenta_longitud(sc, self.ndig, "subcuenta cliente")
        if sp:
            validar_subcuenta_longitud(sp, self.ndig, "subcuenta proveedor")
        rel = {
            "tercero_id": tid,
            "codigo_empresa": self.codigo,
            "subcuenta_cliente": sc,
            "subcuenta_proveedor": sp,
        }
        self.gestor.upsert_tercero_empresa(rel)
        messagebox.showinfo("Gest2A3Eco", "Subcuentas guardadas.")


class FacturaDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa, ndig_plan, factura=None, numero_sugerido=""):
        super().__init__(parent)
        self.title("Factura emitida")
        self.resizable(True, True)
        self.result = None
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ndig = ndig_plan
        self.factura = dict(factura or {})
        if numero_sugerido and not self.factura.get("numero"):
            self.factura["numero"] = numero_sugerido
        f = self.factura

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        def add_row(label, var, row_idx, width=24, col=0):
            ttk.Label(frm, text=label).grid(row=row_idx, column=col, sticky="w", padx=4, pady=3)
            ttk.Entry(frm, textvariable=var, width=width).grid(row=row_idx, column=col + 1, padx=4, pady=3, sticky="we")

        today = date.today().strftime("%Y-%m-%d")
        self.var_serie = tk.StringVar(value=f.get("serie", ""))
        self.var_numero = tk.StringVar(value=f.get("numero", ""))
        self.var_numero_largo = tk.StringVar(value=f.get("numero_largo_sii", ""))
        self.var_fecha_asiento = tk.StringVar(value=f.get("fecha_asiento", today))
        self.var_fecha_exp = tk.StringVar(value=f.get("fecha_expedicion", f.get("fecha_asiento", today)))
        self.var_fecha_op = tk.StringVar(value=f.get("fecha_operacion", ""))
        self.var_nif = tk.StringVar(value=f.get("nif", ""))
        self.var_nombre = tk.StringVar(value=f.get("nombre", ""))
        self.var_desc = tk.StringVar(value=f.get("descripcion", ""))
        self.var_subcuenta = tk.StringVar(value=f.get("subcuenta_cliente", ""))

        row = 0
        ttk.Label(frm, text="Cliente (tercero)").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_tercero = tk.StringVar()
        self.cb_tercero = ttk.Combobox(frm, textvariable=self.var_tercero, width=40, state="readonly")
        self.cb_tercero.grid(row=row, column=1, padx=4, pady=3, sticky="we")
        ttk.Button(frm, text="Terceros...", command=self._gestionar_terceros).grid(row=row, column=2, padx=4, pady=3)
        row += 1

        add_row("Serie", self.var_serie, row)
        add_row("Numero", self.var_numero, row, col=2, width=16)
        row += 1
        add_row("Numero Largo SII", self.var_numero_largo, row)
        add_row("Subcuenta cliente", self.var_subcuenta, row, col=2, width=18)
        row += 1
        add_row("Fecha Asiento (YYYY-MM-DD)", self.var_fecha_asiento, row)
        add_row("Fecha Expedicion", self.var_fecha_exp, row, col=2)
        row += 1
        add_row("Fecha Operacion", self.var_fecha_op, row)
        row += 1
        add_row("NIF Cliente", self.var_nif, row)
        add_row("Nombre Cliente", self.var_nombre, row, col=2, width=34)
        row += 1
        add_row("Descripcion", self.var_desc, row, width=40)
        row += 1

        ttk.Label(frm, text="Lineas").grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        row += 1

        self.line_vars = {
            "concepto": tk.StringVar(),
            "unidades": tk.StringVar(),
            "precio": tk.StringVar(),
            "iva": tk.StringVar(),
            "irpf": tk.StringVar(),
        }
        editor = ttk.Frame(frm)
        editor.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4)
        editor.columnconfigure(8, weight=1)
        ttk.Label(editor, text="Concepto").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["concepto"], width=26).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(editor, text="Unidades").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["unidades"], width=10).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(editor, text="Precio").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self.line_vars["precio"], width=10).grid(row=0, column=5, padx=4, pady=2)
        ttk.Label(editor, text="IVA %").grid(row=0, column=6, padx=4, pady=2, sticky="w")
        ttk.Combobox(editor, textvariable=self.line_vars["iva"], values=[str(x) for x in IVA_OPCIONES], width=6, state="readonly").grid(row=0, column=7, padx=4, pady=2)
        ttk.Label(editor, text="IRPF %").grid(row=0, column=8, padx=4, pady=2, sticky="w")
        ttk.Combobox(editor, textvariable=self.line_vars["irpf"], values=[str(x) for x in IRPF_OPCIONES], width=6, state="readonly").grid(row=0, column=9, padx=4, pady=2)
        ttk.Button(editor, text="Añadir/Actualizar", style="Primary.TButton", command=self._add_update_linea).grid(row=0, column=10, padx=6)
        ttk.Button(editor, text="Limpiar", command=self._clear_line_editor).grid(row=0, column=11, padx=4)
        row += 1

        self.tv = ttk.Treeview(
            frm,
            columns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        headers = {
            "concepto": "Concepto",
            "unidades": "Unid",
            "precio": "P. unit",
            "base": "Base",
            "pct_iva": "% IVA",
            "cuota_iva": "Cuota IVA",
            "pct_irpf": "% IRPF",
            "cuota_irpf": "Ret",
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

        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=3, pady=(6, 2))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)

        frm.columnconfigure(1, weight=1)
        self._load_terceros()
        self._preselect_tercero(f.get("tercero_id"))

        for ln in f.get("lineas", []):
            self._insert_linea(ln)
        self._refresh_totales()

        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    # --- terceros helpers
    def _load_terceros(self):
        self._terceros_cache = self.gestor.listar_terceros()
        disp = [f"{t.get('nombre','')} ({t.get('nif','')})" for t in self._terceros_cache]
        self.cb_tercero["values"] = disp
        self.cb_tercero.bind("<<ComboboxSelected>>", lambda e: self._on_tercero_selected())

    def _preselect_tercero(self, tercero_id):
        if not tercero_id:
            return
        for idx, t in enumerate(self._terceros_cache):
            if str(t.get("id")) == str(tercero_id):
                self.cb_tercero.current(idx)
                self._on_tercero_selected()
                return

    def _gestionar_terceros(self):
        TercerosDialog(self, self.gestor, self.codigo, self.ndig)
        self._load_terceros()

    def _on_tercero_selected(self):
        idx = self.cb_tercero.current()
        if idx < 0:
            return
        t = self._terceros_cache[idx]
        self.var_nif.set(t.get("nif", ""))
        self.var_nombre.set(t.get("nombre", ""))
        rel = self.gestor.get_tercero_empresa(self.codigo, t.get("id")) or {}
        sc = rel.get("subcuenta_cliente", "")
        if sc:
            self.var_subcuenta.set(sc)

    # --- line editor
    def _clear_line_editor(self):
        for v in self.line_vars.values():
            v.set("")
        self.tv.selection_remove(self.tv.selection())

    def _line_from_editor(self):
        concepto = self.line_vars["concepto"].get().strip()
        unidades = _to_float(self.line_vars["unidades"].get())
        precio = _to_float(self.line_vars["precio"].get())
        iva = _to_float(self.line_vars["iva"].get())
        irpf = _to_float(self.line_vars["irpf"].get())
        if (
            not concepto
            or unidades == 0
            or precio == 0
            or self.line_vars["iva"].get() == ""
            or self.line_vars["irpf"].get() == ""
        ):
            messagebox.showwarning("Gest2A3Eco", "Completa concepto, unidades, precio, IVA e IRPF.")
            return None
        base = unidades * precio
        cuota_iva = base * iva / 100.0
        cuota_ret = -abs(base * irpf / 100.0)
        return {
            "concepto": concepto,
            "unidades": unidades,
            "precio": precio,
            "base": base,
            "pct_iva": iva,
            "cuota_iva": cuota_iva,
            "pct_irpf": irpf,
            "cuota_irpf": cuota_ret,
            "pct_re": 0.0,
            "cuota_re": 0.0,
        }

    def _add_update_linea(self):
        ln = self._line_from_editor()
        if not ln:
            return
        vals = (
            ln["concepto"],
            f"{ln['unidades']:.2f}",
            f"{ln['precio']:.4f}",
            f"{ln['base']:.2f}",
            f"{ln['pct_iva']:.2f}",
            f"{ln['cuota_iva']:.2f}",
            f"{ln['pct_irpf']:.2f}",
            f"{ln['cuota_irpf']:.2f}",
        )
        sel = self.tv.selection()
        if sel:
            self.tv.item(sel[0], values=vals)
        else:
            self.tv.insert("", tk.END, values=vals)
        self._refresh_totales()
        self._clear_line_editor()

    def _on_select_linea(self, event=None):
        sel = self.tv.selection()
        if not sel:
            return
        vals = self.tv.item(sel[0], "values")
        keys = ["concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva", "pct_irpf", "cuota_irpf"]
        for k, v in zip(keys, vals):
            if k in self.line_vars:
                self.line_vars[k].set(v)

    def _del_linea(self):
        sel = self.tv.selection()
        if sel:
            self.tv.delete(sel[0])
            self._refresh_totales()
            self._clear_line_editor()

    def _get_lineas(self):
        out = []
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values")
            if not vals:
                continue
            out.append(
                {
                    "concepto": vals[0],
                    "unidades": _to_float(vals[1]),
                    "precio": _to_float(vals[2]),
                    "base": _to_float(vals[3]),
                    "pct_iva": _to_float(vals[4]),
                    "cuota_iva": _to_float(vals[5]),
                    "pct_irpf": _to_float(vals[6]),
                    "cuota_irpf": _to_float(vals[7]),
                    "pct_re": 0.0,
                    "cuota_re": 0.0,
                }
            )
        return out

    def _refresh_totales(self):
        base = iva = ret = 0.0
        for ln in self._get_lineas():
            base += ln["base"]
            iva += ln["cuota_iva"]
            ret += ln["cuota_irpf"]
        total = base + iva + ret
        self.lbl_tot_base.config(text=f"Base: {base:.2f}")
        self.lbl_tot_iva.config(text=f"IVA: {iva:.2f}")
        self.lbl_tot_ret.config(text=f"IRPF: {ret:.2f}")
        self.lbl_tot_total.config(text=f"Total: {total:.2f}")

    def _ok(self):
        lineas = self._get_lineas()
        if not lineas:
            messagebox.showerror("Gest2A3Eco", "Añade al menos una linea.")
            return
        if not self.var_numero.get().strip():
            messagebox.showerror("Gest2A3Eco", "Numero de factura vacio.")
            return
        sc = self.var_subcuenta.get().strip()
        if sc:
            validar_subcuenta_longitud(sc, self.ndig, "subcuenta cliente")
        tercero_id = None
        idx = self.cb_tercero.current()
        if idx >= 0:
            tercero_id = self._terceros_cache[idx].get("id")
        self.result = {
            "id": self.factura.get("id"),
            "codigo_empresa": self.factura.get("codigo_empresa"),
            "tercero_id": tercero_id,
            "serie": self.var_serie.get().strip(),
            "numero": self.var_numero.get().strip(),
            "numero_largo_sii": self.var_numero_largo.get().strip(),
            "fecha_asiento": self.var_fecha_asiento.get().strip(),
            "fecha_expedicion": self.var_fecha_exp.get().strip(),
            "fecha_operacion": self.var_fecha_op.get().strip(),
            "nif": self.var_nif.get().strip(),
            "nombre": self.var_nombre.get().strip(),
            "descripcion": self.var_desc.get().strip(),
            "subcuenta_cliente": sc,
            "lineas": lineas,
            "generada": self.factura.get("generada", False),
            "fecha_generacion": self.factura.get("fecha_generacion", ""),
        }
        self.destroy()


class UIFacturasEmitidas(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, nombre_empresa):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.nombre = nombre_empresa
        self.empresa_conf = gestor.get_empresa(codigo_empresa) or {"digitos_plan": 8, "serie_emitidas": "A", "siguiente_num_emitidas": 1}
        self._build()

    # ------------------- UI -------------------
    def _build(self):
        ttk.Label(self, text=f"Facturas emitidas de {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10)
        ttk.Button(top, text="Nueva", style="Primary.TButton", command=self._nueva).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Editar", command=self._editar).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Copiar", command=self._copiar).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Eliminar", command=self._eliminar).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Terceros", command=self._terceros).pack(side=tk.LEFT, padx=12)
        ttk.Button(top, text="Exportar PDF", command=self._export_pdf).pack(side=tk.LEFT, padx=4)

        self.tv = ttk.Treeview(
            self,
            columns=("serie", "numero", "fecha", "cliente", "total", "generada", "fecha_gen"),
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
        ]
        for c, h, w, align in cols:
            self.tv.heading(c, text=h)
            self.tv.column(c, width=w, anchor=align)
        self.tv.pack(fill="both", expand=True, padx=10, pady=8)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=6)
        ttk.Label(bottom, text="Plantilla emitidas:").pack(side=tk.LEFT)
        self.cb_plantilla = ttk.Combobox(bottom, width=40, state="readonly")
        self.cb_plantilla.pack(side=tk.LEFT, padx=6)
        ttk.Button(bottom, text="Generar Suenlace.dat", style="Primary.TButton", command=self._generar).pack(side=tk.RIGHT)

        self._refresh_plantillas()
        self._refresh_facturas()

    # ------------------- Datos -------------------
    def _refresh_plantillas(self):
        pls = [p.get("nombre") for p in self.gestor.listar_emitidas(self.codigo)]
        self.cb_plantilla["values"] = pls
        if pls:
            self.cb_plantilla.current(0)

    def _compute_total(self, fac: dict) -> float:
        total = 0.0
        for ln in fac.get("lineas", []):
            total += (
                _to_float(ln.get("base"))
                + _to_float(ln.get("cuota_iva"))
                + _to_float(ln.get("cuota_re"))
                + _to_float(ln.get("cuota_irpf"))
            )
        return total

    def _refresh_facturas(self):
        self.tv.delete(*self.tv.get_children())
        for fac in self.gestor.listar_facturas_emitidas(self.codigo):
            total = self._compute_total(fac)
            self.tv.insert(
                "",
                tk.END,
                iid=str(fac.get("id")),
                values=(
                    fac.get("serie", ""),
                    fac.get("numero", ""),
                    fac.get("fecha_asiento", ""),
                    fac.get("nombre", ""),
                    f"{total:.2f}",
                    "Si" if fac.get("generada") else "No",
                    fac.get("fecha_generacion", ""),
                ),
            )

    def _selected_ids(self):
        return list(self.tv.selection())

    def _serie(self):
        return str(self.empresa_conf.get("serie_emitidas", "A") or "A")

    def _siguiente_num(self):
        try:
            return int(self.empresa_conf.get("siguiente_num_emitidas", 1))
        except Exception:
            return 1

    def _proximo_numero(self):
        return f"{self._serie()}{self._siguiente_num():06d}"

    def _incrementar_numeracion(self):
        self.empresa_conf["siguiente_num_emitidas"] = self._siguiente_num() + 1
        self.gestor.upsert_empresa(self.empresa_conf)

    def _nueva(self):
        sugerido = self._proximo_numero()
        dlg = FacturaDialog(
            self,
            self.gestor,
            self.codigo,
            int(self.empresa_conf.get("digitos_plan", 8)),
            {"codigo_empresa": self.codigo, "serie": self._serie(), "numero": sugerido},
            numero_sugerido=sugerido,
        )
        if dlg.result:
            dlg.result["generada"] = False
            dlg.result["fecha_generacion"] = ""
            self.gestor.upsert_factura_emitida(dlg.result)
            self._incrementar_numeracion()
            self._refresh_facturas()

    def _editar(self):
        sel = self._selected_ids()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = next((f for f in self.gestor.listar_facturas_emitidas(self.codigo) if str(f.get("id")) == str(sel[0])), None)
        if not fac:
            return
        dlg = FacturaDialog(self, self.gestor, self.codigo, int(self.empresa_conf.get("digitos_plan", 8)), fac)
        if dlg.result:
            self.gestor.upsert_factura_emitida(dlg.result)
            self._refresh_facturas()

    def _copiar(self):
        sel = self._selected_ids()
        if not sel:
            return
        fac = next((f for f in self.gestor.listar_facturas_emitidas(self.codigo) if str(f.get("id")) == str(sel[0])), None)
        if not fac:
            return
        nuevo = dict(fac)
        nuevo.pop("id", None)
        nuevo["numero"] = self._proximo_numero()
        nuevo["serie"] = self._serie()
        nuevo["generada"] = False
        nuevo["fecha_generacion"] = ""
        dlg = FacturaDialog(
            self,
            self.gestor,
            self.codigo,
            int(self.empresa_conf.get("digitos_plan", 8)),
            nuevo,
            numero_sugerido=nuevo["numero"],
        )
        if dlg.result:
            self.gestor.upsert_factura_emitida(dlg.result)
            self._incrementar_numeracion()
            self._refresh_facturas()

    def _eliminar(self):
        sel = self._selected_ids()
        if not sel:
            return
        if not messagebox.askyesno("Gest2A3Eco", "Eliminar las facturas seleccionadas?"):
            return
        for fid in sel:
            self.gestor.eliminar_factura_emitida(self.codigo, fid)
        self._refresh_facturas()

    def _terceros(self):
        TercerosDialog(self, self.gestor, self.codigo, int(self.empresa_conf.get("digitos_plan", 8)))

    # ------------------- Exportar PDF -------------------
    def _simple_pdf(self, path: str, titulo: str, lines: list):
        y = 780
        contents = ["BT\n/F1 12 Tf\n"]
        contents.append(f"50 {y} Td ({titulo}) Tj\n")
        y -= 20
        for ln in lines:
            safe_ln = ln.replace("(", "[").replace(")", "]")
            contents.append(f"50 {y} Td ({safe_ln}) Tj\n")
            y -= 16
        contents.append("ET\n")
        stream = "".join(contents).encode("latin-1", "ignore")
        objs = []
        objs.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
        objs.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
        objs.append("3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n")
        objs.append(f"4 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"endstream\nendobj\n")
        objs.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n")
            offsets = []
            for ob in objs:
                ob_bytes = ob if isinstance(ob, bytes) else ob.encode("latin-1")
                offsets.append(f.tell())
                f.write(ob_bytes)
            xref_pos = f.tell()
            f.write(f"xref\n0 {len(objs)+1}\n".encode())
            f.write(b"0000000000 65535 f \n")
            for off in offsets:
                f.write(f"{off:010d} 00000 n \n".encode())
            f.write(f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode())

    def _export_pdf(self):
        sel = self._selected_ids()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = next((f for f in self.gestor.listar_facturas_emitidas(self.codigo) if str(f.get("id")) == str(sel[0])), None)
        if not fac:
            return
        lines = [
            f"Serie/Numero: {fac.get('serie','')}-{fac.get('numero','')}",
            f"Fecha: {fac.get('fecha_asiento','')}",
            f"Cliente: {fac.get('nombre','')} ({fac.get('nif','')})",
            f"Descripcion: {fac.get('descripcion','')}",
            f"Subcuenta: {fac.get('subcuenta_cliente','')}",
            "",
            "Lineas:",
        ]
        for ln in fac.get("lineas", []):
            lines.append(
                f"- {ln.get('concepto','')}: {ln.get('unidades',0)} x {ln.get('precio',0)} = {ln.get('base',0)} "
                f"IVA {ln.get('pct_iva',0)}% ({ln.get('cuota_iva',0)}) IRPF {ln.get('pct_irpf',0)}% ({ln.get('cuota_irpf',0)})"
            )
        lines.append(f"Total: {self._compute_total(fac):.2f}")

        save_path = filedialog.asksaveasfilename(
            title="Exportar PDF",
            defaultextension=".pdf",
            initialfile=f"Factura_{fac.get('numero','')}.pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not save_path:
            return
        try:
            self._simple_pdf(save_path, "Factura emitida", lines)
            messagebox.showinfo("Gest2A3Eco", f"PDF generado:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"No se pudo generar el PDF:\n{e}")

    def _factura_to_rows(self, fac: dict):
        rows = []
        base_row = {
            "Serie": fac.get("serie", ""),
            "Numero Factura": fac.get("numero", ""),
            "Numero Factura Largo SII": fac.get("numero_largo_sii", ""),
            "Fecha Asiento": fac.get("fecha_asiento", ""),
            "Fecha Expedicion": fac.get("fecha_expedicion") or fac.get("fecha_asiento", ""),
            "Fecha Operacion": fac.get("fecha_operacion", ""),
            "Descripcion Factura": fac.get("descripcion", ""),
            "NIF Cliente Proveedor": fac.get("nif", ""),
            "Nombre Cliente Proveedor": fac.get("nombre", ""),
        }
        if fac.get("subcuenta_cliente"):
            base_row["Cuenta Cliente Proveedor"] = fac.get("subcuenta_cliente")
        for ln in fac.get("lineas", []):
            r = dict(base_row)
            r.update(
                {
                    "Descripcion Linea": ln.get("concepto", "") or fac.get("descripcion", ""),
                    "Base": _to_float(ln.get("base")),
                    "Cuota IVA": _to_float(ln.get("cuota_iva")),
                    "Porcentaje IVA": _to_float(ln.get("pct_iva")),
                    "Porcentaje Recargo Equivalencia": _to_float(ln.get("pct_re")),
                    "Cuota Recargo Equivalencia": _to_float(ln.get("cuota_re")),
                    "Porcentaje Retencion IRPF": _to_float(ln.get("pct_irpf")),
                    "Cuota Retencion IRPF": _to_float(ln.get("cuota_irpf")),
                }
            )
            rows.append(r)
        return rows

    def _generar(self):
        sel = self._selected_ids()
        if not sel:
            messagebox.showwarning("Gest2A3Eco", "Selecciona al menos una factura.")
            return
        pl_name = (self.cb_plantilla.get() or "").strip()
        if not pl_name:
            messagebox.showwarning("Gest2A3Eco", "Selecciona una plantilla de emitidas.")
            return
        plantilla = next((p for p in self.gestor.listar_emitidas(self.codigo) if p.get("nombre") == pl_name), None)
        if not plantilla:
            messagebox.showerror("Gest2A3Eco", "Plantilla no encontrada.")
            return

        rows = []
        for fid in sel:
            fac = next((f for f in self.gestor.listar_facturas_emitidas(self.codigo) if str(f.get("id")) == str(fid)), None)
            if fac:
                rows.extend(self._factura_to_rows(fac))

        if not rows:
            messagebox.showwarning("Gest2A3Eco", "No hay lineas para generar.")
            return

        ndig = int(self.empresa_conf.get("digitos_plan", 8))
        registros = generar_emitidas(rows, plantilla, str(self.codigo), ndig)
        if not registros:
            messagebox.showwarning("Gest2A3Eco", "No se generaron registros.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=f"E{self.codigo}.dat",
            filetypes=[("Ficheros DAT", "*.dat")],
        )
        if not save_path:
            return
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(registros)
        fecha_gen = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.gestor.marcar_facturas_emitidas_generadas(self.codigo, sel, fecha_gen)
        self._refresh_facturas()
        messagebox.showinfo("Gest2A3Eco", f"Fichero generado:\n{save_path}")

