"""Gestion administrativa de etiquetas internas de clientes."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk


COLORES_PREDEFINIDOS = (
    "#D32F2F", "#F57C00", "#FBC02D", "#388E3C",
    "#1976D2", "#6750A4", "#C2185B", "#455A64",
)


def seleccionar_etiquetas(
    parent, gestor, seleccionadas: set[str] | None = None, *,
    titulo: str = "Asignar etiquetas",
) -> set[str] | None:
    etiquetas = gestor.listar_etiquetas_clientes()
    top = tk.Toplevel(parent)
    top.title(titulo)
    top.transient(parent)
    top.grab_set()
    top.resizable(False, True)
    result: dict[str, set[str] | None] = {"value": None}
    vars_by_id = {
        str(item["id"]): tk.BooleanVar(
            value=str(item["id"]) in (seleccionadas or set()),
        )
        for item in etiquetas
    }
    frame = ttk.Frame(top, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text="Selecciona una o varias etiquetas internas.",
    ).pack(anchor="w", pady=(0, 10))
    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="both", expand=True)
    if not etiquetas:
        ttk.Label(
            list_frame,
            text="Todavia no hay etiquetas. Crealas desde Administracion.",
        ).pack(anchor="w", pady=12)
    for item in etiquetas:
        row = ttk.Frame(list_frame)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="  ", bg=str(item.get("color") or "#6750A4"),
            relief="solid", borderwidth=1,
        ).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(
            row, text=str(item.get("nombre") or ""),
            variable=vars_by_id[str(item["id"])],
        ).pack(side="left", fill="x", expand=True)

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(14, 0))

    def accept():
        result["value"] = {
            tag_id for tag_id, var in vars_by_id.items() if var.get()
        }
        top.destroy()

    ttk.Button(buttons, text="Cancelar", command=top.destroy).pack(side="right")
    ttk.Button(
        buttons, text="Aceptar", style="Primary.TButton", command=accept,
    ).pack(side="right", padx=(0, 8))
    top.wait_window()
    return result["value"]


class UIEtiquetasClientes(ttk.Frame):
    def __init__(self, parent, gestor, session, on_back):
        super().__init__(parent)
        self._gestor = gestor
        self._session = session
        self._on_back = on_back
        self._rows: dict[str, dict] = {}
        self._build()
        self.refresh()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=16, pady=12)
        ttk.Label(
            bar, text="Gestion de etiquetas de clientes",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")
        ttk.Button(bar, text="Volver", command=self._on_back).pack(side="right")

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(actions, text="Nueva etiqueta", command=self._new).pack(side="left")
        ttk.Button(actions, text="Editar", command=self._edit).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Activar/desactivar", command=self._toggle_active,
        ).pack(side="left")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="right")

        wrapper = ttk.Frame(self)
        wrapper.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            wrapper, columns=("color", "nombre", "clientes", "estado"),
            show="headings", selectmode="browse",
        )
        for key, label, width in (
            ("color", "Color", 90), ("nombre", "Etiqueta", 320),
            ("clientes", "Clientes", 100), ("estado", "Estado", 100),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center" if key != "nombre" else "w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Double-1>", lambda _event: self._edit())

    def _user(self) -> str:
        return str(getattr(getattr(self._session, "user", None), "nombre", "") or "")

    def refresh(self):
        tags = self._gestor.listar_etiquetas_clientes(incluir_inactivas=True)
        counts: dict[str, int] = {}
        for row in self._gestor.listar_asignaciones_etiquetas_clientes():
            tag_id = str(row.get("etiqueta_id") or "")
            counts[tag_id] = counts.get(tag_id, 0) + 1
        self._rows = {str(row["id"]): row for row in tags}
        self.tree.delete(*self.tree.get_children())
        for row in tags:
            tag_id = str(row["id"])
            self.tree.insert("", "end", iid=tag_id, values=(
                str(row.get("color") or ""), str(row.get("nombre") or ""),
                counts.get(tag_id, 0), "Activa" if row.get("activo") else "Inactiva",
            ))

    def _selected(self) -> dict | None:
        selection = self.tree.selection()
        return self._rows.get(selection[0]) if selection else None

    def _dialog(self, current: dict | None = None) -> dict | None:
        top = tk.Toplevel(self.winfo_toplevel())
        top.title("Editar etiqueta" if current else "Nueva etiqueta")
        top.transient(self.winfo_toplevel())
        top.grab_set()
        top.resizable(False, False)
        name = tk.StringVar(value=str((current or {}).get("nombre") or ""))
        color = tk.StringVar(value=str((current or {}).get("color") or "#6750A4"))
        result: dict[str, dict | None] = {"value": None}
        frame = ttk.Frame(top, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Nombre").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=name, width=36).grid(row=0, column=1, pady=5)
        ttk.Label(frame, text="Color").grid(row=1, column=0, sticky="w", pady=5)
        color_row = ttk.Frame(frame)
        color_row.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Entry(color_row, textvariable=color, width=14).pack(side="left")

        def choose_color():
            chosen = colorchooser.askcolor(color=color.get(), parent=top)[1]
            if chosen:
                color.set(chosen.upper())

        ttk.Button(color_row, text="Elegir...", command=choose_color).pack(side="left", padx=6)
        palette = ttk.Frame(frame)
        palette.grid(row=2, column=0, columnspan=2, pady=8)
        for candidate in COLORES_PREDEFINIDOS:
            tk.Button(
                palette, bg=candidate, width=2, relief="flat",
                command=lambda value=candidate: color.set(value),
            ).pack(side="left", padx=3)

        def accept():
            result["value"] = {
                "id": (current or {}).get("id"), "nombre": name.get(),
                "color": color.get(),
                "activo": bool((current or {}).get("activo", True)),
            }
            top.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancelar", command=top.destroy).pack(side="left")
        ttk.Button(buttons, text="Guardar", command=accept).pack(side="left", padx=(8, 0))
        top.wait_window()
        return result["value"]

    def _save(self, current: dict | None):
        data = self._dialog(current)
        if data is None:
            return
        try:
            self._gestor.guardar_etiqueta_cliente(data, self._user())
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Etiquetas", str(exc), parent=self.winfo_toplevel())

    def _new(self):
        self._save(None)

    def _edit(self):
        current = self._selected()
        if current:
            self._save(current)

    def _toggle_active(self):
        current = self._selected()
        if not current:
            return
        if not current.get("activo"):
            try:
                self._gestor.guardar_etiqueta_cliente(
                    {**current, "activo": True}, self._user(),
                )
                self.refresh()
            except Exception as exc:
                messagebox.showerror(
                    "Etiquetas", str(exc), parent=self.winfo_toplevel(),
                )
            return
        if not messagebox.askyesno(
            "Etiquetas", f"Desactivar la etiqueta '{current.get('nombre')}'?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._gestor.desactivar_etiqueta_cliente(str(current["id"]), self._user())
        self.refresh()
