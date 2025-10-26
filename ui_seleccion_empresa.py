import tkinter as tk
from tkinter import ttk, messagebox

class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, master, gestor, on_ok):
        super().__init__(master)
        self.gestor = gestor
        self.on_ok = on_ok
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        ttk.Label(self, text="Selecciona empresa", font=("Segoe UI", 12, "bold")).pack(pady=8)
        self.tv = ttk.Treeview(self, columns=("codigo","nombre"), show="headings", height=12)
        self.tv.heading("codigo", text="Código"); self.tv.heading("nombre", text="Nombre")
        self.tv.column("codigo", width=140); self.tv.column("nombre", width=520)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        for e in self.gestor.listar_empresas():
            self.tv.insert("", tk.END, values=(e.get("codigo"), e.get("nombre")))

        bottom = ttk.Frame(self); bottom.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(bottom, text="Continuar", command=self._continuar).pack(side=tk.RIGHT)

    def _continuar(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showwarning("Gest2A3Eco", "Selecciona una empresa.")
            return
        codigo, nombre = self.tv.item(sel[0], "values")
        self.on_ok(codigo, nombre)
