"""Vista de detalle de documento OCR — pantalla estilo Inmatic."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from services.terceros_empresa_fiscal_service import (
    DEDUCCION_NO,
    DEDUCCION_PARCIAL,
    DEDUCCION_TOTAL,
    PROVEEDOR_TIPOS_IVA,
    TIPO_IVA_TOOLTIPS,
    apply_proveedor_deduction_mode,
    get_proveedor_deduction_mode,
    ocr_tipo_to_proveedor,
)

TIPOS_DOCUMENTO = [
    "factura_recibida",
    "factura_simplificada",
    "nota_debito",
    "nota_credito",
    "otro",
]
TIPOS_OPERACION = [
    "interior",
    "intracomunitaria",
    "importacion",
    "exterior",
]

DEDUCCION_LABELS = {
    DEDUCCION_TOTAL: "Si",
    DEDUCCION_NO: "No",
    DEDUCCION_PARCIAL: "Parcial",
}
DEDUCCION_LABELS_INV = {label: key for key, label in DEDUCCION_LABELS.items()}

_LINEA_COLS = [
    ("tipo_iva",        "%IVA",   5),
    ("base",            "Base",  10),
    ("cuota_iva",       "C.IVA", 10),
    ("tipo_recargo",    "%Rec",   5),
    ("cuota_recargo",   "Rec.",  10),
    ("tipo_retencion",  "%Ret",   5),
    ("cuota_retencion", "Ret.",  10),
]


class UIOcrDetalle(tk.Toplevel):
    """Ventana de detalle/revision de un documento OCR."""

    def __init__(
        self,
        master,
        gestor,
        codigo_empresa: str,
        ejercicio: int,
        doc_ids: list[str],
        current_id: str,
        on_close=None,
    ):
        super().__init__(master)
        self.title("Detalle de documento OCR")
        self.geometry("1280x780")
        self.minsize(900, 600)
        self.resizable(True, True)

        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio
        self._on_close = on_close

        self._doc_ids = list(doc_ids)
        self._current_idx = (
            self._doc_ids.index(current_id) if current_id in self._doc_ids else 0
        )
        self._lineas_rows: list[dict] = []

        from controllers.ui_ocr_detalle_controller import UIOcrDetalleController
        self.controller = UIOcrDetalleController(gestor, codigo_empresa, ejercicio, self)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_cerrar)
        self.grab_set()
        self.after_idle(
            lambda: self.controller.load_doc(self._doc_ids[self._current_idx])
        )

    # ── Construccion UI ───────────────────────────────────────────────────────

    def _build(self):
        # Barra navegacion superior
        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=10, pady=(8, 4))

        self._btn_anterior = ttk.Button(nav, text="◀ Anterior", command=self._nav_anterior)
        self._btn_anterior.pack(side="left")
        self._lbl_nav = ttk.Label(nav, text="")
        self._lbl_nav.pack(side="left", padx=10)
        self._btn_siguiente = ttk.Button(nav, text="Siguiente ▶", command=self._nav_siguiente)
        self._btn_siguiente.pack(side="left")

        ttk.Separator(nav, orient="vertical").pack(side="left", padx=10, fill="y")
        self._lbl_estado = ttk.Label(nav, text="", font=("Segoe UI", 9, "bold"))
        self._lbl_estado.pack(side="left")

        # Panel principal partido en dos
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(paned)
        paned.add(left, weight=2)
        self._viewer = _DocViewer(left)
        self._viewer.pack(fill="both", expand=True)

        right_outer = ttk.Frame(paned)
        paned.add(right_outer, weight=3)
        self._build_right_scrollable(right_outer)

        # Barra inferior de acciones
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 6))
        self._build_actions(bottom)

        ttk.Separator(self).pack(fill="x", padx=10)
        self._lbl_avisos = ttk.Label(
            self, text="", wraplength=950, foreground="#666666",
            font=("Segoe UI", 8),
        )
        self._lbl_avisos.pack(fill="x", padx=10, pady=(2, 4))

    def _attach_tooltip(self, widget, text: str):
        _Tooltip(widget, text)

    def _build_right_scrollable(self, outer: ttk.Frame):
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._form = ttk.Frame(canvas)
        _cw = canvas.create_window((0, 0), window=self._form, anchor="nw")

        self._form.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(_cw, width=e.width),
        )
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"),
        )

        self._build_form(self._form)

    def _build_form(self, parent: ttk.Frame):
        pad = {"padx": 6, "pady": 3}

        self._v_nif         = tk.StringVar()
        self._v_nombre      = tk.StringVar()
        self._v_numero      = tk.StringVar()
        self._v_fecha       = tk.StringVar()
        self._v_tipo_doc    = tk.StringVar()
        self._v_tipo_op     = tk.StringVar()
        self._v_base        = tk.StringVar()
        self._v_cuota_iva   = tk.StringVar()
        self._v_recargo     = tk.StringVar()
        self._v_retencion   = tk.StringVar()
        self._v_total       = tk.StringVar()
        self._v_cta_gasto   = tk.StringVar()
        self._v_cta_iva     = tk.StringVar()
        self._v_cta_prov    = tk.StringVar()
        self._v_prov_tipo_iva = tk.StringVar(value=PROVEEDOR_TIPOS_IVA[0])
        self._v_prov_ded_mode = tk.StringVar(value=DEDUCCION_LABELS[DEDUCCION_TOTAL])
        self._v_prov_pct_ded = tk.StringVar(value="100")
        self._v_descripcion = tk.StringVar()
        self._v_tercero_info = tk.StringVar()

        row = 0

        # ── Proveedor ─────────────────────────────────────────────────────────
        row = self._section(parent, row, "PROVEEDOR", pad)

        ttk.Label(parent, text="NIF:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_nif, width=15).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Nombre:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_nombre, width=28).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        btn_f = ttk.Frame(parent)
        btn_f.grid(row=row, column=0, columnspan=4, sticky="w", **pad)
        ttk.Button(btn_f, text="Buscar tercero",
                   command=self.controller.buscar_tercero).pack(side="left", padx=(0, 4))
        ttk.Button(btn_f, text="Crear tercero...",
                   command=self.controller.crear_tercero).pack(side="left")
        ttk.Label(btn_f, textvariable=self._v_tercero_info,
                  foreground="#27ae60", font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
        row += 1

        # ── Factura ───────────────────────────────────────────────────────────
        row = self._section(parent, row, "FACTURA", pad)

        ttk.Label(parent, text="Numero:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_numero, width=18).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Fecha:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_fecha, width=12).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="Tipo documento:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Combobox(parent, textvariable=self._v_tipo_doc,
                     values=TIPOS_DOCUMENTO, state="readonly", width=20).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Tipo operacion:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Combobox(parent, textvariable=self._v_tipo_op,
                     values=TIPOS_OPERACION, state="readonly", width=18).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        # ── Importes globales ─────────────────────────────────────────────────
        row = self._section(parent, row, "IMPORTES", pad)

        ttk.Label(parent, text="Base imponible:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_base, width=12).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Cuota IVA:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_cuota_iva, width=12).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="Cuota recargo:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_recargo, width=12).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Cuota retencion:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_retencion, width=12).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="TOTAL:", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_total, width=12,
                  font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Lineas fiscales ───────────────────────────────────────────────────
        row = self._section(parent, row, "LINEAS FISCALES", pad)

        lf_hdr = ttk.Frame(parent)
        lf_hdr.grid(row=row, column=0, columnspan=4, sticky="w", **pad)
        ttk.Button(lf_hdr, text="+", width=3, command=self._add_linea).pack(side="left", padx=(0, 2))
        ttk.Button(lf_hdr, text="−", width=3, command=self._del_linea).pack(side="left")
        row += 1

        col_hdr = ttk.Frame(parent)
        col_hdr.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6)
        for _, label, w in _LINEA_COLS:
            ttk.Label(col_hdr, text=label, font=("Segoe UI", 8, "bold"),
                      width=w, anchor="center").pack(side="left")
        row += 1

        self._lf_frame = ttk.Frame(parent)
        self._lf_frame.grid(row=row, column=0, columnspan=4, sticky="ew", **pad)
        row += 1

        # ── Contabilidad ──────────────────────────────────────────────────────
        row = self._section(parent, row, "CONTABILIDAD", pad)

        ttk.Label(parent, text="Cta. gasto:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_cta_gasto, width=12).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Label(parent, text="Cta. IVA:").grid(row=row, column=2, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_cta_iva, width=12).grid(
            row=row, column=3, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="Cta. proveedor:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=self._v_cta_prov, width=12).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        row = self._section(parent, row, "FISCALIDAD PROVEEDOR", pad)

        lbl_tipo_iva = ttk.Label(parent, text="Tipo operacion IVA:")
        lbl_tipo_iva.grid(row=row, column=0, sticky="w", **pad)
        self._cb_prov_tipo_iva = ttk.Combobox(
            parent,
            textvariable=self._v_prov_tipo_iva,
            values=list(PROVEEDOR_TIPOS_IVA),
            state="readonly",
            width=24,
        )
        self._cb_prov_tipo_iva.grid(row=row, column=1, sticky="ew", **pad)
        self._cb_prov_tipo_iva.bind("<<ComboboxSelected>>", lambda _e: self._refresh_fiscal_tooltip())
        self._attach_tooltip(lbl_tipo_iva, "Configuracion fiscal de compras aplicada al documento.")
        row += 1

        ttk.Label(parent, text="IVA deducible:").grid(row=row, column=0, sticky="w", **pad)
        self._cb_prov_ded = ttk.Combobox(
            parent,
            textvariable=self._v_prov_ded_mode,
            values=list(DEDUCCION_LABELS.values()),
            state="readonly",
            width=14,
        )
        self._cb_prov_ded.grid(row=row, column=1, sticky="w", **pad)
        self._cb_prov_ded.bind("<<ComboboxSelected>>", lambda _e: self._on_ded_mode_changed())
        ttk.Label(parent, text="% deduccion IVA:").grid(row=row, column=2, sticky="w", **pad)
        self._entry_prov_pct = ttk.Entry(parent, textvariable=self._v_prov_pct_ded, width=12)
        self._entry_prov_pct.grid(row=row, column=3, sticky="ew", **pad)
        self._v_prov_pct_ded.trace_add("write", lambda *_: self._on_ded_pct_changed())
        row += 1

        self._lbl_fiscal_hint = ttk.Label(parent, text="", foreground="#64748b", font=("Segoe UI", 8))
        self._lbl_fiscal_hint.grid(row=row, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))
        row += 1

        # ── Descripcion ───────────────────────────────────────────────────────
        row = self._section(parent, row, "DESCRIPCION", pad)

        ttk.Entry(parent, textvariable=self._v_descripcion, width=50).grid(
            row=row, column=0, columnspan=4, sticky="ew", **pad)
        row += 1

        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        self._refresh_fiscal_tooltip()
        self._on_ded_mode_changed()

    def _section(self, parent, row: int, title: str, pad: dict) -> int:
        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", **pad)
        row += 1
        ttk.Label(parent, text=title, font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", **pad)
        return row + 1

    def _build_actions(self, parent: ttk.Frame):
        ttk.Button(parent, text="Guardar", style="Primary.TButton",
                   command=self.controller.guardar).pack(side="left", padx=(0, 4))
        ttk.Button(parent, text="Validar",
                   command=self.controller.validar).pack(side="left", padx=(0, 4))
        ttk.Button(parent, text="→ Pte. Contabilizar",
                   command=self.controller.enviar_pendiente_contabilizar).pack(
            side="left", padx=(0, 4))
        ttk.Button(parent, text="→ Errores",
                   command=self.controller.enviar_a_error).pack(side="left", padx=(0, 10))
        ttk.Separator(parent, orient="vertical").pack(side="left", padx=4, fill="y")
        ttk.Button(parent, text="Cerrar", command=self._on_cerrar).pack(side="left", padx=(6, 0))

    # ── Lineas fiscales ───────────────────────────────────────────────────────

    def _add_linea(self):
        self._append_linea_row({})

    def _del_linea(self):
        if self._lineas_rows:
            last = self._lineas_rows.pop()
            for w in last.get("_widgets", []):
                w.destroy()

    def _append_linea_row(self, linea: dict):
        r = len(self._lineas_rows)
        row_vars: dict = {}
        ws = []
        for col_idx, (key, _label, w) in enumerate(_LINEA_COLS):
            source_key = "base_imponible" if key == "base" else key
            val = linea.get(source_key, "")
            var = tk.StringVar(value=("" if val in (None, 0, 0.0) else str(val)))
            row_vars[key] = var
            e = ttk.Entry(self._lf_frame, textvariable=var, width=w)
            e.grid(row=r, column=col_idx, padx=2, pady=1, sticky="ew")
            ws.append(e)
        row_vars["_widgets"] = ws
        self._lineas_rows.append(row_vars)

    def clear_lineas(self):
        for row in self._lineas_rows:
            for w in row.get("_widgets", []):
                w.destroy()
        self._lineas_rows.clear()

    def get_lineas(self) -> list[dict]:
        result = []
        for i, row in enumerate(self._lineas_rows):
            result.append({
                "orden":           i,
                "tipo_iva":        _to_float(row["tipo_iva"].get()),
                "base_imponible":  _to_float(row["base"].get()),
                "cuota_iva":       _to_float(row["cuota_iva"].get()),
                "tipo_recargo":    _to_float(row["tipo_recargo"].get()),
                "cuota_recargo":   _to_float(row["cuota_recargo"].get()),
                "tipo_retencion":  _to_float(row["tipo_retencion"].get()),
                "cuota_retencion": _to_float(row["cuota_retencion"].get()),
            })
        return result

    # ── Poblado del formulario ────────────────────────────────────────────────

    def populate(self, doc: dict):
        self._v_nif.set(doc.get("proveedor_nif") or "")
        self._v_nombre.set(doc.get("proveedor_nombre") or "")
        self._v_numero.set(doc.get("numero_factura") or "")
        self._v_fecha.set(doc.get("fecha_factura") or "")
        self._v_tipo_doc.set(doc.get("tipo_documento") or "factura_recibida")
        self._v_tipo_op.set(doc.get("tipo_operacion") or "interior")
        self._v_base.set(_fmt_amount(doc.get("base_imponible")))
        self._v_cuota_iva.set(_fmt_amount(doc.get("cuota_iva")))
        self._v_recargo.set(_fmt_amount(doc.get("cuota_recargo")))
        self._v_retencion.set(_fmt_amount(doc.get("cuota_retencion")))
        self._v_total.set(_fmt_amount(doc.get("total")))
        self._v_cta_gasto.set(doc.get("cuenta_gasto") or "")
        self._v_cta_iva.set(doc.get("cuenta_iva") or "")
        self._v_cta_prov.set(doc.get("cuenta_proveedor") or "")
        proveedor_tipo = doc.get("proveedor_tipo_operacion_iva") or ocr_tipo_to_proveedor(doc.get("tipo_operacion"))
        self.set_proveedor_fiscal_config(
            proveedor_tipo,
            int(doc.get("proveedor_iva_deducible", 1) or 0),
            float(doc.get("proveedor_porcentaje_deduccion_iva", 100.0) or 0.0),
            doc.get("tipo_operacion") or None,
        )
        self._v_descripcion.set(doc.get("descripcion") or "")
        self._v_tercero_info.set("")

        self.clear_lineas()
        for linea in doc.get("lineas") or []:
            self._append_linea_row(linea)

        avisos = list((doc.get("datos_extra") or {}).get("avisos") or [])
        if doc.get("error_mensaje"):
            avisos = [doc["error_mensaje"]] + avisos
        self._lbl_avisos.configure(
            text=" | ".join(str(a) for a in avisos[:5]) if avisos else ""
        )

        estado = doc.get("estado_ocr") or ""
        estado_v = doc.get("estado_validacion") or ""
        self._lbl_estado.configure(text=f"OCR: {estado}  |  Validacion: {estado_v}")

        idx = self._current_idx
        total = len(self._doc_ids)
        self._lbl_nav.configure(text=f"Documento {idx + 1} de {total}")
        self._btn_anterior.configure(state="normal" if idx > 0 else "disabled")
        self._btn_siguiente.configure(
            state="normal" if idx < total - 1 else "disabled"
        )

    def get_form_data(self) -> dict:
        ded_mode = DEDUCCION_LABELS_INV.get(self._v_prov_ded_mode.get(), DEDUCCION_TOTAL)
        fiscal = apply_proveedor_deduction_mode(
            {
                "proveedor_tipo_operacion_iva": self._v_prov_tipo_iva.get(),
            },
            ded_mode,
            self._v_prov_pct_ded.get(),
        )
        return {
            "proveedor_nif":    self._v_nif.get().strip(),
            "proveedor_nombre": self._v_nombre.get().strip(),
            "numero_factura":   self._v_numero.get().strip(),
            "fecha_factura":    self._v_fecha.get().strip(),
            "tipo_documento":   self._v_tipo_doc.get(),
            "tipo_operacion":   self._v_tipo_op.get(),
            "base_imponible":   _to_float(self._v_base.get()),
            "cuota_iva":        _to_float(self._v_cuota_iva.get()),
            "cuota_recargo":    _to_float(self._v_recargo.get()),
            "cuota_retencion":  _to_float(self._v_retencion.get()),
            "total":            _to_float(self._v_total.get()),
            "cuenta_gasto":     self._v_cta_gasto.get().strip(),
            "cuenta_iva":       self._v_cta_iva.get().strip(),
            "cuenta_proveedor": self._v_cta_prov.get().strip(),
            "proveedor_tipo_operacion_iva": fiscal["proveedor_tipo_operacion_iva"],
            "proveedor_iva_deducible": fiscal["proveedor_iva_deducible"],
            "proveedor_porcentaje_deduccion_iva": fiscal["proveedor_porcentaje_deduccion_iva"],
            "descripcion":      self._v_descripcion.get().strip(),
            "lineas":           self.get_lineas(),
        }

    def set_tercero_info(self, texto: str):
        self._v_tercero_info.set(texto)

    def set_cuenta_proveedor(self, subcuenta: str):
        self._v_cta_prov.set(subcuenta)

    def set_cuenta_gasto(self, subcuenta: str):
        self._v_cta_gasto.set(subcuenta)

    def set_proveedor_fiscal_config(self, tipo_iva: str, iva_deducible: int, porcentaje: float, tipo_operacion_ocr: str | None = None):
        self._v_prov_tipo_iva.set(tipo_iva or PROVEEDOR_TIPOS_IVA[0])
        rel = {
            "proveedor_iva_deducible": iva_deducible,
            "proveedor_porcentaje_deduccion_iva": porcentaje,
        }
        mode = get_proveedor_deduction_mode(rel)
        self._v_prov_ded_mode.set(DEDUCCION_LABELS[mode])
        pct_val = 100.0 if porcentaje in (None, "") else float(porcentaje)
        pct_txt = str(int(pct_val)) if pct_val == int(pct_val) else str(pct_val)
        self._v_prov_pct_ded.set(pct_txt)
        if tipo_operacion_ocr:
            self._v_tipo_op.set(tipo_operacion_ocr)
        self._refresh_fiscal_tooltip()
        self._on_ded_mode_changed()

    def _on_ded_mode_changed(self):
        mode = DEDUCCION_LABELS_INV.get(self._v_prov_ded_mode.get(), DEDUCCION_TOTAL)
        if mode == DEDUCCION_NO:
            self._v_prov_pct_ded.set("0")
            self._entry_prov_pct.configure(state="disabled")
        elif mode == DEDUCCION_TOTAL:
            self._v_prov_pct_ded.set("100")
            self._entry_prov_pct.configure(state="disabled")
        else:
            self._entry_prov_pct.configure(state="normal")
            if not self._v_prov_pct_ded.get().strip():
                self._v_prov_pct_ded.set("50")
        self._refresh_fiscal_tooltip()

    def _on_ded_pct_changed(self):
        if DEDUCCION_LABELS_INV.get(self._v_prov_ded_mode.get(), DEDUCCION_TOTAL) != DEDUCCION_PARCIAL:
            return
        try:
            value = float((self._v_prov_pct_ded.get() or "").replace(",", "."))
        except Exception:
            self._lbl_fiscal_hint.configure(text="Introduce un porcentaje numerico entre 0 y 100.", foreground="#b45309")
            return
        if value < 0 or value > 100:
            self._lbl_fiscal_hint.configure(text="El porcentaje de deduccion IVA debe estar entre 0 y 100.", foreground="#b91c1c")
            return
        self._refresh_fiscal_tooltip()

    def _refresh_fiscal_tooltip(self):
        tipo = self._v_prov_tipo_iva.get()
        mode = DEDUCCION_LABELS_INV.get(self._v_prov_ded_mode.get(), DEDUCCION_TOTAL)
        base_text = TIPO_IVA_TOOLTIPS.get(tipo, "Configuracion fiscal del proveedor.")
        if mode == DEDUCCION_NO:
            extra = "El IVA no deducible se integrara como mayor gasto."
        elif mode == DEDUCCION_PARCIAL:
            extra = "Se repartira automaticamente entre 472 y mayor gasto."
        else:
            extra = "El IVA deducible ira integro a 472."
        self._lbl_fiscal_hint.configure(text=f"{base_text} {extra}", foreground="#64748b")

    # ── Visor de documentos ───────────────────────────────────────────────────

    def load_document(self, path: str):
        self._viewer.load(path)

    # ── Navegacion ────────────────────────────────────────────────────────────

    def _nav_anterior(self):
        if self._current_idx > 0:
            self.controller.guardar_silencioso()
            self._current_idx -= 1
            self.controller.load_doc(self._doc_ids[self._current_idx])

    def _nav_siguiente(self):
        if self._current_idx < len(self._doc_ids) - 1:
            self.controller.guardar_silencioso()
            self._current_idx += 1
            self.controller.load_doc(self._doc_ids[self._current_idx])

    def _on_cerrar(self):
        self.controller.guardar_silencioso()
        self.grab_release()
        self.destroy()
        if self._on_close:
            self._on_close()

    # ── Dialogos ─────────────────────────────────────────────────────────────

    def ask_yes_no(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message)

    def ask_string(self, title: str, prompt: str, initial: str = "") -> str | None:
        return _SimpleDialog(self, title, prompt, initial).result

    def open_crear_tercero_dialog(self, nif: str, nombre: str) -> dict | None:
        """Abre el dialog de creacion de tercero. Devuelve dict con tipo y subcuenta, o None."""
        return _CrearTerceroDialog(self, nif=nif, nombre=nombre).result

    def show_info(self, title: str, msg: str):
        messagebox.showinfo(title, msg)

    def show_warning(self, title: str, msg: str):
        messagebox.showwarning(title, msg)

    def show_error(self, title: str, msg: str):
        messagebox.showerror(title, msg)


# ── Visor de documentos (PDF + imagen) ───────────────────────────────────────

class _DocViewer(ttk.Frame):
    """Renderiza PDFs via pymupdf o imagenes via Pillow. Placeholder si faltan librerias."""

    def __init__(self, master):
        super().__init__(master)
        self._fitz_doc = None
        self._pil_img = None
        self._page_num = 0
        self._total_pages = 0
        self._photo = None

        self._canvas = tk.Canvas(self, bg="#c8c8c8", cursor="crosshair")
        self._canvas.pack(fill="both", expand=True)

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", pady=2)
        self._btn_prev = ttk.Button(ctrl, text="◀", width=3, command=self._prev_page)
        self._btn_prev.pack(side="left", padx=4)
        self._lbl_page = ttk.Label(ctrl, text="")
        self._lbl_page.pack(side="left", expand=True)
        self._btn_next = ttk.Button(ctrl, text="▶", width=3, command=self._next_page)
        self._btn_next.pack(side="right", padx=4)

        self._canvas.bind("<Configure>", lambda _e: self._render())

    def load(self, path: str):
        self._fitz_doc = None
        self._pil_img = None
        self._page_num = 0
        self._total_pages = 0
        ext = path.lower().rsplit(".", 1)[-1]
        if ext == "pdf":
            self._load_pdf(path)
        elif ext in ("png", "jpg", "jpeg", "tif", "tiff"):
            self._load_image(path)
        else:
            self._placeholder(f"Tipo no soportado: .{ext}")

    def _load_pdf(self, path: str):
        try:
            import fitz
            self._fitz_doc = fitz.open(path)
            self._total_pages = len(self._fitz_doc)
            self._render()
        except ImportError:
            self._placeholder(
                "Instala pymupdf para previsualizar PDFs.\npip install pymupdf"
            )
        except Exception as exc:
            self._placeholder(f"No se pudo abrir el PDF:\n{exc}")

    def _load_image(self, path: str):
        try:
            from PIL import Image
            self._pil_img = Image.open(path)
            self._total_pages = 1
            self._render()
        except ImportError:
            self._placeholder("Pillow no disponible para previsualizar imagenes.")
        except Exception as exc:
            self._placeholder(f"No se pudo abrir la imagen:\n{exc}")

    def _render(self):
        if self._fitz_doc is not None:
            self._render_pdf()
        elif self._pil_img is not None:
            self._render_image()

    def _render_pdf(self):
        try:
            import fitz
            from PIL import Image, ImageTk
        except ImportError:
            self._placeholder("Instala pymupdf y Pillow para la preview.")
            return

        cw = self._canvas.winfo_width() or 400
        ch = self._canvas.winfo_height() or 500
        page = self._fitz_doc[self._page_num]
        rect = page.rect
        zoom = min(cw / rect.width, ch / rect.height) if rect.width > 0 else 1.0
        zoom = max(0.3, min(zoom, 4.0))

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._photo = ImageTk.PhotoImage(img)

        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, 0, anchor="n", image=self._photo)
        self._lbl_page.configure(
            text=f"Pag. {self._page_num + 1} / {self._total_pages}"
        )
        self._btn_prev.configure(state="normal" if self._page_num > 0 else "disabled")
        self._btn_next.configure(
            state="normal" if self._page_num < self._total_pages - 1 else "disabled"
        )

    def _render_image(self):
        try:
            from PIL import ImageTk
        except ImportError:
            self._placeholder("Pillow no disponible.")
            return

        cw = self._canvas.winfo_width() or 400
        ch = self._canvas.winfo_height() or 500
        img = self._pil_img.copy()
        img.thumbnail((cw, ch))
        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, anchor="center", image=self._photo)
        self._lbl_page.configure(text="Imagen")
        self._btn_prev.configure(state="disabled")
        self._btn_next.configure(state="disabled")

    def _prev_page(self):
        if self._page_num > 0:
            self._page_num -= 1
            self._render()

    def _next_page(self):
        if self._page_num < self._total_pages - 1:
            self._page_num += 1
            self._render()

    def _placeholder(self, msg: str):
        self._canvas.delete("all")
        cw = self._canvas.winfo_width() or 400
        ch = self._canvas.winfo_height() or 300
        self._canvas.create_text(
            cw // 2, ch // 2, text=msg, fill="#555555",
            justify="center", font=("Segoe UI", 10),
        )
        self._lbl_page.configure(text="")


# ── Dialogo simple de entrada de texto ───────────────────────────────────────

class _SimpleDialog(tk.Toplevel):
    def __init__(self, master, title: str, prompt: str, initial: str = ""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        ttk.Label(self, text=prompt, wraplength=300).pack(padx=16, pady=(12, 4))
        self._var = tk.StringVar(value=initial)
        e = ttk.Entry(self, textvariable=self._var, width=40)
        e.pack(padx=16, pady=4)
        e.focus_set()
        e.select_range(0, "end")

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 12))
        ttk.Button(btns, text="Aceptar", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())
        self.wait_window()

    def _ok(self):
        self.result = self._var.get().strip() or None
        self.destroy()


# ── Dialog de creacion de tercero ─────────────────────────────────────────────

class _CrearTerceroDialog(tk.Toplevel):
    """Dialog modal para capturar tipo de tercero y subcuenta al crear desde OCR."""

    _TIPOS = ["proveedor", "acreedor", "cliente"]

    def __init__(self, master, *, nif: str = "", nombre: str = "", subcuenta: str = ""):
        super().__init__(master)
        self.title("Crear tercero")
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        # Campos informativos (solo lectura)
        ttk.Label(frm, text="NIF:").grid(row=0, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Label(frm, text=nif or "—", foreground="#0f172a",
                  font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(frm, text="Nombre:").grid(row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Label(frm, text=nombre or "—", foreground="#0f172a",
                  font=("Segoe UI", 9, "bold")).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Separator(frm, orient="horizontal").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        # Tipo de tercero
        ttk.Label(frm, text="Tipo de tercero:").grid(
            row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self._var_tipo = tk.StringVar(value="proveedor")
        ttk.Combobox(frm, textvariable=self._var_tipo,
                     values=self._TIPOS, state="readonly", width=18).grid(
            row=3, column=1, sticky="w", pady=4)

        # Subcuenta (se rellena al confirmar tipo, editable)
        ttk.Label(frm, text="Subcuenta:").grid(
            row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self._var_subcuenta = tk.StringVar(value=subcuenta)
        self._ent_sub = ttk.Entry(frm, textvariable=self._var_subcuenta, width=20)
        self._ent_sub.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(frm, text="(puedes modificarla)",
                  foreground="#64748b", font=("Segoe UI", 8)).grid(
            row=5, column=1, sticky="w")

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(14, 0), sticky="e")
        ttk.Button(btn_row, text="Crear", command=self._ok).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="left")

        frm.columnconfigure(1, weight=1)
        self.transient(master)
        self.wait_window()

    def _ok(self):
        tipo = self._var_tipo.get().strip()
        subcuenta = self._var_subcuenta.get().strip()
        if not tipo or not subcuenta:
            return
        self.result = {"tipo": tipo, "subcuenta": subcuenta}
        self.destroy()


# ── Utilidades ────────────────────────────────────────────────────────────────

def _to_float(val: str) -> float:
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def _fmt_amount(val) -> str:
    try:
        f = float(val or 0)
        return f"{f:.2f}" if f != 0.0 else ""
    except (ValueError, TypeError):
        return ""


class _Tooltip:
    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self._tip or not self._text:
            return
        x = self._widget.winfo_rootx() + 16
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip,
            text=self._text,
            background="#fff7ed",
            foreground="#7c2d12",
            relief="solid",
            borderwidth=1,
            wraplength=280,
            padx=6,
            pady=6,
        ).pack()
        self._tip = tip

    def _hide(self, _event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None
