"""Vista de la pestana Cuotas Periodicas dentro del modulo Facturas Emitidas."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


PERIODICIDAD_LABELS = {
    "mensual": "Mensual",
    "bimestral": "Bimestral",
    "trimestral": "Trimestral",
    "semestral": "Semestral",
    "anual": "Anual",
}


class UICuotasTab(ttk.Frame):
    """Frame que contiene la pestana de cuotas periodicas.

    Comunica con el controller mediante llamadas directas.
    El controller debe estar asignado en self.controller antes de usar la vista.
    """

    def __init__(self, parent, gestor, codigo: str, ejercicio: int,
                 empresa_conf: dict, session=None):
        super().__init__(parent)
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._empresa_conf = empresa_conf
        self._session = session
        self.controller = None  # se asigna desde fuera
        self._build()

    # ── Construccion ─────────────────────────────────────────────────────────

    def _build(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(8, 0))

        can_write = getattr(
            getattr(self._gestor, "security", None),
            "can_write_company",
            lambda _c: True,
        )(self._codigo)

        self.btn_nueva = ttk.Button(top, text="Nueva cuota", style="Primary.TButton",
                                     command=self._nueva)
        self.btn_nueva.pack(side=tk.LEFT, padx=4)
        self.btn_editar = ttk.Button(top, text="Editar", command=self._editar)
        self.btn_editar.pack(side=tk.LEFT, padx=4)
        self.btn_duplicar = ttk.Button(top, text="Duplicar", command=self._duplicar)
        self.btn_duplicar.pack(side=tk.LEFT, padx=4)
        self.btn_toggle = ttk.Button(top, text="Activar/Desactivar", command=self._toggle)
        self.btn_toggle.pack(side=tk.LEFT, padx=4)
        self.btn_eliminar = ttk.Button(top, text="Eliminar", command=self._eliminar)
        self.btn_eliminar.pack(side=tk.LEFT, padx=4)
        ttk.Separator(top, orient="vertical").pack(side=tk.LEFT, fill="y", padx=6)
        self.btn_generar = ttk.Button(top, text="Generar pendientes",
                                       command=self._generar)
        self.btn_generar.pack(side=tk.LEFT, padx=4)

        if not can_write:
            for btn in (self.btn_nueva, self.btn_editar, self.btn_duplicar,
                        self.btn_toggle, self.btn_eliminar, self.btn_generar):
                btn.state(["disabled"])

        # ── Treeview principal ────────────────────────────────────────────────
        cols = ("nombre", "descripcion", "periodicidad", "inicio", "fin",
                "activa", "ultimo_periodo", "num_generadas")
        display = ("nombre", "descripcion", "periodicidad", "inicio", "fin",
                   "activa", "ultimo_periodo", "num_generadas")
        tree_frm = ttk.Frame(self)
        tree_frm.pack(fill="both", expand=True, padx=12, pady=8)

        self.tv = ttk.Treeview(tree_frm, columns=cols, displaycolumns=display,
                                show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frm, orient="vertical", command=self.tv.yview)
        hsb = ttk.Scrollbar(tree_frm, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        for col, head, w in [
            ("nombre",        "Cliente",          180),
            ("descripcion",   "Descripcion",      200),
            ("periodicidad",  "Periodicidad",       90),
            ("inicio",        "Inicio",             90),
            ("fin",           "Fin",                90),
            ("activa",        "Estado",             70),
            ("ultimo_periodo","Ultimo periodo",     110),
            ("num_generadas", "# Generadas",        90),
        ]:
            self.tv.heading(col, text=head,
                             command=lambda c=col: self._sort_by(c))
            self.tv.column(col, width=w, anchor="w" if w > 90 else "center")

        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frm.rowconfigure(0, weight=1)
        tree_frm.columnconfigure(0, weight=1)

        self.tv.bind("<<TreeviewSelect>>", self._on_select)
        self.tv.bind("<Double-1>", lambda _e: self._editar())

        self._sort_col = ""
        self._sort_rev = False

    # ── Metodos de la vista (llamados por el controller) ──────────────────────

    def set_cuotas(self, cuotas: list[dict]):
        for iid in self.tv.get_children():
            self.tv.delete(iid)
        for c in cuotas:
            activa_lbl = "Activa" if c.get("activa") else "Inactiva"
            per_lbl = PERIODICIDAD_LABELS.get(c.get("periodicidad", "mensual"),
                                              c.get("periodicidad", ""))
            self.tv.insert("", "end", iid=c["id"], values=(
                c.get("nombre") or c.get("nif") or "",
                c.get("descripcion") or "",
                per_lbl,
                c.get("fecha_inicio") or "",
                c.get("fecha_fin") or "",
                activa_lbl,
                c.get("_ultimo_periodo") or "",
                c.get("_num_generadas") or 0,
            ), tags=("inactiva",) if not c.get("activa") else ())
        self.tv.tag_configure("inactiva", foreground="#888")

    def get_selected_id(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def show_info(self, title: str, msg: str):
        messagebox.showinfo(title, msg, parent=self)

    def show_warning(self, title: str, msg: str):
        messagebox.showwarning(title, msg, parent=self)

    def ask_confirm(self, title: str, msg: str) -> bool:
        return messagebox.askyesno(title, msg, parent=self)

    def open_cuota_dialog(self, cuota: dict, series: list, terceros: list,
                          empresa_defaults: dict | None = None,
                          plantillas_word: list | None = None,
                          plantillas_emitidas: list | None = None):
        from views.ui_cuota_dialog import CuotaDialog
        dlg = CuotaDialog(self, cuota=cuota, series=series, terceros=terceros,
                          empresa_defaults=empresa_defaults,
                          plantillas_word=plantillas_word,
                          plantillas_emitidas=plantillas_emitidas)
        return dlg.result

    def open_generar_dialog(self, pendientes: list) -> dict | None:
        from views.ui_generar_cuotas_dialog import GenerarCuotasDialog
        dlg = GenerarCuotasDialog(self, pendientes=pendientes)
        return dlg.result

    # ── Handlers de botones ───────────────────────────────────────────────────

    def _nueva(self):
        if self.controller:
            self.controller.nueva_cuota()

    def _editar(self):
        if not self.controller:
            return
        cid = self.get_selected_id()
        if not cid:
            self.show_info("Cuotas", "Selecciona una cuota para editar.")
            return
        self.controller.editar_cuota(cid)

    def _duplicar(self):
        if not self.controller:
            return
        cid = self.get_selected_id()
        if not cid:
            self.show_info("Cuotas", "Selecciona una cuota para duplicar.")
            return
        self.controller.duplicar_cuota(cid)

    def _toggle(self):
        if not self.controller:
            return
        cid = self.get_selected_id()
        if not cid:
            self.show_info("Cuotas", "Selecciona una cuota.")
            return
        self.controller.toggle_activa(cid)

    def _eliminar(self):
        if not self.controller:
            return
        cid = self.get_selected_id()
        if not cid:
            self.show_info("Cuotas", "Selecciona una cuota para eliminar.")
            return
        self.controller.eliminar_cuota(cid)

    def _generar(self):
        if self.controller:
            self.controller.generar_pendientes()

    def _on_select(self, _e=None):
        pass  # Reservado para futuras acciones al seleccionar

    # ── Orden ─────────────────────────────────────────────────────────────────

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        cols = self.tv["columns"]
        idx = list(cols).index(col)
        data = [(self.tv.set(iid, col), iid) for iid in self.tv.get_children()]
        data.sort(key=lambda x: x[0].lower(), reverse=self._sort_rev)
        for order, (_, iid) in enumerate(data):
            self.tv.move(iid, "", order)
