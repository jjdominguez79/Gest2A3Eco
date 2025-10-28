# ui_seleccion_empresa.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import Dialog

class EmpresaDialog(Dialog):
    def __init__(self, parent, titulo, empresa=None):
        self.empresa = empresa or {"codigo":"","nombre":"","digitos_plan":8,"ejercicio":2025}
        super().__init__(parent, titulo)

    def body(self, master):
        self.var_codigo = tk.StringVar(value=str(self.empresa.get("codigo","")))
        self.var_nombre = tk.StringVar(value=str(self.empresa.get("nombre","")))
        self.var_dig = tk.StringVar(value=str(self.empresa.get("digitos_plan",8)))
        self.var_eje = tk.StringVar(value=str(self.empresa.get("ejercicio",2025)))

        ttk.Label(master, text="Código").grid(row=0, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_codigo).grid(row=0, column=1)
        ttk.Label(master, text="Nombre").grid(row=1, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_nombre, width=40).grid(row=1, column=1)
        ttk.Label(master, text="Dígitos plan").grid(row=2, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dig, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(master, text="Ejercicio").grid(row=3, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_eje, width=8).grid(row=3, column=1, sticky="w")
        return master

    def apply(self):
        try:
            self.result = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "ejercicio": int(self.var_eje.get().strip() or "2025"),
            }
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            self.result = None

class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, master, gestor, on_ok):
        super().__init__(master)
        self.gestor = gestor
        self.on_ok = on_ok
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        ttk.Label(self, text="Selecciona empresa", font=("Segoe UI", 12, "bold")).pack(pady=8)
        self.tv = ttk.Treeview(self, columns=("codigo","nombre","digitos","ejercicio"), show="headings", height=12)
        for c,t,w in (("codigo","Código",140),("nombre","Nombre",420),("digitos","Dígitos",80),("ejercicio","Ejercicio",90)):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self._refresh()

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(bar, text="Nueva empresa", command=self._nueva).pack(side=tk.LEFT)
        ttk.Button(bar, text="Editar empresa", command=self._editar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Continuar", command=self._continuar).pack(side=tk.RIGHT)

    def _refresh(self):
        self.tv.delete(*self.tv.get_children())
        for e in self.gestor.listar_empresas():
            self.tv.insert("", tk.END, values=(e.get("codigo"), e.get("nombre"), e.get("digitos_plan",8), e.get("ejercicio",2025)))

    def _nueva(self):
        dlg = EmpresaDialog(self, "Nueva empresa")
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result); self._refresh()

    def _editar(self):
        sel = self.tv.selection()
        if not sel: return
        codigo, *_ = self.tv.item(sel[0], "values")
        emp = self.gestor.get_empresa(codigo)
        dlg = EmpresaDialog(self, "Editar empresa", emp)
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result); self._refresh()

    def _continuar(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Gest2A3Eco","Selecciona una empresa.")
            return
        codigo, nombre, *_ = self.tv.item(sel[0], "values")
        self.on_ok(codigo, nombre)
