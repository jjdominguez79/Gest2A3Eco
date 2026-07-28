# ui_tema.py
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None


APP_TITLE = "Gestinem Suite"
LEGACY_APP_TITLE = "Gest2A3Eco"


def _icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "icono.ico"
    return Path(__file__).resolve().parents[1] / "icono.ico"


def aplicar_icono_ventana(window) -> None:
    """Fuerza la G corporativa en la barra de titulo de Windows."""
    icon_path = _icon_path()
    if not icon_path.exists():
        return
    try:
        window.iconbitmap(str(icon_path))
    except Exception:
        pass
    if Image is None or ImageTk is None:
        return
    try:
        image = Image.open(icon_path).convert("RGBA")
        image.thumbnail((64, 64))
        window._gestinem_icon_img = ImageTk.PhotoImage(image, master=window)
        window.iconphoto(True, window._gestinem_icon_img)
    except Exception:
        pass


def _instalar_marca_dialogos() -> None:
    """Aplica el titulo e icono corporativos a dialogos Tk y messagebox."""
    if getattr(tk.Toplevel, "_marca_gestinem_instalada", False):
        return

    original_title = tk.Toplevel.title
    original_messagebox_show = messagebox._show

    def branded_title(self, string=None):
        if string == LEGACY_APP_TITLE:
            string = APP_TITLE
        return original_title(self, string)

    def branded_messagebox_show(title=None, message=None, _icon=None, _type=None, **options):
        if title == LEGACY_APP_TITLE:
            title = APP_TITLE
        return original_messagebox_show(title, message, _icon, _type, **options)

    tk.Toplevel.title = branded_title
    tk.Toplevel.wm_title = branded_title
    messagebox._show = branded_messagebox_show
    tk.Toplevel._marca_gestinem_instalada = True  # type: ignore[attr-defined]
    tk.Toplevel._set_icono_gestinem = staticmethod(aplicar_icono_ventana)  # type: ignore[attr-defined]

def _instalar_centrado_toplevels() -> None:
    """Parcha tk.Toplevel para que todos los dialogos se centren en pantalla automaticamente."""
    if getattr(tk.Toplevel, "_centrado_instalado", False):
        return
    _orig_init = tk.Toplevel.__init__

    def _patched_init(self, master=None, **kw):
        _orig_init(self, master, **kw)
        try:
            tk.Toplevel._set_icono_gestinem(self)  # type: ignore[attr-defined]
        except Exception:
            pass

        def _center():
            try:
                self.update_idletasks()
                w = self.winfo_width()
                h = self.winfo_height()
                if w <= 1:
                    w = self.winfo_reqwidth()
                if h <= 1:
                    h = self.winfo_reqheight()
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
                self.geometry(f"+{x}+{y}")
            except Exception:
                pass

        self.after(0, _center)

    tk.Toplevel.__init__ = _patched_init
    tk.Toplevel._centrado_instalado = True  # type: ignore[attr-defined]


def aplicar_tema(root: tk.Tk) -> None:
    """
    Aplica un tema visual unificado a toda la app:
    colores suaves, tipografía Segoe UI y estilos de botones.
    """

    # Colores base
    COLOR_BG = "#f5f5f7"
    COLOR_SURFACE = "#ffffff"
    COLOR_PRIMARY = "#002C57"
    COLOR_PRIMARY_DARK = "#002C57"
    COLOR_BORDER = "#d0d0d0"
    COLOR_TEXT = "#222222"
    COLOR_MUTED = "#6c757d"

    # Tema ttk base
    style = ttk.Style(root)
    # Forzamos un tema que respete los colores configurados
    try:
        style.theme_use("clam")
    except tk.TclError:
        # Por si en algún sistema no existe "clam"
        style.theme_use(style.theme_names()[0])

    # Fondo general
    root.configure(bg=COLOR_BG)

    # ====== WIDGETS BÁSICOS ======
    style.configure(
        "TFrame",
        background=COLOR_BG,
    )

    style.configure(
        "Surface.TFrame",
        background=COLOR_SURFACE,
        relief="flat",
        borderwidth=1
    )

    style.configure(
        "TLabel",
        background=COLOR_BG,
        foreground=COLOR_TEXT,
        font=("Segoe UI", 10),
    )

    style.configure(
        "Header.TLabel",
        background=COLOR_BG,
        foreground=COLOR_TEXT,
        font=("Segoe UI", 16, "bold"),
    )

    style.configure(
        "SubHeader.TLabel",
        background=COLOR_BG,
        foreground=COLOR_MUTED,
        font=("Segoe UI", 10),
    )

    style.configure(
        "Section.TLabelframe",
        background=COLOR_SURFACE,
        bordercolor=COLOR_BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Section.TLabelframe.Label",
        background=COLOR_SURFACE,
        foreground=COLOR_TEXT,
        font=("Segoe UI", 10, "bold"),
    )

    style.configure(
        "Treeview",
        background=COLOR_SURFACE,
        fieldbackground=COLOR_SURFACE,
        foreground=COLOR_TEXT,
        rowheight=22,
        bordercolor=COLOR_BORDER,
        borderwidth=1,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Treeview.Heading",
        font=("Segoe UI", 9, "bold"),
    )

    # ====== BOTONES ======
    style.configure(
        "TButton",
        font=("Segoe UI", 10),
        padding=(10, 4),
    )

    style.configure(
        "Primary.TButton",
        font=("Segoe UI", 10, "bold"),
        padding=(12, 5),
        foreground="#ffffff",
        background=COLOR_PRIMARY,
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", COLOR_PRIMARY_DARK),
            ("pressed", COLOR_PRIMARY_DARK),
        ],
    )

    style.configure(
        "Secondary.TButton",
        font=("Segoe UI", 10),
        padding=(10, 4),
    )

    style.configure(
        "Danger.TButton",
        font=("Segoe UI", 10, "bold"),
        padding=(12, 5),
        foreground="#ffffff",
        background="#D64545",
        borderwidth=0,
    )
    style.map(
        "Danger.TButton",
        background=[
            ("active", "#bb3434"),
            ("pressed", "#a52d2d"),
        ],
        foreground=[
            ("active", "#ffffff"),
            ("pressed", "#ffffff"),
        ],
    )

    # ====== ENTRADAS ======
    style.configure(
        "TEntry",
        padding=3,
    )

    style.configure(
        "TCombobox",
        padding=3,
    )

    # Notebook (pestañas)
    style.configure(
        "TNotebook",
        background=COLOR_BG,
        tabposition="n",
    )
    style.configure(
        "TNotebook.Tab",
        padding=(10, 4),
        font=("Segoe UI", 10),
    )

    _instalar_marca_dialogos()
    _instalar_centrado_toplevels()

    style.configure("Login.TFrame", background="#edf2f7")
