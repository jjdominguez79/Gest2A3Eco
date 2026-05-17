"""Vista integrada del maestro de subcuentas contables de empresa."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.maestro_contable_empresa_service import (
    TIPOS_SUBCUENTA,
    MaestroContableEmpresaService,
    clasificar_tipo_subcuenta,
)


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
        ttk.Button(bar, text="Nueva subcuenta", command=self._nueva).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Importar Excel", command=self._importar_excel).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Marcar alta A3", command=self._marcar_alta_a3).pack(side="left")

        # Treeview
        tree_wrap = tk.Frame(self, bg="#f1f5f9")
        tree_wrap.pack(fill="both", expand=True, padx=16, pady=6)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            tree_wrap,
            columns=("subcuenta", "nombre", "tipo", "nif", "tercero_id", "pendiente_a3", "origen"),
            show="headings", height=22,
        )
        for col, txt, width, anchor in [
            ("subcuenta",    "Subcuenta",   110, "w"),
            ("nombre",       "Nombre",      280, "w"),
            ("tipo",         "Tipo",        110, "center"),
            ("nif",          "NIF",         120, "w"),
            ("tercero_id",   "Tercero ID",   90, "center"),
            ("pendiente_a3", "Pend. A3",     80, "center"),
            ("origen",       "Origen",      100, "center"),
        ]:
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor=anchor)
        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=vsb.set)
        self.tv.bind("<Double-Button-1>", lambda _: self._editar())

        self.lbl_status = tk.Label(self, text="", bg="#f1f5f9", fg="#64748b",
                                   font=("Segoe UI", 8))
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 6))

    # ── Datos ─────────────────────────────────────────────────────────────────

    def refresh(self):
        self._rows = self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None)
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
            if q and q not in subcuenta.lower() and q not in nombre.lower() and q not in nif.lower():
                continue
            if tipo_fil != "todos" and tipo != tipo_fil:
                continue
            if solo_pend and not r.get("pendiente_alta_a3"):
                continue
            pend = "Si" if r.get("pendiente_alta_a3") else "No"
            self.tv.insert(
                "", tk.END, iid=str(r["id"]),
                values=(subcuenta, nombre, tipo, nif,
                        r.get("tercero_id") or "", pend, r.get("origen") or ""),
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

        # NIF
        ttk.Label(frm, text="NIF:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_nif = tk.StringVar(value=str(rec.get("nif_snapshot") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_nif, width=22).grid(row=3, column=1, sticky="w", pady=4)

        # Tercero ID
        ttk.Label(frm, text="Tercero ID:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_tercero = tk.StringVar(value=str(rec.get("tercero_id") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_tercero, width=22).grid(row=4, column=1, sticky="w", pady=4)

        # Observaciones
        ttk.Label(frm, text="Observaciones:").grid(row=5, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_obs = tk.StringVar(value=str(rec.get("observaciones") or "") if rec else "")
        ttk.Entry(frm, textvariable=self.var_obs, width=38).grid(row=5, column=1, sticky="ew", pady=4)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(btn_row, text="Guardar", command=self._save).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="left")

        frm.columnconfigure(1, weight=1)
        self.transient(parent)
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

    def _save(self):
        sub = self.var_subcuenta.get().strip()
        if not sub:
            messagebox.showwarning("Gest2A3Eco", "La subcuenta es obligatoria.", parent=self)
            return
        self.result = {
            "subcuenta":        sub,
            "tipo_subcuenta":   self.var_tipo.get() or None,
            "nombre_subcuenta": self.var_nombre.get().strip(),
            "nif":              self.var_nif.get().strip(),
            "tercero_id":       self.var_tercero.get().strip() or None,
            "observaciones":    self.var_obs.get().strip() or None,
        }
        self.destroy()
