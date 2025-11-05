# ui_procesos.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from collections import defaultdict

# Importa Linea y el render TIPO 0 (512 bytes) para bancos
from facturas_common import Linea, render_a3_tipo0_bancos


class UIProcesos(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, nombre_empresa):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.nombre = nombre_empresa
        self.pack(fill=tk.BOTH, expand=True)
        self.excel_path = None
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
        path = filedialog.askopenfilename(title="Seleccionar Excel", filetypes=[("Archivos Excel","*.xlsx *.xls *.xlsm")])
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
            # Vista previa con encabezado (header=0)
            df = pd.read_excel(self.excel_path, sheet_name=hoja, header=0)
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

    # ---- helpers procesamiento por letras de columna con header y primera fila ----
    def _col_letter_to_index(self, letter: str) -> int:
        letter = (letter or "").strip().upper()
        if not letter:
            return -1
        idx = 0
        for ch in letter:
            if not ('A' <= ch <= 'Z'):
                return -1
            idx = idx * 26 + (ord(ch) - ord('A') + 1)
        return idx - 1

    def _extract_rows_by_mapping(self, xlsx_path: str, sheet: str, mapping: dict):
        """
        Lee el Excel sin encabezado (header=None) y extrae campos por letra de columna.
        Respeta 'primera_fila_procesar' (1-based).
        """
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, dtype=object)
        first = int(mapping.get("primera_fila_procesar", 2))
        start_idx = max(0, first - 1)
        cols_map = mapping.get("columnas", {})
        ign = mapping.get("ignorar_filas", "").strip()
        gen = mapping.get("condicion_cuenta_generica", "").strip()

        def pick(row, letter):
            ci = self._col_letter_to_index(letter)
            if ci < 0 or ci >= len(row): return None
            return row.iloc[ci]

        def parse_cond(cond):
            if "=" not in cond: return None, None
            a, b = cond.split("=", 1)
            return a.strip().upper(), b

        ign_col, ign_val = parse_cond(ign)
        gen_col, gen_val = parse_cond(gen)

        rows = []
        for r in range(start_idx, len(raw)):
            row = raw.iloc[r]
            if ign_col:
                cidx = self._col_letter_to_index(ign_col)
                if 0 <= cidx < len(row) and str(row.iloc[cidx]).strip() == str(ign_val):
                    continue
            rec = {}
            for k, letter in cols_map.items():
                rec[k] = pick(row, letter) if letter else None
            rec["_usar_cuenta_generica"] = False
            if gen_col:
                cidx = self._col_letter_to_index(gen_col)
                if 0 <= cidx < len(row) and str(row.iloc[cidx]).strip() == str(gen_val):
                    rec["_usar_cuenta_generica"] = True
            rows.append(rec)
        return rows

    def _generar(self):
        try:
            # Validaciones básicas
            if not self.excel_path or not self.cb_sheet.get():
                messagebox.showwarning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
                return

            tipo = self.tipo.get()
            nombre_pl = self.cb_plantilla.get().strip()
            if not nombre_pl:
                messagebox.showwarning("Gest2A3Eco", "Selecciona una plantilla.")
                return

            # Plantilla seleccionada
            if tipo == "bancos":
                pl = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==nombre_pl), None)
            elif "emitidas" in tipo:
                pl = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==nombre_pl), None)
            else:
                pl = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==nombre_pl), None)

            if not pl:
                messagebox.showerror("Gest2A3Eco", "Plantilla no encontrada.")
                return

            # Empresa (para ndig y código empresa)
            empresa_config = self.gestor.get_empresa(self.codigo) or {}
            ndig = int(empresa_config.get("digitos_plan", 8))
            codigo_empresa = str(self.codigo)  # el render se encarga de formatearlo a 5 dígitos

            # Leer Excel según mapeo por letras
            excel_conf = pl.get("excel") or {}
            rows = self._extract_rows_by_mapping(self.excel_path, self.cb_sheet.get(), excel_conf)

            lineas = []

            # =======================
            #      B A N C O S
            # =======================
            if tipo == "bancos":
                sub_banco = (pl.get("subcuenta_banco") or "").strip()
                sub_def   = (pl.get("subcuenta_por_defecto") or "").strip()
                conceptos = pl.get("conceptos", [])

                if not sub_banco:
                    messagebox.showerror("Gest2A3Eco", "La plantilla de bancos no tiene 'Subcuenta banco'.")
                    return
                if not sub_def:
                    messagebox.showerror("Gest2A3Eco", "La plantilla de bancos no tiene 'Subcuenta por defecto'.")
                    return

                import fnmatch
                def subcuenta_por_concepto(txt: str) -> str:
                    t = (str(txt) or "").lower()
                    for cm in (conceptos or []):
                        patron = (cm.get("patron","*") or "*").lower()
                        if fnmatch.fnmatch(t, patron):
                            sub = (cm.get("subcuenta") or "").strip()
                            if sub:
                                return sub
                    return sub_def

                for rec in rows:
                    fecha = rec.get("Fecha Asiento") or rec.get("Fecha Operacion") or rec.get("Fecha Expedicion")
                    concepto_txt = rec.get("Concepto") or rec.get("Descripcion Factura") or ""
                    imp_raw = rec.get("Importe")
                    if imp_raw in (None, ""):
                        continue
                    try:
                        val = float(str(imp_raw).replace(",", "."))  # conserva el signo original
                    except Exception:
                        continue
                    if val == 0:
                        continue

                    imp = abs(val)
                    sub_contra = subcuenta_por_concepto(concepto_txt) or sub_def

                    if val > 0:
                        # + => Banco al Debe, Contrapartida al Haber
                        lineas.append(Linea(fecha, sub_banco,  "D", imp, str(concepto_txt)))
                        lineas.append(Linea(fecha, sub_contra, "H", imp, str(concepto_txt)))
                    else:
                        # - => Banco al Haber, Contrapartida al Debe
                        lineas.append(Linea(fecha, sub_contra, "D", imp, str(concepto_txt)))
                        lineas.append(Linea(fecha, sub_banco,  "H", imp, str(concepto_txt)))

                if not lineas:
                    messagebox.showwarning("Gest2A3Eco","No se generaron líneas para bancos.")
                    return

                # Render 512 bytes (tipo 0 bancos)
                out_lines = render_a3_tipo0_bancos(lineas, codigo_empresa, ndig_plan=ndig)

                save_path = filedialog.asksaveasfilename(
                    title="Guardar fichero suenlace.dat",
                    defaultextension=".dat",
                    initialfile=f"suenlace_{self.codigo}.dat",
                    filetypes=[("Ficheros DAT","*.dat")]
                )
                if not save_path:
                    return

                with open(save_path, "w", encoding="utf-8", newline="") as f:
                    f.writelines(out_lines)

                messagebox.showinfo("Gest2A3Eco", f"Fichero generado:\n{save_path}")
                return


            # =======================
            #   F A C T U R A S
            # =======================
            # Si aún no has migrado facturas al esquema 512, deja tu lógica previa aquí
            # (por ejemplo, usando render_a3_een o tu antiguo render) hasta que
            # adaptemos tipo 1/9. De momento avisamos:
            messagebox.showinfo("Gest2A3Eco", "La generación de facturas en formato 512 se añadirá a continuación. De momento, usa bancos.")
            return

        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error en la generación:\n{e}")
