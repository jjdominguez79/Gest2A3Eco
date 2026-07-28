from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app_version import APP_VERSION

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None


APP_TITLE = "Gestinem Suite"
CONTACT_EMAIL = "jjdominguez@gestinem.es"
CONTACT_PHONE = "942 791 404"
COPYRIGHT = "Copyright 2026 Asesoria Gestinem S.L. Todos los derechos reservados."


def _center_window(win, parent=None):
    try:
        win.update_idletasks()
        width = win.winfo_width()
        height = win.winfo_height()
        if parent is None:
            pos_x = (win.winfo_screenwidth() - width) // 2
            pos_y = (win.winfo_screenheight() - height) // 2
        else:
            parent.update_idletasks()
            pos_x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            pos_y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        win.geometry(f"+{max(pos_x, 0)}+{max(pos_y, 0)}")
    except Exception:
        pass


class UILogin(ttk.Frame):
    def __init__(self, parent, on_login, logo_path: str | None = None):
        super().__init__(parent)
        self._on_login = on_login
        self._logo_path = str(logo_path or "").strip()
        self._logo_tk_img = None
        self.var_username = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_error = tk.StringVar()
        self._build()

    def _build(self):
        self.configure(style="Login.TFrame")
        shell = tk.Frame(self, bg="#ffffff", highlightbackground="#d7dee8", highlightthickness=1)
        shell.place(relx=0.5, rely=0.5, anchor="center", width=900, height=500)

        brand = tk.Frame(shell, bg="#002C57", width=390)
        brand.pack(side="left", fill="both")
        brand.pack_propagate(False)
        self._build_brand_panel(brand)

        access = tk.Frame(shell, bg="#ffffff", padx=64, pady=58)
        access.pack(side="right", fill="both", expand=True)
        self._build_access_panel(access)

    def _build_brand_panel(self, parent):
        mark = self._load_logo_image(max_h=110)
        if mark is not None:
            tk.Label(parent, image=mark, bg="#002C57", borderwidth=0).pack(pady=(82, 28))
        else:
            tk.Label(parent, text="G", bg="#002C57", fg="#ffffff", font=("Segoe UI", 54, "bold")).pack(pady=(82, 28))

        tk.Label(
            parent, text=APP_TITLE, bg="#002C57", fg="#ffffff",
            font=("Segoe UI", 29, "bold"),
        ).pack()
        tk.Label(
            parent, text="Gestion integral para tu empresa", bg="#002C57", fg="#c4d9ee",
            font=("Segoe UI", 13),
        ).pack(pady=(6, 0))

    def _build_access_panel(self, parent):
        tk.Label(
            parent, text="Bienvenido de nuevo", bg="#ffffff", fg="#002C57",
            font=("Segoe UI", 23, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            parent, text="Accede a tu espacio de trabajo", bg="#ffffff", fg="#667085",
            font=("Segoe UI", 11), anchor="w",
        ).pack(fill="x", pady=(6, 34))

        self._field(parent, "Usuario", self.var_username, show=None)
        entry_password = self._field(parent, "Contrasena", self.var_password, show="*")

        tk.Label(
            parent, textvariable=self.var_error, bg="#ffffff", fg="#b42318",
            font=("Segoe UI", 9), anchor="w", wraplength=360,
        ).pack(fill="x", pady=(0, 12))
        tk.Button(
            parent, text="Iniciar sesion", command=self._submit, bg="#0759af", fg="#ffffff",
            activebackground="#002C57", activeforeground="#ffffff", relief="flat", borderwidth=0,
            cursor="hand2", font=("Segoe UI", 11, "bold"), pady=10,
        ).pack(fill="x")

        footer = tk.Frame(parent, bg="#ffffff")
        footer.pack(side="bottom", fill="x", pady=(58, 0))
        tk.Label(
            footer, text=f"{CONTACT_EMAIL}  |  Tel.: {CONTACT_PHONE}", bg="#ffffff", fg="#667085",
            font=("Segoe UI", 9),
        ).pack()
        tk.Label(
            footer, text=COPYRIGHT, bg="#ffffff", fg="#98a2b3", font=("Segoe UI", 8),
        ).pack(pady=(5, 0))
        tk.Label(
            footer, text=f"Version {APP_VERSION}", bg="#ffffff", fg="#98a2b3", font=("Segoe UI", 8),
        ).pack(pady=(5, 0))

        self._entry_user.bind("<Return>", lambda _e: entry_password.focus_set())
        entry_password.bind("<Return>", lambda _e: self._submit())
        self._entry_user.focus_set()

    def _field(self, parent, label, variable, show):
        tk.Label(
            parent, text=label, bg="#ffffff", fg="#344054", font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 6))
        entry = ttk.Entry(parent, textvariable=variable, show=show, width=36, font=("Segoe UI", 11))
        entry.pack(fill="x", ipady=6, pady=(0, 18))
        if label == "Usuario":
            self._entry_user = entry
        return entry

    def _load_logo_image(self, max_h: int):
        if not self._logo_path or Image is None or ImageTk is None:
            return None
        path = Path(self._logo_path)
        if not path.exists():
            return None
        try:
            pil_img = Image.open(path)
            ratio = min(1.0, max_h / float(max(1, pil_img.height)))
            size = (max(1, int(pil_img.width * ratio)), max(1, int(pil_img.height * ratio)))
            if size != pil_img.size:
                pil_img = pil_img.resize(size)
            self._logo_tk_img = ImageTk.PhotoImage(pil_img)
            return self._logo_tk_img
        except Exception:
            return None

    def _submit(self):
        self.var_error.set("")
        self._on_login(self.var_username.get(), self.var_password.get())

    def show_error(self, message: str):
        self.var_error.set(message)


class ChangePasswordDialog(tk.Toplevel):
    def __init__(self, parent, title: str = "Cambiar contrasena", username: str = ""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.var_current = tk.StringVar()
        self.var_new = tk.StringVar()
        self.var_repeat = tk.StringVar()

        frm = ttk.Frame(self, padding=16, style="Surface.TFrame")
        frm.pack(fill="both", expand=True)

        if username:
            ttk.Label(frm, text=f"Usuario: {username}", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 12))

        ttk.Label(frm, text="Contrasena actual").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.var_current, show="*", width=32).pack(fill="x", pady=(4, 10))
        ttk.Label(frm, text="Nueva contrasena").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.var_new, show="*", width=32).pack(fill="x", pady=(4, 10))
        ttk.Label(frm, text="Repetir contrasena").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.var_repeat, show="*", width=32).pack(fill="x", pady=(4, 12))

        actions = ttk.Frame(frm)
        actions.pack(fill="x")
        ttk.Button(actions, text="Guardar", style="Primary.TButton", command=self._ok).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left", padx=(8, 0))

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        _center_window(self, parent)
        self.focus_set()

    def _ok(self):
        current = self.var_current.get()
        new_password = self.var_new.get()
        repeated = self.var_repeat.get()
        if not new_password.strip():
            messagebox.showerror(APP_TITLE, "La nueva contrasena no puede estar vacia.", parent=self)
            return
        if new_password != repeated:
            messagebox.showerror(APP_TITLE, "Las contrasenas no coinciden.", parent=self)
            return
        self.result = {"current_password": current, "new_password": new_password}
        self.destroy()
