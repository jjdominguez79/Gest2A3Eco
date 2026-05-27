"""Vista integrada del maestro de subcuentas contables de empresa."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.maestro_contable_empresa_service import (
    TIPOS_SUBCUENTA,
    MaestroContableEmpresaService,
    clasificar_tipo_subcuenta,
)
from services.terceros_empresa_fiscal_service import (
    CLASES_INTRACOMUNITARIA,
    CLIENTE_TIPOS_IVA,
    DEDUCCION_LABELS,
    DEDUCCION_LABELS_INV,
    PROVEEDOR_TIPOS_IVA,
    TIPO_IVA_TOOLTIPS,
    build_cliente_factura_defaults,
    get_proveedor_deduction_mode,
    validate_tercero_empresa_rel,
)
from utils.validaciones import (
    inferir_pais_desde_identificacion,
    normalizar_codigo_pais,
    normalizar_nif_cif,
    validar_nif_o_nif_iva_intracomunitario,
)
from views.ui_facturas_emitidas import TerceroFicha


def _read_excel_autodetect(path: str):
    """Lee un Excel detectando automaticamente la fila de cabecera.

    Soporta el formato de exportacion A3ECO (5 filas de metadatos antes de
    las cabeceras reales) y cualquier Excel con cabecera en la primera fila.
    """
    import unicodedata
    import pandas as pd

    def _norm(s: str) -> str:
        nfkd = unicodedata.normalize("NFKD", str(s))
        return nfkd.encode("ascii", "ignore").decode("ascii").lower().strip().replace(".", "")

    df = pd.read_excel(path, dtype=str)
    if any(_norm(c) in ("cuenta", "subcuenta") for c in df.columns):
        return df

    # Busca la fila de cabecera en las primeras 10 filas
    peek = pd.read_excel(path, header=None, nrows=10, dtype=str)
    for i, row in peek.iterrows():
        vals = [v for v in row if str(v).strip().lower() not in ("nan", "none", "")]
        if any(_norm(v) in ("cuenta", "subcuenta") for v in vals):
            return pd.read_excel(path, header=i, dtype=str)

    return df


class UIMaestroCuentas(tk.Frame):
    """Frame embebible para gestionar el maestro_subcuentas_empresa de una empresa."""

    def __init__(
        self, parent, gestor, codigo_empresa: str, ejercicio: int,
        nombre: str = "", session=None,
    ):
        super().__init__(parent, bg="#f1f5f9")
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio
        self._nombre = nombre
        self._session = session
        self._svc = MaestroContableEmpresaService()
        self._rows: list[dict] = []
        self._rels_by_tercero: dict[str, dict] = {}
        self._build()
        self.refresh()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        header = tk.Frame(self, bg="#ffffff",
                          highlightbackground="#e2e8f0", highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text="Maestro de cuentas",
                 bg="#ffffff", fg="#0f172a",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(14, 2))
        tk.Label(
            header,
            text=f"Subcuentas contables de {self._nombre or self._codigo}.",
            bg="#ffffff", fg="#64748b",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # Barra de filtros y acciones
        bar = tk.Frame(self, bg="#f1f5f9")
        bar.pack(fill="x", padx=16, pady=(8, 4))

        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._filter())
        ttk.Entry(bar, textvariable=self.var_search, width=28).pack(side="left", padx=(0, 6))

        self.var_tipo = tk.StringVar(value="todos")
        cb = ttk.Combobox(bar, textvariable=self.var_tipo,
                          values=["todos"] + list(TIPOS_SUBCUENTA),
                          state="readonly", width=16)
        cb.pack(side="left", padx=(0, 6))
        cb.bind("<<ComboboxSelected>>", lambda _: self._filter())

        self.var_solo_pendientes = tk.BooleanVar()
        ttk.Checkbutton(
            bar, text="Solo pendientes A3",
            variable=self.var_solo_pendientes,
            command=self._filter,
        ).pack(side="left", padx=(0, 10))

        ttk.Button(bar, text="Actualizar", command=self.refresh).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Configurar subcuenta", command=self._configurar_subcuenta_empresa).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Nueva subcuenta", command=self._nueva).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Eliminar subcuenta", command=self._eliminar).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Importar Excel", command=self._importar_excel).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Marcar alta A3", command=self._marcar_alta_a3).pack(side="left")

        # Treeview
        tree_wrap = tk.Frame(self, bg="#f1f5f9")
        tree_wrap.pack(fill="both", expand=True, padx=16, pady=6)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            tree_wrap,
            columns=("subcuenta", "nombre", "tipo", "nif", "cta_ingreso", "cta_gasto", "iva_ventas", "iva_compras", "ded_iva", "pendiente_a3"),
            show="headings", height=22,
        )
        for col, txt, width, anchor in [
            ("subcuenta",    "Subcuenta",   110, "w"),
            ("nombre",       "Nombre",      230, "w"),
            ("tipo",         "Tipo",        110, "center"),
            ("nif",          "NIF",         120, "w"),
            ("cta_ingreso",  "Cta ingreso", 100, "w"),
            ("cta_gasto",    "Cta gasto",   100, "w"),
            ("iva_ventas",   "IVA ventas",  150, "w"),
            ("iva_compras",  "IVA compras", 160, "w"),
            ("ded_iva",      "Deduccion IVA", 120, "w"),
            ("pendiente_a3", "Pend. A3",     80, "center"),
        ]:
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor=anchor)
        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=vsb.set)
        self.tv.bind("<Double-Button-1>", lambda _: self._on_open_selected())

        self.lbl_status = tk.Label(self, text="", bg="#f1f5f9", fg="#64748b",
                                   font=("Segoe UI", 8))
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 6))

    # ── Datos ─────────────────────────────────────────────────────────────────

    def refresh(self):
        self._rows = self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None)
        self._rels_by_tercero = {}
        try:
            for rel in self._gestor.listar_terceros_empresa(self._codigo, self._ejercicio):
                tid = str(rel.get("tercero_id") or "").strip()
                if tid:
                    self._rels_by_tercero[tid] = validate_tercero_empresa_rel(rel)
        except Exception:
            self._rels_by_tercero = {}
        self._filter()

    def _filter(self):
        q = self.var_search.get().strip().lower()
        tipo_fil = self.var_tipo.get()
        solo_pend = self.var_solo_pendientes.get()
        self.tv.delete(*self.tv.get_children())
        count = 0
        for r in self._rows:
            subcuenta = str(r.get("subcuenta") or "")
            nombre = str(r.get("nombre_subcuenta") or "")
            nif = str(r.get("nif_snapshot") or "")
            tipo = str(r.get("tipo_subcuenta") or "")
            tercero_id = str(r.get("tercero_id") or "").strip()
            rel = self._rels_by_tercero.get(tercero_id) or {}
            if q and q not in subcuenta.lower() and q not in nombre.lower() and q not in nif.lower():
                continue
            if tipo_fil != "todos" and tipo != tipo_fil:
                continue
            if solo_pend and not r.get("pendiente_alta_a3"):
                continue
            pend = "Si" if r.get("pendiente_alta_a3") else "No"
            iva_ventas = rel.get("cliente_tipo_operacion_iva", "") if tercero_id else ""
            iva_compras = rel.get("proveedor_tipo_operacion_iva", "") if tercero_id else ""
            cta_ingreso = rel.get("subcuenta_ingreso", "") if tercero_id else ""
            cta_gasto = rel.get("subcuenta_gasto", "") if tercero_id else ""
            ded_iva = self._deduccion_label(rel) if tercero_id else ""
            self.tv.insert(
                "", tk.END, iid=str(r["id"]),
                values=(subcuenta, nombre, tipo, nif, cta_ingreso, cta_gasto, iva_ventas, iva_compras, ded_iva, pend),
            )
            count += 1
        self.lbl_status.configure(
            text=f"{count} subcuentas mostradas  |  {len(self._rows)} total"
        )

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _nueva(self):
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)
        dlg = _SubcuentaDialog(
            self.winfo_toplevel(), None,
            gestor=self._gestor, svc=self._svc,
            codigo_empresa=self._codigo, digitos_plan=ndig,
        )
        if dlg.result:
            try:
                self._svc.crear_subcuenta_empresa(self._gestor, {
                    **dlg.result,
                    "codigo_empresa": self._codigo,
                    "creado_en_gest2a3eco": 1,
                })
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self.winfo_toplevel())

    def _on_open_selected(self):
        sel = self.tv.selection()
        if not sel:
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return
        if self._permite_configuracion_fiscal(rec):
            self._configurar_subcuenta_empresa()
            return
        self._editar()

    def _configurar_subcuenta_empresa(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una subcuenta asociada a un tercero.", parent=self.winfo_toplevel())
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return
        if not self._permite_configuracion_fiscal(rec):
            messagebox.showinfo(
                "Gest2A3Eco",
                "La configuracion fiscal debe hacerse desde la subcuenta del tercero (430/440 para clientes, 400/410 para proveedores).",
                parent=self.winfo_toplevel(),
            )
            return
        tercero = self._resolver_tercero_para_subcuenta(rec)
        if not tercero:
            tercero = self._crear_tercero_global_desde_subcuenta(rec)
            if not tercero:
                return
        tercero_id = str(tercero.get("id") or "").strip()
        self._asegurar_relacion_empresa_tercero_desde_subcuenta(tercero_id, rec)
        rel = validate_tercero_empresa_rel(self._gestor.get_tercero_empresa(self._codigo, tercero_id, self._ejercicio) or {})
        dlg = _RelacionTerceroEmpresaDialog(self.winfo_toplevel(), self._gestor, self._codigo, tercero, rel, rec)
        if dlg.saved:
            self.refresh()

    def _deduccion_label(self, rel: dict) -> str:
        if not rel:
            return ""
        mode = get_proveedor_deduction_mode(rel)
        if mode == "no":
            return "No"
        if mode == "parcial":
            try:
                pct = float(rel.get("proveedor_porcentaje_deduccion_iva", 0) or 0)
                pct_txt = str(int(pct)) if pct == int(pct) else str(pct)
            except Exception:
                pct_txt = str(rel.get("proveedor_porcentaje_deduccion_iva") or "")
            return f"Parcial {pct_txt}%"
        return "Si 100%"

    def _resolver_tercero_para_subcuenta(self, rec: dict) -> dict | None:
        tercero_id = str(rec.get("tercero_id") or "").strip()
        terceros = list(self._gestor.listar_terceros() or [])
        if tercero_id:
            tercero = next((t for t in terceros if str(t.get("id")) == tercero_id), None)
            if tercero:
                return tercero
        nif = normalizar_nif_cif(rec.get("nif_snapshot"))
        if nif:
            tercero = next((t for t in terceros if normalizar_nif_cif(t.get("nif")) == nif), None)
            if tercero:
                return tercero
        nombre = str(rec.get("nombre_subcuenta") or "").strip().lower()
        if nombre:
            tercero = next(
                (
                    t for t in terceros
                    if str(t.get("nombre_legal") or t.get("nombre") or "").strip().lower() == nombre
                ),
                None,
            )
            if tercero:
                return tercero
        return None

    def _permite_configuracion_fiscal(self, rec: dict) -> bool:
        return str(rec.get("tipo_subcuenta") or "") in {"cliente", "deudor", "proveedor", "acreedor"}

    def _crear_tercero_global_desde_subcuenta(self, rec: dict) -> dict | None:
        if not messagebox.askyesno(
            "Gest2A3Eco",
            "La subcuenta no esta vinculada a ningun tercero global.\n\nQuieres darlo de alta ahora en la tabla global de terceros?",
            parent=self.winfo_toplevel(),
        ):
            return None
        tercero_base = {
            "nif": str(rec.get("nif_snapshot") or "").strip(),
            "nombre": str(rec.get("nombre_subcuenta") or "").strip(),
            "nombre_legal": str(rec.get("nombre_subcuenta") or "").strip(),
            "pais": inferir_pais_desde_identificacion(rec.get("nif_snapshot")) or "",
        }
        dlg = TerceroFicha(self.winfo_toplevel(), tercero_base)
        payload = dlg.result
        if not payload:
            return None
        nif_extranjero = bool(payload.pop("_nif_extranjero", False))
        nif = str(payload.get("nif") or "").strip().upper() if nif_extranjero else normalizar_nif_cif(payload.get("nif"))
        if nif and not nif_extranjero and not validar_nif_o_nif_iva_intracomunitario(nif):
            messagebox.showerror("Gest2A3Eco", "NIF/CIF/NIE o NIF-IVA intracomunitario invalido.", parent=self.winfo_toplevel())
            return None
        existente = None
        if nif:
            for tercero in self._gestor.listar_terceros():
                if normalizar_nif_cif(tercero.get("nif")) == nif:
                    existente = tercero
                    break
        tercero_payload = dict(payload)
        tercero_payload["nif"] = nif
        tercero_payload["pais"] = normalizar_codigo_pais(tercero_payload.get("pais")) or inferir_pais_desde_identificacion(nif)
        tercero_payload["tipo_identificacion"] = {
            "vat": "vat",
            "foreign": "foreign",
            "nacional": "nif",
        }.get(payload.get("_tipo_identificacion_selector"))
        tercero_id = str(existente.get("id")) if existente else self._gestor.upsert_tercero(tercero_payload)
        return next((t for t in self._gestor.listar_terceros() if str(t.get("id")) == str(tercero_id)), None)

    def _asegurar_relacion_empresa_tercero_desde_subcuenta(self, tercero_id: str, rec: dict):
        rel_actual = self._gestor.get_tercero_empresa(self._codigo, tercero_id, self._ejercicio) or {}
        payload = dict(rel_actual)
        payload.update(
            {
                "tercero_id": tercero_id,
                "codigo_empresa": self._codigo,
                "ejercicio": 0,
            }
        )
        tipo = str(rec.get("tipo_subcuenta") or "")
        subcuenta = str(rec.get("subcuenta") or "").strip()
        if tipo == "cliente" and not str(payload.get("subcuenta_cliente") or "").strip():
            payload["subcuenta_cliente"] = subcuenta
        elif tipo in ("proveedor", "acreedor") and not str(payload.get("subcuenta_proveedor") or "").strip():
            payload["subcuenta_proveedor"] = subcuenta
        elif tipo == "ingreso" and not str(payload.get("subcuenta_ingreso") or "").strip():
            payload["subcuenta_ingreso"] = subcuenta
        elif tipo == "gasto" and not str(payload.get("subcuenta_gasto") or "").strip():
            payload["subcuenta_gasto"] = subcuenta
        self._gestor.upsert_tercero_empresa(payload)
        if not str(rec.get("tercero_id") or "").strip():
            self._gestor.upsert_maestro_subcuenta(
                {
                    "id": rec.get("id"),
                    "codigo_empresa": self._codigo,
                    "subcuenta": subcuenta,
                    "tercero_id": tercero_id,
                    "nombre_subcuenta": rec.get("nombre_subcuenta"),
                    "tipo_subcuenta": rec.get("tipo_subcuenta"),
                    "nif_snapshot": rec.get("nif_snapshot"),
                    "activo": rec.get("activo", 1),
                    "origen": rec.get("origen"),
                    "creado_en_gest2a3eco": rec.get("creado_en_gest2a3eco", 0),
                    "pendiente_alta_a3": rec.get("pendiente_alta_a3", 0),
                    "observaciones": rec.get("observaciones"),
                }
            )

    def _editar(self):
        sel = self.tv.selection()
        if not sel:
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)
        dlg = _SubcuentaDialog(
            self.winfo_toplevel(), rec,
            gestor=self._gestor, svc=self._svc,
            codigo_empresa=self._codigo, digitos_plan=ndig,
        )
        if dlg.result:
            try:
                self._svc.crear_subcuenta_empresa(self._gestor, {
                    **dlg.result,
                    "codigo_empresa": self._codigo,
                    "creado_en_gest2a3eco": rec.get("creado_en_gest2a3eco", 0),
                    "pendiente_alta_a3": rec.get("pendiente_alta_a3", 0),
                })
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self.winfo_toplevel())

    def _marcar_alta_a3(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una subcuenta.", parent=self.winfo_toplevel())
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return
        if not messagebox.askyesno(
            "Confirmar",
            f"Marcar subcuenta {rec.get('subcuenta')} como dada de alta en A3?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._svc.marcar_subcuenta_alta_a3_realizada(self._gestor, rec["id"])
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self.winfo_toplevel())

    def _eliminar(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una subcuenta.", parent=self.winfo_toplevel())
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return
        subcuenta = str(rec.get("subcuenta") or "").strip()
        if not messagebox.askyesno(
            "Confirmar",
            f"Eliminar la subcuenta {subcuenta}?\n\nEsta accion no se puede deshacer.",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._svc.eliminar_subcuenta_empresa(self._gestor, int(rec["id"]))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())

    def _importar_excel(self):
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Seleccionar fichero Excel o CSV",
            filetypes=[("Excel / CSV", "*.xlsx *.xls *.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            import pandas as pd
            df = pd.read_csv(path, dtype=str) if path.endswith(".csv") else _read_excel_autodetect(path)
            resultado = self._svc.importar_subcuentas_desde_dataframe(
                self._gestor, self._codigo, df
            )
            msg = (
                f"Importadas: {resultado['importadas']}\n"
                f"Actualizadas: {resultado['actualizadas']}\n"
                f"Errores: {resultado['errores']}"
            )
            if resultado["detalles_error"]:
                msg += "\n\nErrores:\n" + "\n".join(resultado["detalles_error"][:10])
            messagebox.showinfo("Importacion completada", msg, parent=self.winfo_toplevel())
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Error de importacion", str(exc), parent=self.winfo_toplevel())


# ── Dialog de subcuenta ────────────────────────────────────────────────────────

class _SubcuentaDialog(tk.Toplevel):
    """Dialog modal para crear o editar una subcuenta del maestro contable."""

    def __init__(self, parent, rec: dict | None, *, gestor, svc, codigo_empresa, digitos_plan):
        super().__init__(parent)
        self.title("Nueva subcuenta" if rec is None else "Editar subcuenta")
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None
        self._svc = svc
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ndig = digitos_plan
        self._terceros_cache = list(self._gestor.listar_terceros() or [])
        self._coincidencias_tercero: list[dict] = []

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        # Subcuenta
        ttk.Label(frm, text="Subcuenta:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_subcuenta = tk.StringVar(value=str(rec.get("subcuenta") or "") if rec else "")
        sub_row = ttk.Frame(frm)
        sub_row.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Entry(sub_row, textvariable=self.var_subcuenta, width=20).pack(side="left", padx=(0, 6))
        ttk.Button(sub_row, text="Sugerir", command=self._sugerir).pack(side="left")

        # Tipo
        ttk.Label(frm, text="Tipo:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_tipo = tk.StringVar(value=str(rec.get("tipo_subcuenta") or "") if rec else "")
        ttk.Combobox(frm, textvariable=self.var_tipo,
                     values=list(TIPOS_SUBCUENTA), state="readonly", width=20).grid(
            row=1, column=1, sticky="w", pady=4)
        self.var_subcuenta.trace_add("write", self._auto_tipo)

        # Nombre
        ttk.Label(frm, text="Nombre:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_nombre = tk.StringVar(value=str(rec.get("nombre_subcuenta") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_nombre, width=38).grid(row=2, column=1, sticky="ew", pady=4)
        self.var_nombre.trace_add("write", lambda *_: self._sync_tercero_match())

        # NIF
        ttk.Label(frm, text="NIF:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_nif = tk.StringVar(value=str(rec.get("nif_snapshot") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_nif, width=22).grid(row=3, column=1, sticky="w", pady=4)
        self.var_nif.trace_add("write", lambda *_: self._sync_tercero_match())

        # Tercero ID
        ttk.Label(frm, text="Tercero ID:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_tercero = tk.StringVar(value=str(rec.get("tercero_id") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_tercero, width=22).grid(row=4, column=1, sticky="w", pady=4)

        self.lbl_tercero_match = ttk.Label(frm, text="", foreground="#64748b")
        self.lbl_tercero_match.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 4))

        self.lb_terceros = tk.Listbox(
            frm,
            height=4,
            exportselection=False,
            bg="#ffffff",
            fg="#334155",
            font=("Segoe UI", 9),
        )
        self.lb_terceros.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.lb_terceros.bind("<Double-Button-1>", lambda _e: self._usar_tercero_seleccionado())

        tercero_btns = ttk.Frame(frm)
        tercero_btns.grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Button(tercero_btns, text="Buscar tercero", command=self._sync_tercero_match).pack(side="left", padx=(0, 6))
        ttk.Button(tercero_btns, text="Usar tercero seleccionado", command=self._usar_tercero_seleccionado).pack(side="left", padx=(0, 6))
        ttk.Button(tercero_btns, text="Dar de alta tercero", command=self._alta_tercero).pack(side="left")

        # Observaciones
        ttk.Label(frm, text="Observaciones:").grid(row=8, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_obs = tk.StringVar(value=str(rec.get("observaciones") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_obs, width=38).grid(row=8, column=1, sticky="ew", pady=4)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=9, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(btn_row, text="Guardar", command=self._save).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="left")

        frm.columnconfigure(1, weight=1)
        self.transient(parent)
        self._sync_tercero_match()
        self.wait_window()

    def _auto_tipo(self, *_):
        sub = self.var_subcuenta.get().strip()
        if sub and not self.var_tipo.get():
            tipo = clasificar_tipo_subcuenta(sub)
            if tipo != "otra":
                self.var_tipo.set(tipo)

    def _sugerir(self):
        tipo = self.var_tipo.get() or "proveedor"
        try:
            sub = self._svc.proponer_siguiente_subcuenta(
                self._gestor, self._codigo, tipo, digitos_plan=self._ndig
            )
            self.var_subcuenta.set(sub)
        except Exception:
            pass

    def _buscar_tercero_existente(self) -> dict | None:
        tercero_id = self.var_tercero.get().strip()
        if tercero_id:
            return next((t for t in self._terceros_cache if str(t.get("id")) == tercero_id), None)
        nif = normalizar_nif_cif(self.var_nif.get())
        if nif:
            tercero = next(
                (t for t in self._terceros_cache if normalizar_nif_cif(t.get("nif")) == nif),
                None,
            )
            if tercero:
                return tercero
        nombre = self.var_nombre.get().strip().lower()
        if nombre:
            return next(
                (
                    t for t in self._terceros_cache
                    if str(t.get("nombre_legal") or t.get("nombre") or "").strip().lower() == nombre
                ),
                None,
            )
        return None

    def _buscar_posibles_terceros(self) -> list[dict]:
        nif = normalizar_nif_cif(self.var_nif.get())
        nombre = self.var_nombre.get().strip().lower()
        if not nif and not nombre:
            return []
        matches = []
        for tercero in self._terceros_cache:
            t_nif = normalizar_nif_cif(tercero.get("nif"))
            t_nombre = str(tercero.get("nombre_legal") or tercero.get("nombre") or "").strip()
            t_nombre_l = t_nombre.lower()
            if nif and t_nif == nif:
                matches.append(tercero)
                continue
            if nombre and (nombre in t_nombre_l or t_nombre_l in nombre):
                matches.append(tercero)
        seen = set()
        out = []
        for tercero in matches:
            tid = str(tercero.get("id") or "")
            if tid in seen:
                continue
            seen.add(tid)
            out.append(tercero)
        return out[:20]

    def _refresh_terceros_list(self):
        self._coincidencias_tercero = self._buscar_posibles_terceros()
        self.lb_terceros.delete(0, tk.END)
        for tercero in self._coincidencias_tercero:
            nombre = str(tercero.get("nombre_legal") or tercero.get("nombre") or "").strip()
            nif = str(tercero.get("nif") or "").strip()
            self.lb_terceros.insert(tk.END, f"{nombre} ({nif})")

    def _aplicar_tercero(self, tercero: dict):
        self.var_tercero.set(str(tercero.get("id") or ""))
        self.var_nombre.set(str(tercero.get("nombre_legal") or tercero.get("nombre") or "").strip())
        self.var_nif.set(str(tercero.get("nif") or "").strip())
        self._sync_tercero_match()

    def _usar_tercero_seleccionado(self):
        idx = self.lb_terceros.curselection()
        if not idx:
            tercero = self._buscar_tercero_existente()
            if tercero:
                self._aplicar_tercero(tercero)
            return
        self._aplicar_tercero(self._coincidencias_tercero[idx[0]])

    def _sync_tercero_match(self):
        self._refresh_terceros_list()
        tercero = self._buscar_tercero_existente()
        if tercero:
            self.var_tercero.set(str(tercero.get("id") or ""))
            nombre = str(tercero.get("nombre_legal") or tercero.get("nombre") or "").strip()
            nif = str(tercero.get("nif") or "").strip()
            self.lbl_tercero_match.configure(text=f"Tercero existente: {nombre} ({nif})")
            return tercero
        if self.var_tercero.get().strip():
            self.var_tercero.set("")
        texto = "No existe en el maestro de terceros."
        if self._coincidencias_tercero:
            texto = f"{len(self._coincidencias_tercero)} posible(s) tercero(s) encontrado(s). Selecciona uno para copiarlo."
        if self.var_nombre.get().strip() or self.var_nif.get().strip():
            texto += " Puedes darlo de alta."
        self.lbl_tercero_match.configure(text=texto)
        return None

    def _alta_tercero(self):
        tercero = self._buscar_tercero_existente()
        if tercero:
            self.var_tercero.set(str(tercero.get("id") or ""))
            self._sync_tercero_match()
            messagebox.showinfo("Gest2A3Eco", "Ese tercero ya existe en el maestro.", parent=self)
            return
        tercero_base = {
            "nif": self.var_nif.get().strip(),
            "nombre": self.var_nombre.get().strip(),
            "nombre_legal": self.var_nombre.get().strip(),
            "pais": inferir_pais_desde_identificacion(self.var_nif.get().strip()) or "",
        }
        dlg = TerceroFicha(self, tercero_base)
        payload = dlg.result
        if not payload:
            return
        nif_extranjero = bool(payload.pop("_nif_extranjero", False))
        nif = str(payload.get("nif") or "").strip().upper() if nif_extranjero else normalizar_nif_cif(payload.get("nif"))
        if nif and not nif_extranjero and not validar_nif_o_nif_iva_intracomunitario(nif):
            messagebox.showerror("Gest2A3Eco", "NIF/CIF/NIE o NIF-IVA intracomunitario invalido.", parent=self)
            return
        existente = None
        if nif:
            existente = next(
                (t for t in self._terceros_cache if normalizar_nif_cif(t.get("nif")) == nif),
                None,
            )
        tercero_payload = dict(payload)
        tercero_payload["nif"] = nif
        tercero_payload["pais"] = normalizar_codigo_pais(tercero_payload.get("pais")) or inferir_pais_desde_identificacion(nif)
        tercero_payload["tipo_identificacion"] = {
            "vat": "vat",
            "foreign": "foreign",
            "nacional": "nif",
        }.get(payload.get("_tipo_identificacion_selector"))
        tercero_id = str(existente.get("id")) if existente else str(self._gestor.upsert_tercero(tercero_payload))
        self._terceros_cache = list(self._gestor.listar_terceros() or [])
        tercero = next((t for t in self._terceros_cache if str(t.get("id")) == tercero_id), None)
        if tercero:
            self.var_tercero.set(tercero_id)
            self.var_nombre.set(str(tercero.get("nombre_legal") or tercero.get("nombre") or "").strip())
            self.var_nif.set(str(tercero.get("nif") or "").strip())
        self._sync_tercero_match()

    def _save(self):
        sub = self.var_subcuenta.get().strip()
        if not sub:
            messagebox.showwarning("Gest2A3Eco", "La subcuenta es obligatoria.", parent=self)
            return
        self._sync_tercero_match()
        self.result = {
            "subcuenta":        sub,
            "tipo_subcuenta":   self.var_tipo.get() or None,
            "nombre_subcuenta": self.var_nombre.get().strip(),
            "nif":              self.var_nif.get().strip(),
            "tercero_id":       self.var_tercero.get().strip() or None,
            "observaciones":    self.var_obs.get().strip() or None,
        }
        self.destroy()


class _RelacionTerceroEmpresaDialog(tk.Toplevel):
    def __init__(self, parent, gestor, codigo_empresa: str, tercero: dict, rel: dict, rec: dict):
        super().__init__(parent)
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._tercero = tercero
        self._rel = validate_tercero_empresa_rel(rel)
        self._rec = dict(rec or {})
        self._tipo = str(self._rec.get("tipo_subcuenta") or "")
        self._side = "cliente" if self._tipo in {"cliente", "deudor"} else "proveedor"
        self._svc = MaestroContableEmpresaService()
        empresa = self._gestor.get_empresa(self._codigo, 0) or {}
        self._ndig = int(empresa.get("digitos_plan") or 8)
        self._catalogo_ingresos = self._load_account_catalog("ingreso")
        self._catalogo_gastos = self._load_account_catalog("gasto")
        self.saved = False

        self.title("Configuracion fiscal de subcuenta")
        self.resizable(False, False)
        self.grab_set()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        titulo = "Cliente / ventas" if self._side == "cliente" else "Proveedor / compras"
        ttk.Label(
            frm,
            text=f"{titulo}: {self._rec.get('subcuenta') or ''}",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frm,
            text=f"{tercero.get('nombre_legal') or tercero.get('nombre') or ''}  ({tercero.get('nif') or ''})",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        self.vars = {
            "subcuenta_cliente": tk.StringVar(value=str(self._rel.get("subcuenta_cliente") or "")),
            "subcuenta_ingreso": tk.StringVar(value=str(self._rel.get("subcuenta_ingreso") or "")),
            "cliente_tipo_operacion_iva": tk.StringVar(value=str(self._rel.get("cliente_tipo_operacion_iva") or CLIENTE_TIPOS_IVA[0])),
            "cliente_intracomunitaria_clase": tk.StringVar(value=str(self._rel.get("cliente_intracomunitaria_clase") or "")),
            "subcuenta_proveedor": tk.StringVar(value=str(self._rel.get("subcuenta_proveedor") or "")),
            "subcuenta_gasto": tk.StringVar(value=str(self._rel.get("subcuenta_gasto") or "")),
            "proveedor_tipo_operacion_iva": tk.StringVar(value=str(self._rel.get("proveedor_tipo_operacion_iva") or PROVEEDOR_TIPOS_IVA[0])),
            "proveedor_intracomunitaria_clase": tk.StringVar(value=str(self._rel.get("proveedor_intracomunitaria_clase") or "")),
            "proveedor_ded_mode": tk.StringVar(value=DEDUCCION_LABELS[get_proveedor_deduction_mode(self._rel)]),
            "proveedor_porcentaje_deduccion_iva": tk.StringVar(value=self._format_pct(self._rel.get("proveedor_porcentaje_deduccion_iva", 100))),
        }

        if self._side == "cliente":
            self.vars["subcuenta_cliente"].set(str(self._rec.get("subcuenta") or "").strip())
            self._build_cliente(frm, row=2)
        else:
            self.vars["subcuenta_proveedor"].set(str(self._rec.get("subcuenta") or "").strip())
            self._build_proveedor(frm, row=2)

        btns = ttk.Frame(frm)
        btns.grid(row=20, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Guardar", command=self._save).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="left")

        frm.columnconfigure(1, weight=1)
        self.transient(parent)
        self.wait_window()

    def _build_cliente(self, frm, row: int):
        box = ttk.LabelFrame(frm, text="Configuracion cliente", padding=10)
        box.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Label(box, text="Subcuenta cliente").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(box, textvariable=self.vars["subcuenta_cliente"], width=22, state="readonly").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(box, text="Subcuenta ingreso").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self.cb_sub_ingreso = ttk.Combobox(box, textvariable=self.vars["subcuenta_ingreso"], width=32)
        self.cb_sub_ingreso.grid(row=1, column=1, sticky="w", pady=4)
        self.cb_sub_ingreso.configure(postcommand=lambda: self._filter_account_values("ingreso"))
        self.cb_sub_ingreso.bind("<KeyRelease>", lambda _e: self._filter_account_values("ingreso"))
        self.cb_sub_ingreso.bind("<<ComboboxSelected>>", lambda _e: self._normalize_account_selection("ingreso"))
        ttk.Button(box, text="Alta", width=6, command=lambda: self._create_related_account("ingreso")).grid(row=1, column=2, sticky="w", padx=(6, 0), pady=4)
        ttk.Label(box, text="Tipo operacion IVA ventas").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(box, textvariable=self.vars["cliente_tipo_operacion_iva"], values=list(CLIENTE_TIPOS_IVA), state="readonly", width=28).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(box, text="Intracomunitaria").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self.cb_cli_intracom = ttk.Combobox(box, textvariable=self.vars["cliente_intracomunitaria_clase"], values=list(CLASES_INTRACOMUNITARIA), state="readonly", width=18)
        self.cb_cli_intracom.grid(row=3, column=1, sticky="w", pady=4)
        self.lbl_hint = ttk.Label(box, text="", foreground="#64748b", font=("Segoe UI", 8))
        self.lbl_hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.vars["cliente_tipo_operacion_iva"].trace_add("write", lambda *_: self._sync_cliente_state())
        self.vars["cliente_intracomunitaria_clase"].trace_add("write", lambda *_: self._sync_cliente_state())
        self.cb_sub_ingreso["values"] = self._matching_account_values("ingreso", "")
        self._filter_account_values("ingreso")
        self._sync_cliente_state()

    def _build_proveedor(self, frm, row: int):
        box = ttk.LabelFrame(frm, text="Configuracion proveedor", padding=10)
        box.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Label(box, text="Subcuenta proveedor").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(box, textvariable=self.vars["subcuenta_proveedor"], width=22, state="readonly").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(box, text="Subcuenta gasto").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self.cb_sub_gasto = ttk.Combobox(box, textvariable=self.vars["subcuenta_gasto"], width=32)
        self.cb_sub_gasto.grid(row=1, column=1, sticky="w", pady=4)
        self.cb_sub_gasto.configure(postcommand=lambda: self._filter_account_values("gasto"))
        self.cb_sub_gasto.bind("<KeyRelease>", lambda _e: self._filter_account_values("gasto"))
        self.cb_sub_gasto.bind("<<ComboboxSelected>>", lambda _e: self._normalize_account_selection("gasto"))
        ttk.Button(box, text="Alta", width=6, command=lambda: self._create_related_account("gasto")).grid(row=1, column=2, sticky="w", padx=(6, 0), pady=4)
        ttk.Label(box, text="Tipo operacion IVA compras").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(box, textvariable=self.vars["proveedor_tipo_operacion_iva"], values=list(PROVEEDOR_TIPOS_IVA), state="readonly", width=28).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(box, text="Intracomunitaria").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self.cb_prov_intracom = ttk.Combobox(box, textvariable=self.vars["proveedor_intracomunitaria_clase"], values=list(CLASES_INTRACOMUNITARIA), state="readonly", width=18)
        self.cb_prov_intracom.grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(box, text="IVA deducible").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self.cb_ded = ttk.Combobox(box, textvariable=self.vars["proveedor_ded_mode"], values=list(DEDUCCION_LABELS.values()), state="readonly", width=12)
        self.cb_ded.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(box, text="% deduccion IVA").grid(row=5, column=0, sticky="w", pady=4, padx=(0, 8))
        self.entry_pct = ttk.Entry(box, textvariable=self.vars["proveedor_porcentaje_deduccion_iva"], width=12)
        self.entry_pct.grid(row=5, column=1, sticky="w", pady=4)
        self.lbl_hint = ttk.Label(box, text="", foreground="#64748b", font=("Segoe UI", 8))
        self.lbl_hint.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.vars["proveedor_ded_mode"].trace_add("write", lambda *_: self._sync_proveedor_state())
        self.vars["proveedor_tipo_operacion_iva"].trace_add("write", lambda *_: self._sync_proveedor_state())
        self.vars["proveedor_intracomunitaria_clase"].trace_add("write", lambda *_: self._sync_proveedor_state())
        self.cb_sub_gasto["values"] = self._matching_account_values("gasto", "")
        self._filter_account_values("gasto")
        self._sync_proveedor_state()

    def _format_pct(self, value) -> str:
        try:
            pct = float(value)
            return str(int(pct)) if pct == int(pct) else str(pct)
        except Exception:
            return "100"

    def _load_account_catalog(self, tipo: str) -> list[dict]:
        return [
            row for row in (self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None) or [])
            if int(row.get("activo", 1) or 0) == 1
            if str(row.get("tipo_subcuenta") or "") == tipo
        ]

    def _account_label(self, row: dict) -> str:
        sub = str(row.get("subcuenta") or "").strip()
        nombre = str(row.get("nombre_subcuenta") or "").strip()
        return f"{sub} - {nombre}" if nombre else sub

    def _matching_account_values(self, tipo: str, typed: str) -> list[str]:
        catalogo = self._catalogo_ingresos if tipo == "ingreso" else self._catalogo_gastos
        texto = str(typed or "").strip().lower()
        values = []
        for row in catalogo:
            label = self._account_label(row)
            if not texto or texto in label.lower() or texto in str(row.get("subcuenta") or "").lower():
                values.append(label)
        return values[:50]

    def _filter_account_values(self, tipo: str):
        cb = self.cb_sub_ingreso if tipo == "ingreso" else self.cb_sub_gasto
        var = self.vars["subcuenta_ingreso"] if tipo == "ingreso" else self.vars["subcuenta_gasto"]
        cb["values"] = self._matching_account_values(tipo, var.get())

    def _extract_account_code(self, value: str) -> str:
        txt = str(value or "").strip()
        if " - " in txt:
            return txt.split(" - ", 1)[0].strip()
        return txt

    def _normalize_account_selection(self, tipo: str):
        var = self.vars["subcuenta_ingreso"] if tipo == "ingreso" else self.vars["subcuenta_gasto"]
        var.set(self._extract_account_code(var.get()))

    def _create_related_account(self, tipo: str):
        var = self.vars["subcuenta_ingreso"] if tipo == "ingreso" else self.vars["subcuenta_gasto"]
        actual = self._extract_account_code(var.get())
        rec = {
            "subcuenta": actual,
            "tipo_subcuenta": tipo,
            "nombre_subcuenta": str(self._tercero.get("nombre_legal") or self._tercero.get("nombre") or "").strip(),
            "nif_snapshot": str(self._tercero.get("nif") or "").strip(),
            "tercero_id": str(self._tercero.get("id") or "").strip(),
        }
        dlg = _SubcuentaDialog(
            self,
            rec,
            gestor=self._gestor,
            svc=self._svc,
            codigo_empresa=self._codigo,
            digitos_plan=self._ndig,
        )
        if not dlg.result:
            return
        try:
            creada = self._svc.crear_subcuenta_empresa(
                self._gestor,
                {
                    **dlg.result,
                    "codigo_empresa": self._codigo,
                    "creado_en_gest2a3eco": 1,
                },
            )
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            return
        nueva = {
            "subcuenta": creada.get("subcuenta"),
            "nombre_subcuenta": creada.get("nombre_subcuenta"),
            "tipo_subcuenta": tipo,
        }
        catalogo = self._catalogo_ingresos if tipo == "ingreso" else self._catalogo_gastos
        if not any(str(r.get("subcuenta")) == str(nueva.get("subcuenta")) for r in catalogo):
            catalogo.append(nueva)
            catalogo.sort(key=lambda r: str(r.get("subcuenta") or ""))
        var.set(str(creada.get("subcuenta") or ""))
        self._filter_account_values(tipo)

    def _ensure_related_account_exists(self, tipo: str) -> str:
        var = self.vars["subcuenta_ingreso"] if tipo == "ingreso" else self.vars["subcuenta_gasto"]
        code = self._extract_account_code(var.get())
        if not code:
            return ""
        existente = self._gestor.get_maestro_subcuenta_por_subcuenta(self._codigo, code)
        if existente:
            return code
        if not messagebox.askyesno(
            "Gest2A3Eco",
            f"La subcuenta {code} no existe en el Maestro.\n\nQuieres darla de alta ahora?",
            parent=self,
        ):
            raise ValueError(f"La subcuenta {code} no existe en el Maestro.")
        self._create_related_account(tipo)
        code = self._extract_account_code(var.get())
        existente = self._gestor.get_maestro_subcuenta_por_subcuenta(self._codigo, code)
        if not existente:
            raise ValueError(f"No se pudo crear la subcuenta {code}.")
        return code

    def _sync_cliente_state(self):
        is_intracom = self.vars["cliente_tipo_operacion_iva"].get() == "INTRACOMUNITARIA"
        if not is_intracom:
            self.vars["cliente_intracomunitaria_clase"].set("")
            self.cb_cli_intracom.configure(state="disabled")
        else:
            self.cb_cli_intracom.configure(state="readonly")
        defaults = build_cliente_factura_defaults(
            {
                "cliente_tipo_operacion_iva": self.vars["cliente_tipo_operacion_iva"].get(),
                "cliente_intracomunitaria_clase": self.vars["cliente_intracomunitaria_clase"].get(),
            }
        )
        self.lbl_hint.configure(
            text=f"{TIPO_IVA_TOOLTIPS.get(self.vars['cliente_tipo_operacion_iva'].get(), 'Configuracion fiscal del cliente.')}  Suenlace: tipo {defaults.get('tipo_operacion', '01')} / modelo {defaults.get('modelo_fiscal') or 'sin modelo'}."
        )

    def _sync_proveedor_state(self):
        is_intracom = self.vars["proveedor_tipo_operacion_iva"].get() == "INTRACOMUNITARIA"
        if not is_intracom:
            self.vars["proveedor_intracomunitaria_clase"].set("")
            self.cb_prov_intracom.configure(state="disabled")
        else:
            self.cb_prov_intracom.configure(state="readonly")
        mode = DEDUCCION_LABELS_INV.get(self.vars["proveedor_ded_mode"].get(), "total")
        if mode == "no":
            self.vars["proveedor_porcentaje_deduccion_iva"].set("0")
            self.entry_pct.configure(state="disabled")
        elif mode == "total":
            self.vars["proveedor_porcentaje_deduccion_iva"].set("100")
            self.entry_pct.configure(state="disabled")
        else:
            self.entry_pct.configure(state="normal")
        self.lbl_hint.configure(text=TIPO_IVA_TOOLTIPS.get(self.vars["proveedor_tipo_operacion_iva"].get(), "Configuracion fiscal del proveedor."))

    def _save(self):
        payload = {
            "tercero_id": self._tercero.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": 0,
            "subcuenta_cliente": self._rel.get("subcuenta_cliente", ""),
            "subcuenta_proveedor": self._rel.get("subcuenta_proveedor", ""),
            "subcuenta_ingreso": self._rel.get("subcuenta_ingreso", ""),
            "subcuenta_gasto": self._rel.get("subcuenta_gasto", ""),
            "cliente_tipo_operacion_iva": self._rel.get("cliente_tipo_operacion_iva"),
            "cliente_intracomunitaria_clase": self._rel.get("cliente_intracomunitaria_clase"),
            "proveedor_tipo_operacion_iva": self._rel.get("proveedor_tipo_operacion_iva"),
            "proveedor_intracomunitaria_clase": self._rel.get("proveedor_intracomunitaria_clase"),
            "proveedor_iva_deducible": self._rel.get("proveedor_iva_deducible"),
            "proveedor_porcentaje_deduccion_iva": self._rel.get("proveedor_porcentaje_deduccion_iva"),
        }
        if self._side == "cliente":
            try:
                sub_ingreso = self._ensure_related_account_exists("ingreso")
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
                return
            payload.update(
                {
                    "subcuenta_cliente": self.vars["subcuenta_cliente"].get().strip(),
                    "subcuenta_ingreso": sub_ingreso,
                    "cliente_tipo_operacion_iva": self.vars["cliente_tipo_operacion_iva"].get().strip(),
                    "cliente_intracomunitaria_clase": self.vars["cliente_intracomunitaria_clase"].get().strip(),
                }
            )
        else:
            try:
                pct = float((self.vars["proveedor_porcentaje_deduccion_iva"].get() or "0").replace(",", "."))
            except Exception:
                messagebox.showerror("Gest2A3Eco", "El porcentaje de deduccion IVA debe ser numerico.", parent=self)
                return
            try:
                sub_gasto = self._ensure_related_account_exists("gasto")
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
                return
            payload.update(
                {
                    "subcuenta_proveedor": self.vars["subcuenta_proveedor"].get().strip(),
                    "subcuenta_gasto": sub_gasto,
                    "proveedor_tipo_operacion_iva": self.vars["proveedor_tipo_operacion_iva"].get().strip(),
                    "proveedor_intracomunitaria_clase": self.vars["proveedor_intracomunitaria_clase"].get().strip(),
                    "proveedor_iva_deducible": 0 if DEDUCCION_LABELS_INV.get(self.vars["proveedor_ded_mode"].get(), "total") == "no" else 1,
                    "proveedor_porcentaje_deduccion_iva": pct,
                }
            )
        try:
            self._gestor.upsert_tercero_empresa(payload)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            return
        self.saved = True
        self.destroy()
