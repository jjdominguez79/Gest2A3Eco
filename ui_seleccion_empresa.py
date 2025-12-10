import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import Dialog

from ui_facturas_emitidas import TercerosDialog

class EmpresaDialog(Dialog):
    def __init__(self, parent, titulo, empresa=None):
        self.empresa = empresa or {"codigo":"","nombre":"","digitos_plan":8,"ejercicio":2025,"serie_emitidas":"A","siguiente_num_emitidas":1}
        super().__init__(parent, titulo)

    def body(self, master):
        self.var_codigo = tk.StringVar(value=str(self.empresa.get("codigo","")))
        self.var_nombre = tk.StringVar(value=str(self.empresa.get("nombre","")))
        self.var_dig = tk.StringVar(value=str(self.empresa.get("digitos_plan",8)))
        self.var_eje = tk.StringVar(value=str(self.empresa.get("ejercicio",2025)))
        self.var_serie = tk.StringVar(value=str(self.empresa.get("serie_emitidas","A")))
        self.var_next = tk.StringVar(value=str(self.empresa.get("siguiente_num_emitidas",1)))

        ttk.Label(master, text="Codigo").grid(row=0, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_codigo).grid(row=0, column=1)
        ttk.Label(master, text="Nombre").grid(row=1, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_nombre, width=40).grid(row=1, column=1)
        ttk.Label(master, text="Digitos plan").grid(row=2, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dig, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(master, text="Ejercicio").grid(row=3, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_eje, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(master, text="Serie emitidas").grid(row=4, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_serie, width=10).grid(row=4, column=1, sticky="w")
        ttk.Label(master, text="Siguiente numero").grid(row=5, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_next, width=10).grid(row=5, column=1, sticky="w")
        return master

    def apply(self):
        try:
            self.result = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "ejercicio": int(self.var_eje.get().strip() or "2025"),
                "serie_emitidas": self.var_serie.get().strip() or "A",
                "siguiente_num_emitidas": int(self.var_next.get().strip() or "1"),
            }
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            self.result = None

class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, parent, gestor, on_ok):
        super().__init__(parent)
        self.gestor = gestor
        self.on_ok = on_ok
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        ttk.Label(self, text="Selecciona empresa", font=("Segoe UI", 12, "bold")).pack(pady=8)
        self.tv = ttk.Treeview(self, columns=("codigo","nombre","digitos","ejercicio","serie","next"), show="headings", height=12)
        for c,t,w in (
            ("codigo","Codigo",120),
            ("nombre","Nombre",320),
            ("digitos","Digitos",70),
            ("ejercicio","Ejercicio",80),
            ("serie","Serie",80),
            ("next","Siguiente",90),
        ):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self._refresh()

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(bar, text="Nueva empresa", style="Primary.TButton", command=self._nueva).pack(side=tk.LEFT)
        ttk.Button(bar, text="Editar empresa", style="Primary.TButton", command=self._editar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Terceros", command=self._terceros).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Continuar", style="Primary.TButton", command=self._continuar).pack(side=tk.RIGHT)

    def _refresh(self):
        self.tv.delete(*self.tv.get_children())
        for e in self.gestor.listar_empresas():
            self.tv.insert("", tk.END, values=(
                e.get("codigo"),
                e.get("nombre"),
                e.get("digitos_plan",8),
                e.get("ejercicio",2025),
                e.get("serie_emitidas","A"),
                e.get("siguiente_num_emitidas",1),
            ))

    def _sel_codigo(self):
        sel = self.tv.selection()
        if not sel:
            return None
        codigo, *_ = self.tv.item(sel[0], "values")
        return codigo

    def _nueva(self):
        dlg = EmpresaDialog(self, "Nueva empresa")
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result)
            self._refresh()
            messagebox.showinfo("Gest2A3Eco", "Empresa guardada.")

    def _editar(self):
        codigo = self._sel_codigo()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self.gestor.get_empresa(codigo)
        dlg = EmpresaDialog(self, "Editar empresa", emp)
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result)
            self._refresh()
            messagebox.showinfo("Gest2A3Eco", "Cambios guardados.")

    def _terceros(self):
        codigo = self._sel_codigo()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self.gestor.get_empresa(codigo) or {"codigo":codigo,"digitos_plan":8}
        TercerosDialog(self, self.gestor, emp.get("codigo"), emp.get("digitos_plan",8))

    def _continuar(self):
        codigo = self._sel_codigo()
        if not codigo:
            messagebox.showwarning("Gest2A3Eco","Selecciona una empresa.")
            return
        nombre = self.gestor.get_empresa(codigo).get("nombre","")
        self.on_ok(codigo, nombre)
