import tkinter as tk
from tkinter import ttk
from pathlib import Path
import json

from gestor_plantillas import GestorPlantillas
from ui_seleccion_empresa import UISeleccionEmpresa
from ui_plantillas import UIPlantillasEmpresa
from ui_procesos import UIProcesos

APP_NAME = "Gest2A3Eco"

def main():
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8")) if Path("config.json").exists() else {"templates_path":"plantillas/plantillas.json"}
    tpl_path = Path(cfg.get("templates_path","plantillas/plantillas.json")).resolve()
    gestor = GestorPlantillas(tpl_path)

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1200x780")

    container = ttk.Frame(root); container.pack(fill=tk.BOTH, expand=True)
    current = {"frame": None, "empresa": None}

    def show(factory):
        if current["frame"] is not None and current["frame"].winfo_exists():
            try:
                current["frame"].destroy()
            except Exception:
                pass
        fr = factory()
        current["frame"] = fr
        try:
            fr.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass

    def on_empresa_ok(codigo, nombre):
        current["empresa"] = (codigo, nombre)
        show(build_dashboard)

    def build_dashboard():
        fr = ttk.Frame(container)
        top = ttk.Frame(fr); top.pack(fill=tk.X, padx=10, pady=6)
        codigo, nombre = current["empresa"]
        ttk.Label(top, text=f"Empresa seleccionada: {nombre} ({codigo})", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="Cambiar empresa", command=lambda: show(lambda: UISeleccionEmpresa(container, gestor, on_empresa_ok))).pack(side=tk.RIGHT)

        nb = ttk.Notebook(fr); nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        nb.add(UIPlantillasEmpresa(nb, gestor, codigo, nombre), text="Plantillas")
        nb.add(UIProcesos(nb, gestor, codigo), text="Generar enlace")
        return fr

    menubar = tk.Menu(root); root.config(menu=menubar)
    menubar.add_command(label="Seleccionar empresa", command=lambda: show(lambda: UISeleccionEmpresa(container, gestor, on_empresa_ok)))
    menubar.add_command(label="Salir", command=root.destroy)

    show(lambda: UISeleccionEmpresa(container, gestor, on_empresa_ok))
    root.mainloop()

if __name__ == "__main__":
    main()
