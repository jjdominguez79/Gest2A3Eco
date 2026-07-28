# ui_procesos.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from controllers.ui_procesos_controller import ProcesosController



class UIProcesos(ttk.Frame):
    def __init__(self, master, gestor, codigo_empresa, ejercicio, nombre_empresa, session=None, initial_tipo=None):
        super().__init__(master)
        self.gestor = gestor
        self.codigo = codigo_empresa
        self.ejercicio = ejercicio
        self.nombre = nombre_empresa
        self.session = session
        self._initial_tipo = initial_tipo or "Bancos"
        self.pack(fill=tk.BOTH, expand=True)
        self._build()
        self.controller = ProcesosController(
            gestor, codigo_empresa, ejercicio, self, session=session
        )
        self.controller.refresh_plantillas()

    # UI
    def _build(self):
        ttk.Label(self, text=f"Generar fichero - {self.nombre} ({self.codigo})", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=8)

        form = ttk.Frame(self)
        form.pack(fill=tk.X, padx=10, pady=4)

        ttk.Label(form, text="Tipo de enlace:").grid(row=0, column=0, sticky="w")
        self.tipo = tk.StringVar(value=self._initial_tipo)
        ttk.Combobox(
            form,
            textvariable=self.tipo,
            values=["Bancos", "Facturas Emitidas", "Facturas Recibidas"],
            width=25,
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(form, text="Plantilla:").grid(row=1, column=0, sticky="w")
        self.cb_plantilla = ttk.Combobox(form, width=40)
        self.cb_plantilla.grid(row=1, column=1, sticky="w")

        ttk.Button(form, text="Cargar Excel", style="Primary.TButton", command=lambda: self.controller.cargar_excel()).grid(row=2, column=0, pady=6)
        self.lbl_excel = ttk.Label(form, text="Ningun archivo seleccionado")
        self.lbl_excel.grid(row=2, column=1, sticky="w")

        ttk.Label(form, text="Seleccione Hoja:").grid(row=3, column=0, sticky="w")
        self.cb_sheet = ttk.Combobox(form, width=30)
        self.cb_sheet.grid(row=3, column=1, sticky="w")
        self.cb_sheet.bind("<<ComboboxSelected>>", lambda e: self.controller.preview_excel())

        self.btn_generar = ttk.Button(
            self,
            text="Generar Suenlace.dat",
            style="Primary.TButton",
            command=lambda: self.controller.generar(),
        )
        self.btn_generar.pack(side=tk.BOTTOM, pady=10)

        ttk.Button(
            form,
            text="Historial de importaciones bancarias",
            command=lambda: self.controller.mostrar_historial_bancos(),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        preview_wrap = ttk.Frame(self, height=320, width=900)
        preview_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        preview_wrap.pack_propagate(False)
        preview_wrap.grid_propagate(False)
        preview_wrap.rowconfigure(0, weight=1)
        preview_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(preview_wrap, show="headings", height=12)
        self.tv.grid(row=0, column=0, sticky="nsew")

        self.vsb = ttk.Scrollbar(preview_wrap, orient="vertical", command=self.tv.yview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb = ttk.Scrollbar(preview_wrap, orient="horizontal", command=self.tv.xview)
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.tv.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tipo.trace_add("write", lambda *_: self.controller.refresh_plantillas())

    def get_tipo(self):
        return self.tipo.get()

    def set_tipo(self, value: str):
        self.tipo.set(value)

    def get_selected_plantilla(self):
        return self.cb_plantilla.get()

    def set_plantillas(self, values):
        self.cb_plantilla["values"] = values
        if values:
            self.cb_plantilla.current(0)
        else:
            self.cb_plantilla.set("")

    def set_plantilla_enabled(self, enabled: bool):
        self.cb_plantilla.configure(state=("normal" if enabled else "disabled"))

    def set_generar_text(self, text: str):
        self.btn_generar.configure(text=text)

    def ask_open_excel_path(self):
        return filedialog.askopenfilename(
            title="Seleccionar Excel",
            filetypes=[("Archivos Excel", "*.xlsx *.xls *.xlsm")],
        )

    def ask_save_path(self, initialfile):
        return filedialog.asksaveasfilename(
            title="Guardar fichero suenlace.dat",
            defaultextension=".dat",
            initialfile=initialfile,
            filetypes=[("Ficheros DAT", "*.dat")],
        )

    def set_excel_label(self, text):
        self.lbl_excel.config(text=text)

    def set_sheet_values(self, values):
        self.cb_sheet["values"] = values

    def clear_sheet_selection(self):
        self.cb_sheet.set("")

    def get_selected_sheet(self):
        return self.cb_sheet.get()

    def clear_preview(self):
        self.tv.delete(*self.tv.get_children())
        self.tv["columns"] = []

    def pedir_accion_duplicados_banco(self, analisis):
        dlg = tk.Toplevel(self)
        dlg.title("Movimientos bancarios ya generados")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.resizable(False, False)

        solapadas = analisis.get("importaciones_solapadas") or []
        duplicados = analisis.get("duplicados") or []
        nuevos = analisis.get("nuevos") or []
        modificados = analisis.get("modificados") or []
        texto = (
            f"El fichero comprende del {analisis.get('fecha_desde') or '-'} "
            f"al {analisis.get('fecha_hasta') or '-'}.\n\n"
            f"Importaciones anteriores solapadas: {len(solapadas)}\n"
            f"Movimientos ya generados: {len(duplicados)}\n"
            f"Movimientos nuevos: {len(nuevos)}\n"
            f"Posiblemente modificados: {len(modificados)}\n\n"
        )
        if analisis.get("sin_detalle_previo"):
            texto += (
                "Las importaciones anteriores no guardaban el detalle de sus "
                "movimientos, por lo que no es posible separar los nuevos con "
                "seguridad. Puedes regenerar todo o cancelar."
            )
        else:
            texto += (
                "Se recomienda generar solamente los movimientos nuevos. "
                "Los posibles movimientos modificados requieren revision y "
                "no se incluiran en esa opcion."
            )
        ttk.Label(
            dlg, text=texto, justify="left", wraplength=620, padding=16
        ).pack(fill="x")

        resultado = tk.StringVar(value="cancelar")
        botones = ttk.Frame(dlg, padding=(16, 0, 16, 16))
        botones.pack(fill="x")

        def cerrar(valor):
            resultado.set(valor)
            dlg.destroy()

        btn_nuevos = ttk.Button(
            botones,
            text="Generar solo nuevos",
            style="Primary.TButton",
            command=lambda: cerrar("solo_nuevos"),
        )
        btn_nuevos.pack(side="left")
        if analisis.get("sin_detalle_previo"):
            btn_nuevos.configure(state="disabled")
        ttk.Button(
            botones, text="Regenerar todo",
            command=lambda: cerrar("todo"),
        ).pack(side="left", padx=8)
        ttk.Button(
            botones, text="Cancelar",
            command=lambda: cerrar("cancelar"),
        ).pack(side="right")
        dlg.protocol("WM_DELETE_WINDOW", lambda: cerrar("cancelar"))
        dlg.wait_window()
        return resultado.get()

    def mostrar_historial_bancos(self, registros):
        dlg = tk.Toplevel(self)
        dlg.title(f"Historial de importaciones bancarias - {self.nombre}")
        dlg.geometry("1180x620")
        dlg.transient(self.winfo_toplevel())

        cols = (
            "fecha", "estado", "banco", "cuenta", "subcuenta", "usuario", "periodo",
            "movimientos", "saldo_final", "archivo",
        )
        tv = ttk.Treeview(dlg, columns=cols, show="headings")
        etiquetas = {
            "fecha": "Importacion", "estado": "Estado", "banco": "Banco",
            "cuenta": "Cuenta / IBAN",
            "subcuenta": "Subcuenta", "usuario": "Usuario",
            "periodo": "Periodo asientos", "movimientos": "Mov.",
            "saldo_final": "Saldo final", "archivo": "Excel origen",
        }
        anchos = (145, 100, 130, 170, 95, 125, 190, 55, 95, 150)
        for col, ancho in zip(cols, anchos):
            tv.heading(col, text=etiquetas[col])
            tv.column(col, width=ancho, stretch=col in ("banco", "archivo"))
        tv.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        detalle = tk.Text(dlg, height=9, wrap="word", state="disabled")
        detalle.pack(fill="x", padx=10, pady=(4, 10))
        por_id = {}
        for reg in registros:
            iid = str(reg["id"])
            por_id[iid] = reg
            periodo = "{} - {}".format(
                reg.get("fecha_primer_asiento") or "-",
                reg.get("fecha_ultimo_asiento") or "-",
            )
            saldo = reg.get("saldo_final")
            tv.insert("", "end", iid=iid, values=(
                str(reg.get("fecha_importacion") or "").replace("T", " "),
                reg.get("estado") or "", reg.get("banco") or "",
                reg.get("numero_cuenta") or "",
                reg.get("subcuenta_banco") or "", reg.get("usuario") or "",
                periodo, reg.get("movimientos_generados") or 0,
                "-" if saldo is None else f"{saldo:,.2f}",
                reg.get("archivo_origen") or "",
            ))

        def ver_detalle(_event=None):
            seleccion = tv.selection()
            if not seleccion:
                return
            reg = por_id[seleccion[0]]
            avisos = reg.get("avisos") or []
            texto = (
                f"Filas leidas: {reg.get('filas_leidas', 0)} | "
                f"Movimientos: {reg.get('movimientos_generados', 0)} | "
                f"Omitidos: {reg.get('movimientos_omitidos', 0)}\n"
                f"Primer asiento: {reg.get('fecha_primer_asiento') or '-'} | "
                f"Saldo primer asiento: {reg.get('saldo_primer_asiento') if reg.get('saldo_primer_asiento') is not None else '-'}\n"
                f"Ultimo asiento: {reg.get('fecha_ultimo_asiento') or '-'} | "
                f"Saldo final: {reg.get('saldo_final') if reg.get('saldo_final') is not None else '-'}\n"
                f"Entradas: {reg.get('importe_entradas', 0):,.2f} | "
                f"Salidas: {reg.get('importe_salidas', 0):,.2f} | "
                f"Variacion neta: {reg.get('variacion_neta', 0):,.2f}\n"
                f"Control duplicados: {reg.get('modo_duplicados') or '-'} | "
                f"Repetidos excluidos/detectados: {reg.get('movimientos_duplicados') or 0} | "
                f"Modificados: {reg.get('movimientos_modificados') or 0}\n"
                f"DAT: {reg.get('archivo_generado') or '-'}\n"
                f"Error: {reg.get('error') or '-'}"
            )
            if avisos:
                texto += "\nAvisos:\n- " + "\n- ".join(avisos)
            detalle.configure(state="normal")
            detalle.delete("1.0", "end")
            detalle.insert("1.0", texto)
            detalle.configure(state="disabled")

        tv.bind("<<TreeviewSelect>>", ver_detalle)
        if registros:
            primero = str(registros[0]["id"])
            tv.selection_set(primero)
            ver_detalle()

    def render_preview(self, df):
        self.tv.delete(*self.tv.get_children())
        self.tv["columns"] = list(df.columns)
        for c in df.columns:
            self.tv.heading(c, text=c)
            self.tv.column(c, width=120, minwidth=80, stretch=False)
        # Limpiar modo contrapartida y bindings anteriores
        self._preview_cols = []
        try:
            self.tv.unbind("<Double-1>")
        except Exception:
            pass
        for row in df.itertuples(index=False):
            vals = [str(x) for x in row]
            self.tv.insert("", tk.END, values=vals)
        self.tv.xview_moveto(0)
        self.tv.yview_moveto(0)

    def mostrar_contrapartidas_preview(self, rows: list):
        """Muestra las filas mapeadas con columna Contrapartida editable (mejora 7)."""
        self.tv.delete(*self.tv.get_children())
        if not rows:
            self.tv["columns"] = []
            return

        # Columnas visibles: las que no empiezan por '_', mas "Contrapartida" al final
        visible_keys = [k for k in rows[0].keys() if not k.startswith("_")]
        cols = visible_keys + ["Contrapartida"]
        self.tv["columns"] = cols
        for c in cols:
            self.tv.heading(c, text=c)
            w = 160 if c == "Contrapartida" else 120
            self.tv.column(c, width=w, minwidth=80, stretch=False)

        self.tv.tag_configure("contra_ok", foreground="#1a5276")
        self.tv.tag_configure("contra_mod", foreground="#922b21")

        for row in rows:
            vals = [str(row.get(k, "") or "") for k in visible_keys]
            contra = str(row.get("_contrapartida_defecto") or "")
            vals.append(contra)
            self.tv.insert("", tk.END, values=vals, tags=("contra_ok",))

        # Guardar referencia de columnas y estado del editor editable
        self._preview_editable_col_map = {"Contrapartida": self.controller.set_contrapartida_override}
        self._preview_ok_tag = "contra_ok"
        self._preview_mod_tag = "contra_mod"
        self._preview_cols = cols

        try:
            self.tv.unbind("<Double-1>")
        except Exception:
            pass
        self.tv.bind("<Double-1>", self._on_preview_double_click)

        self.tv.xview_moveto(0)
        self.tv.yview_moveto(0)

    def mostrar_subcuentas_preview(self, rows: list, col_label: str = "Subcuenta"):
        """Muestra filas mapeadas con columna de subcuenta editable (emitidas/recibidas)."""
        self.tv.delete(*self.tv.get_children())
        if not rows:
            self.tv["columns"] = []
            return

        visible_keys = [k for k in rows[0].keys() if not k.startswith("_")]
        cols = visible_keys + [col_label]
        self.tv["columns"] = cols
        for c in cols:
            self.tv.heading(c, text=c)
            w = 160 if c == col_label else 120
            self.tv.column(c, width=w, minwidth=80, stretch=False)

        self.tv.tag_configure("sub_ok",    foreground="#1a5276")
        self.tv.tag_configure("sub_mod",   foreground="#922b21")
        self.tv.tag_configure("sub_empty", foreground="#94a3b8")

        self._preview_editable_col_map = {col_label: self.controller.set_subcuenta_override}
        self._preview_ok_tag = "sub_ok"
        self._preview_mod_tag = "sub_mod"
        self._preview_cols = cols

        for row in rows:
            vals = [str(row.get(k, "") or "") for k in visible_keys]
            defecto = str(row.get("_subcuenta_defecto") or "")
            vals.append(defecto)
            tag = "sub_ok" if defecto else "sub_empty"
            self.tv.insert("", tk.END, values=vals, tags=(tag,))

        try:
            self.tv.unbind("<Double-1>")
        except Exception:
            pass
        self.tv.bind("<Double-1>", self._on_preview_double_click)
        self.tv.xview_moveto(0)
        self.tv.yview_moveto(0)

    def mostrar_dos_subcuentas_preview(
        self, rows: list,
        col1_label: str, col1_key: str, fn1,
        col2_label: str, col2_key: str, fn2,
    ):
        """Muestra filas con dos columnas editables: cuenta tercero + cuenta compras/ventas."""
        self.tv.delete(*self.tv.get_children())
        if not rows:
            self.tv["columns"] = []
            return

        visible_keys = [k for k in rows[0].keys() if not k.startswith("_")]
        editable_cols = [col1_label, col2_label]
        cols = editable_cols + visible_keys
        self.tv["columns"] = cols
        for c in cols:
            self.tv.heading(c, text=c)
            w = 160 if c in editable_cols else 120
            self.tv.column(c, width=w, minwidth=80, stretch=False)

        self.tv.tag_configure("sub_ok",    foreground="#1a5276")
        self.tv.tag_configure("sub_mod",   foreground="#922b21")
        self.tv.tag_configure("sub_empty", foreground="#94a3b8")

        self._preview_editable_col_map = {col1_label: fn1, col2_label: fn2}
        self._preview_ok_tag = "sub_ok"
        self._preview_mod_tag = "sub_mod"
        self._preview_cols = cols

        for row in rows:
            v1 = str(row.get(col1_key) or "")
            v2 = str(row.get(col2_key) or "")
            vals = [v1, v2] + [str(row.get(k, "") or "") for k in visible_keys]
            tag = "sub_ok" if (v1 or v2) else "sub_empty"
            self.tv.insert("", tk.END, values=vals, tags=(tag,))

        try:
            self.tv.unbind("<Double-1>")
        except Exception:
            pass
        self.tv.bind("<Double-1>", self._on_preview_double_click)
        self.tv.xview_moveto(0)
        self.tv.yview_moveto(0)

    def _on_preview_double_click(self, event):
        """Abre editor con autocompletado en la celda editable (Contrapartida, cuenta tercero o cuenta gasto/ingreso)."""
        region = self.tv.identify("region", event.x, event.y)
        if region != "cell":
            return
        col_id = self.tv.identify_column(event.x)
        row_id = self.tv.identify_row(event.y)
        if not row_id:
            return

        cols = getattr(self, "_preview_cols", [])
        editable_col_map = getattr(self, "_preview_editable_col_map", {})
        if not cols or not editable_col_map:
            return
        try:
            col_idx = int(col_id.replace("#", "")) - 1  # 0-based
        except ValueError:
            return
        if col_idx < 0 or col_idx >= len(cols):
            return
        clicked_col = cols[col_idx]
        if clicked_col not in editable_col_map:
            return

        all_items = self.tv.get_children()
        try:
            row_idx = list(all_items).index(row_id)
        except ValueError:
            return

        current_val = self.tv.set(row_id, clicked_col)
        override_fn = editable_col_map[clicked_col]
        self._abrir_autocomplete_subcuenta(row_id, row_idx, col_id, clicked_col, current_val, override_fn)

    def _cargar_catalogo_subcuentas(self) -> list[dict]:
        """Carga (y cachea) el maestro de subcuentas de la empresa actual."""
        if not hasattr(self, "_subcuentas_catalogo"):
            try:
                self._subcuentas_catalogo = (
                    self.gestor.listar_maestro_subcuentas_empresa(self.codigo, activo=True) or []
                )
            except Exception:
                self._subcuentas_catalogo = []
        return self._subcuentas_catalogo

    def _abrir_autocomplete_subcuenta(self, row_id: str, row_idx: int, col_id: str, col_name: str, valor_actual: str, override_fn):
        """Editor de subcuenta con dropdown de autocompletado sobre el maestro de cuentas."""
        bbox = self.tv.bbox(row_id, col_id)
        if not bbox:
            return
        x_rel, y_rel, cell_w, cell_h = bbox

        # Posicion absoluta en pantalla
        tv_x = self.tv.winfo_rootx()
        tv_y = self.tv.winfo_rooty()
        abs_x = tv_x + x_rel
        abs_y = tv_y + y_rel

        catalogo = self._cargar_catalogo_subcuentas()

        # Ventana flotante (entry + listbox)
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"{max(cell_w, 280)}x160+{abs_x}+{abs_y}")
        popup.attributes("-topmost", True)

        entry_var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(popup, textvariable=entry_var, font=("Segoe UI", 9))
        entry.pack(fill="x")
        entry.select_range(0, tk.END)
        entry.focus_set()

        lb_frame = tk.Frame(popup, bd=1, relief="solid")
        lb_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(lb_frame, font=("Segoe UI", 8), activestyle="dotbox", height=7)
        sb = tk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(fill="both", expand=True)

        def _actualizar_lista(*_):
            txt = entry_var.get().strip().lower()
            lb.delete(0, tk.END)
            if not txt:
                return
            for sc in catalogo:
                codigo = str(sc.get("subcuenta") or "")
                nombre = str(sc.get("nombre_subcuenta") or "")
                # Busqueda por contenido: codigo O nombre contienen el texto
                if txt in codigo.lower() or txt in nombre.lower():
                    lb.insert(tk.END, f"{codigo}  {nombre}")

        entry_var.trace_add("write", _actualizar_lista)
        _actualizar_lista()

        _committed = [False]

        def _commit_value(code: str):
            if _committed[0]:
                return
            _committed[0] = True
            try:
                popup.destroy()
            except Exception:
                pass
            ok_tag = getattr(self, "_preview_ok_tag", "contra_ok")
            mod_tag = getattr(self, "_preview_mod_tag", "contra_mod")
            self.tv.set(row_id, col_name, code)
            tag = mod_tag if code else ok_tag
            self.tv.item(row_id, tags=(tag,))
            override_fn(row_idx, code)

        def _on_entry_return(event=None):
            txt = entry_var.get().strip()
            # Si hay exactamente una coincidencia en el listbox, usarla
            if lb.size() == 1:
                item = lb.get(0)
                code = item.split()[0]
            elif lb.curselection():
                item = lb.get(lb.curselection()[0])
                code = item.split()[0]
            else:
                code = txt
            _commit_value(code)

        def _on_lb_select(event=None):
            sel = lb.curselection()
            if sel:
                item = lb.get(sel[0])
                code = item.split()[0]
                _commit_value(code)

        def _on_cancel(event=None):
            if not _committed[0]:
                _committed[0] = True
                try:
                    popup.destroy()
                except Exception:
                    pass

        entry.bind("<Return>",  _on_entry_return)
        entry.bind("<Tab>",     _on_entry_return)
        entry.bind("<Escape>",  _on_cancel)
        entry.bind("<Down>",    lambda _: lb.focus_set())
        lb.bind("<Return>",     _on_lb_select)
        lb.bind("<Double-Button-1>", _on_lb_select)
        lb.bind("<Escape>",     _on_cancel)
        popup.bind("<FocusOut>", lambda e: self.after(100, lambda: _on_cancel() if not _committed[0] and not popup.focus_get() else None))

    def show_info(self, title, message):
        messagebox.showinfo(title, message)

    def show_warning(self, title, message):
        messagebox.showwarning(title, message)

    def show_error(self, title, message):
        messagebox.showerror(title, message)
