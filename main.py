import os, sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from controllers.app_controller import AppController
from models.gestor_sqlite import GestorSQLite
from utils.utilidades import load_app_config, save_app_config
from views.ui_config_monedas import MonedasDialog
from views.ui_theme import aplicar_tema


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
def _build_header(root: tk.Tk, on_cambiar_empresa, on_cambiar_db=None, db_path: str | None = None) -> ttk.Frame:
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

    # Path BD
    if db_path:
        try:
            header.rowconfigure(3, weight=0)
            ttk.Label(
                header,
                text=f"Base de datos: {db_path}",
                style="SubHeader.TLabel",
                foreground="#3f3f3f",
            ).grid(row=3, column=1, sticky="w")
        except Exception:
            pass

    # Que la columna central se expanda
    header.columnconfigure(1, weight=1)

    return header

# ─────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────
def _select_db_path(default_path: str) -> str:
    try:
        initial_dir = os.path.dirname(default_path)
    except Exception:
        initial_dir = ""
    path = filedialog.askopenfilename(
        title="Selecciona base de datos",
        initialdir=initial_dir,
        initialfile=os.path.basename(default_path),
        filetypes=[("SQLite DB", "*.db"), ("Todos", "*.*")],
    )
    return path or default_path

def _get_last_db_path(default_path: str) -> str:
    cfg = load_app_config()
    last = str(cfg.get("last_db_path") or "").strip()
    if last and os.path.exists(last):
        return last
    return default_path

def _set_last_db_path(path: str) -> None:
    cfg = load_app_config()
    cfg["last_db_path"] = path
    save_app_config(cfg)

def _restart_app():
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass

def main():
    root = tk.Tk()
    root.title("Gest2A3Eco")
    root.geometry("1850x1100+60+30")
    root.resizable(True, True)
    try:
        root.iconbitmap(resource_path("icono.ico"))
    except Exception:
        pass

    # Tema visual unificado
    aplicar_tema(root)
    
    # Contenedor de pantallas bajo la cabecera
    content = ttk.Frame(root, padding=10, style="TFrame")
    content.pack(side="top", fill="both", expand=True)

    # Seleccionar base de datos (recuerda la ultima)
    db_path = _get_last_db_path(RUTA_DB)
    if not db_path or not os.path.exists(db_path):
        db_path = _select_db_path(RUTA_DB)
    _set_last_db_path(db_path)

    # Gestor de datos en SQLite (migra desde JSON si existe)
    gestor = GestorSQLite(db_path, json_seed=RUTA_JSON)

    # Controlador de navegacion entre pantallas (MVC)
    controller = AppController(content, gestor)

    def _on_cambiar_db():
        new_path = _select_db_path(db_path)
        if new_path and new_path != db_path:
            _set_last_db_path(new_path)
            try:
                messagebox.showinfo("Gest2A3Eco", "Base de datos cambiada. La aplicacion se reiniciara.")
            except Exception:
                pass
            root.destroy()
            _restart_app()

    def _on_config_monedas():
        MonedasDialog(root)

    # Cabecera (usa el controlador para "Cambiar empresa")
    _build_header(root, on_cambiar_empresa=controller.start, on_cambiar_db=_on_cambiar_db, db_path=db_path)

    # Menu contextual
    ctx = tk.Menu(root, tearoff=0)
    ctx.add_command(label="Menu principal", command=controller.start)
    cfg_menu = tk.Menu(ctx, tearoff=0)
    cfg_menu.add_command(label="Seleccionar base de datos", command=_on_cambiar_db)
    cfg_menu.add_command(label="Configurar monedas", command=_on_config_monedas)
    ctx.add_cascade(label="Configuracion", menu=cfg_menu)
    ctx.add_separator()
    ctx.add_command(label="Cerrar", command=root.destroy)

    def _show_ctx(event):
        try:
            ctx.tk_popup(event.x_root, event.y_root)
        finally:
            ctx.grab_release()

    root.bind("<Button-3>", _show_ctx)

    # Pantalla inicial
    controller.start()

    root.mainloop()


if __name__ == "__main__":
    main()
