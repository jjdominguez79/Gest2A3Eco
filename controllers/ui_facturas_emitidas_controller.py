import os
import sys
from datetime import datetime

from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_word import (
    build_context_emitida,
    generar_pdf_desde_plantilla_word,
)


class FacturasEmitidasController:
    def __init__(self, gestor, codigo, ejercicio, empresa_conf, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._empresa_conf = empresa_conf
        self._view = view

    def refresh_plantillas(self):
        pls = [p.get("nombre") for p in self._gestor.listar_emitidas(self._codigo, self._ejercicio)]
        self._view.set_plantillas(pls)

    def refresh_facturas(self):
        self._view.clear_facturas()
        for fac in self._gestor.listar_facturas_emitidas(self._codigo, self._ejercicio):
            total = self._compute_total(fac)
            self._view.insert_factura_row(fac, total)

    def nueva(self):
        sugerido = self._proximo_numero()
        cuenta_default = self._cuenta_bancaria_default()
        result = self._view.open_factura_dialog(
            {
                "codigo_empresa": self._codigo,
                "ejercicio": self._ejercicio,
                "serie": self._serie(),
                "numero": sugerido,
                "forma_pago": "",
                "cuenta_bancaria": cuenta_default,
            },
            numero_sugerido=sugerido,
        )
        if result:
            result["generada"] = False
            result["fecha_generacion"] = ""
            result["ejercicio"] = self._ejercicio
            result["codigo_empresa"] = self._codigo
            self._gestor.upsert_factura_emitida(result)
            self._incrementar_numeracion()
            self.refresh_facturas()

    def editar(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return
        result = self._view.open_factura_dialog(fac)
        if result:
            self._gestor.upsert_factura_emitida(result)
            self.refresh_facturas()

    def copiar(self):
        sel = self._view.get_selected_ids()
        if not sel:
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return
        nuevo = dict(fac)
        nuevo.pop("id", None)
        nuevo["numero"] = self._proximo_numero()
        nuevo["serie"] = self._serie()
        nuevo["generada"] = False
        nuevo["fecha_generacion"] = ""
        result = self._view.open_factura_dialog(nuevo, numero_sugerido=nuevo["numero"])
        if result:
            self._gestor.upsert_factura_emitida(result)
            self._incrementar_numeracion()
            self.refresh_facturas()

    def eliminar(self):
        sel = self._view.get_selected_ids()
        if not sel:
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar las facturas seleccionadas?"):
            return
        for fid in sel:
            self._gestor.eliminar_factura_emitida(self._codigo, fid, self._ejercicio)
        self.refresh_facturas()

    def terceros(self):
        self._view.open_terceros_dialog(
            self._codigo,
            self._ejercicio,
            int(self._empresa_conf.get("digitos_plan", 8)),
        )

    def export_pdf(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return

        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return

        safe_cliente = self._safe_filename(fac.get("nombre", ""))
        safe_num = self._safe_filename(fac.get("numero", ""))
        base_name = f"{safe_num} {safe_cliente}".strip() or f"Factura_{safe_num}"
        save_path = self._view.ask_save_pdf_path(f"{base_name}.pdf")
        if not save_path:
            return

        template_path = self._docx_template_path()
        if not os.path.exists(template_path):
            self._view.show_error("Gest2A3Eco", "No se encuentra plantilla.docx en la carpeta del programa.")
            return

        cliente = self._cliente_factura(fac)
        tot = self._totales_factura(fac)
        context = build_context_emitida(self._empresa_conf, fac, cliente, tot)

        try:
            generar_pdf_desde_plantilla_word(
                template_path=template_path,
                context=context,
                out_pdf_path=save_path,
                guardar_docx=False,
            )
            self._view.show_info("Gest2A3Eco", f"PDF generado desde Word:\n{save_path}")
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"No se pudo generar el PDF desde Word:\n{e}")

    def generar_suenlace(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_warning("Gest2A3Eco", "Selecciona al menos una factura.")
            return
        plantillas = self._gestor.listar_emitidas(self._codigo, self._ejercicio)
        plantilla = plantillas[0] if plantillas else {}

        facturas_sel = []
        rows = []
        for fid in sel:
            fac = self._get_factura_by_id(fid)
            if fac:
                facturas_sel.append(fac)
                rows.extend(self._factura_to_rows(fac))

        ya_generadas = [f for f in facturas_sel if f.get("generada")]
        if ya_generadas:
            nums = ", ".join(f"{f.get('serie','')}-{f.get('numero','')}" for f in ya_generadas)
            if not self._view.ask_yes_no(
                "Gest2A3Eco",
                "Las facturas {} ya estan marcadas como generadas.\nGenerar suenlace de todas formas?".format(nums),
            ):
                return

        if not rows:
            self._view.show_warning("Gest2A3Eco", "No hay lineas para generar.")
            return

        ndig = int(self._empresa_conf.get("digitos_plan", 8))
        registros = generar_emitidas(rows, plantilla, str(self._codigo), ndig)
        if not registros:
            self._view.show_warning("Gest2A3Eco", "No se generaron registros.")
            return

        save_path = self._view.ask_save_dat_path(f"E{self._codigo}.dat")
        if not save_path:
            return
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(registros)
        fecha_gen = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._gestor.marcar_facturas_emitidas_generadas(self._codigo, sel, fecha_gen, self._ejercicio)
        self.refresh_facturas()
        self._view.show_info("Gest2A3Eco", f"Fichero generado:\n{save_path}")

    def _get_factura_by_id(self, fid):
        return next(
            (
                f
                for f in self._gestor.listar_facturas_emitidas(self._codigo, self._ejercicio)
                if str(f.get("id")) == str(fid)
            ),
            None,
        )

    def _serie(self):
        return str(self._empresa_conf.get("serie_emitidas", "A") or "A")

    def _siguiente_num(self):
        try:
            return int(self._empresa_conf.get("siguiente_num_emitidas", 1))
        except Exception:
            return 1

    def _proximo_numero(self):
        return f"{self._serie()}{self._siguiente_num():06d}"

    def _incrementar_numeracion(self):
        self._empresa_conf["siguiente_num_emitidas"] = self._siguiente_num() + 1
        self._gestor.upsert_empresa(self._empresa_conf)

    def _compute_total(self, fac: dict) -> float:
        total = 0.0
        for ln in fac.get("lineas", []):
            total += (
                self._to_float(ln.get("base"))
                + self._to_float(ln.get("cuota_iva"))
                + self._to_float(ln.get("cuota_re"))
                + self._to_float(ln.get("cuota_irpf"))
            )
        return self._round2(total)

    def _totales_factura(self, fac: dict):
        base = iva = re = ret = 0.0
        for ln in fac.get("lineas", []):
            base += self._to_float(ln.get("base"))
            iva += self._to_float(ln.get("cuota_iva"))
            re += self._to_float(ln.get("cuota_re"))
            ret += self._to_float(ln.get("cuota_irpf"))
        total = base + iva + re + ret
        return {
            "base": self._round2(base),
            "iva": self._round2(iva),
            "re": self._round2(re),
            "ret": self._round2(ret),
            "total": self._round2(total),
        }

    def _cliente_factura(self, fac: dict):
        cli = next(
            (
                t
                for t in self._gestor.listar_terceros()
                if str(t.get("id")) == str(fac.get("tercero_id"))
            ),
            {},
        )
        return {
            "nombre": fac.get("nombre") or cli.get("nombre", ""),
            "nif": fac.get("nif") or cli.get("nif", ""),
            "direccion": cli.get("direccion", ""),
            "cp": cli.get("cp", ""),
            "poblacion": cli.get("poblacion", ""),
            "provincia": cli.get("provincia", ""),
            "telefono": cli.get("telefono", ""),
            "email": cli.get("email", ""),
        }

    def _factura_to_rows(self, fac: dict):
        rows = []
        base_row = {
            "Serie": fac.get("serie", ""),
            "Numero Factura": fac.get("numero", ""),
            "Numero Factura Largo SII": fac.get("numero_largo_sii", ""),
            "Fecha Asiento": fac.get("fecha_asiento", ""),
            "Fecha Expedicion": fac.get("fecha_expedicion") or fac.get("fecha_asiento", ""),
            "Fecha Operacion": fac.get("fecha_operacion", ""),
            "Descripcion Factura": fac.get("descripcion", ""),
            "NIF Cliente Proveedor": fac.get("nif", ""),
            "Nombre Cliente Proveedor": fac.get("nombre", ""),
        }
        if fac.get("subcuenta_cliente"):
            base_row["Cuenta Cliente Proveedor"] = fac.get("subcuenta_cliente")
        for ln in fac.get("lineas", []):
            r = dict(base_row)
            r.update(
                {
                    "Descripcion Linea": ln.get("concepto", "") or fac.get("descripcion", ""),
                    "Base": self._round2(self._to_float(ln.get("base"))),
                    "Cuota IVA": self._round2(self._to_float(ln.get("cuota_iva"))),
                    "Porcentaje IVA": self._round2(self._to_float(ln.get("pct_iva"))),
                    "Porcentaje Recargo Equivalencia": self._round2(self._to_float(ln.get("pct_re"))),
                    "Cuota Recargo Equivalencia": self._round2(self._to_float(ln.get("cuota_re"))),
                    "Porcentaje Retencion IRPF": self._round2(self._to_float(ln.get("pct_irpf"))),
                    "Cuota Retencion IRPF": self._round2(self._to_float(ln.get("cuota_irpf"))),
                }
            )
            rows.append(r)
        return rows

    def _docx_template_path(self) -> str:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "plantillas", "factura_emitida_template.docx")

    def _to_float(self, x) -> float:
        try:
            if x is None or x == "":
                return 0.0
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                return float(x)
            s = str(x).strip().replace("\\xa0", " ")
            if "." in s and "," in s:
                s = s.replace(".", "").replace(",", ".")
            elif "," in s:
                s = s.replace(",", ".")
            return float(s)
        except Exception:
            return 0.0

    def _safe_filename(self, value: str) -> str:
        s = (value or "").strip()
        if not s:
            return ""
        bad = '<>:"/\\\\|?*'
        for ch in bad:
            s = s.replace(ch, " ")
        s = " ".join(s.split())
        return s

    def _cuenta_bancaria_default(self) -> str:
        raw = self._empresa_conf.get("cuenta_bancaria") or ""
        if str(raw).strip():
            return str(raw).strip()
        cuentas = self._empresa_conf.get("cuentas_bancarias") or ""
        for sep in ["\n", ";", ","]:
            cuentas = str(cuentas).replace(sep, ",")
        for p in str(cuentas).split(","):
            p = p.strip()
            if p:
                return p
        return ""

    def _round2(self, x) -> float:
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0
