"""Vista integrada del maestro global de terceros."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from controllers.terceros_global_controller import TercerosGlobalController


class UITercerosGlobales(tk.Frame):
    """Frame embebible que implementa la interfaz esperada por TercerosGlobalController."""

    def __init__(self, parent, gestor, session=None):
        super().__init__(parent, bg="#f1f5f9")
        self._gestor = gestor
        self._session = session
        self._terceros: list[dict] = []
        self._empresas: list[dict] = []
        self._build()
        self._controller = TercerosGlobalController(gestor, self)
        self._controller.refresh()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        header = tk.Frame(self, bg="#ffffff",
                          highlightbackground="#e2e8f0", highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text="Maestro de terceros",
                 bg="#ffffff", fg="#0f172a",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(14, 2))
        tk.Label(header,
                 text="Gestion global de proveedores, clientes, acreedores y deudores.",
                 bg="#ffffff", fg="#64748b",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 12))

        body = tk.Frame(self, bg="#f1f5f9")
        body.pack(fill="both", expand=True, padx=16, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left: lista de terceros
        left = tk.Frame(body, bg="#f1f5f9")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        # Barra de busqueda y acciones
        search_row = tk.Frame(left, bg="#f1f5f9")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._filter_terceros())
        ttk.Entry(search_row, textvariable=self.var_search, width=36).pack(
            side="left", padx=(0, 6))
        ttk.Button(search_row, text="Actualizar",
                   command=lambda: self._controller.refresh()).pack(side="left", padx=(0, 6))
        ttk.Button(search_row, text="Nuevo",
                   command=lambda: self._controller.nuevo()).pack(side="left", padx=(0, 4))
        ttk.Button(search_row, text="Editar",
                   command=lambda: self._controller.editar()).pack(side="left", padx=(0, 4))
        ttk.Button(search_row, text="Eliminar",
                   command=lambda: self._controller.eliminar()).pack(side="left")

        # Treeview
        tree_wrap = tk.Frame(left, bg="#f1f5f9")
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            tree_wrap,
            columns=("nif", "nombre", "pais", "email"),
            show="headings", height=20,
        )
        for col, txt, width, anchor in [
            ("nif",    "NIF/CIF",  130, "w"),
            ("nombre", "Nombre",   340, "w"),
            ("pais",   "Pais",      60, "center"),
            ("email",  "Email",    180, "w"),
        ]:
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor=anchor)
        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=vsb.set)
        self.tv.bind("<<TreeviewSelect>>",
                     lambda _: self._controller.load_empresas_asignadas())
        self.tv.bind("<Double-Button-1>", lambda _: self._controller.editar())

        # Right: panel de asignacion a empresa
        right = tk.Frame(body, bg="#ffffff",
                         highlightbackground="#e2e8f0", highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(right, text="Asignar a empresa",
                 bg="#ffffff", fg="#0f172a",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))

        self.lb_empresas = tk.Listbox(
            right, height=8, selectmode="single",
            bg="#ffffff", fg="#475569",
            font=("Segoe UI", 9),
            relief="flat", bd=0,
            selectbackground="#eff6ff",
            highlightthickness=0,
        )
        self.lb_empresas.pack(fill="x", padx=8, pady=(0, 6))

        ttk.Button(right, text="Asignar",
                   command=lambda: self._controller.asignar_a_empresa()).pack(
            anchor="w", padx=12, pady=(0, 10))

        tk.Frame(right, bg="#e2e8f0", height=1).pack(fill="x", padx=8)

        tk.Label(right, text="Empresas asignadas",
                 bg="#ffffff", fg="#0f172a",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        self.lb_asignadas = tk.Listbox(
            right, height=12, selectmode="single",
            bg="#ffffff", fg="#475569",
            font=("Segoe UI", 9),
            relief="flat", bd=0,
            highlightthickness=0,
        )
        self.lb_asignadas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ── Interfaz del controlador ──────────────────────────────────────────────

    def set_terceros(self, rows: list[dict]):
        self._terceros = rows
        self._filter_terceros()

    def set_empresas(self, rows: list[dict]):
        self._empresas = rows
        self.lb_empresas.delete(0, tk.END)
        for e in rows:
            self.lb_empresas.insert(
                tk.END, f"{e.get('codigo', '')}  {e.get('nombre', '')}"
            )

    def set_empresas_asignadas(self, rows: list[dict]):
        self.lb_asignadas.delete(0, tk.END)
        for e in rows:
            self.lb_asignadas.insert(
                tk.END, f"{e.get('codigo', '')}  {e.get('nombre', '')}"
            )

    def get_selected_tercero_id(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def get_selected_empresa(self):
        idx = self.lb_empresas.curselection()
        if not idx:
            return None, []
        return self._empresas[idx[0]].get("codigo"), []

    def select_tercero(self, tid: str):
        tid_str = str(tid)
        if tid_str in self.tv.get_children():
            self.tv.selection_set(tid_str)
            self.tv.see(tid_str)

    def open_tercero_ficha(self, ter: dict | None) -> dict | None:
        return _TerceroFichaDialog(self.winfo_toplevel(), ter).result

    def show_error(self, title: str, msg: str):
        messagebox.showerror(title, msg, parent=self.winfo_toplevel())

    def show_warning(self, title: str, msg: str):
        messagebox.showwarning(title, msg, parent=self.winfo_toplevel())

    def show_info(self, title: str, msg: str):
        messagebox.showinfo(title, msg, parent=self.winfo_toplevel())

    def ask_yes_no(self, title: str, msg: str) -> bool:
        return messagebox.askyesno(title, msg, parent=self.winfo_toplevel())

    # ── Filtrado ─────────────────────────────────────────────────────────────

    def _filter_terceros(self):
        q = self.var_search.get().strip().lower()
        self.tv.delete(*self.tv.get_children())
        for t in self._terceros:
            nif = str(t.get("nif") or "")
            nombre = str(t.get("nombre_legal") or t.get("nombre") or "")
            email = str(t.get("email") or "")
            if q and q not in nif.lower() and q not in nombre.lower() and q not in email.lower():
                continue
            pais = str(t.get("pais") or "ES")
            self.tv.insert(
                "", tk.END, iid=str(t["id"]),
                values=(nif, nombre, pais, email),
            )


# ── Dialog de ficha de tercero ────────────────────────────────────────────────

class _TerceroFichaDialog(tk.Toplevel):
    """Dialog modal simple para crear/editar datos de un tercero."""

    _FIELDS = [
        ("nif",       "NIF / CIF"),
        ("nombre",    "Nombre / Razon social"),
        ("direccion", "Direccion"),
        ("cp",        "Codigo postal"),
        ("poblacion", "Poblacion"),
        ("provincia", "Provincia"),
        ("telefono",  "Telefono"),
        ("email",     "Email"),
        ("contacto",  "Persona de contacto"),
    ]

    def __init__(self, parent, ter: dict | None):
        super().__init__(parent)
        self.title("Ficha de tercero" if ter else "Nuevo tercero")
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None
        self._vars: dict[str, tk.StringVar] = {}
        self._nif_extranjero_var = tk.BooleanVar()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        for i, (key, label) in enumerate(self._FIELDS):
            ttk.Label(frm, text=label + ":").grid(
                row=i, column=0, sticky="w", pady=3, padx=(0, 8))
            var = tk.StringVar(value=str(ter.get(key) or "") if ter else "")
            self._vars[key] = var
            ttk.Entry(frm, textvariable=var, width=38).grid(
                row=i, column=1, sticky="ew", pady=3)

        row_extra = len(self._FIELDS)
        ttk.Checkbutton(
            frm,
            text="NIF extranjero (omitir validacion espanola)",
            variable=self._nif_extranjero_var,
        ).grid(row=row_extra, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=row_extra + 1, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(btn_row, text="Guardar", command=self._save).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="left")

        frm.columnconfigure(1, weight=1)
        self.transient(parent)
        self.wait_window()

    def _save(self):
        self.result = {k: v.get().strip() for k, v in self._vars.items()}
        self.result["_nif_extranjero"] = self._nif_extranjero_var.get()
        self.destroy()
