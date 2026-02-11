import tkinter as tk
from tkinter import ttk, messagebox

from utils.utilidades import load_app_config, save_app_config


def _center_window(win, parent=None):
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if parent is None:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        else:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        win.geometry(f"+{max(x,0)}+{max(y,0)}")
    except Exception:
        pass


class MonedasDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configurar monedas")
        self.resizable(False, False)
        self._build()
        self._load()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        self.lb = tk.Listbox(frm, height=8, exportselection=False)
        self.lb.grid(row=0, column=0, rowspan=6, sticky="ns", padx=(0, 10))
        self.lb.bind("<<ListboxSelect>>", lambda e: self._on_select())

        ttk.Label(frm, text="Codigo").grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text="Simbolo").grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="Nombre").grid(row=2, column=1, sticky="w")

        self.var_codigo = tk.StringVar()
        self.var_simbolo = tk.StringVar()
        self.var_nombre = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_codigo, width=12).grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(frm, textvariable=self.var_simbolo, width=12).grid(row=1, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(frm, textvariable=self.var_nombre, width=22).grid(row=2, column=2, padx=4, pady=2, sticky="w")

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=1, columnspan=2, pady=(6, 0), sticky="w")
        ttk.Button(btns, text="Añadir", style="Primary.TButton", command=self._add).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Eliminar", command=self._remove).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Cerrar", command=self.destroy).pack(side=tk.LEFT, padx=2)

    def _load(self):
        cfg = load_app_config()
        self._monedas = cfg.get("monedas") or []
        self.lb.delete(0, tk.END)
        for m in self._monedas:
            codigo = str(m.get("codigo") or "").upper()
            simbolo = str(m.get("simbolo") or "")
            nombre = str(m.get("nombre") or "")
            texto = f"{codigo} {simbolo}".strip()
            if nombre:
                texto = f"{texto} - {nombre}"
            self.lb.insert(tk.END, texto)

    def _save(self):
        cfg = load_app_config()
        cfg["monedas"] = self._monedas
        save_app_config(cfg)

    def _on_select(self):
        sel = self.lb.curselection()
        if not sel:
            return
        idx = sel[0]
        m = self._monedas[idx]
        self.var_codigo.set(str(m.get("codigo") or "").upper())
        self.var_simbolo.set(str(m.get("simbolo") or ""))
        self.var_nombre.set(str(m.get("nombre") or ""))

    def _add(self):
        codigo = (self.var_codigo.get() or "").strip().upper()
        simbolo = (self.var_simbolo.get() or "").strip()
        nombre = (self.var_nombre.get() or "").strip()
        if not codigo:
            messagebox.showwarning("Gest2A3Eco", "Introduce un codigo de moneda.")
            return
        if any(str(m.get("codigo") or "").upper() == codigo for m in self._monedas):
            messagebox.showwarning("Gest2A3Eco", "La moneda ya existe.")
            return
        self._monedas.append({"codigo": codigo, "simbolo": simbolo, "nombre": nombre})
        self._save()
        self._load()

    def _remove(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una moneda.")
            return
        idx = sel[0]
        if len(self._monedas) <= 1:
            messagebox.showwarning("Gest2A3Eco", "Debe existir al menos una moneda.")
            return
        self._monedas.pop(idx)
        self._save()
        self._load()
