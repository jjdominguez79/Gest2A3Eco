"""Dialogo para configurar y ejecutar la generacion de cuotas periodicas pendientes."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk


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


class GenerarCuotasDialog(tk.Toplevel):
    """Dialogo modal que muestra cuotas pendientes y permite seleccionar cuales generar.

    Parametros:
        pendientes  — lista de dicts {cuota: dict, periodos: list[str]} de calcular_cuotas_pendientes()

    Resultado:
        self.result = {
            "fecha_factura": str "dd/mm/yyyy",
            "seleccionados": list of (cuota_id, periodo)
        }
        o None si el usuario cancelo.
    """

    def __init__(self, parent, pendientes: list[dict]):
        super().__init__(parent)
        self.title("Generar cuotas pendientes")
        self.resizable(True, True)
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = max(760, int(sw * 0.52))
            h = max(580, int(sh * 0.62))
            self.geometry(f"{w}x{h}")
            self.minsize(680, 480)
        except Exception:
            pass
        self.result = None
        self._pendientes = pendientes
        self._checks: dict[tuple, tk.BooleanVar] = {}  # (cuota_id, periodo) -> BooleanVar
        self._build()
        self.grab_set()
        self.transient(parent)
        _center_window(self, parent)
        self.wait_window(self)

    # ── Construccion UI ───────────────────────────────────────────────────────

    def _build(self):
        # ── Cabecera ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg="#1e3a5f", padx=12, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Generar facturas de cuotas periodicas",
                 bg="#1e3a5f", fg="white",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(hdr, text="Selecciona la fecha y los periodos a generar. "
                           "Se crearan como borradores.",
                 bg="#1e3a5f", fg="#a8c7e8",
                 font=("Segoe UI", 9)).pack(anchor="w")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)

        # ── Fecha de factura ──────────────────────────────────────────────────
        date_frm = ttk.LabelFrame(body, text="Fecha de factura", padding=6)
        date_frm.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        today_str = date.today().strftime("%d/%m/%Y")
        ttk.Label(date_frm, text="Fecha (dd/mm/aaaa):").pack(side=tk.LEFT, padx=(0, 6))
        self.var_fecha = tk.StringVar(value=today_str)
        ttk.Entry(date_frm, textvariable=self.var_fecha, width=14).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(date_frm, text="...", width=3, command=self._pick_fecha).pack(side=tk.LEFT)

        # ── Botones seleccion ─────────────────────────────────────────────────
        sel_frm = ttk.Frame(body)
        sel_frm.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(sel_frm, text="Seleccionar todo", command=self._sel_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(sel_frm, text="Deseleccionar todo", command=self._desel_all).pack(side=tk.LEFT, padx=4)
        self.lbl_count = ttk.Label(sel_frm, text="")
        self.lbl_count.pack(side=tk.RIGHT, padx=8)

        # ── Tabla de cuotas pendientes ────────────────────────────────────────
        table_frm = ttk.Frame(body)
        table_frm.grid(row=2, column=0, sticky="nsew")
        table_frm.rowconfigure(0, weight=1)
        table_frm.columnconfigure(0, weight=1)

        canvas = tk.Canvas(table_frm, highlightthickness=0)
        vscroll = ttk.Scrollbar(table_frm, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas, padding=4)
        cwin = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_w(_e):
            canvas.itemconfigure(cwin, width=_e.width)

        def _mwheel(_e):
            try:
                canvas.yview_scroll(int(-_e.delta / 120), "units")
            except Exception:
                pass

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync_w)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _mwheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        # Cabecera de columnas
        hdrs = ttk.Frame(inner)
        hdrs.pack(fill="x", pady=(0, 2))
        ttk.Label(hdrs, text="Sel.", width=4, anchor="center").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(hdrs, text="Cliente", width=24, anchor="w", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(hdrs, text="Descripcion", width=22, anchor="w", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(hdrs, text="Periodo", width=10, anchor="w", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(hdrs, text="Periodicidad", width=12, anchor="w", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=2)

        # Una fila por cada (cuota, periodo)
        for item in self._pendientes:
            cuota = item["cuota"]
            cuota_id = cuota["id"]
            nombre = str(cuota.get("nombre") or "").strip() or str(cuota.get("nif") or "")
            descripcion = str(cuota.get("descripcion") or "")
            periodicidad = str(cuota.get("periodicidad") or "mensual")
            # Agrupar visual por cuota (separador y encabezado de cuota)
            grp = ttk.LabelFrame(inner, text=f"  {nombre} — {descripcion}", padding=(6, 2))
            grp.pack(fill="x", pady=3)
            for periodo in sorted(item["periodos"]):
                key = (cuota_id, periodo)
                var = tk.BooleanVar(value=True)
                self._checks[key] = var
                row_frm = ttk.Frame(grp)
                row_frm.pack(fill="x", pady=1)
                ttk.Checkbutton(row_frm, variable=var,
                                 command=self._update_count).pack(side=tk.LEFT, padx=(0, 6))
                ttk.Label(row_frm, text=periodo, width=10).pack(side=tk.LEFT, padx=4)
                ttk.Label(row_frm, text=periodicidad, width=14, foreground="#555").pack(side=tk.LEFT, padx=4)

        self._update_count()

        # ── Botones finales ───────────────────────────────────────────────────
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=8)
        ttk.Button(btns, text="Generar seleccionados", style="Primary.TButton",
                   command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=4)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _pick_fecha(self):
        from datetime import datetime as dt
        try:
            d = dt.strptime(self.var_fecha.get().strip(), "%d/%m/%Y").date()
        except Exception:
            d = date.today()
        from views.ui_facturas_emitidas import DatePicker
        dlg = DatePicker(self, initial=d)
        if dlg.result:
            self.var_fecha.set(dlg.result.strftime("%d/%m/%Y"))

    def _sel_all(self):
        for var in self._checks.values():
            var.set(True)
        self._update_count()

    def _desel_all(self):
        for var in self._checks.values():
            var.set(False)
        self._update_count()

    def _update_count(self):
        n = sum(1 for v in self._checks.values() if v.get())
        total = len(self._checks)
        self.lbl_count.config(text=f"{n} de {total} periodos seleccionados")

    def _ok(self):
        fecha = self.var_fecha.get().strip()
        if not fecha:
            from tkinter import messagebox
            messagebox.showwarning("Generar cuotas", "Introduce una fecha de factura.", parent=self)
            return
        seleccionados = [(cid, p) for (cid, p), var in self._checks.items() if var.get()]
        self.result = {
            "fecha_factura": fecha,
            "seleccionados": seleccionados,
        }
        self.destroy()
