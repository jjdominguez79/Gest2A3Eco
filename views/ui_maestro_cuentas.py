"""Vista integrada del maestro de subcuentas contables de empresa."""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

_log = logging.getLogger(__name__)

from models.facturas_common import render_a3_tipoC_alta_cuenta
from services.import_a3_empresa import importar_empresa_desde_a3
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
            text=f"Plan contable de {self._nombre or self._codigo}.",
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
        ttk.Button(bar, text="Importar desde A3", style="Primary.TButton",
                   command=self._importar_plan_desde_a3).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Configurar subcuenta", command=self._configurar_subcuenta_empresa).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Ficha tercero", command=self._abrir_ficha_tercero_global).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Nueva subcuenta", command=self._nueva).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Eliminar subcuenta", command=self._eliminar).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Importar Excel", command=self._importar_excel).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Enviar a A3", command=self._enviar_a3).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Marcar alta A3", command=self._marcar_alta_a3).pack(side="left")

        # Treeview
        tree_wrap = tk.Frame(self, bg="#f1f5f9")
        tree_wrap.pack(fill="both", expand=True, padx=16, pady=6)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            tree_wrap,
            columns=("subcuenta", "nombre", "tipo", "nif", "vinculado", "cta_ingreso", "cta_gasto", "iva_ventas", "iva_compras", "ded_iva", "pendiente_a3"),
            show="headings", height=22,
        )
        for col, txt, width, anchor in [
            ("subcuenta",    "Subcuenta",   110, "w"),
            ("nombre",       "Nombre",      230, "w"),
            ("tipo",         "Tipo",        110, "center"),
            ("nif",          "NIF",         120, "w"),
            ("vinculado",    "Vinculado",    70, "center"),
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
            vinculado = "Si" if r.get("tercero_id") else "No"
            iva_ventas = rel.get("cliente_tipo_operacion_iva", "") if tercero_id else ""
            iva_compras = rel.get("proveedor_tipo_operacion_iva", "") if tercero_id else ""
            cta_ingreso = rel.get("subcuenta_ingreso", "") if tercero_id else ""
            cta_gasto = rel.get("subcuenta_gasto", "") if tercero_id else ""
            ded_iva = self._deduccion_label(rel) if tercero_id else ""
            self.tv.insert(
                "", tk.END, iid=str(r["id"]),
                values=(subcuenta, nombre, tipo, nif, vinculado, cta_ingreso, cta_gasto, iva_ventas, iva_compras, ded_iva, pend),
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

    def _enviar_a3(self):
        """Genera un fichero SUENLACE DAT con registros tipo C para las subcuentas
        pendientes seleccionadas (o todas las pendientes si no hay seleccion) y las
        marca como enlazadas a A3."""
        sel = self.tv.selection()
        if sel:
            candidatas = [r for r in self._rows if str(r["id"]) in sel]
        else:
            candidatas = [r for r in self._rows if r.get("pendiente_alta_a3")]

        pendientes = [r for r in candidatas if r.get("pendiente_alta_a3")]
        if not pendientes:
            messagebox.showinfo(
                "Gest2A3Eco",
                "No hay subcuentas pendientes de envio a A3.\n"
                "Crea una subcuenta nueva o filtra por 'Solo pendientes A3'.",
                parent=self.winfo_toplevel(),
            )
            return

        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")

        registros = []
        for r in pendientes:
            subcuenta = str(r.get("subcuenta") or "").strip()
            nombre = str(r.get("nombre_subcuenta") or "").strip()[:30]
            nif = str(r.get("nif_snapshot") or "").strip()
            # Datos de domicilio opcionales desde tercero enlazado
            tercero_id = str(r.get("tercero_id") or "").strip()
            tercero = {}
            if tercero_id:
                try:
                    tercero = self._gestor.get_tercero(tercero_id) or {}
                except Exception:
                    pass
            registros.append(render_a3_tipoC_alta_cuenta(
                codigo_empresa=self._codigo,
                fecha_alta=fecha_hoy,
                cuenta=subcuenta,
                ndig_plan=ndig,
                nombre=nombre,
                nif=nif,
                via=str(tercero.get("direccion") or "")[:30],
                municipio=str(tercero.get("poblacion") or "")[:20],
                cp=str(tercero.get("cp") or "")[:5],
                provincia=str(tercero.get("provincia") or "")[:15],
                telefono=str(tercero.get("telefono") or "")[:12],
                email=str(tercero.get("email") or "")[:30],
            ))

        save_path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Guardar fichero de alta de cuentas para A3",
            defaultextension=".dat",
            filetypes=[("DAT", "*.dat"), ("Todos", "*.*")],
            initialfile=f"{self._codigo}_cuentas.dat",
        )
        if not save_path:
            return

        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(registros)

        # Marcar como enlazadas
        lote = datetime.now().strftime("%Y%m%d%H%M%S")
        ids_enviados = [r["id"] for r in pendientes]
        for rid in ids_enviados:
            try:
                self._svc.marcar_subcuenta_alta_a3_realizada(self._gestor, rid, lote=lote)
            except Exception:
                pass

        self.refresh()
        messagebox.showinfo(
            "Gest2A3Eco",
            f"Fichero generado con {len(pendientes)} subcuenta(s):\n{save_path}\n\n"
            "Importa el fichero en A3ECO y las subcuentas quedaran marcadas como enlazadas.",
            parent=self.winfo_toplevel(),
        )

    def _importar_plan_desde_a3(self):
        """Lee CU.DAT de A3 en hilo de fondo y abre una ventana de previsualizacion."""
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)

        def _on_data(data):
            plan = data.get("plan_cuentas") or []
            if not plan:
                messagebox.showinfo(
                    "Gest2A3Eco",
                    "No se ha encontrado plan de cuentas en A3.\n"
                    "Comprueba que el codigo de empresa y la ruta a A3ECO son correctos.",
                    parent=self.winfo_toplevel(),
                )
                return
            codigo_a3 = str(data.get("codigo") or self._codigo)
            ejercicio_plan = int(data.get("ejercicio") or 0) or 0
            _PrevisualizacionPlanDialog(
                self.winfo_toplevel(),
                plan=plan,
                codigo_empresa=codigo_a3,
                ejercicio=ejercicio_plan,
                digitos=ndig,
                gestor=self._gestor,
                on_confirm=self.refresh,
            )

        _ProgressA3Dialog(
            self.winfo_toplevel(),
            codigo=self._codigo,
            digitos_plan_objetivo=ndig,
            on_complete=_on_data,
        )

    def _importar_excel(self):
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Seleccionar fichero Excel o CSV",
            filetypes=[("Excel / CSV", "*.xlsx *.xls *.csv"), ("Todos", "*.*")],
        )
        if not path:
            return

        # Leer DataFrame (operacion bloqueante pero rapida)
        try:
            import pandas as pd
            df = pd.read_csv(path, dtype=str) if path.endswith(".csv") else _read_excel_autodetect(path)
        except Exception as exc:
            messagebox.showerror(
                "Error de importacion", f"No se pudo leer el fichero:\n{exc}",
                parent=self.winfo_toplevel(),
            )
            return

        # Detectar duplicados ANTES de importar
        try:
            duplicados = self._svc.detectar_duplicados_en_dataframe(
                self._gestor, self._codigo, df
            )
        except Exception:
            duplicados = []

        actualizar_duplicados = True
        if duplicados:
            n = len(duplicados)
            ejemplos = ", ".join(duplicados[:5])
            if n > 5:
                ejemplos += f" ... y {n - 5} mas"
            resp = messagebox.askyesnocancel(
                "Subcuentas duplicadas",
                f"Se han encontrado {n} subcuenta(s) que ya existen en el maestro:\n\n"
                f"  {ejemplos}\n\n"
                "  Si      → Actualizar los registros existentes con los nuevos datos\n"
                "  No      → Conservar los existentes e importar solo las nuevas\n"
                "  Cancelar → Cancelar toda la importacion",
                parent=self.winfo_toplevel(),
            )
            if resp is None:
                _log.info("Importacion Excel cancelada por el usuario (duplicados).")
                return
            actualizar_duplicados = bool(resp)

        # Lanzar importacion en hilo con dialogo de progreso
        _ProgressImportDialog(
            self.winfo_toplevel(),
            svc=self._svc,
            gestor=self._gestor,
            codigo=self._codigo,
            df=df,
            actualizar_duplicados=actualizar_duplicados,
            on_complete=lambda r: (self.after(0, self.refresh), self.after(0, lambda: self._mostrar_resumen_importacion(r))),
        )

    def _mostrar_resumen_importacion(self, resultado: dict):
        msg = (
            f"Importacion completada:\n\n"
            f"  Nuevas:      {resultado.get('importadas', 0)}\n"
            f"  Actualizadas: {resultado.get('actualizadas', 0)}\n"
            f"  Omitidas:    {resultado.get('omitidas', 0)}\n"
            f"  Errores:     {resultado.get('errores', 0)}\n"
            f"  Vinculadas:  {resultado.get('vinculadas', 0)}"
        )
        errores = resultado.get("detalles_error") or []
        if errores:
            msg += "\n\nDetalle de errores:\n" + "\n".join(errores[:10])
            if len(errores) > 10:
                msg += f"\n... y {len(errores) - 10} error(es) mas"
        messagebox.showinfo("Importacion completada", msg, parent=self.winfo_toplevel())

    def _abrir_ficha_tercero_global(self):
        """Abre la ficha global del tercero vinculado a la subcuenta seleccionada."""
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo(
                "Gest2A3Eco", "Selecciona una subcuenta.", parent=self.winfo_toplevel()
            )
            return
        rec = next((r for r in self._rows if str(r["id"]) == sel[0]), None)
        if not rec:
            return

        tercero = self._resolver_tercero_para_subcuenta(rec)
        if not tercero:
            if not messagebox.askyesno(
                "Gest2A3Eco",
                "La subcuenta no tiene tercero global vinculado.\n\n"
                "Quieres crear o vincular un tercero global ahora?",
                parent=self.winfo_toplevel(),
            ):
                return
            tercero = self._crear_tercero_global_desde_subcuenta(rec)
            if not tercero:
                return
            # Actualizar el vinculo en la subcuenta
            tercero_id = str(tercero.get("id") or "").strip()
            if tercero_id:
                try:
                    self._gestor.upsert_maestro_subcuenta({
                        "id": rec.get("id"),
                        "codigo_empresa": self._codigo,
                        "subcuenta": rec.get("subcuenta"),
                        "tercero_id": tercero_id,
                        "nombre_subcuenta": rec.get("nombre_subcuenta"),
                        "tipo_subcuenta": rec.get("tipo_subcuenta"),
                        "nif_snapshot": rec.get("nif_snapshot"),
                        "activo": rec.get("activo", 1),
                        "origen": rec.get("origen"),
                        "creado_en_gest2a3eco": rec.get("creado_en_gest2a3eco", 0),
                        "pendiente_alta_a3": rec.get("pendiente_alta_a3", 0),
                        "observaciones": rec.get("observaciones"),
                    })
                    _log.info("Tercero %s vinculado a subcuenta %s", tercero_id, rec.get("subcuenta"))
                except Exception as exc:
                    _log.warning("No se pudo actualizar vinculo tercero-subcuenta: %s", exc)
            self.refresh()
            return

        # Abrir ficha global del tercero para edicion
        dlg = TerceroFicha(self.winfo_toplevel(), tercero)
        payload = dlg.result
        if not payload:
            return

        nif_extranjero = bool(payload.pop("_nif_extranjero", False))
        nif = (
            str(payload.get("nif") or "").strip().upper()
            if nif_extranjero
            else normalizar_nif_cif(payload.get("nif"))
        )
        if nif and not nif_extranjero and not validar_nif_o_nif_iva_intracomunitario(nif):
            messagebox.showerror(
                "Gest2A3Eco", "NIF/CIF/NIE o NIF-IVA intracomunitario invalido.",
                parent=self.winfo_toplevel(),
            )
            return

        payload["nif"] = nif
        payload["id"] = tercero.get("id")
        tipo_ident_key = payload.pop("_tipo_identificacion_selector", None)
        if tipo_ident_key:
            payload["tipo_identificacion"] = {
                "vat": "vat", "foreign": "foreign", "nacional": "nif",
            }.get(tipo_ident_key)

        try:
            self._gestor.upsert_tercero(payload)
            _log.info("Tercero global actualizado: id=%s nif=%s", tercero.get("id"), nif)
            self.refresh()
            messagebox.showinfo(
                "Gest2A3Eco", "Ficha del tercero actualizada correctamente.",
                parent=self.winfo_toplevel(),
            )
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())


# ── Dialogo de progreso para importacion desde A3 ─────────────────────────────

class _ProgressA3Dialog(tk.Toplevel):
    """Dialogo modal que ejecuta la importacion de A3 en un hilo de fondo
    y muestra una barra de progreso indeterminada mientras dura la operacion.

    Al finalizar llama a on_complete(data) desde el hilo principal, donde
    data es el dict devuelto por importar_empresa_desde_a3.
    """

    def __init__(self, parent, *, codigo, digitos_plan_objetivo, on_complete):
        super().__init__(parent)
        self.title("Importando desde A3...")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._on_complete = on_complete
        self._resultado = None
        self._error = None

        frm = tk.Frame(self, padx=24, pady=20, bg="#f1f5f9")
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text="Leyendo plan contable desde A3ECO...",
            bg="#f1f5f9", fg="#0f172a",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self.lbl_estado = tk.Label(
            frm,
            text=f"Empresa {codigo} — leyendo fichero CU.DAT...",
            bg="#f1f5f9", fg="#475569",
            font=("Segoe UI", 9),
        )
        self.lbl_estado.pack(anchor="w", pady=(0, 8))

        self.pb = ttk.Progressbar(frm, mode="indeterminate", length=340)
        self.pb.pack(fill="x", pady=(0, 8))
        self.pb.start(12)

        tk.Label(
            frm,
            text="Esto puede tardar unos segundos en redes lentas.",
            bg="#f1f5f9", fg="#94a3b8",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        try:
            self.update_idletasks()
            pw = parent.winfo_rootx() + (parent.winfo_width() - 420) // 2
            ph = parent.winfo_rooty() + (parent.winfo_height() - 150) // 2
            self.geometry(f"420x150+{max(pw, 0)}+{max(ph, 0)}")
        except Exception:
            self.geometry("420x150")

        # Forzar render completo antes de lanzar el hilo, para que la barra
        # sea visible aunque la operacion termine muy rapidamente.
        self.update()

        self.after(20, lambda: threading.Thread(
            target=self._run,
            args=(codigo, digitos_plan_objetivo),
            daemon=True,
        ).start())

    def _run(self, codigo, digitos_plan_objetivo):
        try:
            self._resultado = importar_empresa_desde_a3(
                codigo, digitos_plan_objetivo=digitos_plan_objetivo
            )
        except Exception as exc:
            self._error = exc
        self.after(0, self._finalizar)

    def _finalizar(self):
        self.pb.stop()
        self.destroy()
        if self._error:
            import tkinter.messagebox as mb
            mb.showerror("Error de importacion", str(self._error))
            return
        if self._on_complete and self._resultado is not None:
            try:
                self._on_complete(self._resultado)
            except Exception:
                pass


# ── Dialogo de progreso para importacion Excel ────────────────────────────────

class _ProgressImportDialog(tk.Toplevel):
    """Dialogo modal que ejecuta la importacion de subcuentas en un hilo de fondo
    y muestra una barra de progreso indeterminada mientras dura la operacion.

    Al finalizar llama a on_complete(resultado) desde el hilo principal.
    """

    def __init__(self, parent, *, svc, gestor, codigo, df, actualizar_duplicados, on_complete):
        super().__init__(parent)
        self.title("Importando subcuentas...")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # No cerrar durante importacion

        self._on_complete = on_complete
        self._resultado = None
        self._error = None

        frm = tk.Frame(self, padx=24, pady=20, bg="#f1f5f9")
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text="Importando subcuentas desde Excel...",
            bg="#f1f5f9", fg="#0f172a",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self.lbl_estado = tk.Label(
            frm,
            text="Preparando importacion...",
            bg="#f1f5f9", fg="#475569",
            font=("Segoe UI", 9),
        )
        self.lbl_estado.pack(anchor="w", pady=(0, 8))

        self.pb = ttk.Progressbar(frm, mode="indeterminate", length=340)
        self.pb.pack(fill="x", pady=(0, 8))
        self.pb.start(12)

        self.lbl_progreso = tk.Label(
            frm,
            text="",
            bg="#f1f5f9", fg="#64748b",
            font=("Segoe UI", 8),
        )
        self.lbl_progreso.pack(anchor="w")

        try:
            self.update_idletasks()
            pw = parent.winfo_rootx() + (parent.winfo_width() - 400) // 2
            ph = parent.winfo_rooty() + (parent.winfo_height() - 160) // 2
            self.geometry(f"400x160+{max(pw, 0)}+{max(ph, 0)}")
        except Exception:
            self.geometry("400x160")

        # Iniciar hilo
        t = threading.Thread(
            target=self._run,
            args=(svc, gestor, codigo, df, actualizar_duplicados),
            daemon=True,
        )
        t.start()

    def _progress_cb(self, idx: int, total: int):
        """Callback desde el hilo de importacion para actualizar la etiqueta."""
        try:
            pct = int(idx * 100 / total) if total > 0 else 0
            self.after(0, lambda: self.lbl_progreso.configure(
                text=f"Procesando fila {idx} de {total} ({pct}%)"
            ))
        except Exception:
            pass

    def _run(self, svc, gestor, codigo, df, actualizar_duplicados):
        try:
            resultado = svc.importar_subcuentas_desde_dataframe(
                gestor, codigo, df,
                actualizar_duplicados=actualizar_duplicados,
                progress_callback=self._progress_cb,
            )
            self._resultado = resultado
        except Exception as exc:
            self._error = exc
        self.after(0, self._finalizar)

    def _finalizar(self):
        self.pb.stop()
        self.destroy()
        if self._error:
            import tkinter.messagebox as mb
            mb.showerror("Error de importacion", str(self._error))
            return
        if self._on_complete and self._resultado is not None:
            try:
                self._on_complete(self._resultado)
            except Exception:
                pass


# ── Helpers para deteccion de descripciones sospechosas ───────────────────────

import re as _re

_SUFIJOS_ENTIDAD = _re.compile(
    r"\b(S\.?L\.?|S\.?A\.?|S\.?L\.?U\.?|S\.?A\.?U\.?|S\.?C\.?|C\.?B\.?|"
    r"S\.?L\.?P\.?|S\.?R\.?L\.?|S\.?L\.?L\.?|A\.?I\.?E\.?|"
    r"SL|SA|SLU|SAU|SC|CB|SLP|SRL|SLL|AIE)\b",
    _re.IGNORECASE,
)

_PALABRAS_ENTIDAD = _re.compile(
    r"\b(ASESORIA|ASESORES|GESTORIA|CONSULTORIA|CONTABILIDAD|EMPRESA|"
    r"GRUPO|SERVICIOS|SOLUCIONES|SOCIEDAD|COMUNIDAD|COMUNITAT|"
    r"INVERSIONES|INMOBILIARIA|CONSTRUCCIONES|TRANSPORTES|DISTRIBUCIONES|"
    r"COMERCIAL|INDUSTRIAL|TECNOLOGIAS|INFORMATICA|INFORMATIQUES)\b",
    _re.IGNORECASE,
)


def _parece_nombre_entidad(descripcion: str) -> bool:
    """Devuelve True si la descripcion parece un nombre de empresa/persona en lugar
    de un concepto contable del PGC (ej. 'ASESORIA GESTINEM SL' en vez de 'CAPITAL SOCIAL')."""
    d = (descripcion or "").strip()
    if not d:
        return False
    # Si contiene un sufijo juridico tipico (S.L., S.A., etc.) -> muy sospechoso
    if _SUFIJOS_ENTIDAD.search(d):
        return True
    # Si contiene palabras que suelen ser parte de nombres de empresas
    if _PALABRAS_ENTIDAD.search(d):
        return True
    return False


# ── Previsualizacion de plan contable desde A3 ────────────────────────────────

class _PrevisualizacionPlanDialog(tk.Toplevel):
    """Muestra las cuentas leidas del CU.DAT de A3 antes de confirmar la importacion.

    Doble clic sobre una fila (o F2) permite editar la descripcion o el codigo de cuenta
    directamente en la previsualizacion antes de guardar.
    """

    def __init__(self, parent, *, plan: list[dict], codigo_empresa: str,
                 ejercicio: int, digitos: int, gestor, on_confirm=None):
        super().__init__(parent)
        self.title(f"Previa importacion plan contable — {codigo_empresa}")
        self.resizable(True, True)
        self.grab_set()
        # Copia editable del plan: lista de dicts con 'cuenta' y 'descripcion'
        self._plan: list[dict] = [dict(c) for c in plan]
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio
        self._digitos = digitos
        self._gestor = gestor
        self._on_confirm = on_confirm
        self._edit_entry: tk.Entry | None = None
        self._build()
        self.geometry("920x640")
        try:
            self.update_idletasks()
            pw = parent.winfo_rootx() + (parent.winfo_width() - 920) // 2
            ph = parent.winfo_rooty() + (parent.winfo_height() - 640) // 2
            self.geometry(f"+{max(pw, 0)}+{max(ph, 0)}")
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        # Cabecera con resumen
        info = tk.Frame(self, bg="#f0f9ff", pady=8)
        info.pack(fill="x")
        self._lbl_resumen = tk.Label(
            info, bg="#f0f9ff", fg="#0369a1", font=("Segoe UI", 9), anchor="w",
        )
        self._lbl_resumen.pack(anchor="w", padx=12)
        tk.Label(
            info,
            text="  Doble clic o F2 sobre una fila para editar su descripcion antes de importar.",
            bg="#f0f9ff", fg="#64748b", font=("Segoe UI", 8), anchor="w",
        ).pack(anchor="w", padx=12)

        # Barra de busqueda + botones
        bar = tk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(bar, text="Buscar:").pack(side="left")
        self._var_buscar = tk.StringVar()
        self._var_buscar.trace_add("write", lambda *_: self._filtrar())
        ttk.Entry(bar, textvariable=self._var_buscar, width=30).pack(side="left", padx=(6, 12))
        self._var_solo_sospechosas = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Solo sospechosas",
            variable=self._var_solo_sospechosas,
            command=self._filtrar,
        ).pack(side="left", padx=(0, 12))
        self._lbl_conteo = tk.Label(bar, text="", fg="#64748b", font=("Segoe UI", 8))
        self._lbl_conteo.pack(side="left")

        # Treeview
        wrap = tk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=12, pady=4)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self._tv = ttk.Treeview(
            wrap,
            columns=("cuenta", "descripcion"),
            show="headings",
        )
        self._tv.heading("cuenta", text="Cuenta", anchor="w")
        self._tv.column("cuenta", width=150, anchor="w", stretch=False)
        self._tv.heading("descripcion", text="Descripcion  (doble clic para editar)", anchor="w")
        self._tv.column("descripcion", width=700, anchor="w")
        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tv.configure(yscrollcommand=vsb.set)
        self._tv.bind("<Double-Button-1>", self._on_double_click)
        self._tv.bind("<F2>", lambda _e: self._editar_seleccion())

        # Tags de color para cuentas sospechosas
        self._tv.tag_configure("sospechosa", background="#fef3c7", foreground="#92400e")

        # Leyenda
        leyenda = tk.Frame(self)
        leyenda.pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(
            leyenda, width=2, bg="#fef3c7", relief="solid", bd=1,
        ).pack(side="left")
        self._lbl_sospechosas = tk.Label(
            leyenda,
            text="  Descripcion posiblemente incorrecta (nombre de empresa/persona). "
                 "Edita antes de importar.",
            fg="#92400e", font=("Segoe UI", 8), anchor="w",
        )
        self._lbl_sospechosas.pack(side="left", padx=(4, 0))

        # Botones de accion
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(
            btns, text="Confirmar importacion", style="Primary.TButton",
            command=self._confirmar,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="left")

        self._filtrar()

    # ── Filtro y refresco ─────────────────────────────────────────────────────

    def _filtrar(self):
        q = (self._var_buscar.get() or "").strip().lower()
        self._tv.delete(*self._tv.get_children())
        solo_sospechosas = self._var_solo_sospechosas.get()
        n_sospechosas = 0
        for c in self._plan:
            cuenta = c.get("cuenta", "")
            desc = c.get("descripcion", "")
            if q and q not in f"{cuenta} {desc}".lower():
                continue
            sospechosa = _parece_nombre_entidad(desc)
            if sospechosa:
                n_sospechosas += 1
            if solo_sospechosas and not sospechosa:
                continue
            self._tv.insert(
                "", tk.END, iid=cuenta, values=(cuenta, desc),
                tags=("sospechosa",) if sospechosa else (),
            )
        visibles = len(self._tv.get_children())
        self._lbl_conteo.configure(text=f"{visibles} de {len(self._plan)} cuentas")
        if n_sospechosas:
            self._lbl_sospechosas.configure(
                text=f"  {n_sospechosas} descripcion{'es' if n_sospechosas != 1 else ''} "
                     f"posiblemente incorrecta{'s' if n_sospechosas != 1 else ''} "
                     f"(nombre de empresa/persona). Edita antes de importar."
            )
        else:
            self._lbl_sospechosas.configure(text="  Sin descripciones sospechosas detectadas.")
        self._lbl_resumen.configure(
            text=f"  {len(self._plan)} cuentas leidas de A3  |  "
                 f"Empresa: {self._codigo}  |  "
                 f"Ejercicio: {self._ejercicio or 'base'}  |  "
                 f"Digitos plan: {self._digitos}"
        )

    # ── Edicion inline ────────────────────────────────────────────────────────

    def _on_double_click(self, event: tk.Event):
        region = self._tv.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self._tv.identify_column(event.x)
        row_id = self._tv.identify_row(event.y)
        if not row_id:
            return
        # Solo editar la columna descripcion (#2); para cuenta usar col #1
        col_idx = int(col.replace("#", "")) - 1  # 0-based
        self._abrir_editor(row_id, col_idx)

    def _editar_seleccion(self):
        sel = self._tv.selection()
        if sel:
            self._abrir_editor(sel[0], 1)  # edita descripcion por defecto

    def _abrir_editor(self, row_id: str, col_idx: int):
        """Coloca un Entry encima de la celda seleccionada para edicion inline."""
        self._cerrar_editor()

        # Coordenadas de la celda
        col_name = ("#1", "#2")[col_idx]
        x, y, w, h = self._tv.bbox(row_id, col_name)
        if not w:
            return

        valor_actual = self._tv.set(row_id, col_name)
        var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(self._tv, textvariable=var, font=("Segoe UI", 9))
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._edit_entry = entry

        def _aplicar(_event=None):
            nuevo = var.get().strip()
            self._cerrar_editor()
            if nuevo == valor_actual:
                return
            # Actualizar la lista _plan en memoria
            cuenta_key = row_id  # iid = codigo de cuenta
            for item in self._plan:
                if item.get("cuenta") == cuenta_key:
                    if col_idx == 0:
                        item["cuenta"] = nuevo
                    else:
                        item["descripcion"] = nuevo
                    break
            # Refrescar la fila en el treeview
            vals = list(self._tv.item(row_id, "values"))
            vals[col_idx] = nuevo
            self._tv.item(row_id, values=vals)
            # Si cambio el codigo de cuenta, actualizar el iid es complejo;
            # refrescamos el treeview completo para mantener consistencia
            if col_idx == 0:
                self._filtrar()

        def _cancelar(_event=None):
            self._cerrar_editor()

        entry.bind("<Return>", _aplicar)
        entry.bind("<Tab>", _aplicar)
        entry.bind("<Escape>", _cancelar)
        entry.bind("<FocusOut>", _aplicar)

    def _cerrar_editor(self):
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except Exception:
                pass
            self._edit_entry = None

    # ── Confirmacion ──────────────────────────────────────────────────────────

    def _confirmar(self):
        self._cerrar_editor()
        plan = list(self._plan)
        gestor = self._gestor
        codigo = self._codigo
        ejercicio = self._ejercicio
        digitos = self._digitos
        on_confirm = self._on_confirm
        parent = self.master
        self.destroy()
        _ProgressGuardadoPlanDialog(
            parent,
            plan=plan,
            gestor=gestor,
            codigo=codigo,
            ejercicio=ejercicio,
            digitos=digitos,
            on_complete=on_confirm,
        )


# ── Dialogo de progreso al guardar el plan en el maestro ──────────────────────

class _ProgressGuardadoPlanDialog(tk.Toplevel):
    """Guarda el plan en maestro_subcuentas_empresa en un hilo de fondo
    mostrando progreso determinado mientras dura la operacion."""

    def __init__(self, parent, *, plan, gestor, codigo, ejercicio, digitos, on_complete):
        super().__init__(parent)
        self.title("Importando plan contable...")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._on_complete = on_complete
        self._n = 0
        self._total = len(plan)

        frm = tk.Frame(self, padx=24, pady=20, bg="#f1f5f9")
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text="Guardando cuentas en el maestro contable...",
            bg="#f1f5f9", fg="#0f172a",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        self.lbl_estado = tk.Label(
            frm, text="Preparando...",
            bg="#f1f5f9", fg="#475569", font=("Segoe UI", 9),
        )
        self.lbl_estado.pack(anchor="w", pady=(0, 6))

        self.pb = ttk.Progressbar(frm, mode="determinate", length=360, maximum=max(self._total, 1))
        self.pb.pack(fill="x", pady=(0, 6))

        self.lbl_pct = tk.Label(frm, text="0 %", bg="#f1f5f9", fg="#64748b", font=("Segoe UI", 8))
        self.lbl_pct.pack(anchor="e")

        try:
            self.update_idletasks()
            pw = parent.winfo_rootx() + (parent.winfo_width() - 420) // 2
            ph = parent.winfo_rooty() + (parent.winfo_height() - 160) // 2
            self.geometry(f"420x160+{max(pw, 0)}+{max(ph, 0)}")
        except Exception:
            self.geometry("420x160")

        self.update()

        self.after(20, lambda: threading.Thread(
            target=self._run,
            args=(plan, gestor, codigo, ejercicio, digitos),
            daemon=True,
        ).start())

    def _run(self, plan, gestor, codigo, ejercicio, digitos):
        n = 0
        total = len(plan)
        for i, cuenta_dict in enumerate(plan, 1):
            try:
                nif_snapshot = normalizar_nif_cif(cuenta_dict.get("nif") or "") or None
                tercero_id = None
                if nif_snapshot:
                    try:
                        ter = gestor.get_tercero_by_nif_normalizado(nif_snapshot)
                        if ter:
                            tercero_id = str(ter.get("id") or "").strip() or None
                    except Exception:
                        pass
                gestor.upsert_maestro_subcuenta({
                    "codigo_empresa": codigo,
                    "subcuenta": cuenta_dict["cuenta"],
                    "nombre_subcuenta": cuenta_dict["descripcion"],
                    "tipo_subcuenta": clasificar_tipo_subcuenta(cuenta_dict["cuenta"]),
                    "nif_snapshot": nif_snapshot,
                    "tercero_id": tercero_id,
                    "activo": 1,
                    "origen": "a3",
                    "creado_en_gest2a3eco": 0,
                    "pendiente_alta_a3": 0,
                })
                n += 1
            except Exception:
                pass
            if i % 20 == 0 or i == total:
                pct = int(i * 100 / total)
                self.after(0, lambda v=i, p=pct: (
                    self.pb.configure(value=v),
                    self.lbl_estado.configure(text=f"Cuenta {v} de {total}..."),
                    self.lbl_pct.configure(text=f"{p} %"),
                ))
        self._n = n
        self.after(0, lambda: self._finalizar(n, ejercicio, digitos))

    def _finalizar(self, n, ejercicio, digitos):
        self.destroy()
        if self._on_complete:
            try:
                self._on_complete()
            except Exception:
                pass
        messagebox.showinfo(
            "Gest2A3Eco",
            f"Plan contable importado: {n} cuentas al maestro.\n"
            f"Ejercicio: {ejercicio or 'base'}  |  Digitos: {digitos}",
        )


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
