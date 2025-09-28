# ui_seleccion_empresa.py
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
        self.tv.heading("codigo", text="Código")
        self.tv.heading("nombre", text="Nombre")
        self.tv.column("codigo", width=100)
        self.tv.column("nombre", width=300)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

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
