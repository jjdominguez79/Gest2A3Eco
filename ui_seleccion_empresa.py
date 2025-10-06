import tkinter as tk
from tkinter import ttk, messagebox


class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, master, gestor, on_ok):
        super().__init__(master)
        self.gestor = gestor
        self.on_ok = on_ok
        self.pack(fill=tk.BOTH, expand=True)

        ttk.Label(self, text="Seleccionar empresa", font=("Segoe UI", 14, "bold")).pack(pady=10)

        cols = ("codigo", "nombre")
        self.tv = ttk.Treeview(self, columns=cols, show="headings", height=12)
        self.tv.heading("codigo", text="C\u00f3digo")
        self.tv.heading("nombre", text="Nombre")
        self.tv.column("codigo", width=110)
        self.tv.column("nombre", width=320)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tv.bind("<Double-1>", lambda _event: self._continuar())

        acciones = ttk.Frame(self)
        acciones.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Button(acciones, text="Agregar", command=self._nueva_empresa).pack(side=tk.LEFT)
        ttk.Button(acciones, text="Editar", command=self._editar_empresa).pack(side=tk.LEFT, padx=5)
        ttk.Button(acciones, text="Eliminar", command=self._eliminar_empresa).pack(side=tk.LEFT)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="Continuar", command=self._continuar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btns, text="Salir", command=self.quit).pack(side=tk.RIGHT)

        self._cargar_empresas()

    def _cargar_empresas(self):
        self.tv.delete(*self.tv.get_children())
        for emp in self.gestor.listar_empresas():
            self.tv.insert("", tk.END, values=(emp.get("codigo"), emp.get("nombre")))

    def _continuar(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Gest2A3Eco", "Selecciona una empresa primero.")
            return
        codigo, nombre = self.tv.item(sel[0], "values")
        if self.on_ok:
            self.on_ok(codigo, nombre)

    def _seleccion_actual(self):
        sel = self.tv.selection()
        if not sel:
            return None
        codigo, _nombre = self.tv.item(sel[0], "values")
        return self.gestor.obtener_empresa(codigo)

    def _nueva_empresa(self):
        self._abrir_dialogo_empresa()

    def _editar_empresa(self):
        empresa = self._seleccion_actual()
        if not empresa:
            messagebox.showinfo("Gest2A3Eco", "Selecciona la empresa a editar.")
            return
        self._abrir_dialogo_empresa(empresa)

    def _eliminar_empresa(self):
        empresa = self._seleccion_actual()
        if not empresa:
            messagebox.showinfo("Gest2A3Eco", "Selecciona la empresa a eliminar.")
            return
        if not messagebox.askyesno(
            "Gest2A3Eco",
            "\u00bfSeguro que deseas eliminar la empresa {} ({})?\n"
            "Se eliminar\u00e1n tambi\u00e9n sus plantillas asociadas.".format(
                empresa.get("nombre"), empresa.get("codigo")
            ),
        ):
            return
        try:
            self.gestor.eliminar_empresa(empresa.get("codigo"))
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No fue posible eliminar la empresa.\n{exc}")
            return
        self._cargar_empresas()
        messagebox.showinfo("Gest2A3Eco", "Empresa eliminada correctamente.")

    def _abrir_dialogo_empresa(self, empresa=None):
        dlg = tk.Toplevel(self)
        dlg.transient(self.winfo_toplevel())
        dlg.title("Editar empresa" if empresa else "Nueva empresa")
        dlg.resizable(False, False)
        dlg.grab_set()

        codigo_var = tk.StringVar(value=empresa.get("codigo") if empresa else "")
        nombre_var = tk.StringVar(value=empresa.get("nombre") if empresa else "")

        cuerpo = ttk.Frame(dlg, padding=15)
        cuerpo.pack(fill=tk.BOTH, expand=True)

        ttk.Label(cuerpo, text="C\u00f3digo:").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        codigo_entry = ttk.Entry(cuerpo, textvariable=codigo_var)
        codigo_entry.grid(row=0, column=1, sticky=tk.EW, pady=(0, 6))
        ttk.Label(cuerpo, text="Nombre:").grid(row=1, column=0, sticky=tk.W)
        nombre_entry = ttk.Entry(cuerpo, textvariable=nombre_var)
        nombre_entry.grid(row=1, column=1, sticky=tk.EW)
        cuerpo.columnconfigure(1, weight=1)

        botones = ttk.Frame(dlg, padding=(0, 0, 15, 15))
        botones.pack(fill=tk.X)
        ttk.Button(botones, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            botones,
            text="Guardar",
            command=lambda: self._guardar_empresa(dlg, empresa, codigo_var, nombre_var),
        ).pack(side=tk.RIGHT, padx=5)

        codigo_entry.focus_set()
        dlg.wait_window()

    def _guardar_empresa(self, dlg, empresa, codigo_var, nombre_var):
        codigo = codigo_var.get().strip()
        nombre = nombre_var.get().strip()
        if not codigo or not nombre:
            messagebox.showwarning("Gest2A3Eco", "C\u00f3digo y nombre son obligatorios.")
            return
        datos = dict(empresa) if empresa else {}
        datos["codigo"] = codigo
        datos["nombre"] = nombre
        datos.setdefault("excel", {})
        try:
            if empresa:
                self.gestor.actualizar_empresa(empresa.get("codigo"), datos)
            else:
                self.gestor.crear_empresa(datos)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc))
            return
        dlg.destroy()
        self._cargar_empresas()
