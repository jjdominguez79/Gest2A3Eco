from datetime import date

from services.terceros_empresa_fiscal_service import build_cliente_factura_defaults
from utils.utilidades import validar_subcuenta_longitud, aplicar_descuento_total_lineas, format_num_es
from utils.validaciones import (
    inferir_pais_desde_identificacion,
    normalizar_codigo_pais,
    normalizar_nif_cif,
    validar_nif_o_nif_iva_intracomunitario,
)


class FacturaDialogController:
    def __init__(self, gestor, codigo, ejercicio, ndig, factura, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._ndig = ndig
        self._factura = factura
        self._view = view
        self._allow_fecha_fuera_ejercicio = bool(factura.get("_allow_fecha_fuera_ejercicio"))
        self._auto_ejercicio_por_fecha = bool(factura.get("_auto_ejercicio_por_fecha"))
        self._terceros_cache = []
        self._display_to_tercero: dict = {}
        self._editing_existing = bool(factura.get("id"))

    def load_terceros(self):
        all_terceros = self._gestor.listar_subcuentas_facturacion(
            self._codigo,
            ["cliente", "deudor"],
            activo=True,
        )
        self._terceros_cache = list(all_terceros or [])
        current_tercero_id = str(self._factura.get("tercero_id") or "").strip()
        current_nif = normalizar_nif_cif(self._factura.get("nif"))
        current_subcuenta = str(self._factura.get("subcuenta_cliente") or "").strip()
        if current_subcuenta and not any(str(t.get("subcuenta") or "").strip() == current_subcuenta for t in self._terceros_cache):
            extra = self._gestor.listar_subcuentas_facturacion(
                self._codigo,
                ["cliente", "deudor"],
                activo=None,
                subcuenta=current_subcuenta,
            )
            if extra:
                self._terceros_cache.extend(extra)
        known_ids = {str(t.get("tercero_global_id") or t.get("id") or "") for t in self._terceros_cache}
        if current_tercero_id and current_tercero_id not in known_ids:
            extra = next(
                (t for t in self._gestor.listar_terceros() if str(t.get("id")) == current_tercero_id),
                None,
            )
            if extra:
                self._terceros_cache.append(extra)
        if current_nif and not any(self._nif_tercero(t) == current_nif for t in self._terceros_cache):
            extra = next(
                (t for t in self._gestor.listar_terceros() if normalizar_nif_cif(t.get("nif")) == current_nif),
                None,
            )
            if extra:
                self._terceros_cache.append(extra)
        self._display_to_tercero = {}
        disp = []
        for t in self._terceros_cache:
            label = self._build_display_label(t)
            self._display_to_tercero[label] = t
            disp.append(label)
        self._view.set_terceros(disp)

    def _get_selected_tercero(self):
        label = self._view.get_selected_tercero_display()
        return self._display_to_tercero.get(label)

    def _build_display_label(self, tercero: dict) -> str:
        subcuenta = str(tercero.get("subcuenta") or "").strip()
        nombre = self._nombre_tercero(tercero)
        nif = self._nif_tercero(tercero)
        suffix = f" ({nif})" if nif else ""
        return f"{subcuenta} - {nombre}{suffix}" if subcuenta else f"{nombre}{suffix}"

    def _nombre_tercero(self, tercero: dict) -> str:
        return str(
            tercero.get("tercero_nombre_legal")
            or tercero.get("tercero_nombre")
            or tercero.get("nombre")
            or tercero.get("nombre_subcuenta")
            or ""
        ).strip()

    def _nif_tercero(self, tercero: dict) -> str:
        return normalizar_nif_cif(
            tercero.get("tercero_nif")
            or tercero.get("nif")
            or tercero.get("nif_snapshot")
            or ""
        )

    def _has_cliente_autofill_config(self, tercero: dict) -> bool:
        return bool(str(tercero.get("cliente_tipo_operacion_iva") or "").strip())

    def preselect_tercero(self, tercero_id):
        tercero_id = str(tercero_id or "").strip()
        current_subcuenta = str(self._factura.get("subcuenta_cliente") or "").strip()
        for label, t in self._display_to_tercero.items():
            if tercero_id and str(t.get("tercero_global_id") or t.get("id") or "").strip() == tercero_id:
                self._view.set_tercero_display(label)
                self.on_tercero_selected()
                return
            if current_subcuenta and str(t.get("subcuenta") or "").strip() == current_subcuenta:
                self._view.set_tercero_display(label)
                self.on_tercero_selected()
                return

    def get_tercero_full_data(self, tercero_global_id: str) -> dict:
        """Devuelve los datos completos del tercero (incluye direccion, telefono, email, etc.)."""
        if not tercero_global_id:
            return {}
        t = self._gestor.get_tercero(tercero_global_id)
        return t or {}

    def actualizar_tercero(self, tercero_id: str, datos: dict):
        """Persiste los cambios del panel de datos del tercero en la tabla terceros."""
        if not tercero_id:
            self._view.show_warning("Gest2A3Eco", "No hay ningun tercero seleccionado para actualizar.")
            return
        existing = self._gestor.get_tercero(tercero_id)
        if not existing:
            self._view.show_warning("Gest2A3Eco", "No se encontro el tercero en la base de datos.")
            return
        payload = dict(existing)
        payload.update({k: v for k, v in datos.items() if v is not None})
        self._gestor.upsert_tercero(payload)
        self._view.show_info("Gest2A3Eco", "Datos del tercero actualizados correctamente.")

    def on_tercero_selected(self):
        t = self._get_selected_tercero()
        if not t:
            return
        self._view.set_nif(self._nif_tercero(t))
        self._view.set_nombre(self._nombre_tercero(t))
        sc = str(t.get("subcuenta") or t.get("subcuenta_cliente") or "")
        if sc:
            self._view.set_subcuenta(sc)
        if not self._editing_existing and self._has_cliente_autofill_config(t):
            defaults = build_cliente_factura_defaults(t)
            self._view.set_tipo_operacion(defaults.get("tipo_operacion") or "01")
            self._view.set_modelo_fiscal(defaults.get("modelo_fiscal") or "")
        self._view.set_subcuenta_warning(
            ""
            if self._has_cliente_autofill_config(t)
            else "La subcuenta seleccionada no tiene configuracion fiscal/contable completa. Puede continuar, pero algunos campos deberan revisarse manualmente."
        )
        # Rellenar panel de datos completos del tercero
        tercero_global_id = str(t.get("tercero_global_id") or t.get("id") or "").strip()
        full = self.get_tercero_full_data(tercero_global_id) if tercero_global_id else t
        self._view.set_tercero_panel(full, tercero_global_id)

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
        self._sync_retencion()
        self.refresh_totales()
        self.clear_line_editor()

    def del_linea(self):
        if self._view.delete_selected_line():
            self._sync_retencion()
            self.refresh_totales()
            self.clear_line_editor()

    def move_linea_up(self):
        if self._view.move_selected_line(-1):
            self._sync_retencion()
            self.refresh_totales()

    def move_linea_down(self):
        if self._view.move_selected_line(1):
            self._sync_retencion()
            self.refresh_totales()

    def refresh_totales(self):
        base = iva = 0.0
        resumen = {}
        lineas = self._view.get_lineas()
        dtipo, dvalor = self._view.get_descuento_total()
        lineas_calc = aplicar_descuento_total_lineas(lineas, dtipo, dvalor)
        for ln in lineas_calc:
            if str(ln.get("tipo") or "").strip().lower() == "obs":
                continue
            base += ln["base"]
            iva += ln["cuota_iva"]
            pct = self._round2(ln.get("pct_iva", 0))
            item = resumen.setdefault(pct, {"tipo": f"{format_num_es(pct, 2)}%", "base": 0.0, "cuota": 0.0})
            item["base"] += ln.get("base", 0.0)
            item["cuota"] += ln.get("cuota_iva", 0.0)
        base = self._round2(base)
        iva = self._round2(iva)
        ret = self._round2(self._view.get_retencion_importe() if self._view.get_retencion_aplica() else 0.0)
        total = self._round2(base + iva + ret)
        self._view.set_totales(base, iva, ret, total)
        rows = [resumen[k] for k in sorted(resumen.keys(), reverse=True)]
        self._view.set_iva_resumen(rows)
        if self._view.get_retencion_aplica() and not self._view.is_retencion_manual():
            dtipo, dvalor = self._view.get_descuento_total()
            base_total = self._sum_base_imponible(self._view.get_lineas(), dtipo, dvalor)
            self._view.set_retencion_base(f"{base_total:.2f}" if base_total else "")

    def insert_linea(self, ln):
        self._view.insert_line_row(ln)

    def get_series_disponibles(self) -> list:
        return list(self._factura.get("_series_disponibles") or [])

    def on_serie_selected(self, nombre_serie: str):
        """Actualiza el numero sugerido cuando el usuario cambia la serie."""
        try:
            num = self._gestor.get_siguiente_serie_num(self._codigo, self._ejercicio, nombre_serie)
            self._view.set_numero(f"{num:06d}")
        except Exception:
            pass

    def ok_borrador(self):
        """Guarda como borrador sin asignar numero."""
        if self._view.get_retencion_aplica():
            self._sync_retencion()
        lineas = self._view.get_lineas()
        if not lineas:
            self._view.show_error("Gest2A3Eco", "Anade al menos una linea.")
            return
        fecha_common = self._view.get_fecha_exp()
        t_sel = self._get_selected_tercero()
        tercero_id = (t_sel.get("tercero_global_id") or t_sel.get("id")) if t_sel else None
        result = {
            "id": self._factura.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": tercero_id,
            "serie": self._view.get_serie(),
            "numero": "",
            "numero_asiento": self._view.get_numero_asiento(),
            "numero_largo_sii": self._factura.get("numero_largo_sii", ""),
            "fecha_asiento": fecha_common,
            "fecha_expedicion": fecha_common,
            "fecha_operacion": fecha_common,
            "tipo_operacion": self._view.get_tipo_operacion(),
            "modelo_fiscal": self._view.get_modelo_fiscal(),
            "nif": normalizar_nif_cif(self._view.get_nif()),
            "nombre": self._view.get_nombre(),
            "descripcion": self._view.get_descripcion(),
            "observaciones": self._view.get_observaciones(),
            "subcuenta_cliente": self._view.get_subcuenta().strip(),
            "forma_pago": self._view.get_forma_pago(),
            "cuenta_bancaria": self._view.get_cuenta_bancaria(),
            "moneda_codigo": self._view.get_moneda()[0],
            "moneda_simbolo": self._view.get_moneda()[1],
            "plantilla_word": self._view.get_plantilla_word(),
            "plantilla_emitidas": self._view.get_plantilla_emitidas(),
            "retencion_aplica": self._view.get_retencion_aplica(),
            "retencion_pct": self._view.get_retencion_pct(),
            "retencion_base": self._view.get_retencion_base() if self._view.get_retencion_aplica() else None,
            "retencion_importe": self._view.get_retencion_importe() if (self._view.get_retencion_aplica() and self._view.is_retencion_manual()) else None,
            "descuento_total_tipo": self._view.get_descuento_total()[0],
            "descuento_total_valor": self._view.get_descuento_total()[1],
            "pdf_ref": self._factura.get("pdf_ref", ""),
            "lineas": lineas,
            "generada": self._factura.get("generada", False),
            "fecha_generacion": self._factura.get("fecha_generacion", ""),
            "_borrador": True,
        }
        if self._auto_ejercicio_por_fecha:
            try:
                d = self._view.parse_date(str(fecha_common))
                result["ejercicio"] = d.year
            except Exception:
                pass
        self._view.set_result_and_close(result)

    def ok(self):
        if self._view.get_retencion_aplica():
            self._sync_retencion()
        lineas = self._view.get_lineas()
        if not lineas:
            self._view.show_error("Gest2A3Eco", "Anade al menos una linea.")
            return
        if not self._view.get_numero_factura():
            self._view.show_error("Gest2A3Eco", "Numero de factura vacio.")
            return
        fecha_common = self._view.get_fecha_exp()
        if not self._allow_fecha_fuera_ejercicio:
            try:
                d = self._view.parse_date(str(fecha_common))
                if self._ejercicio and d.year != int(self._ejercicio):
                    self._view.show_error(
                        "Gest2A3Eco",
                        f"La fecha de la factura ({d.strftime('%d/%m/%Y')}) debe estar dentro del ejercicio {self._ejercicio}.",
                    )
                    return
            except Exception:
                pass
        sc = self._view.get_subcuenta().strip()
        if sc:
            validar_subcuenta_longitud(sc, self._ndig, "subcuenta cliente")
        t_sel = self._get_selected_tercero()
        tercero_id = (t_sel.get("tercero_global_id") or t_sel.get("id")) if t_sel else None
        result = {
            "id": self._factura.get("id"),
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": tercero_id,
            "serie": self._view.get_serie(),
            "numero": self._view.get_numero_factura(),
            "numero_asiento": self._view.get_numero_asiento(),
            "numero_largo_sii": self._factura.get("numero_largo_sii", ""),
            "fecha_asiento": fecha_common,
            "fecha_expedicion": fecha_common,
            "fecha_operacion": fecha_common,
            "tipo_operacion": self._view.get_tipo_operacion(),
            "modelo_fiscal": self._view.get_modelo_fiscal(),
            "nif": normalizar_nif_cif(self._view.get_nif()),
            "nombre": self._view.get_nombre(),
            "descripcion": self._view.get_descripcion(),
            "observaciones": self._view.get_observaciones(),
            "subcuenta_cliente": sc,
            "forma_pago": self._view.get_forma_pago(),
            "cuenta_bancaria": self._view.get_cuenta_bancaria(),
            "moneda_codigo": self._view.get_moneda()[0],
            "moneda_simbolo": self._view.get_moneda()[1],
            "plantilla_word": self._view.get_plantilla_word(),
            "plantilla_emitidas": self._view.get_plantilla_emitidas(),
            "retencion_aplica": self._view.get_retencion_aplica(),
            "retencion_pct": self._view.get_retencion_pct(),
            "retencion_base": self._view.get_retencion_base() if self._view.get_retencion_aplica() else None,
            "retencion_importe": self._view.get_retencion_importe() if (self._view.get_retencion_aplica() and self._view.is_retencion_manual()) else None,
            "descuento_total_tipo": self._view.get_descuento_total()[0],
            "descuento_total_valor": self._view.get_descuento_total()[1],
            "pdf_ref": self._factura.get("pdf_ref", ""),
            "lineas": lineas,
            "generada": self._factura.get("generada", False),
            "fecha_generacion": self._factura.get("fecha_generacion", ""),
        }
        if self._auto_ejercicio_por_fecha:
            try:
                d = self._view.parse_date(str(fecha_common))
                result["ejercicio"] = d.year
            except Exception:
                pass
        self._view.set_result_and_close(result)

    def retencion_toggled(self):
        if self._view.get_retencion_aplica():
            self._view.set_retencion_manual(False)
            self._sync_retencion()
        else:
            self._view.set_retencion_manual(False)
            self.apply_retencion_header()
        self.refresh_totales()

    def retencion_pct_changed(self):
        if not self._view.get_retencion_aplica():
            return
        self._sync_retencion()
        self.refresh_totales()

    def retencion_base_changed(self):
        if not self._view.get_retencion_aplica():
            return
        self._sync_retencion()
        self.refresh_totales()

    def apply_retencion_header(self):
        if self._view.get_retencion_aplica():
            pct = self._view.get_retencion_pct()
            base_ret = self._view.get_retencion_base()
        else:
            pct = 0.0
            base_ret = 0.0
        lineas = self._view.get_lineas()
        lineas = self._apply_retencion_to_lineas(lineas, pct, base_ret)
        self._view.set_lineas(lineas)

    def _line_from_editor(self):
        concepto, unidades, precio, iva, iva_raw, desc_tipo, desc_val = self._view.get_line_editor_values()
        if self._view.is_line_observacion():
            if not concepto:
                self._view.show_warning("Gest2A3Eco", "Completa el concepto de la observacion.")
                return None
            return {
                "concepto": concepto,
                "unidades": 0.0,
                "precio": 0.0,
                "base": 0.0,
                "pct_iva": 0.0,
                "cuota_iva": 0.0,
                "descuento_tipo": "",
                "descuento_valor": 0.0,
                "pct_irpf": 0.0,
                "cuota_irpf": 0.0,
                "pct_re": 0.0,
                "cuota_re": 0.0,
                "tipo": "obs",
            }
        if not concepto or unidades == 0 or iva_raw == "":
            self._view.show_warning("Gest2A3Eco", "Completa concepto, unidades e IVA.")
            return None
        if precio == 0:
            self._view.show_warning("Gest2A3Eco", "La linea tiene precio 0. Se guardara con importe 0.")
        base = self._round2(unidades * precio)
        dtipo = (desc_tipo or "").strip().lower()
        dval = self._round2(desc_val)
        if dtipo in ("pct", "imp") and dval > 0:
            if dtipo == "pct":
                pct = min(max(dval, 0.0), 100.0)
                if pct != dval:
                    self._view.show_warning("Gest2A3Eco", "El descuento % se ha ajustado al rango 0-100.")
                base = self._round2(base * (1.0 - pct / 100.0))
            else:
                if dval > base:
                    self._view.show_warning("Gest2A3Eco", "El descuento supera la base. Se ajusta al maximo.")
                    dval = base
                base = self._round2(base - dval)
        cuota_iva = self._round2(base * iva / 100.0)
        return {
            "concepto": concepto,
            "unidades": self._round2(unidades),
            "precio": self._round4(precio),
            "base": self._round2(base),
            "pct_iva": self._round2(iva),
            "cuota_iva": self._round2(cuota_iva),
            "descuento_tipo": dtipo if dtipo in ("pct", "imp") else "",
            "descuento_valor": self._round2(dval) if dtipo in ("pct", "imp") else 0.0,
            "pct_irpf": 0.0,
            "cuota_irpf": 0.0,
            "pct_re": 0.0,
            "cuota_re": 0.0,
            "tipo": "",
        }

    def _apply_retencion_to_lineas(self, lineas, pct, base_ret):
        if not lineas:
            return lineas
        for ln in lineas:
            ln["pct_irpf"] = 0.0
            ln["cuota_irpf"] = 0.0
        return lineas

    def _sync_retencion(self):
        if not self._view.get_retencion_aplica():
            return
        if not self._view.is_retencion_manual():
            dtipo, dvalor = self._view.get_descuento_total()
            base = self._sum_base_imponible(self._view.get_lineas(), dtipo, dvalor)
            self._view.set_retencion_base(f"{base:.2f}" if base else "")
        self.apply_retencion_header()

    def _sum_base_imponible(self, lineas, dtipo, dvalor):
        total = 0.0
        lineas_calc = aplicar_descuento_total_lineas(lineas, dtipo, dvalor)
        for ln in lineas_calc:
            if str(ln.get("tipo") or "").strip().lower() == "obs":
                continue
            total += ln.get("base", 0.0)
        return self._round2(total)

    def _round2(self, x) -> float:
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0

    def _round4(self, x) -> float:
        try:
            return round(float(x), 4)
        except Exception:
            return 0.0
