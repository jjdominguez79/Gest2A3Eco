# ui_procesos.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from pathlib import Path
from facturas_common import Linea, render_tabular
from utilidades import d2, fmt_fecha, fmt_importe_pos, SEP, pad_subcuenta
from collections import defaultdict

class UIProcesos(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, nombre_empresa):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.nombre = nombre_empresa
        self.pack(fill=tk.BOTH, expand=True)
        self.excel_path = None
        self.sheet_name = None
        self.df_preview = None
        self._build()

    def _build(self):
        ttk.Label(self, text=f"Generar fichero — {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        form = ttk.Frame(self)
        form.pack(fill=tk.X, padx=10, pady=4)

        ttk.Label(form, text="Tipo de enlace:").grid(row=0, column=0, sticky="w")
        self.tipo = tk.StringVar(value="bancos")
        ttk.Combobox(form, textvariable=self.tipo, values=["bancos","facturas emitidas","facturas recibidas"], width=25).grid(row=0, column=1, sticky="w")

        ttk.Label(form, text="Plantilla:").grid(row=1, column=0, sticky="w")
        self.cb_plantilla = ttk.Combobox(form, width=40)
        self.cb_plantilla.grid(row=1, column=1, sticky="w")

        ttk.Button(form, text="Cargar Excel", command=self._cargar_excel).grid(row=2, column=0, pady=6)
        self.lbl_excel = ttk.Label(form, text="Ningún archivo seleccionado")
        self.lbl_excel.grid(row=2, column=1, sticky="w")

        ttk.Label(form, text="Hoja:").grid(row=3, column=0, sticky="w")
        self.cb_sheet = ttk.Combobox(form, width=30)
        self.cb_sheet.grid(row=3, column=1, sticky="w")
        self.cb_sheet.bind("<<ComboboxSelected>>", lambda e: self._preview_excel())

        ttk.Button(self, text="Generar suenlace.dat", command=self._generar).pack(side=tk.BOTTOM, pady=10)

        self.tv = ttk.Treeview(self, show="headings")
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tipo.trace_add("write", lambda *_: self._refresh_plantillas())
        self._refresh_plantillas()

    def _refresh_plantillas(self):
        tipo = self.tipo.get()
        if tipo == "bancos":
            pls = [p.get("banco") for p in self.gestor.listar_bancos(self.codigo)]
        elif "emitidas" in tipo:
            pls = [p.get("nombre") for p in self.gestor.listar_emitidas(self.codigo)]
        else:
            pls = [p.get("nombre") for p in self.gestor.listar_recibidas(self.codigo)]
        self.cb_plantilla["values"] = pls
        if pls:
            self.cb_plantilla.current(0)

    def _cargar_excel(self):
        path = filedialog.askopenfilename(title="Seleccionar Excel", filetypes=[("Archivos Excel","*.xlsx *.xls")])
        if not path:
            return
        self.excel_path = path
        self.lbl_excel.config(text=os.path.basename(path))
        try:
            xls = pd.ExcelFile(path)
            self.cb_sheet["values"] = xls.sheet_names
            self.cb_sheet.set("")
            self.df_preview = None
            self.tv.delete(*self.tv.get_children())
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error al abrir Excel:\n{e}")

    def _preview_excel(self):
        hoja = self.cb_sheet.get()
        if not hoja or not self.excel_path:
            return
        try:
            df = pd.read_excel(self.excel_path, sheet_name=hoja)
            self.df_preview = df
            self.tv.delete(*self.tv.get_children())
            self.tv["columns"] = list(df.columns)
            for c in df.columns:
                self.tv.heading(c, text=c)
                self.tv.column(c, width=120)
            for _, row in df.head(10).iterrows():
                vals = [str(x) for x in row.tolist()]
                self.tv.insert("", tk.END, values=vals)
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error al leer hoja:\n{e}")

    def _generar(self):
        if not self.excel_path or not self.cb_sheet.get():
            messagebox.showwarning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
            return

        tipo = self.tipo.get()
        nombre_pl = self.cb_plantilla.get().strip()
        if not nombre_pl:
            messagebox.showwarning("Gest2A3Eco", "Selecciona una plantilla.")
            return

        # obtener plantilla
        if tipo == "bancos":
            pl = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==nombre_pl), None)
        elif "emitidas" in tipo:
            pl = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==nombre_pl), None)
        else:
            pl = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==nombre_pl), None)

        if not pl:
            messagebox.showerror("Gest2A3Eco", "Plantilla no encontrada.")
            return

        empresa = self.gestor.get_empresa(self.codigo)
        ndig = int(empresa.get("digitos_plan", 8))

        try:
            df = pd.read_excel(self.excel_path, sheet_name=self.cb_sheet.get())
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error leyendo Excel:\n{e}")
            return

        excel_conf = pl.get("excel") or {}
        col_map = excel_conf.get("columnas", {})
        primera = int(excel_conf.get("primera_fila_procesar", 2)) - 1

        # renombrar columnas segun mapeo
        renamed = {}
        for k, letra in col_map.items():
            if letra:
                try:
                    idx = ord(letra.upper()) - ord("A")
                    if idx < len(df.columns):
                        renamed[df.columns[idx]] = k
                except:
                    pass
        df = df.rename(columns=renamed)
        df = df.iloc[primera:].reset_index(drop=True)

        lineas = []

        # --- CASO BANCOS ---
        if tipo == "bancos":
            sub_banco = pl.get("subcuenta_banco")
            sub_def = pl.get("subcuenta_por_defecto")
            conceptos = pl.get("conceptos", [])
            for _, row in df.iterrows():
                concepto_txt = str(row.get("Concepto",""))
                importe = abs(float(str(row.get("Importe") or 0).replace(",",".")))
                fecha = str(row.get("Fecha Asiento") or "")
                matched = None
                for pat in conceptos:
                    patron = str(pat.get("patron","")).lower().replace("*","")
                    if patron and patron in concepto_txt.lower():
                        matched = pat.get("subcuenta")
                        break
                sub = matched or sub_def
                lineas.append(Linea(fecha, sub, "D", d2(importe), concepto_txt))
                lineas.append(Linea(fecha, sub_banco, "H", d2(importe), concepto_txt))

        # --- CASO FACTURAS (emitidas / recibidas) ---
        else:
            df = df.fillna("")
            rows = df.to_dict(orient="records")

            def _norm(x):
                return (str(x).strip().upper() if x is not None else "")

            def _group_key(rec):
                nfl = rec.get("Numero Factura Largo SII")
                if nfl not in (None, ""):
                    return ("NFL", _norm(nfl))
                serie = rec.get("Serie") or ""
                num = rec.get("Numero Factura") or rec.get("Número Factura") or ""
                if (serie or num):
                    return ("SERIE_NUM", f"{_norm(serie)}|{_norm(num)}")
                return ("ROW", id(rec))

            groups = defaultdict(list)
            for rec in rows:
                groups[_group_key(rec)].append(rec)

            for key, grecs in groups.items():
                if not grecs:
                    continue
                rec0 = grecs[0]
                fecha = rec0.get("Fecha Asiento") or rec0.get("Fecha Expedicion") or rec0.get("Fecha Operacion")
                desc = rec0.get("Descripcion Factura") or ""
                nif = rec0.get("NIF Cliente Proveedor")
                nombre = rec0.get("Nombre Cliente Proveedor")

                def to_num(x):
                    if x in (None, "", "nan"):
                        return 0.0
                    try:
                        return float(str(x).replace(",", "."))
                    except:
                        return 0.0

                base_total = sum(to_num(r.get("Base")) for r in grecs)
                iva_total = sum(to_num(r.get("Cuota IVA")) for r in grecs)
                ret_total = sum(to_num(r.get("Cuota Retencion IRPF")) for r in grecs)
                total = base_total + iva_total - ret_total

                if "emitidas" in tipo:
                    cuenta_terc = (pl.get("cuenta_cliente_prefijo","430") + nif[-(ndig-len(pl.get("cuenta_cliente_prefijo","430"))):]).zfill(ndig)
                    cuenta_iva = pl.get("cuenta_iva_repercutido_defecto","47700000")
                    cuenta_ing = pl.get("cuenta_ingreso_por_defecto","70000000")
                    lineas.append(Linea(fecha, cuenta_terc, "D", d2(total), desc))
                    lineas.append(Linea(fecha, cuenta_iva, "H", d2(iva_total), desc))
                    lineas.append(Linea(fecha, cuenta_ing, "H", d2(base_total), desc))
                else:
                    cuenta_terc = (pl.get("cuenta_proveedor_prefijo","400") + nif[-(ndig-len(pl.get("cuenta_proveedor_prefijo","400"))):]).zfill(ndig)
                    cuenta_iva = pl.get("cuenta_iva_soportado_defecto","47200000")
                    cuenta_gasto = pl.get("cuenta_gasto_por_defecto","62900000")
                    lineas.append(Linea(fecha, cuenta_terc, "H", d2(total), desc))
                    lineas.append(Linea(fecha, cuenta_iva, "D", d2(iva_total), desc))
                    lineas.append(Linea(fecha, cuenta_gasto, "D", d2(base_total), desc))

        # --- GENERAR FICHERO ---
        if not lineas:
            messagebox.showwarning("Gest2A3Eco","No se generaron líneas.")
            return

        out_lines = render_tabular(lineas, ndig)
        save_path = filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=f"suenlace_{self.codigo}.dat",
            filetypes=[("Ficheros DAT","*.dat")]
        )
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines))
            messagebox.showinfo("Gest2A3Eco", f"Fichero generado:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error al guardar:\n{e}")
