from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


class PostgresConfigDialog(tk.Toplevel):
    """Configuracion inicial de la base central para cada puesto."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Conexion con la base de datos central")
        self.resizable(False, False)
        self.result = None

        self.var_host = tk.StringVar(value="192.168.0.19")
        self.var_port = tk.StringVar(value="5433")
        self.var_database = tk.StringVar(value="gest2a3eco")
        self.var_user = tk.StringVar(value="gest2a3eco")
        self.var_password = tk.StringVar()

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Configurar PostgreSQL",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(
            frame,
            text=(
                "Este puesto utilizara la base PostgreSQL central.\n"
                "Introduce la contraseña de la base de datos central."
            ),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))

        fields = (
            ("Servidor", self.var_host, False),
            ("Puerto", self.var_port, False),
            ("Base de datos", self.var_database, False),
            ("Usuario", self.var_user, False),
            ("Contraseña", self.var_password, True),
        )
        password_entry = None
        for row, (label, variable, secret) in enumerate(fields, start=2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            entry = ttk.Entry(frame, textvariable=variable, width=38, show="*" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if secret:
                password_entry = entry

        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(actions, text="Cancelar", command=self._cancel).pack(side="right")
        ttk.Button(actions, text="Guardar y conectar", command=self._ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda _event: self._ok())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() - self.winfo_width()) // 2)
        y = max(0, (self.winfo_screenheight() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
        if password_entry is not None:
            password_entry.focus_set()
        self.wait_window()

    def _ok(self):
        values = {
            "host": self.var_host.get().strip(),
            "port": self.var_port.get().strip(),
            "database": self.var_database.get().strip(),
            "user": self.var_user.get().strip(),
            "password": self.var_password.get(),
        }
        if not all(values.values()):
            messagebox.showerror(
                "Gest2A3Eco",
                "Debes cumplimentar todos los datos de conexion.",
                parent=self,
            )
            return
        try:
            port = int(values["port"])
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Gest2A3Eco", "El puerto no es valido.", parent=self)
            return
        values["port"] = port
        self.result = values
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
