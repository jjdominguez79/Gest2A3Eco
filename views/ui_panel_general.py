from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class UIPanelGeneral(ttk.Frame):
    def __init__(
        self,
        parent,
        empresa_service,
        session,
        on_open_dashboard,
    ):
        super().__init__(parent)
        self._empresa_service = empresa_service
        self._session = session
        self._on_open_dashboard = on_open_dashboard
        self._empresas = []
        self.var_buscar = tk.StringVar()
        self.var_ver_bajas = tk.BooleanVar(value=False)
        self._build()
        self.refresh()

    def _build(self):
        title = ttk.Frame(self)
        title.pack(fill="x", padx=12, pady=(8, 2))
        ttk.Label(title, text="Panel general", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            title,
            text="Buscar empresa por nombre, NIF/CIF o codigo A3 y acceder al modulo correspondiente.",
        ).pack(anchor="w", pady=(2, 0))

        filtros = ttk.Frame(self)
        filtros.pack(fill="x", padx=12, pady=8)
        ttk.Label(filtros, text="Buscar").pack(side=tk.LEFT)
        ent = ttk.Entry(filtros, textvariable=self.var_buscar, width=42)
        ent.pack(side=tk.LEFT, padx=6, fill="x", expand=True)
        ttk.Checkbutton(
            filtros,
            text="Ver bajas",
            variable=self.var_ver_bajas,
            command=self.refresh,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(filtros, text="Actualizar", style="Primary.TButton", command=self.refresh).pack(side=tk.LEFT, padx=6)
        ttk.Button(filtros, text="Abrir empresa", style="Primary.TButton", command=self.open_selected).pack(side=tk.LEFT, padx=6)
        self.var_buscar.trace_add("write", lambda *_: self.refresh())

        info = ttk.Frame(self)
        info.pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_resumen = ttk.Label(info, text="")
        self.lbl_resumen.pack(anchor="w")

        tree_wrap = ttk.Frame(self)
        tree_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            tree_wrap,
            columns=("codigo", "nombre", "cif", "ultimo_ejercicio", "digitos", "permiso", "estado"),
            show="headings",
            height=16,
        )
        headers = (
            ("codigo", "Codigo A3", 110, "w"),
            ("nombre", "Empresa", 320, "w"),
            ("cif", "NIF/CIF", 120, "w"),
            ("ultimo_ejercicio", "Ult. ejercicio", 110, "center"),
            ("digitos", "Digitos", 80, "center"),
            ("permiso", "Acceso", 100, "center"),
            ("estado", "Configuracion", 120, "center"),
        )
        for col, text, width, anchor in headers:
            self.tv.heading(col, text=text)
            self.tv.column(col, width=width, anchor=anchor)
        self.tv.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tv.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=yscroll.set)
        self.tv.bind("<Double-1>", lambda _e: self.open_selected())

    def refresh(self):
        query = self.var_buscar.get()
        include_inactive = bool(self.var_ver_bajas.get())
        self._empresas = self._empresa_service.listar_empresas_panel(query, include_inactive)
        self.tv.delete(*self.tv.get_children())
        for item in self._empresas:
            iid = f"{item.get('codigo')}::{item.get('ejercicio')}"
            self.tv.insert(
                "",
                "end",
                iid=iid,
                values=(
                    item.get("codigo", ""),
                    item.get("nombre", ""),
                    item.get("cif", ""),
                    item.get("ultimo_ejercicio", ""),
                    item.get("digitos_plan", 8),
                    item.get("permiso", ""),
                    item.get("estado_configuracion", ""),
                ),
            )
        self.lbl_resumen.configure(text=f"Empresas accesibles: {len(self._empresas)}")
        children = self.tv.get_children()
        if children:
            self.tv.selection_set(children[0])
            self.tv.focus(children[0])

    def open_selected(self):
        selected = self.get_selected_company()
        if not selected:
            return
        self._on_open_dashboard(selected["codigo"], selected["ejercicio"])

    def get_selected_company(self):
        sel = self.tv.selection()
        if not sel:
            return None
        iid = str(sel[0])
        for item in self._empresas:
            if iid == f"{item.get('codigo')}::{item.get('ejercicio')}":
                return item
        return None
