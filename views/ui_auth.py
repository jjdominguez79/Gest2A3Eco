from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app_version import get_version_label

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = None
    ImageTk = None


APP_TITLE = "Gestinem ERP"
CONTACT_EMAIL = "jjdominguez@gestinem.es"
CONTACT_PHONE = "942 791 404"
COPYRIGHT = "Copyright 2026 Asesoria Gestinem S.L. Todos los derechos reservados."


def _center_window(win, parent=None):
    try:
        
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
    def __init__(
        self, parent, on_login, logo_path: str | None = None,
        on_microsoft_login=None,
    ):
        super().__init__(parent)
        self._on_login = on_login
        self._logo_path = str(logo_path or "").strip()
        self._on_microsoft_login = on_microsoft_login
        self._logo_tk_img = None
        self._microsoft_icon = None
        self._access_content = None
        self._notice_label = None
        self._notice_is_error = True
        self._current_access_mode = "microsoft"
        self.var_username = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_error = tk.StringVar()
        self._build()

    def _build(self):
        self.configure(style="Login.TFrame")
        shell = tk.Frame(self, bg="#ffffff", highlightbackground="#d7dee8", highlightthickness=1)
        # El acceso Microsoft anade una segunda accion y una explicacion. La
        # altura anterior recortaba esos controles en Windows con escalado de
        # texto/DPI, aunque el boton estuviera correctamente creado.
        shell.place(relx=0.5, rely=0.5, anchor="center", width=900, height=560)

        brand = tk.Frame(shell, bg="#002C57", width=390)
        brand.pack(side="left", fill="both")
        brand.pack_propagate(False)
        self._build_brand_panel(brand)

        access = tk.Frame(shell, bg="#ffffff", padx=64, pady=26)
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
        # Pack footer first so pack reserves space from the bottom before top elements fill.
        footer = tk.Frame(parent, bg="#ffffff")
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Label(
            footer, text=get_version_label(), bg="#ffffff", fg="#98a2b3", font=("Segoe UI", 8),
        ).pack()
        tk.Label(
            footer, text=COPYRIGHT, bg="#ffffff", fg="#98a2b3", font=("Segoe UI", 8),
        ).pack(pady=(3, 0))
        tk.Label(
            footer, text=f"{CONTACT_EMAIL}  |  Tel.: {CONTACT_PHONE}", bg="#ffffff", fg="#667085",
            font=("Segoe UI", 9),
        ).pack(pady=(3, 0))

        self._access_content = tk.Frame(parent, bg="#ffffff")
        self._access_content.pack(fill="both", expand=True)
        if self._on_microsoft_login is None:
            self._show_emergency_access()
        else:
            self._show_microsoft_access()

    def _clear_access_content(self):
        for child in self._access_content.winfo_children():
            child.destroy()
        self._notice_label = None

    def _title(self, text: str, subtitle: str, *, bottom_padding=26):
        tk.Label(
            self._access_content, text=text, bg="#ffffff", fg="#002C57",
            font=("Segoe UI", 23, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            self._access_content, text=subtitle, bg="#ffffff", fg="#667085",
            font=("Segoe UI", 10), anchor="w", justify="left", wraplength=380,
        ).pack(fill="x", pady=(7, bottom_padding))

    def _build_notice(self, *, top_padding=12):
        self._notice_label = tk.Label(
            self._access_content,
            textvariable=self.var_error,
            bg="#ffffff",
            fg="#b42318" if self._notice_is_error else "#0759af",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self._notice_label.pack(fill="x", pady=(top_padding, 0))

    def _create_microsoft_icon(self):
        icon = tk.PhotoImage(width=19, height=19)
        icon.put("#f25022", to=(0, 0, 9, 9))
        icon.put("#7fba00", to=(10, 0, 19, 9))
        icon.put("#00a4ef", to=(0, 10, 9, 19))
        icon.put("#ffb900", to=(10, 10, 19, 19))
        self._microsoft_icon = icon
        return icon

    def _show_microsoft_access(self):
        self._current_access_mode = "microsoft"
        self.var_error.set("")
        self._notice_is_error = True
        self._clear_access_content()
        self._title(
            "Bienvenido de nuevo",
            "Accede con la misma cuenta corporativa que utilizas en Outlook y en Gestinem.",
        )

        microsoft_button = tk.Button(
            self._access_content,
            text="Continuar con Microsoft",
            image=self._create_microsoft_icon(),
            compound="left",
            command=self._on_microsoft_login,
            bg="#ffffff",
            fg="#1f2937",
            activebackground="#f3f6fa",
            activeforeground="#111827",
            relief="solid",
            borderwidth=1,
            cursor="hand2",
            font=("Segoe UI", 11, "bold"),
            padx=18,
            pady=13,
        )
        microsoft_button.pack(fill="x")

        tk.Label(
            self._access_content,
            text="Inicio de sesión corporativo protegido por Microsoft Entra ID",
            bg="#ffffff",
            fg="#667085",
            font=("Segoe UI", 9),
            anchor="center",
        ).pack(fill="x", pady=(11, 0))

        separator = tk.Frame(self._access_content, bg="#ffffff")
        separator.pack(fill="x", pady=(34, 16))
        tk.Frame(separator, bg="#e4e7ec", height=1).pack(side="left", fill="x", expand=True)
        tk.Label(
            separator,
            text="  ACCESO EXCEPCIONAL  ",
            bg="#ffffff",
            fg="#98a2b3",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left")
        tk.Frame(separator, bg="#e4e7ec", height=1).pack(side="left", fill="x", expand=True)

        emergency_button = tk.Button(
            self._access_content,
            text="Usar la cuenta local de emergencia",
            command=self._show_emergency_access,
            bg="#ffffff",
            fg="#475467",
            activebackground="#ffffff",
            activeforeground="#002C57",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 9, "underline"),
            pady=4,
        )
        emergency_button.pack()
        tk.Label(
            self._access_content,
            text="Reservado para incidencias en las que Microsoft no esté disponible.",
            bg="#ffffff",
            fg="#98a2b3",
            font=("Segoe UI", 8),
            justify="center",
            wraplength=340,
        ).pack(pady=(5, 0))
        self._build_notice()
        microsoft_button.focus_set()

    def _show_emergency_access(self):
        self._current_access_mode = "emergency"
        self.var_error.set("")
        self._notice_is_error = True
        self._clear_access_content()
        self._title(
            "Acceso de emergencia",
            "Utiliza esta entrada solo si el inicio de sesión con Microsoft no está disponible.",
            bottom_padding=16,
        )

        warning = tk.Frame(
            self._access_content,
            bg="#fff8e7",
            highlightbackground="#f2cf7d",
            highlightthickness=1,
            padx=12,
            pady=9,
        )
        warning.pack(fill="x", pady=(0, 12))
        tk.Label(
            warning,
            text="Solo admite la cuenta local admin de emergencia.",
            bg="#fff8e7",
            fg="#7a4d00",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x")

        self._field(
            self._access_content, "Usuario de emergencia", self.var_username,
            show=None, bottom_padding=9,
        )
        entry_password = self._field(
            self._access_content, "Contraseña", self.var_password,
            show="*", bottom_padding=11,
        )

        tk.Button(
            self._access_content,
            text="Entrar con la cuenta de emergencia",
            command=self._submit,
            bg="#344054",
            fg="#ffffff",
            activebackground="#1d2939",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            pady=8,
        ).pack(fill="x")

        if self._on_microsoft_login is not None:
            tk.Button(
                self._access_content,
                text="Volver al acceso con Microsoft",
                command=self._show_microsoft_access,
                bg="#ffffff",
                fg="#0759af",
                activebackground="#ffffff",
                activeforeground="#002C57",
                relief="flat",
                borderwidth=0,
                cursor="hand2",
                font=("Segoe UI", 9, "underline"),
                pady=4,
            ).pack(pady=(5, 0))

        self._build_notice(top_padding=6)
        self._entry_user.bind("<Return>", lambda _e: entry_password.focus_set())
        entry_password.bind("<Return>", lambda _e: self._submit())
        self._entry_user.focus_set()

    def _field(self, parent, label, variable, show, *, bottom_padding=18):
        tk.Label(
            parent, text=label, bg="#ffffff", fg="#344054", font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 6))
        entry = ttk.Entry(parent, textvariable=variable, show=show, width=36, font=("Segoe UI", 11))
        entry.pack(fill="x", ipady=6, pady=(0, bottom_padding))
        if label in {"Usuario", "Usuario de emergencia"}:
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
        self._notice_is_error = True
        self.var_error.set(message)
        if self._notice_label is not None:
            self._notice_label.configure(fg="#b42318")

    def show_status(self, message: str):
        self._notice_is_error = False
        self.var_error.set(message)
        if self._notice_label is not None:
            self._notice_label.configure(fg="#0759af")


class ChangePasswordDialog(tk.Toplevel):
    def __init__(self, parent, title: str = "Cambiar contraseña", username: str = ""):
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

        ttk.Label(frm, text="Contraseña actual").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.var_current, show="*", width=32).pack(fill="x", pady=(4, 10))
        ttk.Label(frm, text="Nueva contraseña").pack(anchor="w")
        ttk.Entry(frm, textvariable=self.var_new, show="*", width=32).pack(fill="x", pady=(4, 10))
        ttk.Label(frm, text="Repetir contraseña").pack(anchor="w")
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
            messagebox.showerror(APP_TITLE, "La nueva contraseña no puede estar vacia.", parent=self)
            return
        if new_password != repeated:
            messagebox.showerror(APP_TITLE, "Las contraseñas no coinciden.", parent=self)
            return
        self.result = {"current_password": current, "new_password": new_password}
        self.destroy()
