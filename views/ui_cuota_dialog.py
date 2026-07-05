"""Dialogo para crear o editar una cuota periodica."""
from __future__ import annotations

import json
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from utils.ui_facturas_emitidas_helpers import fmt2, round2, to_float


IVA_OPCIONES = [21, 10, 4, 0]
PERIODICIDADES = ["mensual", "bimestral", "trimestral", "semestral", "anual"]


def _center_window(win, parent=None):
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if parent is None:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        else:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        win.geometry(f"+{max(x,0)}+{max(y,0)}")
    except Exception:
        pass


class _DatePickerEntry(ttk.Frame):
    """Campo de fecha con boton de calendario integrado."""

    def __init__(self, parent, variable: tk.StringVar, **kwargs):
        super().__init__(parent, **kwargs)
        self._var = variable
        ttk.Entry(self, textvariable=variable, width=12).pack(side=tk.LEFT)
        ttk.Button(self, text="...", width=3, command=self._pick).pack(side=tk.LEFT, padx=2)

    def _pick(self):
        from views.ui_facturas_emitidas import DatePicker
        try:
            d = datetime.strptime(self._var.get().strip(), "%d/%m/%Y").date()
        except Exception:
            d = date.today()
        dlg = DatePicker(self.winfo_toplevel(), initial=d)
        if dlg.result:
            self._var.set(dlg.result.strftime("%d/%m/%Y"))


class CuotaDialog(tk.Toplevel):
    """Dialogo modal para crear o editar una cuota periodica."""

    def __init__(self, parent, cuota: dict | None = None,
                 series: list[str] | None = None,
                 terceros: list[dict] | None = None,
                 empresa_defaults: dict | None = None):
        super().__init__(parent)
        self.title("Cuota periodica" if not cuota or not cuota.get("id") else "Editar cuota")
        self.resizable(True, True)
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = max(960, int(sw * 0.65))
            h = max(740, int(sh * 0.78))
            self.geometry(f"{w}x{h}")
            self.minsize(860, 660)
        except Exception:
            pass
        self.result = None
        self._cuota = dict(cuota or {})
        self._series = series or []
        self._terceros = terceros or []
        self._empresa_defaults = empresa_defaults or {}
        self._lineas: list[dict] = list(self._cuota.get("lineas") or [])
        self._build()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    # ── Construccion UI ───────────────────────────────────────────────────────

    def _build(self):
        c = self._cuota
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill="both", expand=True)
        vscroll.pack(side=tk.RIGHT, fill="y")
        frm = ttk.Frame(canvas, padding=12)
        cwin = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_w(_e):
            canvas.itemconfigure(cwin, width=_e.width)

        def _mwheel(_e):
            try:
                canvas.yview_scroll(int(-_e.delta / 120), "units")
            except Exception:
                pass

        frm.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync_w)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _mwheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        row = 0

        # ── Tercero ──────────────────────────────────────────────────────────
        ttk.Label(frm, text="Cliente", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=(0, 2))
        row += 1

        ttk.Label(frm, text="Seleccione cliente").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_tercero = tk.StringVar()
        self._tercero_values: list[str] = []
        self._tercero_by_label: dict[str, dict] = {}
        for t in self._terceros:
            nif = str(t.get("nif") or "").strip()
            nombre = str(t.get("nombre") or "").strip()
            lbl = f"{nif} – {nombre}" if nif else nombre
            self._tercero_values.append(lbl)
            self._tercero_by_label[lbl] = t
        self.cb_tercero = ttk.Combobox(frm, textvariable=self.var_tercero,
                                        values=self._tercero_values, width=46)
        self.cb_tercero.grid(row=row, column=1, columnspan=3, padx=4, pady=3, sticky="w")
        self.cb_tercero.bind("<KeyRelease>", self._filter_terceros)
        self.cb_tercero.bind("<<ComboboxSelected>>", self._on_tercero_selected)
        row += 1

        ttk.Label(frm, text="NIF").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_nif = tk.StringVar(value=c.get("nif") or "")
        ttk.Entry(frm, textvariable=self.var_nif, width=20).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Nombre").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_nombre = tk.StringVar(value=c.get("nombre") or "")
        ttk.Entry(frm, textvariable=self.var_nombre, width=40).grid(row=row, column=1, columnspan=3, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Subcuenta cliente").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_subcuenta = tk.StringVar(value=c.get("subcuenta_cliente") or "")
        ttk.Entry(frm, textvariable=self.var_subcuenta, width=20).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=5, sticky="ew", pady=6)
        row += 1

        # ── Descripcion y configuracion ───────────────────────────────────────
        ttk.Label(frm, text="Facturacion", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=(0, 2))
        row += 1

        ttk.Label(frm, text="Descripcion").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_desc = tk.StringVar(value=c.get("descripcion") or "")
        ttk.Entry(frm, textvariable=self.var_desc, width=46).grid(row=row, column=1, columnspan=3, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Serie").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_serie = tk.StringVar(value=c.get("serie") or (self._series[0] if self._series else ""))
        cb_serie = ttk.Combobox(frm, textvariable=self.var_serie, values=self._series, width=10,
                                 state="readonly" if self._series else "normal")
        cb_serie.grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Forma de pago").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_forma_pago = tk.StringVar(value=c.get("forma_pago") or "")
        ttk.Entry(frm, textvariable=self.var_forma_pago, width=30).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Cuenta bancaria").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        _cuenta_init = (c.get("cuenta_bancaria")
                        or self._empresa_defaults.get("cuenta_bancaria") or "")
        self.var_cuenta = tk.StringVar(value=_cuenta_init)
        ttk.Entry(frm, textvariable=self.var_cuenta, width=30).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Observaciones").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_obs = tk.StringVar(value=c.get("observaciones") or "")
        ttk.Entry(frm, textvariable=self.var_obs, width=46).grid(row=row, column=1, columnspan=3, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=5, sticky="ew", pady=6)
        row += 1

        # ── Periodicidad y fechas ─────────────────────────────────────────────
        ttk.Label(frm, text="Periodicidad", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=(0, 2))
        row += 1

        ttk.Label(frm, text="Periodicidad").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_periodicidad = tk.StringVar(value=c.get("periodicidad") or "mensual")
        ttk.Combobox(frm, textvariable=self.var_periodicidad, values=PERIODICIDADES,
                      width=14, state="readonly").grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        today_str = date.today().strftime("%d/%m/%Y")
        ttk.Label(frm, text="Fecha inicio").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_fecha_inicio = tk.StringVar(value=c.get("fecha_inicio") or today_str)
        _DatePickerEntry(frm, self.var_fecha_inicio).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        row += 1

        ttk.Label(frm, text="Fecha fin (opcional)").grid(row=row, column=0, sticky="w", padx=4, pady=3)
        self.var_fecha_fin = tk.StringVar(value=c.get("fecha_fin") or "")
        _DatePickerEntry(frm, self.var_fecha_fin).grid(row=row, column=1, padx=4, pady=3, sticky="w")
        ttk.Label(frm, text="Dejar en blanco = sin vencimiento", foreground="#666").grid(
            row=row, column=2, padx=4, sticky="w")
        row += 1

        self.var_activa = tk.BooleanVar(value=bool(c.get("activa", True)))
        ttk.Checkbutton(frm, text="Cuota activa", variable=self.var_activa).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=3)
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=5, sticky="ew", pady=6)
        row += 1

        # ── Lineas de factura ─────────────────────────────────────────────────
        ttk.Label(frm, text="Lineas de factura", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=(0, 2))
        row += 1

        self._line_vars = {
            "concepto": tk.StringVar(),
            "unidades": tk.StringVar(value="1"),
            "precio": tk.StringVar(),
            "iva": tk.StringVar(value="21"),
            "desc_tipo": tk.StringVar(),
            "desc_val": tk.StringVar(),
        }
        editor = ttk.Frame(frm)
        editor.grid(row=row, column=0, columnspan=5, sticky="ew", padx=4)
        ttk.Label(editor, text="Concepto").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self._line_vars["concepto"], width=26).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(editor, text="Unid.").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self._line_vars["unidades"], width=7).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(editor, text="Precio").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        ttk.Entry(editor, textvariable=self._line_vars["precio"], width=10).grid(row=0, column=5, padx=4, pady=2)
        ttk.Label(editor, text="IVA %").grid(row=0, column=6, padx=4, pady=2, sticky="w")
        ttk.Combobox(editor, textvariable=self._line_vars["iva"],
                      values=[str(x) for x in IVA_OPCIONES], width=6, state="readonly").grid(row=0, column=7, padx=4, pady=2)
        ttk.Button(editor, text="Anadir", style="Primary.TButton",
                   command=self._add_linea).grid(row=0, column=8, padx=6)
        ttk.Button(editor, text="Limpiar", command=self._clear_editor).grid(row=0, column=9, padx=4)
        row += 1

        self.tv = ttk.Treeview(
            frm,
            columns=("concepto", "unidades", "precio", "base", "pct_iva", "cuota_iva"),
            show="headings",
            height=7,
            selectmode="browse",
        )
        for col, head, w in [
            ("concepto", "Concepto", 200),
            ("unidades", "Unid.", 60),
            ("precio", "Precio unit.", 90),
            ("base", "Base", 90),
            ("pct_iva", "% IVA", 60),
            ("cuota_iva", "Cuota IVA", 90),
        ]:
            self.tv.heading(col, text=head)
            self.tv.column(col, width=w, anchor="w" if col == "concepto" else "e")
        self.tv.grid(row=row, column=0, columnspan=5, sticky="nsew", padx=4, pady=4)
        self.tv.bind("<<TreeviewSelect>>", self._on_select_linea)
        row += 1

        bar = ttk.Frame(frm)
        bar.grid(row=row, column=0, columnspan=5, sticky="w", pady=(0, 4))
        ttk.Button(bar, text="Subir", command=self._move_up).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Bajar", command=self._move_down).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Eliminar linea", command=self._del_linea).pack(side=tk.LEFT, padx=4)
        row += 1

        tot = ttk.Frame(frm)
        tot.grid(row=row, column=0, columnspan=5, sticky="w", pady=(2, 8))
        self.lbl_base = ttk.Label(tot, text="Base: 0,00")
        self.lbl_iva = ttk.Label(tot, text="IVA: 0,00")
        self.lbl_total = ttk.Label(tot, text="Total: 0,00", font=("Segoe UI", 10, "bold"))
        for i, lb in enumerate([self.lbl_base, self.lbl_iva, self.lbl_total]):
            lb.grid(row=0, column=i, padx=8)
        row += 1

        # ── Botones finales ───────────────────────────────────────────────────
        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=5, pady=(6, 4))
        ttk.Button(btns, text="Guardar cuota", style="Primary.TButton",
                   command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)

        # Preseleccionar tercero y cargar lineas existentes
        self._preselect_tercero()
        for ln in self._lineas:
            self._insert_linea_tv(ln)
        self._refresh_totales()

    # ── Tercero helpers ───────────────────────────────────────────────────────

    def _filter_terceros(self, _e=None):
        txt = self.var_tercero.get().lower()
        filtered = [v for v in self._tercero_values if txt in v.lower()]
        self.cb_tercero["values"] = filtered or self._tercero_values

    def _on_tercero_selected(self, _e=None):
        lbl = self.var_tercero.get()
        t = self._tercero_by_label.get(lbl)
        if not t:
            return
        self.var_nif.set(t.get("nif") or "")
        self.var_nombre.set(t.get("nombre") or "")
        # Subcuenta cliente: rellenar si esta vacia o si viene del tercero
        sc = str(t.get("subcuenta_cliente") or "").strip()
        if sc:
            self.var_subcuenta.set(sc)
        # Cuenta bancaria: rellenar con default de empresa solo si esta vacia
        if not self.var_cuenta.get().strip():
            cb = str(self._empresa_defaults.get("cuenta_bancaria") or "").strip()
            if cb:
                self.var_cuenta.set(cb)

    def _preselect_tercero(self):
        tid = self._cuota.get("tercero_id")
        nif = self._cuota.get("nif") or ""
        if tid:
            for lbl, t in self._tercero_by_label.items():
                if t.get("id") == tid:
                    self.var_tercero.set(lbl)
                    return
        if nif:
            for lbl, t in self._tercero_by_label.items():
                if str(t.get("nif") or "").strip().upper() == nif.strip().upper():
                    self.var_tercero.set(lbl)
                    return

    # ── Lineas helpers ────────────────────────────────────────────────────────

    def _calc_linea(self, concepto: str, unidades: float, precio: float,
                    pct_iva: float) -> dict:
        base = round2(unidades * precio)
        cuota_iva = round2(base * pct_iva / 100.0) if pct_iva else 0.0
        return {
            "concepto": concepto,
            "unidades": unidades,
            "precio": precio,
            "pct_iva": pct_iva,
            "base": base,
            "cuota_iva": cuota_iva,
        }

    def _insert_linea_tv(self, ln: dict):
        base = to_float(ln.get("base"))
        cuota_iva = to_float(ln.get("cuota_iva"))
        self.tv.insert("", "end", values=(
            ln.get("concepto", ""),
            fmt2(to_float(ln.get("unidades", ln.get("cantidad", 1)))),
            fmt2(to_float(ln.get("precio", ln.get("precio_unitario", 0)))),
            fmt2(base),
            fmt2(to_float(ln.get("pct_iva", 0))),
            fmt2(cuota_iva),
        ), tags=(json.dumps(ln),))

    def _add_linea(self):
        concepto = self._line_vars["concepto"].get().strip()
        if not concepto:
            messagebox.showwarning("Cuota", "Introduce un concepto.", parent=self)
            return
        try:
            unidades = float(self._line_vars["unidades"].get().replace(",", ".") or "1")
            precio = float(self._line_vars["precio"].get().replace(",", ".") or "0")
        except ValueError:
            messagebox.showwarning("Cuota", "Unidades y precio deben ser numericos.", parent=self)
            return
        pct_iva = to_float(self._line_vars["iva"].get())
        # Si hay fila seleccionada, actualizarla; si no, insertar nueva
        sel = self.tv.selection()
        ln = self._calc_linea(concepto, unidades, precio, pct_iva)
        if sel:
            self.tv.delete(sel[0])
        self._lineas_from_tv()  # sincroniza _lineas antes de insertar
        self._lineas.append(ln)
        self._rebuild_tv()
        self._clear_editor()
        self._refresh_totales()

    def _clear_editor(self):
        self._line_vars["concepto"].set("")
        self._line_vars["unidades"].set("1")
        self._line_vars["precio"].set("")
        self._line_vars["iva"].set("21")
        self.tv.selection_remove(*self.tv.selection())

    def _on_select_linea(self, _e=None):
        sel = self.tv.selection()
        if not sel:
            return
        vals = self.tv.item(sel[0], "values")
        if vals:
            self._line_vars["concepto"].set(str(vals[0]))
            try:
                self._line_vars["unidades"].set(str(vals[1]).replace(",", "."))
                self._line_vars["precio"].set(str(vals[2]).replace(",", "."))
                self._line_vars["iva"].set(str(vals[4]).replace(",", "."))
            except Exception:
                pass

    def _del_linea(self):
        sel = self.tv.selection()
        if not sel:
            return
        idx = self.tv.index(sel[0])
        self.tv.delete(sel[0])
        self._lineas_from_tv()
        if 0 <= idx < len(self._lineas):
            self._lineas.pop(idx)
        self._rebuild_tv()
        self._refresh_totales()

    def _move_up(self):
        sel = self.tv.selection()
        if not sel:
            return
        self._lineas_from_tv()
        idx = self.tv.index(sel[0])
        if idx == 0:
            return
        self._lineas[idx - 1], self._lineas[idx] = self._lineas[idx], self._lineas[idx - 1]
        self._rebuild_tv()

    def _move_down(self):
        sel = self.tv.selection()
        if not sel:
            return
        self._lineas_from_tv()
        idx = self.tv.index(sel[0])
        if idx >= len(self._lineas) - 1:
            return
        self._lineas[idx], self._lineas[idx + 1] = self._lineas[idx + 1], self._lineas[idx]
        self._rebuild_tv()

    def _lineas_from_tv(self):
        """Sincroniza self._lineas desde el Treeview (usando los tags)."""
        lineas = []
        for iid in self.tv.get_children():
            tags = self.tv.item(iid, "tags")
            if tags:
                try:
                    lineas.append(json.loads(tags[0]))
                except Exception:
                    pass
        self._lineas = lineas

    def _rebuild_tv(self):
        for iid in self.tv.get_children():
            self.tv.delete(iid)
        for ln in self._lineas:
            self._insert_linea_tv(ln)
        self._refresh_totales()

    def _refresh_totales(self):
        self._lineas_from_tv()
        base = sum(to_float(ln.get("base")) for ln in self._lineas)
        iva = sum(to_float(ln.get("cuota_iva")) for ln in self._lineas)
        total = base + iva
        self.lbl_base.config(text=f"Base: {fmt2(round2(base))}")
        self.lbl_iva.config(text=f"IVA: {fmt2(round2(iva))}")
        self.lbl_total.config(text=f"Total: {fmt2(round2(total))}")

    # ── Guardar ───────────────────────────────────────────────────────────────

    def _ok(self):
        nif = self.var_nif.get().strip()
        nombre = self.var_nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Cuota", "El nombre del cliente es obligatorio.", parent=self)
            return
        fecha_inicio = self.var_fecha_inicio.get().strip()
        if not fecha_inicio:
            messagebox.showwarning("Cuota", "La fecha de inicio es obligatoria.", parent=self)
            return
        self._lineas_from_tv()

        # Buscar tercero_id
        tercero_id = None
        lbl = self.var_tercero.get()
        t = self._tercero_by_label.get(lbl)
        if t:
            tercero_id = t.get("id")

        doc = dict(self._cuota)
        doc.update({
            "codigo_empresa": self._cuota.get("codigo_empresa"),
            "ejercicio": self._cuota.get("ejercicio"),
            "tercero_id": tercero_id,
            "nif": nif,
            "nombre": nombre,
            "descripcion": self.var_desc.get().strip(),
            "subcuenta_cliente": self.var_subcuenta.get().strip(),
            "forma_pago": self.var_forma_pago.get().strip(),
            "cuenta_bancaria": self.var_cuenta.get().strip(),
            "observaciones": self.var_obs.get().strip(),
            "periodicidad": self.var_periodicidad.get(),
            "fecha_inicio": fecha_inicio,
            "fecha_fin": self.var_fecha_fin.get().strip() or None,
            "activa": 1 if self.var_activa.get() else 0,
            "serie": self.var_serie.get().strip(),
            "tipo_operacion": "01",
            "modelo_fiscal": "",
            "lineas": self._lineas,
        })
        self.result = doc
        self.destroy()
