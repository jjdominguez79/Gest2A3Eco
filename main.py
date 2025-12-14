import os, sys
import json
import tkinter as tk
from tkinter import ttk

from ui_seleccion_empresa import UISeleccionEmpresa
from ui_plantillas import UIPlantillasEmpresa
from ui_procesos import UIProcesos
from ui_facturas_emitidas import UIFacturasEmitidas
from gestor_sqlite import GestorSQLite
from ui_theme import aplicar_tema


# ─────────────────────────────────────────────
# Datos de la asesoría (cabecera)
# ─────────────────────────────────────────────
EMPRESA_NOMBRE    = "Asesoría Gestinem S.L."
EMPRESA_CIF       = "B16916967"
EMPRESA_DIRECCION = "CL Atilano Rodríguez 4, Entlo. 7, 39002 Santander (Cantabria)"
EMPRESA_EMAIL     = "jjdominguez@gestinem.es"
EMPRESA_TELEFONO  = "Tel.: 691 474 519"

# ─────────────────────────────────────────────
# Ruta al logo compatible con .exe
# ─────────────────────────────────────────────
def resource_path(relpath: str) -> str:
    """
    Devuelve la ruta absoluta a un recurso (p.ej. 'logo.png') tanto en desarrollo
    como en el ejecutable PyInstaller (onefile).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # carpeta temporal de PyInstaller
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relpath)

# ─────────────────────────────────────────────
# Rutas robustas para script y .exe
# ─────────────────────────────────────────────
def app_base_dir() -> str:
    """
    Devuelve la carpeta base de la aplicación:
    - Si está congelada (.exe con PyInstaller), la carpeta del ejecutable.
    - Si es script .py, la carpeta del propio archivo.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_base_dir()
PLANTILLAS_DIR = os.path.join(BASE_DIR, "plantillas")
os.makedirs(PLANTILLAS_DIR, exist_ok=True)
RUTA_JSON = os.path.join(PLANTILLAS_DIR, "plantillas.json")
RUTA_DB = os.path.join(PLANTILLAS_DIR, "gest2a3eco.db")


# ─────────────────────────────────────────────
# Cabecera común (logo + datos + botones)
# ─────────────────────────────────────────────
def _build_header(root: tk.Tk, on_cambiar_empresa) -> ttk.Frame:
    """Cabecera fija con logo, datos de contacto y botones globales."""
    header = ttk.Frame(root, padding=10, style="TFrame")
    header.pack(side="top", fill="x")

    # Logo
    try:
        logo_img = tk.PhotoImage(file=resource_path("logo.png"))

        # Reducir tamano si es muy alto
        max_h = 48
        if logo_img.height() > max_h:
            factor = max(1, logo_img.height() // max_h)
            logo_img = logo_img.subsample(factor, factor)

        root._logo_img = logo_img  # evitar GC
        lbl_logo = ttk.Label(header, image=logo_img, style="TLabel")
        lbl_logo.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 10))
    except Exception:
        pass

    # Datos empresa
    ttk.Label(
        header,
        text=EMPRESA_NOMBRE,
        style="Header.TLabel"
    ).grid(row=0, column=1, sticky="w")

    ttk.Label(
        header,
        text=f"CIF: {EMPRESA_CIF}  ·  {EMPRESA_DIRECCION}",
        style="SubHeader.TLabel"
    ).grid(row=1, column=1, sticky="w")

    ttk.Label(
        header,
        text=f"Email: {EMPRESA_EMAIL}  ·  {EMPRESA_TELEFONO}",
        style="SubHeader.TLabel"
    ).grid(row=2, column=1, sticky="w")

    # Botones (texto) apilados
    botones_frame = ttk.Frame(header, style="TFrame")
    botones_frame.grid(row=0, column=2, rowspan=3, sticky="e", padx=(20, 0))

    btn_cambiar = ttk.Button(
        botones_frame,
        text="Empresas",
        style="Primary.TButton",
        command=on_cambiar_empresa,
    )
    btn_cambiar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    # Botón rojo personalizado para Cerrar
    style = ttk.Style()
    style.configure("Close.TButton", foreground="#ffffff", background="#D64545")
    style.map("Close.TButton",
              background=[("active", "#bb3434"), ("pressed", "#a52d2d")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

    btn_cerrar = ttk.Button(
        botones_frame,
        text="Cerrar",
        style="Close.TButton",
        command=root.destroy,
    )
    btn_cerrar.grid(row=1, column=0, sticky="ew")

    botones_frame.columnconfigure(0, weight=1)

    # Que la columna central se expanda
    header.columnconfigure(1, weight=1)

    return header

# ─────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.title("Gest2A3Eco")
    root.geometry("1200x800+100+50")
    root.resizable(False, False)
    try:
        root.iconbitmap(resource_path("icono.ico"))
    except Exception:
        pass

    # Tema visual unificado
    aplicar_tema(root)
    
    # Cabecera (usa show(build_seleccion) para "Cambiar empresa")
    _build_header(root, on_cambiar_empresa=lambda: show(build_seleccion))

    # Contenedor de pantallas bajo la cabecera
    content = ttk.Frame(root, padding=10, style="TFrame")
    content.pack(side="top", fill="both", expand=True)

    # Gestor de datos en SQLite (migra desde JSON si existe)
    gestor = GestorSQLite(RUTA_DB, json_seed=RUTA_JSON)

    estado = {"frame": None}

    def show(factory):
        """Destruye la pantalla actual y muestra la nueva en 'content'."""
        if estado["frame"] is not None:
            estado["frame"].destroy()
        fr = factory(content)
        fr.pack(fill="both", expand=True)
        estado["frame"] = fr

    # Callback al confirmar empresa en la pantalla de selección
    def on_empresa_ok(codigo, ejercicio, nombre):
        def build_dashboard(parent):
            nb = ttk.Notebook(parent)

            # Pestaña de plantillas
            nb.add(
                UIPlantillasEmpresa(nb, gestor, codigo, ejercicio, nombre),
                text="Plantillas"
            )

            # Pestaña de facturas emitidas (módulo interno)
            nb.add(
                UIFacturasEmitidas(nb, gestor, codigo, ejercicio, nombre),
                text="Facturas emitidas"
            )

            # Pestaña de generación de ficheros
            nb.add(
                UIProcesos(nb, gestor, codigo, ejercicio, nombre),
                text="Generar ficheros"
            )

            return nb

        show(build_dashboard)

    # Pantalla de selección de empresa
    def build_seleccion(parent):
        return UISeleccionEmpresa(parent, gestor, on_empresa_ok)

    # Pantalla inicial
    show(build_seleccion)

    root.mainloop()


if __name__ == "__main__":
    main()
