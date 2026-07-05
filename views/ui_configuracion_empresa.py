"""Pantalla integrada de configuracion de empresa (reemplaza EmpresaDialog modal)."""
from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.import_a3_empresa import importar_empresa_desde_a3, listar_empresas_a3
from utils.validaciones import normalizar_codigo_pais, normalizar_nif_cif
from views.ui_buzones import UIBuzones
from views.ui_certificados import UICertificados
from views.ui_notificaciones_cliente import UINotificacionesCliente


def _center_window(win, parent=None):
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if parent is None:
            px, py = win.winfo_screenwidth() // 2, win.winfo_screenheight() // 2
        else:
            parent.update_idletasks()
            px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        win.geometry(f"+{max(px, 0)}+{max(py, 0)}")
    except Exception:
        pass


def _to_float_es(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0


class UIConfiguracionEmpresa(ttk.Frame):
    """Frame integrado de configuracion de empresa, embebible en el area de contenido."""

    def __init__(self, parent, gestor, codigo, ejercicio, nombre, *, on_back, on_deleted=None, session=None):
        super().__init__(parent)
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        empresa = gestor.get_empresa(codigo, ejercicio) if codigo else {}
        empresa = empresa or {}
        self._empresa = dict(empresa)
        self._bank_items: list = []
        self._bank_records: list = []
        self._exercise_rows: list = []
        self._series_por_ejercicio: dict = {}
        self._on_back = on_back
        self._on_deleted = on_deleted or on_back
        self._session = session
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        self.var_codigo  = tk.StringVar(value=str(self._empresa.get("codigo", "")))
        self.var_nombre  = tk.StringVar(value=str(self._empresa.get("nombre", "")))
        self.var_dig     = tk.StringVar(value=str(self._empresa.get("digitos_plan", 8) or "8"))
        self.var_cif     = tk.StringVar(value=normalizar_nif_cif(self._empresa.get("cif", "")))
        self.var_cif.trace_add("write", lambda *_: self._normalize_identifier_var(self.var_cif))
        self.var_dir     = tk.StringVar(value=str(self._empresa.get("direccion", "")))
        self.var_cp      = tk.StringVar(value=str(self._empresa.get("cp", "")))
        self.var_pob     = tk.StringVar(value=str(self._empresa.get("poblacion", "")))
        self.var_prov    = tk.StringVar(value=str(self._empresa.get("provincia", "")))
        self.var_pais    = tk.StringVar(value=str(self._empresa.get("pais", "ES") or "ES"))
        self.var_pais.trace_add("write", lambda *_: self._normalize_country_var(self.var_pais))
        self.var_tel     = tk.StringVar(value=str(self._empresa.get("telefono", "")))
        self.var_mail    = tk.StringVar(value=str(self._empresa.get("email", "")))
        self.var_logo    = tk.StringVar(value=str(self._empresa.get("logo_path", "")))
        self.var_logo_w  = tk.StringVar(value=str(self._empresa.get("logo_max_width_mm") or ""))
        self.var_logo_h  = tk.StringVar(value=str(self._empresa.get("logo_max_height_mm") or ""))
        self.var_activo  = tk.BooleanVar(value=bool(self._empresa.get("activo", True)))
        self.var_naf     = tk.StringVar(value=str(self._empresa.get("naf", "") or ""))
        self.var_a3_info = tk.StringVar(value="Sin importacion realizada.")

        # Barra de acciones superior
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=16, pady=(12, 0))
        ttk.Label(
            bar,
            text=f"Configuracion — {self._empresa.get('nombre') or self._codigo or 'Nueva empresa'}",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        self.btn_delete = ttk.Button(bar, text="Eliminar empresa", style="Danger.TButton",
                                     command=self._request_delete)
        self.btn_delete.pack(side="left", padx=(24, 0))
        if not self._empresa.get("codigo"):
            self.btn_delete.state(["disabled"])
        ttk.Button(bar, text="Volver", command=self._on_back).pack(side="right")
        ttk.Button(bar, text="Guardar", style="Primary.TButton",
                   command=self._save).pack(side="right", padx=(0, 8))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=(8, 4))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._build_general_tab(ttk.Frame(nb, padding=14), nb)
        self._build_exercises_tab(ttk.Frame(nb, padding=14), nb)
        self._build_banks_tab(ttk.Frame(nb, padding=14), nb)
        self._build_notificaciones_tab(ttk.Frame(nb, padding=14), nb)
        self._build_seguridad_social_tab(ttk.Frame(nb, padding=14), nb)

    # ── Pestana General ────────────────────────────────────────────────────────

    def _build_general_tab(self, tab, nb):
        nb.add(tab, text="General")
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)
        tab.rowconfigure(11, weight=1)
        fields = [
            ("Codigo A3", self.var_codigo, 0, 0, 14),
            ("Nombre", self.var_nombre, 1, 0, None),
            ("Digitos plan", self.var_dig, 2, 0, 10),
            ("CIF/NIF", self.var_cif, 3, 0, 20),
            ("Telefono", self.var_tel, 3, 2, 20),
            ("Email", self.var_mail, 4, 0, None),
            ("Direccion", self.var_dir, 5, 0, None),
            ("CP", self.var_cp, 6, 0, 10),
            ("Poblacion", self.var_pob, 6, 2, None),
            ("Provincia", self.var_prov, 7, 0, None),
            ("Pais", self.var_pais, 7, 2, 8),
        ]
        for text, var, row, col, width in fields:
            ttk.Label(tab, text=text).grid(row=row, column=col, sticky="w", pady=4,
                                           padx=(18 if col else 0, 0))
            kwargs = {"textvariable": var}
            if width:
                kwargs["width"] = width
            entry = ttk.Entry(tab, **kwargs)
            span = 1 if width else 3 if row in (1, 4, 5, 7) else 1
            entry.grid(row=row, column=col + 1, columnspan=span,
                       sticky="ew" if not width else "w", pady=4)

        btn_row = ttk.Frame(tab)
        btn_row.grid(row=0, column=2, columnspan=2, sticky="e", pady=4)
        ttk.Button(btn_row, text="Buscar en A3...",
                   command=self._browse_a3_companies).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Importar datos de A3", style="Primary.TButton",
                   command=self._import_from_a3).pack(side=tk.LEFT)

        ttk.Checkbutton(tab, text="Activo", variable=self.var_activo).grid(
            row=2, column=3, sticky="w", pady=4)

        ttk.Label(tab, text="Logo (JPG)").grid(row=8, column=0, sticky="w", pady=4)
        row_logo = ttk.Frame(tab)
        row_logo.grid(row=8, column=1, columnspan=3, sticky="ew", pady=4)
        row_logo.columnconfigure(0, weight=1)
        ttk.Entry(row_logo, textvariable=self.var_logo).pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Button(row_logo, text="Buscar", command=self._choose_logo).pack(side=tk.LEFT, padx=4)

        ttk.Label(tab, text="Logo ancho (mm)").grid(row=9, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.var_logo_w, width=10).grid(row=9, column=1, sticky="w", pady=4)
        ttk.Label(tab, text="Logo alto (mm)").grid(row=9, column=2, sticky="w", pady=4, padx=(18, 0))
        ttk.Entry(tab, textvariable=self.var_logo_h, width=10).grid(row=9, column=3, sticky="w", pady=4)

        ttk.Label(tab, textvariable=self.var_a3_info, justify="left").grid(
            row=10, column=0, columnspan=4, sticky="w", pady=(12, 6))

        preview = ttk.LabelFrame(tab, text="Detalle capturado desde A3")
        preview.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=(0, 4))
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.txt_a3_preview = tk.Text(preview, height=8, wrap="word", state="disabled")
        self.txt_a3_preview.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(preview, orient="vertical", command=self.txt_a3_preview.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.txt_a3_preview.configure(yscrollcommand=scroll.set)

    # ── Pestana Ejercicios ─────────────────────────────────────────────────────

    def _build_exercises_tab(self, tab, nb):
        nb.add(tab, text="Ejercicios")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text="Cada ejercicio mantiene sus propias series y contadores.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        lf_ej = ttk.LabelFrame(tab, text="Ejercicios")
        lf_ej.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        lf_ej.columnconfigure(0, weight=1)
        lf_ej.rowconfigure(0, weight=1)
        self.tv_ejercicios = ttk.Treeview(lf_ej, columns=("ejercicio",), show="headings", height=8)
        self.tv_ejercicios.heading("ejercicio", text="Ejercicio")
        self.tv_ejercicios.column("ejercicio", width=100, anchor="w")
        self.tv_ejercicios.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        scroll_ej = ttk.Scrollbar(lf_ej, orient="vertical", command=self.tv_ejercicios.yview)
        scroll_ej.grid(row=0, column=1, sticky="ns", pady=4)
        self.tv_ejercicios.configure(yscrollcommand=scroll_ej.set)
        btns_ej = ttk.Frame(lf_ej)
        btns_ej.grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        ttk.Button(btns_ej, text="Anadir", style="Primary.TButton",
                   command=self._add_exercise).pack(side=tk.LEFT)
        ttk.Button(btns_ej, text="Eliminar",
                   command=self._remove_exercise).pack(side=tk.LEFT, padx=6)
        self.tv_ejercicios.bind("<<TreeviewSelect>>", lambda _e: self._on_ejercicio_selected())

        lf_ser = ttk.LabelFrame(tab, text="Series del ejercicio seleccionado")
        lf_ser.grid(row=1, column=1, sticky="nsew")
        lf_ser.columnconfigure(0, weight=1)
        lf_ser.rowconfigure(0, weight=1)
        self.tv_series = ttk.Treeview(lf_ser, columns=("nombre", "siguiente", "tipo"),
                                      show="headings", height=8)
        self.tv_series.heading("nombre", text="Nombre serie")
        self.tv_series.column("nombre", width=120, anchor="w")
        self.tv_series.heading("siguiente", text="Sig. numero")
        self.tv_series.column("siguiente", width=100, anchor="center")
        self.tv_series.heading("tipo", text="Tipo")
        self.tv_series.column("tipo", width=120, anchor="w")
        self.tv_series.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        scroll_ser = ttk.Scrollbar(lf_ser, orient="vertical", command=self.tv_series.yview)
        scroll_ser.grid(row=0, column=1, sticky="ns", pady=4)
        self.tv_series.configure(yscrollcommand=scroll_ser.set)
        btns_ser = ttk.Frame(lf_ser)
        btns_ser.grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        ttk.Button(btns_ser, text="Anadir serie", style="Primary.TButton",
                   command=self._add_serie).pack(side=tk.LEFT)
        ttk.Button(btns_ser, text="Editar",
                   command=self._edit_serie).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns_ser, text="Eliminar",
                   command=self._remove_serie).pack(side=tk.LEFT)
        self.lbl_series_info = ttk.Label(lf_ser, text="Selecciona un ejercicio para ver sus series.")
        self.lbl_series_info.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))

        self.lbl_ejercicios = ttk.Label(tab, text="")
        self.lbl_ejercicios.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._load_exercises()

    # ── Pestana Bancos ─────────────────────────────────────────────────────────

    def _build_banks_tab(self, tab, nb):
        nb.add(tab, text="Bancos")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text="Cuentas bancarias de la empresa").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        frame = ttk.Frame(tab)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tv_bancos_empresa = ttk.Treeview(
            frame,
            columns=("descripcion", "iban", "subcuenta", "origen"),
            show="headings", height=10,
        )
        for col, text, width in (
            ("descripcion", "Descripcion", 220),
            ("iban", "IBAN / Cuenta", 220),
            ("subcuenta", "Subcuenta", 110),
            ("origen", "Origen", 90),
        ):
            self.tv_bancos_empresa.heading(col, text=text)
            self.tv_bancos_empresa.column(col, anchor="w" if col != "origen" else "center", width=width)
        self.tv_bancos_empresa.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tv_bancos_empresa.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tv_bancos_empresa.configure(yscrollcommand=scroll.set)
        btns = ttk.Frame(tab)
        btns.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Anadir", style="Primary.TButton",
                   command=self._add_bank).pack(side=tk.LEFT)
        ttk.Button(btns, text="Editar", command=self._edit_bank).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Eliminar", command=self._remove_bank).pack(side=tk.LEFT)
        self.lbl_bancos_info = ttk.Label(tab, text="")
        self.lbl_bancos_info.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._load_bank_records()

    def _build_seguridad_social_tab(self, tab, nb):
        nb.add(tab, text="Seguridad Social")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(4, weight=1)

        ttk.Label(tab, text="NAF (Numero de Afiliacion)").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(tab, textvariable=self.var_naf, width=26).grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(tab, text="Opcional. Se guarda al pulsar 'Guardar'.",
                  foreground="#64748b").grid(row=1, column=0, columnspan=2, sticky="w")

        self._codigo_para_ccc = self._empresa.get("codigo") or self._codigo

        lf = ttk.LabelFrame(tab, text="Codigos de Cuenta de Cotizacion (CCC)")
        lf.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(10, 4))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.tv_ccc = ttk.Treeview(lf, columns=("_id", "ccc", "descripcion", "activo"),
                                   show="headings", selectmode="browse", height=8)
        self.tv_ccc.column("_id", width=0, stretch=False)
        self.tv_ccc.heading("_id", text="")
        for key, txt, w in (("ccc", "CCC", 170), ("descripcion", "Descripcion", 240), ("activo", "Activo", 70)):
            self.tv_ccc.heading(key, text=txt)
            self.tv_ccc.column(key, width=w, anchor="w")
        self.tv_ccc.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tv_ccc.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=4)
        self.tv_ccc.configure(yscrollcommand=sb.set)
        self.tv_ccc.bind("<Double-1>", lambda _e: self._edit_ccc())

        btns = ttk.Frame(lf)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        self._btns_ccc = btns
        ttk.Button(btns, text="Anadir", style="Primary.TButton", command=self._add_ccc).pack(side=tk.LEFT)
        ttk.Button(btns, text="Editar", command=self._edit_ccc).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Eliminar", command=self._del_ccc).pack(side=tk.LEFT)

        if not self._codigo_para_ccc:
            for w in btns.winfo_children():
                try:
                    w.configure(state="disabled")
                except Exception:
                    pass
            ttk.Label(tab, text="Guarda la empresa antes de anadir CCC.",
                      foreground="#b45309").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._refresh_ccc()

    def _refresh_ccc(self):
        if not getattr(self, "tv_ccc", None):
            return
        self.tv_ccc.delete(*self.tv_ccc.get_children())
        cod = getattr(self, "_codigo_para_ccc", None)
        if not cod:
            return
        try:
            filas = self._gestor.listar_ccc(cod)
        except Exception:
            filas = []
        for c in filas:
            self.tv_ccc.insert("", "end", values=(
                c["id"], c.get("ccc", ""), c.get("descripcion", "") or "",
                "Si" if c.get("activo", 1) else "No",
            ))

    def _ccc_seleccionado(self):
        sel = self.tv_ccc.selection()
        if not sel:
            return None
        return {
            "id": self.tv_ccc.set(sel[0], "_id"),
            "ccc": self.tv_ccc.set(sel[0], "ccc"),
            "descripcion": self.tv_ccc.set(sel[0], "descripcion"),
        }

    def _ccc_dialog(self, inicial=None):
        inicial = inicial or {}
        dlg = tk.Toplevel(self)
        dlg.title("Codigo de Cuenta de Cotizacion")
        dlg.resizable(False, False)
        var_ccc = tk.StringVar(value=inicial.get("ccc", ""))
        var_desc = tk.StringVar(value=inicial.get("descripcion", ""))
        res = {}
        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="CCC *").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=var_ccc, width=28).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="Descripcion").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=var_desc, width=28).grid(row=1, column=1, sticky="w", pady=4)

        def _ok():
            if not var_ccc.get().strip():
                messagebox.showerror("Gest2A3Eco", "El CCC es obligatorio.", parent=dlg)
                return
            res["ccc"] = var_ccc.get().strip()
            res["descripcion"] = var_desc.get().strip() or None
            dlg.destroy()

        br = ttk.Frame(dlg, padding=(16, 8))
        br.pack(fill="x")
        ttk.Button(br, text="Cancelar", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(br, text="Guardar", command=_ok).pack(side="right")
        dlg.grab_set()
        dlg.transient(self.winfo_toplevel())
        dlg.wait_window()
        return res or None

    def _add_ccc(self):
        cod = getattr(self, "_codigo_para_ccc", None)
        if not cod:
            return
        data = self._ccc_dialog()
        if not data:
            return
        data["codigo_empresa"] = cod
        self._gestor.upsert_ccc(data)
        self._refresh_ccc()

    def _edit_ccc(self):
        cod = getattr(self, "_codigo_para_ccc", None)
        sel = self._ccc_seleccionado()
        if not cod or not sel:
            return
        data = self._ccc_dialog(sel)
        if not data:
            return
        data["id"] = sel["id"]
        data["codigo_empresa"] = cod
        self._gestor.upsert_ccc(data)
        self._refresh_ccc()

    def _del_ccc(self):
        cod = getattr(self, "_codigo_para_ccc", None)
        sel = self._ccc_seleccionado()
        if not cod or not sel:
            return
        if not messagebox.askyesno("Eliminar CCC", "Eliminar el CCC '" + str(sel.get("ccc")) + "'?",
                                   parent=self.winfo_toplevel()):
            return
        self._gestor.eliminar_ccc(cod, sel["id"])
        self._refresh_ccc()

    def _build_notificaciones_tab(self, tab, nb):
        nb.add(tab, text="Notificaciones electronicas")
        codigo = self._empresa.get("codigo") or self._codigo
        if not codigo:
            ttk.Label(
                tab,
                text="Guarda la empresa antes de configurar las notificaciones electronicas.",
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=20)
            return
        ejercicio = self._empresa.get("ejercicio") or self._ejercicio
        try:
            self._gestor.sembrar_organismos_simulados()
        except Exception:
            pass
        UINotificacionesCliente(tab, self._gestor, codigo, session=self._session).pack(fill="both", expand=True)

    # ── Guardado ───────────────────────────────────────────────────────────────

    def _save(self):
        try:
            if not self._exercise_rows:
                raise ValueError("Debes configurar al menos un ejercicio.")
            self._sync_bank_items_from_records()
            logo_w_txt = self.var_logo_w.get().strip()
            logo_h_txt = self.var_logo_h.get().strip()
            base = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "cuenta_bancaria": self._bank_items[0] if self._bank_items else "",
                "cuentas_bancarias": "\n".join(self._bank_items).strip(),
                "cif": normalizar_nif_cif(self.var_cif.get()),
                "direccion": self.var_dir.get().strip(),
                "cp": self.var_cp.get().strip(),
                "poblacion": self.var_pob.get().strip(),
                "provincia": self.var_prov.get().strip(),
                "pais": normalizar_codigo_pais(self.var_pais.get()) or "ES",
                "telefono": self.var_tel.get().strip(),
                "email": self.var_mail.get().strip(),
                "logo_path": self.var_logo.get().strip(),
                "logo_max_width_mm": _to_float_es(logo_w_txt) if logo_w_txt else None,
                "logo_max_height_mm": _to_float_es(logo_h_txt) if logo_h_txt else None,
                "activo": bool(self.var_activo.get()),
                "naf": self.var_naf.get().strip() or None,
            }
            for row in sorted(self._exercise_rows, key=lambda r: int(r["ejercicio"])):
                item = dict(base)
                item.update(row)
                eje = int(row["ejercicio"])
                series = self._series_por_ejercicio.get(eje, [])
                normales = [s for s in series if not s["es_rectificativa"]]
                rectif   = [s for s in series if s["es_rectificativa"]]
                if normales:
                    item["serie_emitidas"]          = normales[0]["nombre"]
                    item["siguiente_num_emitidas"]   = normales[0]["siguiente_num"]
                if rectif:
                    item["serie_emitidas_rect"]           = rectif[0]["nombre"]
                    item["siguiente_num_emitidas_rect"]    = rectif[0]["siguiente_num"]
                self._gestor.upsert_empresa(item)

            for eje_str, series in self._series_por_ejercicio.items():
                try:
                    eje = int(eje_str)
                except Exception:
                    continue
                for s in (series or []):
                    try:
                        self._gestor.upsert_serie_emitida(
                            base["codigo"], eje,
                            s["nombre"],
                            int(s.get("siguiente_num") or 1),
                            int(s.get("es_rectificativa") or 0),
                        )
                    except Exception:
                        pass

            # Siempre guardar/limpiar (aunque este vacia) para que el DELETE persista
            self._gestor.reemplazar_cuentas_bancarias(base["codigo"], 0, self._bank_records)

            messagebox.showinfo("Gest2A3Eco", "Configuracion guardada correctamente.")
            self._on_back()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc))

    def _request_delete(self):
        codigo = self.var_codigo.get().strip() or str(self._empresa.get("codigo") or "")
        if not codigo:
            return
        if not messagebox.askyesno(
            "Gest2A3Eco",
            f"Se eliminara la empresa {codigo} con todos sus ejercicios.\nContinuar?",
        ):
            return
        try:
            for eje in self._gestor.listar_ejercicios_empresa(codigo):
                self._gestor.eliminar_empresa(codigo, eje)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc))
            return
        self._on_deleted()

    # ── Ejercicios ─────────────────────────────────────────────────────────────

    def _exercise_from_row(self, row: dict) -> dict:
        data = dict(row)
        return {
            "ejercicio":                    int(data.get("ejercicio") or self._ejercicio or datetime.now().year),
            "serie_emitidas":               str(data.get("serie_emitidas") or "A"),
            "siguiente_num_emitidas":       int(data.get("siguiente_num_emitidas") or 1),
            "serie_emitidas_rect":          str(data.get("serie_emitidas_rect") or "R"),
            "siguiente_num_emitidas_rect":  int(data.get("siguiente_num_emitidas_rect") or 1),
        }

    def _default_series_for_exercise(self, row: dict) -> list:
        return [
            {"nombre": str(row.get("serie_emitidas") or "A"),
             "siguiente_num": int(row.get("siguiente_num_emitidas") or 1),
             "es_rectificativa": 0},
            {"nombre": str(row.get("serie_emitidas_rect") or "R"),
             "siguiente_num": int(row.get("siguiente_num_emitidas_rect") or 1),
             "es_rectificativa": 1},
        ]

    def _load_exercises(self):
        self._exercise_rows = []
        self._series_por_ejercicio = {}
        codigo = str(self._empresa.get("codigo") or "")
        if self._gestor and codigo:
            try:
                rows = [dict(x) for x in self._gestor.listar_empresas()
                        if str(x.get("codigo") or "") == codigo]
            except Exception:
                rows = []
            for row in sorted(rows, key=lambda r: int(r.get("ejercicio") or 0)):
                ej_row = self._exercise_from_row(row)
                self._exercise_rows.append(ej_row)
                eje = ej_row["ejercicio"]
                try:
                    series_db = self._gestor.listar_series_emitidas(codigo, eje)
                    if series_db:
                        self._series_por_ejercicio[eje] = [
                            {"nombre": s["nombre"],
                             "siguiente_num": s["siguiente_num"],
                             "es_rectificativa": int(s["es_rectificativa"])}
                            for s in series_db
                        ]
                    else:
                        self._series_por_ejercicio[eje] = self._default_series_for_exercise(ej_row)
                except Exception:
                    self._series_por_ejercicio[eje] = self._default_series_for_exercise(ej_row)
        if not self._exercise_rows:
            ej_row = self._exercise_from_row(self._empresa)
            self._exercise_rows.append(ej_row)
            self._series_por_ejercicio[ej_row["ejercicio"]] = self._default_series_for_exercise(ej_row)
        self._refresh_exercises_tree()

    def _refresh_exercises_tree(self):
        self.tv_ejercicios.delete(*self.tv_ejercicios.get_children())
        for row in self._exercise_rows:
            ejercicio = int(row["ejercicio"])
            self.tv_ejercicios.insert("", "end", iid=str(ejercicio), values=(ejercicio,))
        self.lbl_ejercicios.configure(text=f"Ejercicios configurados: {len(self._exercise_rows)}")
        if self._exercise_rows:
            first = str(int(self._exercise_rows[-1]["ejercicio"]))
            self.tv_ejercicios.selection_set(first)
            self._refresh_series_tree(int(first))
        else:
            self._refresh_series_tree(None)

    def _on_ejercicio_selected(self):
        self._refresh_series_tree(self._selected_exercise())

    def _refresh_series_tree(self, ejercicio: int | None):
        self.tv_series.delete(*self.tv_series.get_children())
        if ejercicio is None:
            self.lbl_series_info.configure(text="Selecciona un ejercicio para ver sus series.")
            return
        series = self._series_por_ejercicio.get(ejercicio, [])
        for idx, s in enumerate(series):
            tipo = "Rectificativa" if s["es_rectificativa"] else "Normal"
            self.tv_series.insert("", "end", iid=str(idx),
                                  values=(s["nombre"], s["siguiente_num"], tipo))
        self.lbl_series_info.configure(
            text=f"Series configuradas para {ejercicio}: {len(series)}")

    def _selected_exercise(self) -> int | None:
        sel = self.tv_ejercicios.selection()
        try:
            return int(sel[0]) if sel else None
        except Exception:
            return None

    def _add_exercise(self):
        top = tk.Toplevel(self)
        top.title("Nuevo ejercicio")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        var_ej = tk.StringVar(value="2025")
        ttk.Label(frm, text="Ejercicio (ano)").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var_ej, width=12).grid(row=0, column=1, sticky="w", pady=4)
        result = {"value": None}

        def _ok():
            try:
                eje = int(var_ej.get().strip())
            except Exception:
                messagebox.showerror("Gest2A3Eco", "Ejercicio invalido.", parent=top)
                return
            if any(int(r["ejercicio"]) == eje for r in self._exercise_rows):
                messagebox.showwarning("Gest2A3Eco", "Ese ejercicio ya existe.", parent=top)
                return
            result["value"] = eje
            top.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Crear", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()
        if not result["value"]:
            return
        eje = result["value"]
        payload = {"ejercicio": eje, "serie_emitidas": "A", "siguiente_num_emitidas": 1,
                   "serie_emitidas_rect": "R", "siguiente_num_emitidas_rect": 1}
        self._exercise_rows.append(payload)
        self._exercise_rows.sort(key=lambda r: int(r["ejercicio"]))
        self._series_por_ejercicio[eje] = [
            {"nombre": "A", "siguiente_num": 1, "es_rectificativa": 0},
            {"nombre": "R", "siguiente_num": 1, "es_rectificativa": 1},
        ]
        self._refresh_exercises_tree()
        self.tv_ejercicios.selection_set(str(eje))
        self._refresh_series_tree(eje)

    def _remove_exercise(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            return
        if len(self._exercise_rows) <= 1:
            messagebox.showwarning("Gest2A3Eco", "Debe existir al menos un ejercicio.")
            return
        self._exercise_rows = [r for r in self._exercise_rows if int(r["ejercicio"]) != ejercicio]
        self._series_por_ejercicio.pop(ejercicio, None)
        self._refresh_exercises_tree()

    # ── Series ─────────────────────────────────────────────────────────────────

    def _selected_serie_index(self) -> int | None:
        sel = self.tv_series.selection()
        try:
            return int(sel[0]) if sel else None
        except Exception:
            return None

    def _serie_editor(self, initial=None):
        data = dict(initial or {"nombre": "", "siguiente_num": 1, "es_rectificativa": 0})
        top = tk.Toplevel(self)
        top.title("Serie")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        var_nombre = tk.StringVar(value=str(data.get("nombre") or ""))
        var_sig    = tk.StringVar(value=str(data.get("siguiente_num") or 1))
        var_rect   = tk.BooleanVar(value=bool(data.get("es_rectificativa")))
        ttk.Label(frm, text="Nombre serie").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var_nombre, width=16).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="Siguiente numero").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var_sig, width=10).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="Es rectificativa").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Checkbutton(frm, variable=var_rect).grid(row=2, column=1, sticky="w", pady=4)
        result = {"value": None}

        def _ok():
            nombre = var_nombre.get().strip()
            if not nombre:
                messagebox.showerror("Gest2A3Eco", "El nombre de la serie no puede estar vacio.", parent=top)
                return
            try:
                sig = int(var_sig.get().strip() or "1")
            except Exception:
                messagebox.showerror("Gest2A3Eco", "Siguiente numero invalido.", parent=top)
                return
            result["value"] = {"nombre": nombre, "siguiente_num": sig,
                                "es_rectificativa": 1 if var_rect.get() else 0}
            top.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()
        return result["value"]

    def _add_serie(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            messagebox.showwarning("Gest2A3Eco", "Selecciona un ejercicio primero.")
            return
        payload = self._serie_editor()
        if not payload:
            return
        series = self._series_por_ejercicio.setdefault(ejercicio, [])
        if any(s["nombre"] == payload["nombre"] for s in series):
            messagebox.showwarning("Gest2A3Eco", "Ya existe una serie con ese nombre en este ejercicio.")
            return
        series.append(payload)
        self._refresh_series_tree(ejercicio)

    def _edit_serie(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            return
        idx = self._selected_serie_index()
        if idx is None:
            return
        series = self._series_por_ejercicio.get(ejercicio, [])
        if idx >= len(series):
            return
        payload = self._serie_editor(series[idx])
        if not payload:
            return
        if payload["nombre"] != series[idx]["nombre"] and any(s["nombre"] == payload["nombre"] for s in series):
            messagebox.showwarning("Gest2A3Eco", "Ya existe una serie con ese nombre en este ejercicio.")
            return
        series[idx] = payload
        self._refresh_series_tree(ejercicio)

    def _remove_serie(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            return
        idx = self._selected_serie_index()
        if idx is None:
            return
        series = self._series_por_ejercicio.get(ejercicio, [])
        if idx >= len(series):
            return
        if len(series) <= 1:
            messagebox.showwarning("Gest2A3Eco", "Debe existir al menos una serie por ejercicio.")
            return
        del series[idx]
        self._refresh_series_tree(ejercicio)

    # ── Bancos ─────────────────────────────────────────────────────────────────

    def _bank_storage_exercise(self) -> int:
        try:
            return max(int(r["ejercicio"]) for r in self._exercise_rows)
        except Exception:
            return int(self._empresa.get("ejercicio") or 0)

    def _load_bank_records(self):
        codigo = str(self._empresa.get("codigo") or "")
        if self._gestor and codigo:
            for ejercicio in (0, self._bank_storage_exercise()):
                try:
                    rows = self._gestor.listar_cuentas_bancarias(codigo, ejercicio)
                except Exception:
                    rows = []
                if rows:
                    self._bank_records = [
                        {"descripcion": str(r.get("descripcion") or ""),
                         "iban": str(r.get("iban") or ""),
                         "subcuenta_contable": str(r.get("subcuenta_contable") or ""),
                         "origen": str(r.get("origen") or ""),
                         "principal": bool(r.get("principal"))}
                        for r in rows
                    ]
                    self._sync_bank_items_from_records()
                    self._refresh_banks_tree()
                    return
        # Legacy fallback
        for idx, line in enumerate(str(self._empresa.get("cuentas_bancarias") or self._empresa.get("cuenta_bancaria") or "").replace(";", "\n").replace(",", "\n").splitlines()):
            value = line.strip()
            if not value:
                continue
            self._bank_records.append({"descripcion": value, "iban": value,
                                       "subcuenta_contable": "", "origen": "legacy",
                                       "principal": idx == 0})
        self._sync_bank_items_from_records()
        self._refresh_banks_tree()

    def _sync_bank_items_from_records(self):
        self._bank_items = [
            str(r.get("iban") or r.get("descripcion") or "").strip()
            for r in self._bank_records
            if str(r.get("iban") or r.get("descripcion") or "").strip()
        ]

    def _refresh_banks_tree(self):
        self.tv_bancos_empresa.delete(*self.tv_bancos_empresa.get_children())
        for idx, rec in enumerate(self._bank_records):
            self.tv_bancos_empresa.insert("", "end", iid=str(idx), values=(
                rec.get("descripcion", ""), rec.get("iban", ""),
                rec.get("subcuenta_contable", ""), rec.get("origen", ""),
            ))
        if hasattr(self, "lbl_bancos_info"):
            self.lbl_bancos_info.configure(text=f"Cuentas bancarias: {len(self._bank_records)}")

    def _selected_bank_index(self) -> int | None:
        sel = self.tv_bancos_empresa.selection()
        return int(sel[0]) if sel else None

    def _bank_editor(self, initial=None, excluding_subcuenta: str = ""):
        data = dict(initial or {})

        # Subcuentas tipo banco del maestro con su descripcion
        banco_info: list[tuple[str, str]] = []  # (subcuenta, nombre)
        try:
            rows = self._gestor.listar_maestro_subcuentas_empresa(
                self._codigo, tipo="banco", activo=None
            )
            banco_info = [
                (str(r.get("subcuenta") or ""), str(r.get("nombre_subcuenta") or ""))
                for r in rows if r.get("subcuenta")
            ]
        except Exception:
            banco_info = []

        # Subcuentas ya asignadas a otras cuentas bancarias
        used: set[str] = {
            str(r.get("subcuenta_contable") or "").strip()
            for r in self._bank_records
            if str(r.get("subcuenta_contable") or "").strip()
        }
        exc = (excluding_subcuenta or "").strip()
        if exc:
            used.discard(exc)

        # Mapas display <-> subcuenta para las disponibles
        display_to_sub: dict[str, str] = {}
        sub_to_display: dict[str, str] = {}
        for sub, nombre in banco_info:
            if sub in used:
                continue
            display = f"{sub}  —  {nombre}" if nombre else sub
            display_to_sub[display] = sub
            sub_to_display[sub] = display

        available_displays = list(display_to_sub.keys())
        current_sub = str(data.get("subcuenta_contable") or "")
        current_display = sub_to_display.get(current_sub, current_sub)

        top = tk.Toplevel(self)
        top.title("Cuenta bancaria")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        vars_map = {
            "descripcion":        tk.StringVar(value=str(data.get("descripcion") or "")),
            "iban":               tk.StringVar(value=str(data.get("iban") or "")),
            "subcuenta_contable": tk.StringVar(value=current_display),
            "origen":             tk.StringVar(value=str(data.get("origen") or "manual")),
        }
        labels = (("descripcion", "Descripcion"), ("iban", "IBAN / Cuenta"),
                  ("subcuenta_contable", "Subcuenta contable"), ("origen", "Origen"))
        for idx, (key, text) in enumerate(labels):
            ttk.Label(frm, text=text).grid(row=idx, column=0, sticky="w", pady=4, padx=(0, 8))
            if key == "origen":
                ttk.Combobox(frm, textvariable=vars_map[key],
                             values=("manual", "a3", "mixto"),
                             state="readonly", width=20).grid(
                    row=idx, column=1, columnspan=2, sticky="w", pady=4)
            elif key == "subcuenta_contable":
                ttk.Combobox(frm, textvariable=vars_map[key],
                             values=available_displays, width=42).grid(
                    row=idx, column=1, sticky="w", pady=4, padx=(0, 6))
                if not banco_info:
                    hint = "(Sin cuentas tipo banco en el maestro)"
                elif not available_displays:
                    hint = "(Todas las cuentas banco ya asignadas)"
                else:
                    hint = ""
                if hint:
                    ttk.Label(frm, text=hint, foreground="#94a3b8").grid(
                        row=idx, column=2, sticky="w", pady=4)
            else:
                ttk.Entry(frm, textvariable=vars_map[key], width=34).grid(
                    row=idx, column=1, columnspan=2, sticky="w", pady=4)
        result = {"value": None}

        def _ok():
            raw = {k: v.get().strip() for k, v in vars_map.items()}
            if not any(raw.values()):
                top.destroy()
                return
            sub_display = raw.get("subcuenta_contable", "")
            sub = display_to_sub.get(sub_display, sub_display)
            if sub and sub in used:
                messagebox.showwarning(
                    "Subcuenta en uso",
                    f"La subcuenta {sub} ya esta asignada a otra cuenta bancaria.",
                    parent=top,
                )
                return
            raw["subcuenta_contable"] = sub
            result["value"] = raw
            top.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=len(labels), column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()
        return result["value"]

    def _add_bank(self):
        payload = self._bank_editor({"origen": "manual"}, excluding_subcuenta="")
        if payload:
            payload["principal"] = not self._bank_records
            self._bank_records.append(payload)
            self._sync_bank_items_from_records()
            self._refresh_banks_tree()

    def _edit_bank(self):
        idx = self._selected_bank_index()
        if idx is None:
            return
        current = self._bank_records[idx] if idx < len(self._bank_records) else {
            "descripcion": "", "iban": "", "origen": "legacy"}
        payload = self._bank_editor(
            current,
            excluding_subcuenta=str(current.get("subcuenta_contable") or ""),
        )
        if payload:
            payload["principal"] = bool(current.get("principal")) or idx == 0
            self._bank_records[idx] = payload
            self._sync_bank_items_from_records()
            self._refresh_banks_tree()

    def _remove_bank(self):
        idx = self._selected_bank_index()
        if idx is None:
            return
        if idx < len(self._bank_records):
            del self._bank_records[idx]
            if self._bank_records:
                self._bank_records[0]["principal"] = True
        self._refresh_banks_tree()

    # ── Importacion A3 ─────────────────────────────────────────────────────────

    def _normalize_identifier_var(self, var: tk.StringVar):
        current = var.get()
        normalized = normalizar_nif_cif(current)
        if current != normalized:
            var.set(normalized)

    def _normalize_country_var(self, var: tk.StringVar):
        current = var.get()
        normalized = normalizar_codigo_pais(current) or "ES"
        if current != normalized:
            var.set(normalized)

    def _choose_logo(self):
        path = filedialog.askopenfilename(
            title="Seleccionar logo (JPG)",
            filetypes=[("JPEG", "*.jpg;*.jpeg"), ("Todos", "*.*")],
        )
        if path:
            self.var_logo.set(path)

    def _browse_a3_companies(self):
        try:
            empresas = listar_empresas_a3()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No se pudo leer el directorio A3: {exc}")
            return
        if not empresas:
            messagebox.showinfo("Gest2A3Eco",
                "No se ha encontrado ningun directorio de empresas A3 (TECODIR.DAT).")
            return
        top = tk.Toplevel(self)
        top.title("Seleccionar empresa A3")
        top.transient(self)
        top.grab_set()
        top.resizable(True, True)
        frm = ttk.Frame(top, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=1)
        var_buscar = tk.StringVar()
        ttk.Label(frm, text="Buscar por nombre, CIF o codigo:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        entry_buscar = ttk.Entry(frm, textvariable=var_buscar, width=60)
        entry_buscar.grid(row=0, column=1, sticky="ew", pady=(0, 4), padx=(6, 0))
        cols = ("codigo", "nombre", "cif")
        tree = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse", height=18)
        tree.heading("codigo", text="Codigo")
        tree.heading("nombre", text="Nombre")
        tree.heading("cif", text="CIF/NIF")
        tree.column("codigo", width=80, stretch=False)
        tree.column("nombre", width=340)
        tree.column("cif", width=100, stretch=False)
        tree.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        scroll = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        scroll.grid(row=1, column=2, sticky="ns", pady=(6, 0))
        tree.configure(yscrollcommand=scroll.set)
        selected_code: list = [None]
        visibles: list = []

        def _render():
            filtro = (var_buscar.get() or "").strip().lower()
            tree.delete(*tree.get_children())
            visibles.clear()
            for emp in empresas:
                texto = f"{emp.get('codigo','')} {emp.get('nombre','')} {emp.get('cif','')}".lower()
                if filtro and filtro not in texto:
                    continue
                visibles.append(emp)
                tree.insert("", tk.END, iid=emp["codigo"],
                            values=(emp["codigo"], emp.get("nombre", ""), emp.get("cif", "")))

        def _on_select_ok(_event=None):
            sel = tree.selection()
            if not sel:
                return
            selected_code[0] = sel[0]
            top.destroy()

        var_buscar.trace_add("write", lambda *_: _render())
        tree.bind("<Double-1>", _on_select_ok)
        tree.bind("<Return>", _on_select_ok)
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Seleccionar", style="Primary.TButton",
                   command=_on_select_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        _render()
        _center_window(top, self)
        entry_buscar.focus_set()
        top.wait_window()
        if selected_code[0]:
            self.var_codigo.set(selected_code[0])
            self._import_from_a3()

    def _import_from_a3(self):
        try:
            data = importar_empresa_desde_a3(self.var_codigo.get())
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc))
            return
        if data.get("codigo"):
            self.var_codigo.set(str(data["codigo"]))
        for field, var in (("nombre", self.var_nombre), ("cif", self.var_cif),
                           ("direccion", self.var_dir), ("cp", self.var_cp),
                           ("poblacion", self.var_pob), ("provincia", self.var_prov),
                           ("telefono", self.var_tel), ("email", self.var_mail)):
            if data.get(field):
                val = normalizar_nif_cif(data[field]) if field == "cif" else str(data[field])
                var.set(val)
        if data.get("digitos_plan"):
            self.var_dig.set(str(data["digitos_plan"]))
        self.var_a3_info.set("Importacion A3 completada.\n" + str(data.get("_a3_info") or "Datos basicos detectados."))
        self._set_a3_preview(data)

    def _update_banks_from_a3(self):
        codigo = self._codigo
        if not codigo:
            messagebox.showwarning("Gest2A3Eco", "Introduce primero el codigo A3 de la empresa.")
            return
        try:
            data = importar_empresa_desde_a3(codigo)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc))
            return
        bank_records = data.get("bank_records") or []
        if not bank_records:
            messagebox.showinfo("Gest2A3Eco", "No se han detectado cuentas bancarias legibles en A3.")
            return
        codigo_a3 = str(data.get("codigo") or codigo)
        if self._gestor:
            try:
                n = self._gestor.reemplazar_cuentas_bancarias(codigo_a3, 0, bank_records)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc))
                return
            messagebox.showinfo("Gest2A3Eco",
                f"Cuentas bancarias actualizadas desde A3: {n} registros.")
        self._bank_records = [dict(item) for item in bank_records]
        self._sync_bank_items_from_records()
        self._refresh_banks_tree()

    def _set_a3_preview(self, data: dict | None):
        payload = dict(data or {})
        ban_labels = payload.get("_ban_labels") or []
        ban_text = (", ".join(ban_labels) if ban_labels
                    else "(no detectadas — introduzca manualmente en pestana Bancos)")
        lines = [
            "=== Datos importados desde A3 ===",
            f"Codigo A3:        {payload.get('codigo', '')}",
            f"Razon Social:     {payload.get('nombre', '')}",
            f"CIF/NIF:          {payload.get('cif', '')}",
            f"Domicilio:        {payload.get('direccion', '')}",
            f"Cod. Postal:      {payload.get('cp', '')}",
            f"Poblacion:        {payload.get('poblacion', '')}",
            f"Provincia:        {payload.get('provincia', '')}",
            f"Telefono:         {payload.get('telefono', '')}",
            f"Email:            {payload.get('email', '')}",
            f"Ejercicio:        {payload.get('ejercicio', '')}",
            f"Digitos plan:     {payload.get('digitos_plan', '')}",
            f"Plan de cuentas:  {len(payload.get('plan_cuentas') or [])} subcuentas importadas",
            f"Bancos (A3):      {ban_text}",
            "",
            "--- Origen de los datos ---",
            str(payload.get("_a3_info") or "Sin detalle."),
        ]
        self.txt_a3_preview.configure(state="normal")
        self.txt_a3_preview.delete("1.0", tk.END)
        self.txt_a3_preview.insert("1.0", "\n".join(lines).strip() + "\n")
        self.txt_a3_preview.configure(state="disabled")
