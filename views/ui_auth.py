from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


class UILogin(ttk.Frame):
    def __init__(self, parent, on_login):
        super().__init__(parent)
        self._on_login = on_login
        self.var_username = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_error = tk.StringVar()
        self._build()

    def _build(self):
        wrapper = ttk.Frame(self)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        card = ttk.Frame(wrapper, padding=24, style="Surface.TFrame")
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="Gest2A3Eco", style="Header.TLabel").pack(anchor="center", pady=(0, 6))
        ttk.Label(card, text="Acceso seguro", style="SubHeader.TLabel").pack(anchor="center", pady=(0, 18))

        ttk.Label(card, text="Usuario").pack(anchor="w")
        entry_user = ttk.Entry(card, textvariable=self.var_username, width=32)
        entry_user.pack(fill="x", pady=(4, 12))

        ttk.Label(card, text="Contraseña").pack(anchor="w")
        entry_password = ttk.Entry(card, textvariable=self.var_password, show="*", width=32)
        entry_password.pack(fill="x", pady=(4, 8))

        lbl_error = ttk.Label(card, textvariable=self.var_error, foreground="#B42318")
        lbl_error.pack(anchor="w", pady=(0, 12))

        ttk.Button(card, text="Iniciar sesion", style="Primary.TButton", command=self._submit).pack(fill="x")

        entry_user.bind("<Return>", lambda _e: entry_password.focus_set())
        entry_password.bind("<Return>", lambda _e: self._submit())
        entry_user.focus_set()

    def _submit(self):
        self.var_error.set("")
        self._on_login(self.var_username.get(), self.var_password.get())

    def show_error(self, message: str):
        self.var_error.set(message)


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
        self.focus_set()

    def _ok(self):
        current = self.var_current.get()
        new_password = self.var_new.get()
        repeated = self.var_repeat.get()
        if not new_password.strip():
            messagebox.showerror("Gest2A3Eco", "La nueva contraseña no puede estar vacia.", parent=self)
            return
        if new_password != repeated:
            messagebox.showerror("Gest2A3Eco", "Las contraseñas no coinciden.", parent=self)
            return
        self.result = {
            "current_password": current,
            "new_password": new_password,
        }
        self.destroy()
