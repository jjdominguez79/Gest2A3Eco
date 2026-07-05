"""Dialogo de visualizacion y edicion del asiento contable de una factura emitida.

Mejora 6: permite ver el asiento contable generado por una factura emitida antes
de contabilizarla/exportarla. Las subcuentas editables se validan contra el maestro
de subcuentas de la empresa.

Estructura del asiento:
  DEBE   : subcuenta_cliente   (importe total - retencion)
  DEBE   : subcuenta_retencion (importe retencion, si procede)
  HABER  : subcuenta_ingreso   (base imponible por tramo IVA)
  HABER  : subcuenta_iva       (cuota IVA por tramo)
  (HABER): subcuenta_re        (cuota recargo equivalencia, si procede)
"""
from __future__ import annotations

import json
import logging
import tkinter as tk
from decimal import Decimal, ROUND_HALF_UP
from tkinter import messagebox, ttk

_log = logging.getLogger(__name__)

# Subcuentas por defecto cuando no hay configuracion
_DEFAULT_IVA_REPERCUTIDO = "47700000"
_DEFAULT_INGRESO          = "70000000"
_DEFAULT_RETENCION        = "47510000"


def _d2(x) -> Decimal:
    try:
        return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _fv(x) -> float:
    if x is None or x == "":
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip().replace("\xa0", "")
    if not s:
        return 0.0
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


class _PedirNombreSubcuentaDialog(tk.Toplevel):
    """Dialogo minimo para pedir el nombre de una subcuenta nueva."""

    def __init__(self, parent, subcuenta: str):
        super().__init__(parent)
        self.title("Nueva subcuenta")
        self.resizable(False, False)
        self.grab_set()
        self.result: str | None = None

        tk.Label(self, text=f"Nombre para la subcuenta {subcuenta}:",
                 font=("Segoe UI", 9)).pack(padx=16, pady=(12, 4))
        self._var = tk.StringVar()
        e = ttk.Entry(self, textvariable=self._var, width=36, font=("Segoe UI", 9))
        e.pack(padx=16, pady=4)
        e.focus_set()

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 12))
        ttk.Button(btns, text="Aceptar", style="Primary.TButton",
                   command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        e.bind("<Return>", lambda _: self._ok())
        self.transient(parent)
        self.wait_window()

    def _ok(self):
        v = self._var.get().strip()
        if v:
            self.result = v
        self.destroy()


def calcular_asiento_emitida(fac: dict, plantilla: dict, ndig: int = 8) -> list[dict]:
    """Calcula las lineas del asiento contable para una factura emitida.

    Parametros:
      fac       — dict de la factura emitida (campos + lineas: list[dict])
      plantilla — dict de la plantilla de facturacion de la empresa
      ndig      — numero de digitos del plan contable

    Devuelve lista de dicts con claves: subcuenta, dh, importe, concepto, tipo, editable.
    """
    lineas_fac = fac.get("lineas") or []

    cta_cliente   = str(fac.get("subcuenta_cliente") or "").strip()
    cta_ingreso   = str(fac.get("subcuenta_ingreso") or plantilla.get("cuenta_ingreso_por_defecto") or _DEFAULT_INGRESO).strip()
    cta_iva       = str(fac.get("subcuenta_iva") or plantilla.get("cuenta_iva_repercutido_defecto") or _DEFAULT_IVA_REPERCUTIDO).strip()
    cta_retencion = str(fac.get("subcuenta_retencion") or plantilla.get("cuenta_retenciones_irpf") or _DEFAULT_RETENCION).strip()

    # Agrupar lineas por tramo IVA
    tramos: dict[tuple, dict] = {}
    total_base     = Decimal("0.00")
    total_iva      = Decimal("0.00")
    total_re       = Decimal("0.00")
    total_retencion = Decimal("0.00")

    for ln in lineas_fac:
        if str(ln.get("tipo") or "").strip().lower() == "obs":
            continue
        base    = _d2(_fv(ln.get("base")))
        pct_iva = _d2(_fv(ln.get("pct_iva")))
        cuota   = _d2(_fv(ln.get("cuota_iva")))
        if base != 0 and pct_iva != 0:
            cuota = (base * pct_iva / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pct_re  = _d2(_fv(ln.get("pct_re")))
        cuota_re = _d2(_fv(ln.get("cuota_re")))
        if base != 0 and pct_re != 0:
            cuota_re = (base * pct_re / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pct_irpf  = _d2(_fv(ln.get("pct_irpf")))
        cuota_irpf = _d2(_fv(ln.get("cuota_irpf")))
        if base != 0 and pct_irpf != 0:
            cuota_irpf = (abs(base) * pct_irpf / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        key = (float(pct_iva), float(pct_re))
        if key not in tramos:
            tramos[key] = {"base": Decimal("0"), "cuota": Decimal("0"), "cuota_re": Decimal("0"), "pct_iva": pct_iva, "pct_re": pct_re}
        tramos[key]["base"]     += base
        tramos[key]["cuota"]    += cuota
        tramos[key]["cuota_re"] += cuota_re
        total_base     += base
        total_iva      += cuota
        total_re       += cuota_re
        total_retencion += cuota_irpf

    # Sobrescribir con campo retencion_importe si existe en la factura
    if fac.get("retencion_aplica") and fac.get("retencion_importe"):
        total_retencion = _d2(_fv(fac.get("retencion_importe")))

    total_cliente = total_base + total_iva + total_re - total_retencion

    asiento: list[dict] = []

    # DEBE: cliente (deudor)
    nombre_cliente = str(fac.get("nombre") or "").strip()
    numero_fac = str(fac.get("numero") or fac.get("serie", "") + str(fac.get("numero", ""))).strip()
    asiento.append({
        "tipo":      "cliente",
        "subcuenta": cta_cliente,
        "dh":        "D",
        "importe":   float(total_cliente),
        "concepto":  f"Fra. {numero_fac} {nombre_cliente}".strip(),
        "editable":  True,
        "obligatoria": True,
    })

    # DEBE: retenciones IRPF (si procede)
    if total_retencion > 0:
        asiento.append({
            "tipo":      "retencion",
            "subcuenta": cta_retencion,
            "dh":        "D",
            "importe":   float(total_retencion),
            "concepto":  f"Retencion IRPF Fra. {numero_fac}",
            "editable":  True,
            "obligatoria": False,
        })

    # HABER: ingresos/ventas por tramo IVA
    for key, tr in sorted(tramos.items()):
        pct_lbl = f"{float(tr['pct_iva']):.0f}%" if tr["pct_iva"] > 0 else "exento"
        asiento.append({
            "tipo":      "ingreso",
            "subcuenta": cta_ingreso,
            "dh":        "H",
            "importe":   float(abs(tr["base"])),
            "concepto":  f"Ventas IVA {pct_lbl} Fra. {numero_fac}",
            "editable":  True,
            "obligatoria": True,
        })
        # HABER: IVA repercutido
        if tr["cuota"] != 0:
            asiento.append({
                "tipo":      "iva",
                "subcuenta": cta_iva,
                "dh":        "H",
                "importe":   float(abs(tr["cuota"])),
                "concepto":  f"IVA repercutido {pct_lbl} Fra. {numero_fac}",
                "editable":  True,
                "obligatoria": True,
            })
        # HABER: recargo equivalencia
        if tr["cuota_re"] != 0:
            asiento.append({
                "tipo":      "re",
                "subcuenta": cta_iva,
                "dh":        "H",
                "importe":   float(abs(tr["cuota_re"])),
                "concepto":  f"Recargo equiv. {float(tr['pct_re']):.1f}% Fra. {numero_fac}",
                "editable":  True,
                "obligatoria": False,
            })

    return asiento


class AsientoEmitidaDialog(tk.Toplevel):
    """Dialog que muestra y permite editar el asiento contable de una factura emitida.

    Parametros:
      parent        — ventana padre Tkinter
      fac           — dict de la factura emitida (con campo 'lineas': list[dict])
      plantilla     — dict de la plantilla de facturacion (cuentas por defecto)
      gestor        — GestorSQLite para buscar subcuentas del maestro
      codigo_empresa — codigo de empresa activa
      ndig          — digitos del plan contable
      on_save       — callable(fac_modificada) llamado si el usuario guarda cambios
    """

    def __init__(
        self,
        parent,
        *,
        fac: dict,
        plantilla: dict,
        gestor,
        codigo_empresa: str,
        ndig: int = 8,
        on_save=None,
    ):
        super().__init__(parent)
        self.title(f"Asiento contable — Fra. {fac.get('serie', '')}{fac.get('numero', '')}")
        self.resizable(True, True)
        self.grab_set()

        self._fac = dict(fac)
        self._plantilla = plantilla
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ndig = ndig
        self._on_save = on_save
        self._edit_entry: tk.Entry | None = None

        # Calcular asiento inicial
        self._lineas: list[dict] = calcular_asiento_emitida(fac, plantilla, ndig)
        # Cargar catalogo de subcuentas para autocompletar
        self._catalogo: list[dict] = []
        try:
            self._catalogo = gestor.listar_maestro_subcuentas_empresa(codigo_empresa, activo=None) or []
        except Exception:
            pass

        self._build()
        self._poblar()
        self._actualizar_balance()

        self.geometry("880x520")
        try:
            self.update_idletasks()
            pw = parent.winfo_rootx() + (parent.winfo_width() - 880) // 2
            ph = parent.winfo_rooty() + (parent.winfo_height() - 520) // 2
            self.geometry(f"+{max(pw, 0)}+{max(ph, 0)}")
        except Exception:
            pass

        self.transient(parent)
        self.wait_window()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        # Cabecera
        hdr = tk.Frame(self, bg="#f0f9ff", pady=8, padx=14)
        hdr.pack(fill="x")
        fac = self._fac
        nombre = str(fac.get("nombre") or "").strip()
        numero = f"{fac.get('serie', '')}{fac.get('numero', '')}".strip()
        fecha  = str(fac.get("fecha_asiento") or fac.get("fecha_expedicion") or "").strip()
        tk.Label(
            hdr,
            text=f"Factura: {numero}   Fecha: {fecha}   Cliente: {nombre}",
            bg="#f0f9ff", fg="#0369a1",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text="  Doble clic sobre una celda de Subcuenta para editarla. "
                 "Las subcuentas se validan contra el maestro de la empresa.",
            bg="#f0f9ff", fg="#64748b",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))

        # Treeview principal
        wrap = tk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=12, pady=(6, 0))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tv = ttk.Treeview(
            wrap,
            columns=("subcuenta", "nombre_subcuenta", "dh", "importe", "concepto"),
            show="headings",
            height=14,
        )
        for col, txt, width, anchor in [
            ("subcuenta",        "Subcuenta",  120, "w"),
            ("nombre_subcuenta", "Descripcion", 200, "w"),
            ("dh",               "D/H",          50, "center"),
            ("importe",          "Importe",      110, "e"),
            ("concepto",         "Concepto",     340, "w"),
        ]:
            self.tv.heading(col, text=txt)
            self.tv.column(col, width=width, anchor=anchor)
        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=vsb.set)
        self.tv.tag_configure("debe",  background="#eff6ff")
        self.tv.tag_configure("haber", background="#f0fdf4")
        self.tv.tag_configure("error", background="#fef2f2", foreground="#991b1b")
        self.tv.bind("<Double-Button-1>", self._on_double_click)

        # Balance
        bal_frame = tk.Frame(self, bg="#f8fafc")
        bal_frame.pack(fill="x", padx=12, pady=4)
        self.lbl_balance = tk.Label(
            bal_frame,
            text="",
            bg="#f8fafc", fg="#475569",
            font=("Segoe UI", 9),
        )
        self.lbl_balance.pack(anchor="w")

        # Botones
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(
            btns, text="Guardar cambios", style="Primary.TButton",
            command=self._guardar,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Copiar al portapapeles", command=self._copiar).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Cerrar", command=self.destroy).pack(side="left")
        self.lbl_msg = tk.Label(btns, text="", fg="#16a34a", font=("Segoe UI", 8))
        self.lbl_msg.pack(side="left", padx=(12, 0))

    # ── Datos ──────────────────────────────────────────────────────────────────

    def _poblar(self):
        self.tv.delete(*self.tv.get_children())
        for idx, ln in enumerate(self._lineas):
            sub = str(ln.get("subcuenta") or "").strip()
            nombre_sub = self._nombre_subcuenta(sub)
            tag = "debe" if ln.get("dh") == "D" else "haber"
            self.tv.insert(
                "", tk.END, iid=str(idx),
                values=(sub, nombre_sub, ln.get("dh", ""), f"{ln.get('importe', 0.0):.2f}", ln.get("concepto", "")),
                tags=(tag,),
            )

    def _nombre_subcuenta(self, codigo: str) -> str:
        if not codigo:
            return ""
        for row in self._catalogo:
            if str(row.get("subcuenta") or "") == codigo:
                return str(row.get("nombre_subcuenta") or "").strip()
        return ""

    def _actualizar_balance(self):
        total_debe  = sum(ln.get("importe", 0.0) for ln in self._lineas if ln.get("dh") == "D")
        total_haber = sum(ln.get("importe", 0.0) for ln in self._lineas if ln.get("dh") == "H")
        diferencia  = round(total_debe - total_haber, 2)
        color = "#16a34a" if diferencia == 0 else "#991b1b"
        self.lbl_balance.configure(
            text=f"  Total Debe: {total_debe:.2f}   Total Haber: {total_haber:.2f}   "
                 f"Diferencia: {diferencia:.2f}{'  ✓ Cuadrado' if diferencia == 0 else '  ✗ No cuadra'}",
            fg=color,
        )

    # ── Edicion inline de subcuenta ────────────────────────────────────────────

    def _on_double_click(self, event: tk.Event):
        region = self.tv.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tv.identify_column(event.x)
        if col != "#1":  # Solo columna Subcuenta (#1)
            return
        row_id = self.tv.identify_row(event.y)
        if not row_id:
            return
        try:
            idx = int(row_id)
            ln = self._lineas[idx]
        except (ValueError, IndexError):
            return
        if not ln.get("editable"):
            return
        self._abrir_editor_subcuenta(row_id, idx)

    def _abrir_editor_subcuenta(self, row_id: str, idx: int):
        self._cerrar_editor()
        bbox = self.tv.bbox(row_id, "#1")
        if not bbox:
            return
        x, y, w, h = bbox
        valor_actual = str(self._lineas[idx].get("subcuenta") or "")

        abs_x = self.tv.winfo_rootx() + x
        abs_y = self.tv.winfo_rooty() + y

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"{max(w, 320)}x200+{abs_x}+{abs_y}")
        popup.attributes("-topmost", True)
        self._edit_entry = popup

        var = tk.StringVar(value=valor_actual)
        entry = ttk.Entry(popup, textvariable=var, font=("Segoe UI", 9))
        entry.pack(fill="x")
        entry.select_range(0, tk.END)
        entry.focus_set()

        lb_frame = tk.Frame(popup, bd=1, relief="solid")
        lb_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(lb_frame, font=("Segoe UI", 8), activestyle="dotbox", height=8)
        sb = tk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(fill="both", expand=True)

        def _actualizar_lista(*_):
            txt = var.get().strip().lower()
            lb.delete(0, tk.END)
            if not txt:
                return
            for sc in self._catalogo:
                codigo = str(sc.get("subcuenta") or "")
                nombre = str(sc.get("nombre_subcuenta") or "")
                # Busqueda por contenido: codigo O nombre contienen el texto
                if txt in codigo.lower() or txt in nombre.lower():
                    lb.insert(tk.END, f"{codigo}  {nombre}")

        var.trace_add("write", _actualizar_lista)
        _actualizar_lista()

        _committed = [False]

        def _aplicar(code: str):
            if _committed[0]:
                return
            _committed[0] = True
            try:
                popup.destroy()
            except Exception:
                pass
            self._edit_entry = None
            if code == valor_actual:
                return
            # Validar que existe en maestro
            existente = None
            try:
                existente = self._gestor.get_maestro_subcuenta_por_subcuenta(self._codigo, code)
            except Exception:
                pass
            if code and not existente:
                resp = messagebox.askyesnocancel(
                    "Subcuenta no existe",
                    f"La subcuenta '{code}' no existe en el maestro de cuentas.\n\n"
                    f"\u00bfDesea crearla ahora como pendiente de alta en A3?\n\n"
                    f"  [Si]     \u2192 Crear en maestro (pendiente A3) y usar\n"
                    f"  [No]     \u2192 Usar sin crear en maestro\n"
                    f"  [Cancelar] \u2192 No aplicar el cambio",
                    parent=self,
                )
                if resp is None:   # Cancelar
                    return
                if resp:           # Si -> crear en maestro
                    try:
                        nombre_dlg = _PedirNombreSubcuentaDialog(self, code)
                        nombre_nuevo = nombre_dlg.result
                        if nombre_nuevo is None:
                            return  # user cancelled name dialog
                        self._gestor.upsert_maestro_subcuenta({
                            "codigo_empresa": self._codigo,
                            "subcuenta":      code,
                            "nombre_subcuenta": nombre_nuevo,
                            "tipo_subcuenta": "ingreso",
                            "activo":         1,
                            "origen":         "manual",
                            "pendiente_alta_a3": 1,
                            "creado_en_gest2a3eco": 1,
                        })
                        # Refresh catalogo
                        try:
                            self._catalogo = self._gestor.listar_maestro_subcuentas_empresa(
                                self._codigo, activo=None) or []
                        except Exception:
                            pass
                    except Exception as exc:
                        messagebox.showerror("Error", f"No se pudo crear la subcuenta:\n{exc}", parent=self)
                        return
                # resp is False -> use without creating (continue)
            self._lineas[idx]["subcuenta"] = code
            _log.info(
                "Asiento factura %s: subcuenta linea %d cambiada de '%s' a '%s'",
                self._fac.get("id"), idx, valor_actual, code,
            )
            self._poblar()
            self._actualizar_balance()

        def _on_entry_return(_event=None):
            txt = var.get().strip()
            if lb.size() == 1:
                item = lb.get(0)
                _aplicar(item.split()[0])
            elif lb.curselection():
                item = lb.get(lb.curselection()[0])
                _aplicar(item.split()[0])
            else:
                _aplicar(txt)

        def _on_lb_select(_event=None):
            sel = lb.curselection()
            if sel:
                item = lb.get(sel[0])
                _aplicar(item.split()[0])

        def _on_cancel(_event=None):
            if not _committed[0]:
                _committed[0] = True
                self._edit_entry = None
                try:
                    popup.destroy()
                except Exception:
                    pass

        entry.bind("<Return>",  _on_entry_return)
        entry.bind("<Tab>",     _on_entry_return)
        entry.bind("<Escape>",  _on_cancel)
        entry.bind("<Down>",    lambda _: lb.focus_set())
        lb.bind("<Return>",     _on_lb_select)
        lb.bind("<Double-Button-1>", _on_lb_select)
        lb.bind("<Escape>",     _on_cancel)
        popup.bind("<FocusOut>", lambda e: self.after(100, lambda: _on_cancel() if not _committed[0] and not popup.focus_get() else None))

    def _cerrar_editor(self):
        if self._edit_entry:
            try:
                self._edit_entry.destroy()
            except Exception:
                pass
            self._edit_entry = None

    # ── Acciones ───────────────────────────────────────────────────────────────

    def _guardar(self):
        """Persiste todas las subcuentas modificadas de vuelta en la factura."""
        self._cerrar_editor()
        upd = dict(self._fac)
        changed = []

        tipo_campos = {
            "cliente":   "subcuenta_cliente",
            "ingreso":   "subcuenta_ingreso",
            "iva":       "subcuenta_iva",
            "retencion": "subcuenta_retencion",
        }
        for tipo, campo in tipo_campos.items():
            linea = next((ln for ln in self._lineas if ln.get("tipo") == tipo), None)
            if linea is None:
                continue
            nueva = str(linea.get("subcuenta") or "").strip()
            original = str(self._fac.get(campo) or "").strip()
            if nueva != original:
                upd[campo] = nueva
                changed.append(campo)

        if not changed:
            self.lbl_msg.configure(text="Sin cambios en las subcuentas.")
            return
        try:
            self._gestor.upsert_factura_emitida(upd)
            for campo in changed:
                self._fac[campo] = upd[campo]
            _log.info(
                "Factura %s: subcuentas actualizadas: %s",
                self._fac.get("id"), changed,
            )
            self.lbl_msg.configure(text=f"Guardado: {', '.join(changed)}.")
            if self._on_save:
                try:
                    self._on_save(self._fac)
                except Exception:
                    pass
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"Error al guardar:\n{exc}", parent=self)

    def _copiar(self):
        self._cerrar_editor()
        lineas_txt = []
        for ln in self._lineas:
            lineas_txt.append(
                f"{ln.get('dh','')}\t{ln.get('subcuenta','')}\t"
                f"{ln.get('importe', 0.0):.2f}\t{ln.get('concepto','')}"
            )
        texto = "\n".join(lineas_txt)
        try:
            self.clipboard_clear()
            self.clipboard_append(texto)
            self.lbl_msg.configure(text="Copiado al portapapeles.")
        except Exception:
            pass
