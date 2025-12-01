import tkinter as tk
import os
from tkinter import ttk

from ui_seleccion_empresa import UISeleccionEmpresa
from ui_plantillas import UIPlantillasEmpresa
from ui_procesos import UIProcesos
from gestor_plantillas import GestorPlantillas
from ui_theme import aplicar_tema

# ▼ datos de tu despacho (ajusta los textos)
EMPRESA_NOMBRE   = "Asesoría Gestinem S.L."
EMPRESA_CIF      = "B16916967"
EMPRESA_DIRECCION= "CL Atilano Rodríguez 4, Entlo. 7, 39002 Santander (Cantabria)"
EMPRESA_EMAIL    = "jjdominguez@gestinem.es"
EMPRESA_TELEFONO = "942 791 404 - 691 474 519"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_JSON = os.path.join(BASE_DIR, "plantillas", "plantillas.json")


def _build_header(root: tk.Tk, on_cambiar_empresa) -> ttk.Frame:
    """Cabecera fija con logo y datos de contacto."""
    header = ttk.Frame(root, padding=10, style="TFrame")
    header.pack(side="top", fill="x")

    # Logo (logo.png en la misma carpeta que main.py)
    try:
        logo_img = tk.PhotoImage(file="logo.png")

        # Reducir tamaño si es muy alto
        max_h = 75
        if logo_img.height() > max_h:
            factor = max(1, logo_img.height() // max_h)
            logo_img = logo_img.subsample(factor, factor)

        root._logo_img = logo_img  # evitar GC
        lbl_logo = ttk.Label(header, image=logo_img, style="TLabel")
        lbl_logo.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 10))
    except Exception:
        pass  # si no existe logo, no pasa nada

    # Línea 1: nombre empresa
    ttk.Label(
        header,
        text=EMPRESA_NOMBRE,
        style="Header.TLabel"
    ).grid(row=0, column=1, sticky="w")

    # Línea 2: CIF + dirección
    ttk.Label(
        header,
        text=f"CIF: {EMPRESA_CIF}  ·  {EMPRESA_DIRECCION}",
        style="SubHeader.TLabel"
    ).grid(row=1, column=1, sticky="w")

    # Línea 3: contacto
    ttk.Label(
        header,
        text=f"Email: {EMPRESA_EMAIL}  ·  Tel.: {EMPRESA_TELEFONO}",
        style="SubHeader.TLabel"
    ).grid(row=2, column=1, sticky="w")

    # BOTÓN CAMBIAR EMPRESA (alineado derecha)
    btn_cambiar = ttk.Button(
        header,
        text="Cambiar Empresa",
        compound="left",
        style="Secondary.TButton",  # o Primary.TButton si lo prefieres
        command=on_cambiar_empresa
    )
    btn_cambiar.grid(row=0, column=2, sticky="e", padx=(20, 0), pady=(0, 5))

    # BOTÓN CERRAR APLICACIÓN (alineado derecha)
    btn_cerrar = ttk.Button(
        header,
        text="Cerrar aplicación",
        compound="left",
        style="Secondary.TButton",  # o Primary.TButton si lo prefieres
        command=root.destroy
    )
    btn_cerrar.grid(row=1, column=2, sticky="e", padx=(20, 0), pady=(5, 0))

    # Que ocupe todo el ancho
    header.columnconfigure(1, weight=1)

    return header


def main():
    root = tk.Tk()
    root.title("Gest2A3Eco")

    aplicar_tema(root) # aplicar tema personalizado

     # 1) Cabecera fija
    _build_header(root, on_cambiar_empresa=lambda: show(build_seleccion))

    # Contenedor de pantallas debajo de la cabecera
    content = ttk.Frame(root, padding=10, style="TFrame")
    content.pack(side="top", fill="both", expand=True)

    gestor = GestorPlantillas(RUTA_JSON)

    estado = {"frame": None}

    def show(factory):
        """Destruye la pantalla actual y crea la nueva dentro de 'content'."""
        if estado["frame"] is not None:
            estado["frame"].destroy()
        fr = factory(content)
        fr.pack(fill="both", expand=True)
        estado["frame"] = fr

    # Callbacks de navegación
    def on_empresa_ok(codigo, nombre):
        # aquí creas el "dashboard" o directamente la pantalla de procesos
        def build_dashboard(parent):
            nb = ttk.Notebook(parent)
            # pestaña de plantillas
            nb.add(
                UIPlantillasEmpresa(nb, gestor, codigo, nombre),
                text="Plantillas"
            )
            # pestaña de generación de ficheros
            nb.add(
                UIProcesos(nb, gestor, codigo, nombre),
                text="Generar ficheros"
            )
            return nb

        show(build_dashboard)

    def build_seleccion(parent):
        return UISeleccionEmpresa(parent, gestor, on_empresa_ok)

    
    # Pantalla inicial: selección de empresa
    show(build_seleccion)

    root.mainloop()


if __name__ == "__main__":
    main()
