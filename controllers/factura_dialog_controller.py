from datetime import date

from utils.utilidades import validar_subcuenta_longitud


class FacturaDialogController:
    def __init__(self, gestor, codigo, ejercicio, ndig, factura, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._ndig = ndig
        self._factura = factura
        self._view = view
        self._terceros_cache = []

    def load_terceros(self):
        self._terceros_cache = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        disp = [f"{t.get('nombre','')} ({t.get('nif','')})" for t in self._terceros_cache]
        self._view.set_terceros(disp)

    def preselect_tercero(self, tercero_id):
        if not tercero_id:
            return
        for idx, t in enumerate(self._terceros_cache):
            if str(t.get("id")) == str(tercero_id):
                self._view.select_tercero_index(idx)
                self.on_tercero_selected()
                return

    def gestionar_terceros(self):
        self._view.open_terceros_dialog(self._codigo, self._ejercicio, self._ndig)
        self.load_terceros()

    def on_tercero_selected(self):
        idx = self._view.get_selected_tercero_index()
        if idx < 0:
            return
        t = self._terceros_cache[idx]
        self._view.set_nif(t.get("nif", ""))
        self._view.set_nombre(t.get("nombre", ""))
        rel = self._gestor.get_tercero_empresa(self._codigo, t.get("id"), self._ejercicio) or {}
        sc = rel.get("subcuenta_cliente", "")
        if sc:
            self._view.set_subcuenta(sc)

    def pick_date(self, target_var):
        txt = (target_var.get() or "").strip()
        initial = self._view.parse_date(txt) if txt else date.today()
        picked = self._view.open_date_picker(initial)
        if picked:
            target_var.set(picked.strftime("%d/%m/%Y"))

    def clear_line_editor(self):
        self._view.clear_line_editor()

    def add_update_linea(self):
        ln = self._line_from_editor()
        if not ln:
            return
        self._view.upsert_line_row(ln)
        if self._view.get_retencion_aplica() and self._view.is_retencion_manual():
            self.apply_retencion_header()
        self.refresh_totales()
        self.clear_line_editor()

    def del_linea(self):
        if self._view.delete_selected_line():
            if self._view.get_retencion_aplica() and self._view.is_retencion_manual():
                self.apply_retencion_header()
            self.refresh_totales()
            self.clear_line_editor()

    def refresh_totales(self):
        base = iva = ret = 0.0
        resumen = {}
        for ln in self._view.get_lineas():
            base += ln["base"]
            iva += ln["cuota_iva"]
            ret += ln["cuota_irpf"]
            pct = self._round2(ln.get("pct_iva", 0))
            item = resumen.setdefault(pct, {"tipo": f"{pct:.2f}%", "base": 0.0, "cuota": 0.0})
            item["base"] += ln.get("base", 0.0)
            item["cuota"] += ln.get("cuota_iva", 0.0)
        base = self._round2(base)
        iva = self._round2(iva)
        ret = self._round2(ret)
        total = self._round2(base + iva + ret)
        self._view.set_totales(base, iva, ret, total)
        rows = [resumen[k] for k in sorted(resumen.keys(), reverse=True)]
        self._view.set_iva_resumen(rows)
        if self._view.get_retencion_aplica() and not self._view.is_retencion_manual():
            self._view.set_retencion_importe(f"{ret:.2f}")

    def insert_linea(self, ln):
        self._view.insert_line_row(ln)

    def ok(self):
        if self._view.get_retencion_aplica():
            self.apply_retencion_header()
        lineas = self._view.get_lineas()
        if not lineas:
            self._view.show_error("Gest2A3Eco", "Anade al menos una linea.")
            return
        if not self._view.get_numero_factura():
            self._view.show_error("Gest2A3Eco", "Numero de factura vacio.")
            return
        sc = self._view.get_subcuenta().strip()
        if sc:
            validar_subcuenta_longitud(sc, self._ndig, "subcuenta cliente")
        tercero_id = None
        idx = self._view.get_selected_tercero_index()
        if idx >= 0 and idx < len(self._terceros_cache):
            tercero_id = self._terceros_cache[idx].get("id")
        fecha_common = self._view.get_fecha_exp()
        result = {
            "id": self._factura.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": tercero_id,
            "serie": self._view.get_serie(),
            "numero": self._view.get_numero_factura(),
            "numero_largo_sii": self._factura.get("numero_largo_sii", ""),
            "fecha_asiento": fecha_common,
            "fecha_expedicion": fecha_common,
            "fecha_operacion": fecha_common,
            "nif": self._view.get_nif(),
            "nombre": self._view.get_nombre(),
            "descripcion": self._view.get_descripcion(),
            "subcuenta_cliente": sc,
            "forma_pago": self._view.get_forma_pago(),
            "cuenta_bancaria": self._view.get_cuenta_bancaria(),
            "retencion_aplica": self._view.get_retencion_aplica(),
            "retencion_pct": self._view.get_retencion_pct(),
            "retencion_importe": self._view.get_retencion_importe() if self._view.get_retencion_aplica() else None,
            "pdf_ref": self._factura.get("pdf_ref", ""),
            "lineas": lineas,
            "generada": self._factura.get("generada", False),
            "fecha_generacion": self._factura.get("fecha_generacion", ""),
        }
        self._view.set_result_and_close(result)

    def retencion_toggled(self):
        if self._view.get_retencion_aplica():
            self._view.set_retencion_manual(False)
            self.apply_retencion_header()
        else:
            self._view.set_retencion_manual(False)
        self.refresh_totales()

    def retencion_pct_changed(self):
        if not self._view.get_retencion_aplica():
            return
        self._view.set_retencion_manual(False)
        self.apply_retencion_header()
        self.refresh_totales()

    def retencion_importe_changed(self):
        if not self._view.get_retencion_aplica():
            return
        self.apply_retencion_header()
        self.refresh_totales()

    def apply_retencion_header(self):
        pct = self._view.get_retencion_pct()
        manual = self._view.is_retencion_manual()
        manual_total = self._view.get_retencion_importe() if manual else None
        lineas = self._view.get_lineas()
        lineas = self._apply_retencion_to_lineas(lineas, pct, manual_total)
        self._view.set_lineas(lineas)

    def _line_from_editor(self):
        concepto, unidades, precio, iva, irpf, iva_raw, irpf_raw = self._view.get_line_editor_values()
        if self._view.get_retencion_aplica():
            irpf = self._view.get_retencion_pct()
            irpf_raw = str(int(irpf)) if irpf else "0"
        if not concepto or unidades == 0 or precio == 0 or iva_raw == "" or irpf_raw == "":
            self._view.show_warning("Gest2A3Eco", "Completa concepto, unidades, precio, IVA e IRPF.")
            return None
        base = self._round2(unidades * precio)
        cuota_iva = self._round2(base * iva / 100.0)
        cuota_ret = -abs(self._round2(base * irpf / 100.0))
        return {
            "concepto": concepto,
            "unidades": self._round2(unidades),
            "precio": self._round2(precio),
            "base": self._round2(base),
            "pct_iva": self._round2(iva),
            "cuota_iva": self._round2(cuota_iva),
            "pct_irpf": self._round2(irpf),
            "cuota_irpf": self._round2(cuota_ret),
            "pct_re": 0.0,
            "cuota_re": 0.0,
        }

    def _apply_retencion_to_lineas(self, lineas, pct, manual_total):
        pct = self._round2(pct)
        if not lineas:
            return lineas
        auto_total = 0.0
        for ln in lineas:
            base = ln.get("base", 0.0)
            cuota = -abs(self._round2(base * pct / 100.0)) if pct else 0.0
            ln["pct_irpf"] = pct
            ln["cuota_irpf"] = cuota
            auto_total += cuota
        if manual_total is not None:
            target = -abs(self._round2(manual_total))
            if abs(auto_total) > 0.0001:
                factor = target / auto_total
                for ln in lineas:
                    ln["cuota_irpf"] = self._round2(ln.get("cuota_irpf", 0.0) * factor)
            else:
                base_total = sum(ln.get("base", 0.0) for ln in lineas)
                if abs(base_total) > 0.0001:
                    for ln in lineas:
                        ln["cuota_irpf"] = self._round2(target * (ln.get("base", 0.0) / base_total))
                else:
                    lineas[-1]["cuota_irpf"] = target
        return lineas

    def _round2(self, x) -> float:
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0
