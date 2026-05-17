# ui_tema.py
import tkinter as tk
from tkinter import ttk

def _instalar_centrado_toplevels() -> None:
    """Parcha tk.Toplevel para que todos los dialogos se centren en pantalla automaticamente."""
    if getattr(tk.Toplevel, "_centrado_instalado", False):
        return
    _orig_init = tk.Toplevel.__init__

    def _patched_init(self, master=None, **kw):
        _orig_init(self, master, **kw)

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

    _instalar_centrado_toplevels()
