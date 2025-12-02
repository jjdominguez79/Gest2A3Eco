import os, sys
import json
import tkinter as tk
from tkinter import ttk

from ui_seleccion_empresa import UISeleccionEmpresa
from ui_plantillas import UIPlantillasEmpresa
from ui_procesos import UIProcesos
from gestor_plantillas import GestorPlantillas
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


def ensure_plantillas_json(base_dir: str) -> str:
    """
    Asegura que existe /plantillas/plantillas.json junto a la app.
    Si no existe, crea la carpeta y un JSON mínimo de ejemplo.
    """
    plantillas_dir = os.path.join(base_dir, "plantillas")
    os.makedirs(plantillas_dir, exist_ok=True)
    path_json = os.path.join(plantillas_dir, "plantillas.json")

    if not os.path.exists(path_json):
        ejemplo = {
            "empresas": [],
            "bancos": [],
            "emitidas": [],
            "recibidas": []
        }
        with open(path_json, "w", encoding="utf-8") as f:
            json.dump(ejemplo, f, ensure_ascii=False, indent=2)

    return path_json


BASE_DIR = app_base_dir()
RUTA_JSON = ensure_plantillas_json(BASE_DIR)


def _color_bg(widget: tk.Widget) -> str:
    """Devuelve el color de fondo actual para mezclar con las imagenes."""
    style = ttk.Style(widget)
    bg = style.lookup("TFrame", "background") or widget.cget("background")
    return bg or "#f5f5f7"


def _rounded_button_image(bg: str, fill: str, icon: str) -> tk.PhotoImage:
    """Genera una imagen con esquinas redondeadas y un icono simple centrado."""
    width, height, radius = 60, 25, 8
    img = tk.PhotoImage(width=width, height=height)

    # Fondo base
    img.put(bg, to=(0, 0, width, height))
    img.put(fill, to=(radius, 0, width - radius, height))
    img.put(fill, to=(0, radius, width, height - radius))

    cx = radius - 1
    cy = radius - 1
    for x in range(radius):
        for y in range(radius):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                for px, py in (
                    (x, y),
                    (width - 1 - x, y),
                    (x, height - 1 - y),
                    (width - 1 - x, height - 1 - y),
                ):
                    img.put(fill, (px, py))

    icon_color = "#ffffff"

    def draw_line(x0, y0, x1, y1, thickness=2, color=None):
        color = color or icon_color
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(steps + 1):
            x = x0 + (x1 - x0) * i // steps
            y = y0 + (y1 - y0) * i // steps
            img.put(color, to=(x - thickness, y - thickness, x + thickness + 1, y + thickness + 1))

    def draw_arrow(x0, y0, x1, y1, direction):
        draw_line(x0, y0, x1, y1)
        if direction == "right":
            draw_line(x1 - 6, y1 - 6, x1, y1)
            draw_line(x1 - 6, y1 + 6, x1, y1)
        else:
            draw_line(x0, y0, x0 + 6, y0 - 6)
            draw_line(x0, y0, x0 + 6, y0 + 6)

    center_y = height // 2
    center_x = width // 2

    if icon == "swap":
        draw_arrow(12, center_y - 4, width - 14, center_y - 4, "right")
        draw_arrow(width - 12, center_y + 4, 14, center_y + 4, "left")
    elif icon == "close":
        draw_line(center_x - 8, center_y - 8, center_x + 8, center_y + 8, thickness=2)
        draw_line(center_x - 8, center_y + 8, center_x + 8, center_y - 8, thickness=2)

    return img


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

    # Botones como imagenes, alineados en paralelo
    botones_frame = ttk.Frame(header, style="TFrame")
    botones_frame.grid(row=0, column=2, rowspan=3, sticky="e", padx=(20, 0))

    bg_color = _color_bg(header)
    img_cambiar = _rounded_button_image(bg_color, fill="#002C57", icon="swap")
    img_cerrar = _rounded_button_image(bg_color, fill="#D64545", icon="close")

    root._img_cambiar_empresa = img_cambiar
    root._img_cerrar = img_cerrar

    btn_cambiar = tk.Button(
        botones_frame,
        image=img_cambiar,
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        bg=bg_color,
        activebackground=bg_color,
        cursor="hand2",
        command=on_cambiar_empresa,
    )
    btn_cambiar.grid(row=0, column=0, padx=(0, 10))

    btn_cerrar = tk.Button(
        botones_frame,
        image=img_cerrar,
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        bg=bg_color,
        activebackground=bg_color,
        cursor="hand2",
        command=root.destroy,
    )
    btn_cerrar.grid(row=0, column=1)

    # Que la columna central se expanda
    header.columnconfigure(1, weight=1)

    return header



# ─────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.title("Gest2A3Eco")

    # Tema visual unificado
    aplicar_tema(root)
    
    # Cabecera (usa show(build_seleccion) para "Cambiar empresa")
    _build_header(root, on_cambiar_empresa=lambda: show(build_seleccion))

    # Contenedor de pantallas bajo la cabecera
    content = ttk.Frame(root, padding=10, style="TFrame")
    content.pack(side="top", fill="both", expand=True)

    # Gestor de plantillas (ruta robusta)
    gestor = GestorPlantillas(RUTA_JSON)

    estado = {"frame": None}

    def show(factory):
        """Destruye la pantalla actual y muestra la nueva en 'content'."""
        if estado["frame"] is not None:
            estado["frame"].destroy()
        fr = factory(content)
        fr.pack(fill="both", expand=True)
        estado["frame"] = fr

    # Callback al confirmar empresa en la pantalla de selección
    def on_empresa_ok(codigo, nombre):
        def build_dashboard(parent):
            nb = ttk.Notebook(parent)

            # Pestaña de plantillas
            nb.add(
                UIPlantillasEmpresa(nb, gestor, codigo, nombre),
                text="Plantillas"
            )

            # Pestaña de generación de ficheros
            nb.add(
                UIProcesos(nb, gestor, codigo, nombre),
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
