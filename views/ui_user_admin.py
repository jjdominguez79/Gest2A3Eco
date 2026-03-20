from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from models.auth import CompanyPermission, UserRole


class UserAdminDialog(tk.Toplevel):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.title("Administracion de usuarios")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.controller = controller
        self.var_username = tk.StringVar()
        self.var_nombre = tk.StringVar()
        self.var_rol = tk.StringVar(value=UserRole.EMPLEADO.value)
        self.var_activo = tk.BooleanVar(value=True)
        self.var_password = tk.StringVar()
        self.var_force_password_change = tk.BooleanVar(value=False)
        self._current_user_id = None
        self._company_rows: list[tuple[str, tk.StringVar]] = []
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(root, text="Usuarios")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        user_bar = ttk.Frame(left)
        user_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(user_bar, text="Nuevo", style="Primary.TButton", command=lambda: self.controller.nuevo()).pack(side="left")
        ttk.Button(user_bar, text="Recargar", command=lambda: self.controller.refresh()).pack(side="left", padx=(8, 0))

        self.tv_users = ttk.Treeview(
            left,
            columns=("username", "nombre", "rol", "activo", "empresas"),
            show="headings",
            selectmode="browse",
        )
        for col, label, width in (
            ("username", "Usuario", 120),
            ("nombre", "Nombre", 180),
            ("rol", "Rol", 90),
            ("activo", "Activo", 70),
            ("empresas", "Empresas", 80),
        ):
            self.tv_users.heading(col, text=label)
            self.tv_users.column(col, width=width, anchor="w")
        self.tv_users.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.tv_users.bind("<<TreeviewSelect>>", lambda _e: self.controller.seleccionar_usuario())

        right = ttk.LabelFrame(root, text="Edicion")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        right.rowconfigure(6, weight=1)

        ttk.Label(right, text="Usuario").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        ttk.Entry(right, textvariable=self.var_username).grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 4))
        ttk.Label(right, text="Nombre").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(right, textvariable=self.var_nombre).grid(row=1, column=1, sticky="ew", padx=10, pady=4)
        ttk.Label(right, text="Rol").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        role_cb = ttk.Combobox(
            right,
            textvariable=self.var_rol,
            state="readonly",
            values=[role.value for role in UserRole],
        )
        role_cb.grid(row=2, column=1, sticky="w", padx=10, pady=4)
        role_cb.bind("<<ComboboxSelected>>", lambda _e: self._toggle_company_permissions())

        ttk.Checkbutton(right, text="Usuario activo", variable=self.var_activo).grid(row=3, column=1, sticky="w", padx=10, pady=4)

        password_frame = ttk.Frame(right)
        password_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        password_frame.columnconfigure(1, weight=1)
        ttk.Label(password_frame, text="Nueva contraseña").grid(row=0, column=0, sticky="w")
        ttk.Entry(password_frame, textvariable=self.var_password, show="*").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Checkbutton(
            password_frame,
            text="Forzar cambio en el siguiente acceso",
            variable=self.var_force_password_change,
        ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

        ttk.Label(right, text="Permisos por empresa").grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
        company_wrap = ttk.Frame(right)
        company_wrap.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        company_wrap.columnconfigure(0, weight=1)
        company_wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(company_wrap, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(company_wrap, orient="vertical", command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)

        self.company_frame = ttk.Frame(canvas)
        self._company_window = canvas.create_window((0, 0), window=self.company_frame, anchor="nw")
        self.company_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(self._company_window, width=e.width))

        actions = ttk.Frame(right)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(actions, text="Guardar usuario", style="Primary.TButton", command=lambda: self.controller.guardar()).pack(side="left")
        ttk.Button(actions, text="Cambiar contraseña", command=lambda: self.controller.cambiar_password()).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Cerrar", command=self.destroy).pack(side="right")

    def set_users(self, users: list[dict]):
        selected = self.get_selected_user_id()
        self.tv_users.delete(*self.tv_users.get_children())
        for row in users:
            iid = str(row.get("id"))
            self.tv_users.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("username", ""),
                    row.get("nombre", ""),
                    row.get("rol", ""),
                    "Si" if row.get("activo") else "No",
                    row.get("empresas_asignadas", 0),
                ),
            )
        if selected and self.tv_users.exists(selected):
            self.tv_users.selection_set(selected)

    def get_selected_user_id(self) -> int | None:
        sel = self.tv_users.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except Exception:
            return None

    def load_user(self, user: dict | None, company_rows: list[dict], assigned_permissions: dict[str, str]):
        self._current_user_id = user.get("id") if user else None
        self.var_username.set("" if not user else str(user.get("username") or ""))
        self.var_nombre.set("" if not user else str(user.get("nombre") or ""))
        self.var_rol.set(UserRole.EMPLEADO.value if not user else str(user.get("rol") or UserRole.EMPLEADO.value))
        self.var_activo.set(True if not user else bool(user.get("activo")))
        self.var_password.set("")
        self.var_force_password_change.set(False if not user else bool(user.get("must_change_password")))
        self._render_company_permissions(company_rows, assigned_permissions)
        self._toggle_company_permissions()

    def _render_company_permissions(self, companies: list[dict], assigned_permissions: dict[str, str]):
        for child in self.company_frame.winfo_children():
            child.destroy()
        self._company_rows = []
        ttk.Label(self.company_frame, text="Empresa", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 8))
        ttk.Label(self.company_frame, text="Permiso", style="SubHeader.TLabel").grid(row=0, column=1, sticky="w", pady=(0, 8))
        values = [perm.value for perm in CompanyPermission]
        for idx, company in enumerate(companies, start=1):
            codigo = str(company.get("codigo") or "")
            nombre = str(company.get("nombre") or "")
            text = f"{codigo} - {nombre}".strip(" -")
            ttk.Label(self.company_frame, text=text).grid(row=idx, column=0, sticky="w", padx=(0, 12), pady=4)
            var = tk.StringVar(value=str(assigned_permissions.get(codigo) or CompanyPermission.NONE.value))
            combo = ttk.Combobox(self.company_frame, textvariable=var, state="readonly", values=values, width=12)
            combo.grid(row=idx, column=1, sticky="w", pady=4)
            self._company_rows.append((codigo, var))

    def _toggle_company_permissions(self):
        is_admin = self.var_rol.get() == UserRole.ADMIN.value
        state = "disabled" if is_admin else "readonly"
        for _, var in self._company_rows:
            pass
        for child in self.company_frame.winfo_children():
            if isinstance(child, ttk.Combobox):
                child.configure(state=state)
                if is_admin:
                    child.set(CompanyPermission.NONE.value)

    def get_form_data(self) -> dict:
        permissions = {codigo: var.get() for codigo, var in self._company_rows}
        return {
            "id": self._current_user_id,
            "username": self.var_username.get().strip(),
            "nombre": self.var_nombre.get().strip(),
            "rol": self.var_rol.get().strip(),
            "activo": bool(self.var_activo.get()),
            "password": self.var_password.get(),
            "must_change_password": bool(self.var_force_password_change.get()),
            "company_permissions": permissions,
        }

    def ask_new_password(self) -> str | None:
        top = tk.Toplevel(self)
        top.title("Cambiar contraseña")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        var_password = tk.StringVar()
        var_repeat = tk.StringVar()
        var_force = tk.BooleanVar(value=False)

        frm = ttk.Frame(top, padding=14, style="Surface.TFrame")
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Nueva contraseña").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var_password, show="*", width=28).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frm, text="Repetir contraseña").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var_repeat, show="*", width=28).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(frm, text="Forzar cambio en el siguiente acceso", variable=var_force).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        result = {"password": None, "must_change_password": False}

        def _ok():
            if not var_password.get().strip():
                messagebox.showerror("Gest2A3Eco", "La contraseña no puede estar vacia.", parent=top)
                return
            if var_password.get() != var_repeat.get():
                messagebox.showerror("Gest2A3Eco", "Las contraseñas no coinciden.", parent=top)
                return
            result["password"] = var_password.get()
            result["must_change_password"] = bool(var_force.get())
            top.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=_ok).pack(side="left")
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side="left", padx=(8, 0))
        top.wait_window()
        if result["password"] is None:
            return None
        return result

    def show_info(self, message: str):
        messagebox.showinfo("Gest2A3Eco", message, parent=self)

    def show_error(self, message: str):
        messagebox.showerror("Gest2A3Eco", message, parent=self)
