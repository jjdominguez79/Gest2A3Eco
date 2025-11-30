# ui_tema.py
import tkinter as tk
from tkinter import ttk

def aplicar_tema(root: tk.Tk) -> None:
    """
    Aplica un tema visual unificado a toda la app:
    colores suaves, tipografía Segoe UI y estilos de botones.
    """

    # Colores base
    COLOR_BG = "#f5f5f7"
    COLOR_SURFACE = "#ffffff"
    COLOR_PRIMARY = "#0d6efd"
    COLOR_PRIMARY_DARK = "#0b5ed7"
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
