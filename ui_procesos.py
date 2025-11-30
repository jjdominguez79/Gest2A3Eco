# ui_procesos.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from collections import defaultdict

from procesos.bancos import generar_bancos
from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_recibidas import generar_recibidas



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

    # ─────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────────────────────
    # Excel
    # ─────────────────────────────────────────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers de mapeo por letras
    # ─────────────────────────────────────────────────────────────────────────
    def _col_letter_to_index(self, letter: str) -> int:
        # Puede venir como número desde el JSON; lo pasamos siempre a str
        letter = "" if letter is None else str(letter)
        letter = letter.strip().upper()
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
        Respeta:
          - 'primera_fila_procesar' (1-based, por ej. 2)
          - 'ignorar_filas' formato 'Letra=Valor' (ej. 'H=0')
          - 'condicion_cuenta_generica' idem (ej. 'D=PARTICULAR')
        Resultado: lista de dicts con claves exactamente las de 'columnas'.
        """
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, dtype=object)
        first = int((mapping or {}).get("primera_fila_procesar", 2))
        start_idx = max(0, first - 1)
        cols_map = (mapping or {}).get("columnas", {}) or {}
        ign = str((mapping or {}).get("ignorar_filas", "") or "").strip()
        gen = str((mapping or {}).get("condicion_cuenta_generica", "") or "").strip()


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

    # ─────────────────────────────────────────────────────────────────────────
    # Validaciones de mapeo
    # ─────────────────────────────────────────────────────────────────────────
    def _has_letter(self, pl_excel, key):
        cols = (pl_excel or {}).get("columnas", {})
        # Aseguramos que siempre trabajamos con str, aunque se haya guardado un número
        val = cols.get(key, "")
        return bool(str(val).strip())

    def _require_mapeo_or_warn(self, pl, tipo, required_keys):
        pl_excel = pl.get("excel") or {}
        missing = [k for k in required_keys if not self._has_letter(pl_excel, k)]
        if missing:
            messagebox.showerror(
                "Gest2A3Eco",
                f"La plantilla de {tipo} no tiene mapeadas estas columnas:\n- " + "\n- ".join(missing)
            )
            return False
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # GENERAR SUENLACE.DAT
    # ─────────────────────────────────────────────────────────────────────────
    def _generar(self):
        try:
            if not self.excel_path or not self.cb_sheet.get():
                messagebox.showwarning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
                return
            
            nombre_pl = self.cb_plantilla.get().strip()
            if not nombre_pl:
                messagebox.showwarning("Gest2A3Eco", "Selecciona una plantilla.")
                return
            
            tipo = self.tipo.get()
            # Obtener plantilla seleccionada
            if tipo == "bancos":
                pl = next((x for x in self.gestor.listar_bancos(self.codigo) if x.get("banco")==nombre_pl), None)
            elif "emitidas" in tipo:
                pl = next((x for x in self.gestor.listar_emitidas(self.codigo) if x.get("nombre")==nombre_pl), None)
            else:
                pl = next((x for x in self.gestor.listar_recibidas(self.codigo) if x.get("nombre")==nombre_pl), None)
            if not pl:
                messagebox.showerror("Gest2A3Eco", "Plantilla no encontrada.")
                return

            # Empresa (digitos plan + código)
            empresa_config = self.gestor.get_empresa(self.codigo) or {}
            ndig = int(empresa_config.get("digitos_plan", 8))
            codigo_empresa = str(self.codigo)

            # Leer Excel por mapeo (letras)
            excel_conf = pl.get("excel") or {}
            rows = self._extract_rows_by_mapping(self.excel_path, self.cb_sheet.get(), excel_conf)

            # =======================
            #      B A N C O S
            # =======================
            if tipo == "bancos":
                # Validación mínima de mapeo (Fecha, Importe, Concepto)
                req = ["Fecha Asiento","Importe","Concepto"]
                if not self._require_mapeo_or_warn(pl, "bancos", req):
                    return
                
                try:
                    out_lines, avisos = generar_bancos(rows, pl, codigo_empresa, ndig)
                except ValueError as e:
                    messagebox.showerror("Gest2A3Eco", str(e))
                    return

                if not out_lines:
                    msg = "No se generaron líneas para bancos."
                    if avisos:
                        msg += "\n\nSe han detectado problemas de fecha en algunas filas:\n"
                        preview = "\n".join(avisos[:10])
                        if len(avisos) > 10:
                            preview += f"\n... y {len(avisos)-10} filas más con fecha inválida."
                        msg += preview
                    messagebox.showwarning("Gest2A3Eco", msg)
                    return

                save_path = filedialog.asksaveasfilename(
                    title="Guardar fichero suenlace.dat",
                    defaultextension=".dat",
                    initialfile=f"{self.codigo}.dat",
                    filetypes=[("Ficheros DAT","*.dat")]
                )
                if not save_path:
                    return
                
                with open(save_path, "w", encoding="latin-1", newline="") as f:
                    f.writelines(out_lines)
                
                msg = f"Fichero generado:\n{save_path}"
                if avisos:
                    msg += "\n\nATENCIÓN: se han omitido movimientos por fecha inválida:\n"
                    preview = "\n".join(avisos[:10])
                    if len(avisos) > 10:
                        preview += f"\n... y {len(avisos)-10} filas más."
                    msg += preview
                    messagebox.showwarning("Gest2A3Eco - Bancos", msg)
                else:
                    messagebox.showinfo("Gest2A3Eco", msg)
                return
            # =======================
            #   F A C T U R A S
            # =======================
            def _fv(x):
                try: return float(str(x).replace(",", "."))
                except: return 0.0

            def key_factura(rec):
                nfl = rec.get("Numero Factura Largo SII") or rec.get("Número Factura Largo SII")
                if nfl: return ("NFL", str(nfl).strip())
                serie = str(rec.get("Serie") or "").strip()
                num = str(rec.get("Numero Factura") or rec.get("Número Factura") or "").strip()
                return ("SERIE_NUM", f"{serie}|{num}")

            grupos = defaultdict(list)
            for rec in rows:
                grupos[key_factura(rec)].append(rec)

            # ─ EMITIDAS (ventas)
            if "emitidas" in tipo:
                req = ["Fecha Asiento","Descripcion Factura","Base","Cuota IVA"]
                if not (self._has_letter(excel_conf, "Numero Factura") or self._has_letter(excel_conf, "Numero Factura Largo SII")):
                    req = [k for k in req if k != "Numero Factura"] + ["Numero Factura Largo SII"]
                else:
                    req = ["Numero Factura"] + req
                if not self._require_mapeo_or_warn(pl, "emitidas", req): 
                    return

                registros = generar_emitidas(rows, pl, codigo_empresa, ndig)

                # Guardar
                if registros:
                    save_path = filedialog.asksaveasfilename(
                        title="Guardar fichero suenlace.dat",
                        defaultextension=".dat",
                        initialfile=f"{self.codigo}",
                        filetypes=[("Ficheros DAT","*.dat")]
                    )
                    if not save_path: return
                    with open(save_path, "w", encoding="latin-1", newline="") as f:
                        f.writelines(registros)
                    messagebox.showinfo("Gest2A3Eco", f"Fichero generado:\n{save_path}")
                else:
                    messagebox.showwarning("Gest2A3Eco", "No se generaron registros para facturas emitidas.")
                return

            # RECIBIDAS (compras)
            else:
                req = ["Fecha Asiento","Descripcion Factura","Base","Cuota IVA"]
                if not (self._has_letter(excel_conf, "Numero Factura") or self._has_letter(excel_conf, "Numero Factura Largo SII")):
                    req = [k for k in req if k != "Numero Factura"] + ["Numero Factura Largo SII"]
                else:
                    req = ["Numero Factura"] + req
                if not self._require_mapeo_or_warn(pl, "recibidas", req):
                    return

                pref_prov = str(pl.get("cuenta_proveedor_prefijo", "400"))
                cta_gasto_def = str(pl.get("cuenta_gasto_por_defecto", "62900000"))
                # subtipo_def lo dejamos de momento para posible futuro detalle 9, pero aquí no se usa

                out_lines, avisos = generar_recibidas(rows, pl, codigo_empresa, ndig)

                if out_lines:
                    save_path = filedialog.asksaveasfilename(
                        title="Guardar fichero suenlace.dat",
                        defaultextension=".dat",
                        initialfile=f"E{self.codigo}",
                        filetypes=[("Ficheros DAT","*.dat")]
                    )
                    if not save_path:
                        return
                    with open(save_path, "w", encoding="latin-1", newline="") as f:
                        f.writelines(out_lines)
                    
                    msg = f"Fichero generado:\n{save_path}"
                    if avisos:
                        # Mostramos solo las primeras 10 para no saturar
                        preview = "\n".join(avisos[:10])
                        if len(avisos) > 10:
                            preview += f"\n... y {len(avisos)-10} descuadres más."
                        msg += f"\n\nATENCIÓN: se han detectado descuadres:\n{preview}"
                        messagebox.showwarning("Gest2A3Eco - Descuadres", msg)
                    else:
                        messagebox.showinfo("Gest2A3Eco", msg)
                else:
                    messagebox.showwarning("Gest2A3Eco", "No se generaron registros para facturas recibidas.")
                return

        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error en la generación:\n{e}")
