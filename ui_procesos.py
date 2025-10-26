import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import pandas as pd
from datetime import datetime

from utilidades import construir_nombre_salida, col_letter_to_index
from generador_suenlace import apuntes_extracto
from facturas_common import render_tabular, Linea, cuenta_por_porcentaje
from facturas_emitidas import generar_asiento_emitida
from facturas_recibidas import generar_asiento_recibida

class UIProcesos(ttk.Frame):
    def __init__(self, master, gestor, empresa_codigo):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = empresa_codigo
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(top, text=f"Empresa: {self.codigo}", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

        self.tipo = tk.StringVar(value="bancos")
        ttk.Radiobutton(top, text="Bancos", variable=self.tipo, value="bancos", command=self._reload_plantillas).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(top, text="Facturas emitidas", variable=self.tipo, value="emitidas", command=self._reload_plantillas).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(top, text="Facturas recibidas", variable=self.tipo, value="recibidas", command=self._reload_plantillas).pack(side=tk.LEFT, padx=8)

        mid = ttk.Frame(self); mid.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(mid, text="Plantilla:").pack(side=tk.LEFT)
        self.cbo = ttk.Combobox(mid, state="readonly"); self.cbo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        filebar = ttk.Frame(self); filebar.pack(fill=tk.X, padx=8, pady=4)
        self.xl = tk.StringVar(); self.sheet = tk.StringVar(); self.out = tk.StringVar()
        ttk.Button(filebar, text="Excel…", command=self._choose_excel).pack(side=tk.LEFT)
        ttk.Entry(filebar, textvariable=self.xl).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.cb_sheets = ttk.Combobox(filebar, textvariable=self.sheet, state="readonly"); self.cb_sheets.pack(side=tk.LEFT, padx=6)
        ttk.Button(filebar, text="Destino…", command=lambda: self.out.set(filedialog.asksaveasfilename(defaultextension=".dat", initialfile="salida.dat"))).pack(side=tk.LEFT)

        self.tv = ttk.Treeview(self, show="headings", height=14); self.tv.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        bottom = ttk.Frame(self); bottom.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(bottom, text="Generar", command=self._generar).pack(side=tk.RIGHT)

        self._reload_plantillas()

    def _reload_plantillas(self):
        t = self.tipo.get()
        if t=="bancos":
            vals = [p.get("banco") for p in self.gestor.listar_bancos(self.codigo)]
        elif t=="emitidas":
            vals = [p.get("nombre") for p in self.gestor.listar_emitidas(self.codigo)]
        else:
            vals = [p.get("nombre") for p in self.gestor.listar_recibidas(self.codigo)]
        self.cbo["values"] = vals
        self.cbo.set(vals[0] if vals else "")

    def _choose_excel(self):
        fp = filedialog.askopenfilename(title="Selecciona Excel", filetypes=[("Excel",".xlsx .xls .xlsm"),("Todos","*.*")])
        if not fp: return
        self.xl.set(fp)
        try:
            xls = pd.ExcelFile(fp)
            self.cb_sheets["values"] = xls.sheet_names
            self.sheet.set("")
            self.tv.delete(*self.tv.get_children()); self.tv["columns"]=()
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))

    def _load_df(self):
        df = pd.read_excel(self.xl.get(), sheet_name=self.sheet.get())
        self.tv.delete(*self.tv.get_children())
        self.tv["columns"] = list(df.columns)
        for c in df.columns:
            self.tv.heading(c, text=str(c)); self.tv.column(c, width=max(80, min(220, int(len(str(c))*10))))
        for _, row in df.head(200).iterrows():
            self.tv.insert("", tk.END, values=[row.get(c,"") for c in df.columns])
        return df

    def _parse_condition(self, cond: str):
        cond = (cond or "").strip()
        if "=" not in cond: return None, None
        col, val = cond.split("=", 1)
        return col.strip().upper(), val

    def _extract_by_mapping(self, xlsx_path: str, sheet: str, mapping: dict):
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, dtype=object)
        def col(letter):
            i = col_letter_to_index(letter)
            return None if i < 0 else i
        first = int(mapping.get("primera_fila_procesar", 2))
        start_idx = max(0, first - 1)
        cols_map = mapping.get("columnas", {})
        ign_col_letter, ign_val = self._parse_condition(mapping.get("ignorar_filas",""))
        gen_col_letter, gen_val = self._parse_condition(mapping.get("condicion_cuenta_generica",""))

        rows = []
        for r in range(start_idx, len(raw)):
            row = raw.iloc[r]
            if ign_col_letter is not None:
                ci = col(ign_col_letter)
                if ci is not None and str(row.iloc[ci]).strip() == str(ign_val):
                    continue
            rec = {}
            for k, letter in cols_map.items():
                if not letter:
                    rec[k] = None; continue
                ci = col(letter); rec[k] = None if ci is None else row.iloc[ci]
            rec["_usar_cuenta_generica"] = False
            if gen_col_letter is not None:
                ci = col(gen_col_letter)
                if ci is not None and str(row.iloc[ci]).strip() == str(gen_val):
                    rec["_usar_cuenta_generica"] = True
            rows.append(rec)
        return rows

    def _unique_dest(self, dest):
        p = Path(dest)
        if not p.exists():
            return p
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return p.with_name(f"{p.stem}_{ts}{p.suffix}")

    def _generar(self):
        try:
            if not self.cbo.get(): raise ValueError("Selecciona una plantilla.")
            if not self.xl.get(): raise ValueError("Selecciona un Excel.")
            if not self.sheet.get(): raise ValueError("Selecciona una hoja.")
            if not self.out.get(): raise ValueError("Elige un destino.")

            _ = self._load_df()  # vista previa
            destino = self._unique_dest(construir_nombre_salida(self.out.get(), self.codigo))

            if self.tipo.get()=="bancos":
                p = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==self.cbo.get()), None)
                if not p: raise ValueError("Plantilla no encontrada.")
                ndig = int(p.get("digitos_plan", 8))

                eff_map = (p.get("excel") or {})
                rows = self._extract_by_mapping(self.xl.get(), self.sheet.get(), eff_map)

                import fnmatch
                def subcuenta_para_concepto(concepto: str) -> str:
                    cc = (concepto or "").lower()
                    for cm in p.get("conceptos", []):
                        if fnmatch.fnmatch(cc, cm.get("patron","*").lower()):
                            return cm.get("subcuenta", p.get("subcuenta_por_defecto"))
                    return p.get("subcuenta_por_defecto")
                out = []
                for rec in rows:
                    fecha = rec.get("Fecha Asiento")
                    concepto = rec.get("Descripcion Factura") or rec.get("Concepto")
                    importe = rec.get("Importe")
                    if fecha in (None, "") or importe in (None, ""): continue
                    try:
                        impf = float(str(importe).replace(",", "."))
                    except Exception:
                        continue
                    subc = subcuenta_para_concepto(str(concepto or ""))
                    out += apuntes_extracto(fecha, str(concepto or ""), impf, p["subcuenta_banco"], subc, ndig)
                if not out: raise ValueError("No hay movimientos válidos.")
                Path(destino).write_text("\n".join(out) + "\n", encoding="utf-8")
            else:
                if self.tipo.get()=="emitidas":
                    conf = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==self.cbo.get()), None)
                    gen_fun = generar_asiento_emitida
                else:
                    conf = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==self.cbo.get()), None)
                    gen_fun = generar_asiento_recibida
                if not conf: raise ValueError("Plantilla no encontrada.")
                ndig = int(conf.get("digitos_plan", 8))

                eff_map = (conf.get("excel") or {})
                rows = self._extract_by_mapping(self.xl.get(), self.sheet.get(), eff_map)

                from collections import defaultdict
                groups = defaultdict(list)
                for rec in rows:
                    serie = (rec.get("Serie") or "").strip()
                    num = (rec.get("Numero Factura") or rec.get("Número Factura") or "").strip()
                    key = (serie, num)
                    if key == ("",""):  # si no hay número, procesa fila individual
                        key = (id(rec), id(rec))
                    groups[key].append(rec)

                lineas = []
                for key, grecs in groups.items():
                    if not grecs: continue
                    rec0 = grecs[0]
                    fecha = rec0.get("Fecha Asiento")
                    desc = rec0.get("Descripcion Factura")
                    nif = rec0.get("NIF Cliente Proveedor")
                    nombre = rec0.get("Nombre Cliente Proveedor")
                    usar_gen = any(bool(r.get("_usar_cuenta_generica")) for r in grecs)
                    c_tercero_override = next((r.get("Cuenta Cliente Proveedor") for r in grecs if r.get("Cuenta Cliente Proveedor")), None)

                    def to_num(x):
                        if x is None or x == "": return 0.0
                        try: return float(str(x).replace(",", "."))
                        except: return 0.0

                    bases_por_cuenta = defaultdict(float)
                    iva_por_cuenta = defaultdict(float)
                    ret_total = 0.0

                    for r in grecs:
                        base = to_num(r.get("Base"))
                        iva_pct = r.get("Porcentaje IVA")
                        cuota_iva = to_num(r.get("Cuota IVA"))
                        ret = to_num(r.get("Cuota Retencion IRPF"))
                        ret_total += ret

                        c_pyg = r.get("Cuenta Compras Ventas")
                        if not c_pyg:
                            c_pyg = conf.get("cuenta_ingreso_por_defecto","70000000") if self.tipo.get()=="emitidas" else conf.get("cuenta_gasto_por_defecto","62900000")
                        bases_por_cuenta[c_pyg] += base

                        c_iva = r.get("Cuenta IVA")
                        if not c_iva:
                            try:
                                iva_pct_val = float(str(iva_pct).replace(",", ".")) if iva_pct not in (None, "") else None
                            except:
                                iva_pct_val = None
                            c_iva = cuenta_por_porcentaje(conf.get("tipos_iva", []), iva_pct_val or (21.0), conf.get("cuenta_iva_repercutido_defecto","47700000") if self.tipo.get()=="emitidas" else conf.get("cuenta_iva_soportado_defecto","47200000"))
                        iva_por_cuenta[c_iva] += cuota_iva

                    base_total = sum(bases_por_cuenta.values())
                    iva_total = sum(iva_por_cuenta.values())
                    total = base_total + iva_total - ret_total

                    row = {
                        "Fecha": fecha,
                        "Descripcion": desc,
                        "Base": base_total,
                        "IVA_pct": None,
                        "CuotaIVA": iva_total,
                        "CuotaRetencion": ret_total,
                        "Total": total,
                        "NIF": nif,
                        "Nombre": nombre,
                        "_usar_cuenta_generica": usar_gen,
                        "_cuenta_tercero_override": c_tercero_override,
                        "_cuenta_py_gv_override": None,
                        "_cuenta_iva_override": None
                    }

                    lineas.extend(gen_fun(row, conf))

                    if self.tipo.get()=="emitidas":
                        for c, b in bases_por_cuenta.items():
                            lineas.append(Linea(fecha, c, "H", b, desc))
                        for c, q in iva_por_cuenta.items():
                            if q: lineas.append(Linea(fecha, c, "H", q, desc))
                    else:
                        for c, b in bases_por_cuenta.items():
                            lineas.append(Linea(fecha, c, "D", b, desc))
                        for c, q in iva_por_cuenta.items():
                            if q: lineas.append(Linea(fecha, c, "D", q, desc))

                txt = "\n".join(render_tabular(lineas, ndig)) + "\n"
                Path(destino).write_text(txt, encoding="utf-8")

            messagebox.showinfo("Gest2A3Eco", f"Fichero generado:\n{destino}")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
