import os
import shutil
import sys
import webbrowser
import subprocess
from urllib.parse import quote
from datetime import datetime
import traceback

from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_word import (
    build_context_emitida,
    generar_pdf_desde_plantilla_word,
)
from procesos.facturas_pdf_basico import generar_pdf_basico
from utils.utilidades import aplicar_descuento_total_lineas, load_monedas


class FacturasEmitidasController:
    def __init__(self, gestor, codigo, ejercicio, empresa_conf, view, allow_all_years: bool = False):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._empresa_conf = empresa_conf
        self._view = view
        self._allow_all_years = bool(allow_all_years)
        self._facturas_cache = []

    def refresh_plantillas(self):
        pls = [p.get("nombre") for p in self._gestor.listar_emitidas(self._codigo, self._ejercicio)]
        self._view.set_plantillas(pls)

    def refresh_facturas(self):
        self._facturas_cache = self._listar_facturas_base()
        if self._allow_all_years:
            years = sorted({y for y in (self._year_from_factura(f) for f in self._facturas_cache) if y is not None})
            self._view.set_facturas_years(years)
        self.apply_facturas_filter()
        self._view.set_detalle_lineas([])

    def apply_facturas_filter(self):
        self._view.clear_facturas()
        year_filter = self._view.get_facturas_year_filter() if self._allow_all_years else None
        for fac in self._facturas_cache:
            if year_filter is not None:
                fyear = self._year_from_factura(fac)
                if fyear != year_filter:
                    continue
            total = self._compute_total(fac)
            self._view.insert_factura_row(fac, total)

    def refresh_albaranes(self):
        self._view.clear_albaranes()
        for alb in self._gestor.listar_albaranes_emitidas(self._codigo, self._ejercicio):
            total = self._compute_total(alb)
            self._view.insert_albaran_row(alb, total)
        self._view.set_albaran_lineas([])

    def nueva(self):
        fecha_sug = datetime.now().strftime("%d/%m/%Y")
        sugerido, serie_sug, eje_sug = self._proximo_numero_por_fecha(fecha_sug, rectificativa=False)
        cuenta_default = self._cuenta_bancaria_default()
        result = self._view.open_factura_dialog(
            {
                "codigo_empresa": self._codigo,
                "ejercicio": eje_sug if eje_sug is not None else self._ejercicio,
                "serie": serie_sug,
                "numero": sugerido,
                "forma_pago": "",
                "cuenta_bancaria": cuenta_default,
                "fecha_asiento": fecha_sug,
            },
            numero_sugerido=sugerido,
        )
        if result:
            result = self._ajustar_numero_por_fecha_si_aplica(result, sugerido, serie_sug, rectificativa=False)
            result["generada"] = False
            result["fecha_generacion"] = ""
            if result.get("ejercicio") is None:
                result["ejercicio"] = self._ejercicio
            result["codigo_empresa"] = self._codigo
            self._gestor.upsert_factura_emitida(result)
            self._incrementar_numeracion_por_factura(result, rectificativa=False)
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
        fecha_base = fac.get("fecha_asiento") or datetime.now().strftime("%d/%m/%Y")
        sugerido, serie_sug, eje_sug = self._proximo_numero_por_fecha(fecha_base, rectificativa=False)
        nuevo["numero"] = sugerido
        nuevo["serie"] = serie_sug
        nuevo["ejercicio"] = eje_sug if eje_sug is not None else self._ejercicio
        nuevo["generada"] = False
        nuevo["fecha_generacion"] = ""
        result = self._view.open_factura_dialog(nuevo, numero_sugerido=nuevo["numero"])
        if result:
            result = self._ajustar_numero_por_fecha_si_aplica(result, sugerido, serie_sug, rectificativa=False)
            self._gestor.upsert_factura_emitida(result)
            self._incrementar_numeracion_por_factura(result, rectificativa=False)
            self.refresh_facturas()

    def rectificar(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return
        nuevo = dict(fac)
        nuevo.pop("id", None)
        fecha_base = fac.get("fecha_asiento") or datetime.now().strftime("%d/%m/%Y")
        sugerido, serie_sug, eje_sug = self._proximo_numero_por_fecha(fecha_base, rectificativa=True)
        nuevo["numero"] = sugerido
        nuevo["serie"] = serie_sug
        nuevo["ejercicio"] = eje_sug if eje_sug is not None else self._ejercicio
        nuevo["generada"] = False
        nuevo["fecha_generacion"] = ""
        nuevo["enviado"] = False
        nuevo["fecha_envio"] = ""
        nuevo["canal_envio"] = ""
        nuevo["_allow_fecha_fuera_ejercicio"] = True
        nuevo["lineas"] = self._negate_factura_lineas(nuevo.get("lineas", []))
        nuevo["retencion_base"] = self._negate_value(nuevo.get("retencion_base"))
        nuevo["retencion_importe"] = self._negate_value(nuevo.get("retencion_importe"))
        result = self._view.open_factura_dialog(nuevo, numero_sugerido=nuevo["numero"])
        if result:
            result = self._ajustar_numero_por_fecha_si_aplica(result, sugerido, serie_sug, rectificativa=True)
            self._gestor.upsert_factura_emitida(result)
            self._incrementar_numeracion_por_factura(result, rectificativa=True)
            self.refresh_facturas()

    def eliminar(self):
        sel = self._view.get_selected_ids()
        if not sel:
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar las facturas seleccionadas?"):
            return
        for fid in sel:
            fac = self._get_factura_by_id(fid)
            if not fac:
                continue
            eje = fac.get("ejercicio") if fac.get("ejercicio") is not None else self._ejercicio
            self._gestor.eliminar_factura_emitida(self._codigo, fid, eje)
        self.refresh_facturas()

    def terceros(self):
        self._view.open_terceros_dialog(
            self._codigo,
            self._ejercicio,
            int(self._empresa_conf.get("digitos_plan", 8)),
        )

    def factura_seleccionada(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.set_detalle_lineas([])
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            self._view.set_detalle_lineas([])
            return
        self._view.set_detalle_lineas(fac.get("lineas", []), fac.get("moneda_simbolo", ""))

    def albaran_seleccionado(self):
        sel = self._view.get_selected_albaran_ids()
        if not sel:
            self._view.set_albaran_lineas([])
            return
        alb = self._get_albaran_by_id(sel[0])
        if not alb:
            self._view.set_albaran_lineas([])
            return
        self._view.set_albaran_lineas(alb.get("lineas", []), alb.get("moneda_simbolo", ""))

    def nuevo_albaran(self):
        sugerido = self._proximo_albaran_numero()
        cuenta_default = self._cuenta_bancaria_default()
        result = self._view.open_albaran_dialog(
            {
                "codigo_empresa": self._codigo,
                "ejercicio": self._ejercicio,
                "serie": "ALB",
                "numero": sugerido,
                "forma_pago": "",
                "cuenta_bancaria": cuenta_default,
            },
            numero_sugerido=sugerido,
        )
        if result:
            result["facturado"] = False
            result["factura_id"] = ""
            result["fecha_facturacion"] = ""
            result["ejercicio"] = self._ejercicio
            result["codigo_empresa"] = self._codigo
            self._gestor.upsert_albaran_emitida(result)
            self.refresh_albaranes()

    def editar_albaran(self):
        sel = self._view.get_selected_albaran_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona un albaran.")
            return
        alb = self._get_albaran_by_id(sel[0])
        if not alb:
            return
        if alb.get("facturado"):
            self._view.show_warning("Gest2A3Eco", "El albaran ya esta facturado.")
            return
        result = self._view.open_albaran_dialog(alb)
        if result:
            self._gestor.upsert_albaran_emitida(result)
            self.refresh_albaranes()

    def copiar_albaran(self):
        sel = self._view.get_selected_albaran_ids()
        if not sel:
            return
        alb = self._get_albaran_by_id(sel[0])
        if not alb:
            return
        nuevo = dict(alb)
        nuevo.pop("id", None)
        nuevo["numero"] = self._proximo_albaran_numero()
        nuevo["serie"] = "ALB"
        nuevo["facturado"] = False
        nuevo["factura_id"] = ""
        nuevo["fecha_facturacion"] = ""
        result = self._view.open_albaran_dialog(nuevo, numero_sugerido=nuevo["numero"])
        if result:
            self._gestor.upsert_albaran_emitida(result)
            self.refresh_albaranes()

    def eliminar_albaran(self):
        sel = self._view.get_selected_albaran_ids()
        if not sel:
            return
        alb = self._get_albaran_by_id(sel[0])
        if alb and alb.get("facturado"):
            self._view.show_warning("Gest2A3Eco", "El albaran ya esta facturado.")
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar los albaranes seleccionados?"):
            return
        for aid in sel:
            self._gestor.eliminar_albaran_emitida(self._codigo, aid, self._ejercicio)
        self.refresh_albaranes()

    def facturar_albaranes(self):
        sel = self._view.get_selected_albaran_ids()
        if not sel:
            self._view.show_warning("Gest2A3Eco", "Selecciona uno o varios albaranes.")
            return
        try:
            if int(datetime.now().strftime("%Y")) != int(self._ejercicio):
                self._view.show_warning(
                    "Gest2A3Eco",
                    f"No se puede emitir factura fuera del ejercicio {self._ejercicio}.",
                )
                return
        except Exception:
            pass
        albaranes = []
        for aid in sel:
            alb = self._get_albaran_by_id(aid)
            if alb:
                if alb.get("facturado"):
                    continue
                albaranes.append(alb)
        if not albaranes:
            self._view.show_warning("Gest2A3Eco", "No hay albaranes pendientes de facturar.")
            return
        nifs = {str(a.get("nif") or "").strip() for a in albaranes}
        if len(nifs) > 1:
            self._view.show_warning("Gest2A3Eco", "Los albaranes seleccionados tienen distintos clientes.")
            return
        base = albaranes[0]
        moneda_codigo = base.get("moneda_codigo", "")
        moneda_simbolo = base.get("moneda_simbolo", "")
        if not moneda_codigo:
            monedas = load_monedas()
            if monedas:
                moneda_codigo = str(monedas[0].get("codigo") or "").upper()
                moneda_simbolo = str(monedas[0].get("simbolo") or "")
        nums = ", ".join(a.get("numero", "") for a in albaranes)
        lineas = []
        for a in albaranes:
            lineas.extend(a.get("lineas", []))
        fecha = datetime.now().strftime("%d/%m/%Y")
        sugerido, serie_sug, eje_sug = self._proximo_numero_por_fecha(fecha, rectificativa=False)
        factura = {
            "codigo_empresa": self._codigo,
            "ejercicio": eje_sug if eje_sug is not None else self._ejercicio,
            "tercero_id": base.get("tercero_id"),
            "serie": serie_sug,
            "numero": sugerido,
            "numero_largo_sii": "",
            "fecha_asiento": fecha,
            "fecha_expedicion": fecha,
            "fecha_operacion": fecha,
            "nif": base.get("nif", ""),
            "nombre": base.get("nombre", ""),
            "descripcion": f"Factura de albaranes: {nums}",
            "subcuenta_cliente": base.get("subcuenta_cliente", ""),
            "forma_pago": base.get("forma_pago", ""),
            "cuenta_bancaria": base.get("cuenta_bancaria", ""),
            "moneda_codigo": moneda_codigo,
            "moneda_simbolo": moneda_simbolo,
            "plantilla_word": base.get("plantilla_word", ""),
            "retencion_aplica": bool(base.get("retencion_aplica")),
            "retencion_pct": base.get("retencion_pct"),
            "retencion_base": base.get("retencion_base"),
            "retencion_importe": base.get("retencion_importe"),
            "lineas": lineas,
            "generada": False,
            "fecha_generacion": "",
        }
        fid = self._gestor.upsert_factura_emitida(factura)
        self._incrementar_numeracion_por_factura(factura, rectificativa=False)
        fecha_gen = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._gestor.marcar_albaranes_facturados(self._codigo, [a.get("id") for a in albaranes], fid, fecha_gen, self._ejercicio)
        self.refresh_facturas()
        self.refresh_albaranes()
        self._view.show_info("Gest2A3Eco", f"Factura generada desde albaranes:\n{factura.get('serie','')}{factura.get('numero','')}")

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

        template_path = self._docx_template_path(fac, warn_missing=True)
        if not os.path.exists(template_path):
            self._view.show_error("Gest2A3Eco", "No se encuentra plantilla.docx en la carpeta del programa.")
            return

        cliente = self._cliente_factura(fac)
        tot = self._totales_factura(fac)
        context = build_context_emitida(self._empresa_conf_for_word(), fac, cliente, tot)

        try:
            generar_pdf_desde_plantilla_word(
                template_path=template_path,
                context=context,
                out_pdf_path=save_path,
                guardar_docx=False,
            )
            self._store_pdf_copies(fac, save_path)
            self._view.show_info("Gest2A3Eco", f"PDF generado desde Word:\n{save_path}")
        except Exception as e:
            self._log_pdf_error("Error al generar PDF con Word.", e, template_path, save_path)
            try:
                generar_pdf_basico(self._empresa_conf, fac, cliente, tot, save_path)
                self._store_pdf_copies(fac, save_path)
                self._view.show_warning(
                    "Gest2A3Eco",
                    "No se pudo generar el PDF desde Word:\n"
                    f"{e}\n\nSe genero un PDF basico:\n{save_path}",
                )
            except Exception as e2:
                self._log_pdf_error("Error al generar PDF basico.", e2, template_path, save_path)
                self._view.show_error(
                    "Gest2A3Eco",
                    f"No se pudo generar el PDF:\n{e}\n{e2}",
                )

    def abrir_pdf(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return
        self._ensure_app_pdf(fac)
        pdf_path = str(fac.get("pdf_path") or "").strip()
        if not pdf_path:
            pdf_path = self._app_pdf_path(fac)
        if not pdf_path or not os.path.exists(pdf_path):
            self._ensure_a3_pdf(fac)
            pdf_path = str(fac.get("pdf_path_a3") or "").strip()
        if not pdf_path or not os.path.exists(pdf_path):
            self._view.show_warning("Gest2A3Eco", "No se encuentra el PDF asociado.")
            return
        try:
            os.startfile(pdf_path)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"No se pudo abrir el PDF:\n{e}")

    def compartir_pdf(self):
        sel = self._view.get_selected_ids()
        if not sel:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = self._get_factura_by_id(sel[0])
        if not fac:
            return
        canal = self._view.ask_share_channel()
        if not canal:
            return
        self._ensure_app_pdf(fac)
        pdf_path = str(fac.get("pdf_path") or "").strip()
        if not pdf_path:
            pdf_path = self._app_pdf_path(fac)
        if not pdf_path or not os.path.exists(pdf_path):
            self._ensure_a3_pdf(fac)
            pdf_path = str(fac.get("pdf_path_a3") or "").strip()
        if not pdf_path or not os.path.exists(pdf_path):
            self._view.show_warning("Gest2A3Eco", "No se encuentra el PDF asociado.")
            return

        serie = str(fac.get("serie", "") or "")
        numero = str(fac.get("numero", "") or "")
        asunto = f"Factura {serie}{numero}".strip()
        cuerpo = f"Adjunto factura {serie}{numero}.".strip()

        if canal == "email":
            cliente = self._cliente_factura(fac)
            email = str(cliente.get("email") or "").strip()
            if not email:
                email = self._view.ask_email("")
            if not email:
                return
            try:
                url = "mailto:{}?subject={}&body={}".format(
                    quote(email), quote(asunto), quote(cuerpo)
                )
                webbrowser.open(url)
            except Exception:
                pass
        elif canal == "whatsapp":
            try:
                webbrowser.open("https://web.whatsapp.com/")
            except Exception:
                pass

        self._view.copy_to_clipboard(pdf_path)
        try:
            subprocess.run(["explorer.exe", f"/select,{pdf_path}"], check=False)
        except Exception:
            try:
                os.startfile(os.path.dirname(pdf_path))
            except Exception:
                pass

        if self._view.ask_yes_no("Gest2A3Eco", "¿Marcar factura como enviada?"):
            fecha_envio = datetime.now().strftime("%Y-%m-%d %H:%M")
            eje = fac.get("ejercicio") if fac.get("ejercicio") is not None else self._ejercicio
            self._gestor.marcar_factura_emitida_enviada(
                self._codigo, fac.get("id"), fecha_envio, canal, eje
            )
            self.refresh_facturas()

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
                fac = self._ensure_pdf_ref(fac)
                self._ensure_app_pdf(fac)
                self._ensure_a3_pdf(fac)
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
        terceros = self._gestor.listar_terceros()
        terceros_by_nif = {
            str(t.get("nif") or "").strip().upper(): t
            for t in terceros
            if str(t.get("nif") or "").strip()
        }
        terceros_empresa = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        for t in terceros_empresa:
            nif = str(t.get("nif") or "").strip().upper()
            if nif:
                terceros_by_nif[nif] = t
        registros = generar_emitidas(
            rows,
            plantilla,
            str(self._codigo),
            ndig,
            ejercicio=self._ejercicio,
            terceros_by_nif=terceros_by_nif,
        )
        if not registros:
            self._view.show_warning("Gest2A3Eco", "No se generaron registros.")
            return

        save_path = self._view.ask_save_dat_path(f"E{self._codigo}.dat")
        if not save_path:
            return
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(registros)
        fecha_gen = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self._allow_all_years:
            grupos = {}
            for fac in facturas_sel:
                eje = fac.get("ejercicio") if fac.get("ejercicio") is not None else self._ejercicio
                grupos.setdefault(eje, []).append(fac.get("id"))
            for eje, ids in grupos.items():
                self._gestor.marcar_facturas_emitidas_generadas(self._codigo, ids, fecha_gen, eje)
        else:
            self._gestor.marcar_facturas_emitidas_generadas(self._codigo, sel, fecha_gen, self._ejercicio)
        self.refresh_facturas()
        self._view.show_info("Gest2A3Eco", f"Fichero generado:\n{save_path}")

    def _get_factura_by_id(self, fid):
        for f in self._facturas_cache or []:
            if str(f.get("id")) == str(fid):
                return f
        for f in self._listar_facturas_base():
            if str(f.get("id")) == str(fid):
                return f
        return None

    def _listar_facturas_base(self):
        if self._allow_all_years:
            return self._gestor.listar_facturas_emitidas_global(self._codigo, None)
        return self._gestor.listar_facturas_emitidas(self._codigo, self._ejercicio)

    def _year_from_factura(self, fac: dict):
        txt = str(fac.get("fecha_asiento") or fac.get("fecha_expedicion") or "").strip()
        year = self._year_from_fecha_txt(txt)
        if year is not None:
            return year
        try:
            return int(fac.get("ejercicio"))
        except Exception:
            return None

    def _year_from_fecha_txt(self, txt: str):
        txt = str(txt or "").strip()
        if not txt:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(txt, fmt).year
            except Exception:
                continue
        return None

    def _get_albaran_by_id(self, aid):
        return next(
            (
                a
                for a in self._gestor.listar_albaranes_emitidas(self._codigo, self._ejercicio)
                if str(a.get("id")) == str(aid)
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

    def _serie_for_year(self, year: int | None, rectificativa: bool = False) -> str:
        emp = self._empresa_for_year(year)
        if rectificativa:
            serie = str(emp.get("serie_emitidas_rect") or "").strip()
            if not serie:
                serie = "R"
            return serie
        return str(emp.get("serie_emitidas", "A") or "A")

    def _siguiente_num_for_year(self, year: int | None, rectificativa: bool = False) -> int:
        emp = self._empresa_for_year(year)
        key = "siguiente_num_emitidas_rect" if rectificativa else "siguiente_num_emitidas"
        try:
            return int(emp.get(key, 1))
        except Exception:
            return 1

    def _proximo_numero_por_fecha(self, fecha_txt: str, rectificativa: bool = False):
        year = self._year_from_fecha_txt(fecha_txt)
        serie = self._serie_for_year(year, rectificativa=rectificativa)
        num = self._siguiente_num_for_year(year, rectificativa=rectificativa)
        return f"{serie}{num:06d}", serie, year

    def _incrementar_numeracion_por_factura(self, fac: dict, rectificativa: bool = False):
        year = self._year_from_factura(fac)
        emp = self._empresa_for_year(year)
        key = "siguiente_num_emitidas_rect" if rectificativa else "siguiente_num_emitidas"
        try:
            emp[key] = int(emp.get(key, 1)) + 1
        except Exception:
            emp[key] = 2
        self._gestor.upsert_empresa(emp)
        if year == self._ejercicio:
            self._empresa_conf.update(emp)

    def _ajustar_numero_por_fecha_si_aplica(self, fac: dict, numero_sugerido: str, serie_sugerida: str, rectificativa: bool = False):
        num_actual = str(fac.get("numero") or "")
        serie_actual = str(fac.get("serie") or "")
        if num_actual == str(numero_sugerido) and serie_actual == str(serie_sugerida):
            fecha_base = fac.get("fecha_asiento") or fac.get("fecha_expedicion") or ""
            sugerido, serie_sug, year = self._proximo_numero_por_fecha(fecha_base, rectificativa=rectificativa)
            fac["numero"] = sugerido
            fac["serie"] = serie_sug
            if year is not None:
                fac["ejercicio"] = year
        return fac

    def _empresa_for_year(self, year: int | None):
        if year is None:
            return dict(self._empresa_conf)
        emp = self._gestor.get_empresa(self._codigo, year)
        if emp:
            changed = False
            if not str(emp.get("serie_emitidas_rect") or "").strip():
                emp["serie_emitidas_rect"] = "R"
                changed = True
            if emp.get("siguiente_num_emitidas_rect") in (None, ""):
                emp["siguiente_num_emitidas_rect"] = 1
                changed = True
            if changed:
                self._gestor.upsert_empresa(emp)
            return emp
        base = dict(self._empresa_conf)
        base["ejercicio"] = year
        base.setdefault("serie_emitidas", "A")
        base.setdefault("siguiente_num_emitidas", 1)
        base.setdefault("serie_emitidas_rect", "R")
        base.setdefault("siguiente_num_emitidas_rect", 1)
        base["activo"] = True
        self._gestor.upsert_empresa(base)
        return base

    def _proximo_albaran_numero(self):
        pref = f"Alb-{self._ejercicio}-"
        max_n = 0
        for a in self._gestor.listar_albaranes_emitidas(self._codigo, self._ejercicio):
            num_txt = str(a.get("numero") or "")
            if pref in num_txt:
                tail = num_txt.split(pref, 1)[-1]
            else:
                tail = "".join(ch for ch in num_txt if ch.isdigit())
            digits = "".join(ch for ch in tail if ch.isdigit())
            if digits:
                try:
                    max_n = max(max_n, int(digits))
                except Exception:
                    pass
        return f"{pref}{max_n + 1:05d}"

    def _compute_total(self, fac: dict) -> float:
        total = 0.0
        lineas = aplicar_descuento_total_lineas(
            fac.get("lineas", []),
            fac.get("descuento_total_tipo"),
            fac.get("descuento_total_valor"),
        )
        for ln in lineas:
            total += (
                self._to_float(ln.get("base"))
                + self._to_float(ln.get("cuota_iva"))
                + self._to_float(ln.get("cuota_re"))
            )
        total += self._retencion_importe(fac)
        return self._round2(total)

    def _totales_factura(self, fac: dict):
        base = iva = re = 0.0
        lineas = aplicar_descuento_total_lineas(
            fac.get("lineas", []),
            fac.get("descuento_total_tipo"),
            fac.get("descuento_total_valor"),
        )
        for ln in lineas:
            base += self._to_float(ln.get("base"))
            iva += self._to_float(ln.get("cuota_iva"))
            re += self._to_float(ln.get("cuota_re"))
        ret = self._retencion_importe(fac)
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
            "_pdf_ref": fac.get("pdf_ref", ""),
        }
        if fac.get("subcuenta_cliente"):
            base_row["Cuenta Cliente Proveedor"] = fac.get("subcuenta_cliente")
        lineas = aplicar_descuento_total_lineas(
            list(fac.get("lineas", [])),
            fac.get("descuento_total_tipo"),
            fac.get("descuento_total_valor"),
        )
        ret_pct = self._round2(self._to_float(fac.get("retencion_pct")))
        ret_importe = self._retencion_importe(fac)
        lineas_validas = [ln for ln in lineas if str(ln.get("tipo") or "").strip().lower() != "obs"]
        for idx, ln in enumerate(lineas_validas):
            ret_aplica_linea = ret_importe != 0 and idx == len(lineas_validas) - 1
            r = dict(base_row)
            r.update(
                {
                    "Descripcion Linea": ln.get("concepto", "") or fac.get("descripcion", ""),
                    "Base": self._round2(self._to_float(ln.get("base"))),
                    "Cuota IVA": self._round2(self._to_float(ln.get("cuota_iva"))),
                    "Porcentaje IVA": self._round2(self._to_float(ln.get("pct_iva"))),
                    "Porcentaje Recargo Equivalencia": self._round2(self._to_float(ln.get("pct_re"))),
                    "Cuota Recargo Equivalencia": self._round2(self._to_float(ln.get("cuota_re"))),
                    "Porcentaje Retencion IRPF": ret_pct if ret_aplica_linea else 0.0,
                    "Cuota Retencion IRPF": ret_importe if ret_aplica_linea else 0.0,
                }
            )
            rows.append(r)
        return rows

    def _docx_template_path(self, fac: dict | None = None, warn_missing: bool = False) -> str:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_path = os.path.join(base_dir, "plantillas", "factura_emitida_template.docx")
        if not fac:
            return default_path
        chosen = str(fac.get("plantilla_word") or "").strip()
        if not chosen:
            return default_path
        candidate = os.path.join(base_dir, "plantillas", chosen)
        if os.path.exists(candidate):
            return candidate
        if warn_missing:
            self._view.show_warning(
                "Gest2A3Eco",
                f"No se encuentra la plantilla seleccionada:\n{chosen}\nSe usara la plantilla por defecto.",
            )
        return default_path

    def _empresa_conf_for_word(self) -> dict:
        emp = dict(self._empresa_conf or {})
        emp.setdefault("codigo", self._codigo)
        emp.setdefault("codigo_empresa", self._codigo)
        return emp

    def _store_pdf_copies(self, fac: dict, src_path: str) -> None:
        fac = self._ensure_pdf_ref(fac)
        upd = dict(fac)
        app_path = self._app_pdf_path(fac)
        if app_path:
            try:
                shutil.copy2(src_path, app_path)
                upd["pdf_path"] = app_path
            except Exception:
                pass
        a3_path = self._a3_pdf_path_for(
            fac.get("pdf_ref", ""),
            fac.get("ejercicio") if fac.get("ejercicio") is not None else self._ejercicio,
        )
        if a3_path:
            try:
                shutil.copy2(src_path, a3_path)
                upd["pdf_path_a3"] = a3_path
            except Exception:
                pass
        self._gestor.upsert_factura_emitida(upd)

    def _ensure_app_pdf(self, fac: dict) -> None:
        pdf_ref = str(fac.get("pdf_ref") or "").strip()
        if not pdf_ref:
            return
        app_path = self._app_pdf_path(fac)
        if not app_path:
            return
        if os.path.exists(app_path):
            if fac.get("pdf_path") != app_path:
                upd = dict(fac)
                upd["pdf_path"] = app_path
                self._gestor.upsert_factura_emitida(upd)
            return
        existing_path = str(fac.get("pdf_path") or "").strip()
        if existing_path and os.path.exists(existing_path):
            try:
                shutil.copy2(existing_path, app_path)
                upd = dict(fac)
                if existing_path.lower().startswith("z:\\") and not fac.get("pdf_path_a3"):
                    upd["pdf_path_a3"] = existing_path
                upd["pdf_path"] = app_path
                self._gestor.upsert_factura_emitida(upd)
                return
            except Exception:
                pass
        a3_path = str(fac.get("pdf_path_a3") or "").strip()
        if a3_path and os.path.exists(a3_path):
            try:
                shutil.copy2(a3_path, app_path)
                upd = dict(fac)
                upd["pdf_path"] = app_path
                self._gestor.upsert_factura_emitida(upd)
                return
            except Exception:
                pass
        template_path = self._docx_template_path(fac, warn_missing=False)
        cliente = self._cliente_factura(fac)
        tot = self._totales_factura(fac)
        context = build_context_emitida(self._empresa_conf_for_word(), fac, cliente, tot)
        try:
            if os.path.exists(template_path):
                generar_pdf_desde_plantilla_word(
                    template_path=template_path,
                    context=context,
                    out_pdf_path=app_path,
                    guardar_docx=False,
                )
            else:
                generar_pdf_basico(self._empresa_conf, fac, cliente, tot, app_path)
        except Exception:
            return
        upd = dict(fac)
        upd["pdf_path"] = app_path
        self._gestor.upsert_factura_emitida(upd)

    def _ensure_a3_pdf(self, fac: dict) -> None:
        pdf_ref = str(fac.get("pdf_ref") or "").strip()
        if not pdf_ref:
            return
        a3_path = self._a3_pdf_path_for(pdf_ref, fac.get("ejercicio") if fac.get("ejercicio") is not None else self._ejercicio)
        if not a3_path:
            return
        if os.path.exists(a3_path):
            if fac.get("pdf_path_a3") != a3_path:
                upd = dict(fac)
                upd["pdf_path_a3"] = a3_path
                self._gestor.upsert_factura_emitida(upd)
            return
        app_path = str(fac.get("pdf_path") or "").strip()
        if app_path and os.path.exists(app_path):
            try:
                shutil.copy2(app_path, a3_path)
                upd = dict(fac)
                upd["pdf_path_a3"] = a3_path
                self._gestor.upsert_factura_emitida(upd)
                return
            except Exception:
                pass
        template_path = self._docx_template_path(fac, warn_missing=False)
        cliente = self._cliente_factura(fac)
        tot = self._totales_factura(fac)
        context = build_context_emitida(self._empresa_conf_for_word(), fac, cliente, tot)
        try:
            if os.path.exists(template_path):
                generar_pdf_desde_plantilla_word(
                    template_path=template_path,
                    context=context,
                    out_pdf_path=a3_path,
                    guardar_docx=False,
                )
            else:
                generar_pdf_basico(self._empresa_conf, fac, cliente, tot, a3_path)
        except Exception:
            return
        upd = dict(fac)
        upd["pdf_path_a3"] = a3_path
        self._gestor.upsert_factura_emitida(upd)

    def _app_pdf_path(self, fac: dict) -> str:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdf_dir = os.path.join(base_dir, "pdfs_emitidas")
        emp_name = self._safe_filename(self._empresa_conf.get("nombre") or "") or "Sin_empresa"
        cliente = self._safe_filename(fac.get("nombre", "")) or "Sin_cliente"
        num = self._safe_filename(f"{fac.get('numero','')}")
        filename = f"{num} {cliente}".strip() if num or cliente else f"Factura_{fac.get('id','')}"
        try:
            os.makedirs(os.path.join(pdf_dir, emp_name), exist_ok=True)
        except Exception:
            return ""
        if not filename:
            return ""
        return os.path.join(pdf_dir, emp_name, f"{filename}.pdf")

    def _a3_pdf_path(self, pdf_ref: str) -> str:
        return self._a3_pdf_path_for(pdf_ref, self._ejercicio)

    def _a3_pdf_path_for(self, pdf_ref: str, ejercicio) -> str:
        codigo = str(self._codigo or "").strip()
        ejercicio = str(ejercicio or "").strip()
        if not codigo or not ejercicio:
            return ""
        base_dir = os.path.join("Z:\\", "A3", "A3ECO", f"E{codigo}", "FACTURAS", ejercicio)
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            return ""
        ref = str(pdf_ref or "").strip()
        filename = f"{ref}.pdf" if ref else ""
        if not filename:
            return ""
        return os.path.join(base_dir, filename)

    def _ensure_pdf_ref(self, fac: dict) -> dict:
        ref = str(fac.get("pdf_ref") or "").strip()
        if ref:
            base_ref = ref.split("@", 1)[0].strip()
            if base_ref and base_ref != ref:
                fac = dict(fac)
                fac["pdf_ref"] = base_ref
                self._gestor.upsert_factura_emitida(fac)
            return fac
        raw_id = "".join(ch for ch in str(fac.get("id") or "") if ch.isdigit())
        if not raw_id:
            raw_id = str(int(datetime.now().timestamp() * 1000))
        prefix = "E"
        ref = f"{prefix}{raw_id[-8:].rjust(8, '0')}"
        fac = dict(fac)
        fac["pdf_ref"] = ref
        self._gestor.upsert_factura_emitida(fac)
        return fac

    def _log_pdf_error(self, msg: str, exc: Exception, template_path: str, save_path: str) -> None:
        try:
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "pdf_error.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n---- PDF ERROR ----\n")
                f.write(f"Message: {msg}\n")
                f.write(f"Template: {template_path}\n")
                f.write(f"Output: {save_path}\n")
                f.write("Exception:\n")
                f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            pass

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

    def _retencion_importe(self, fac: dict) -> float:
        if not fac:
            return 0.0
        if not bool(fac.get("retencion_aplica")):
            ret_lineas = 0.0
            for ln in fac.get("lineas", []):
                ret_lineas += self._to_float(ln.get("cuota_irpf"))
            return self._round2(ret_lineas)
        importe = fac.get("retencion_importe")
        if importe is None or importe == "":
            base = self._to_float(fac.get("retencion_base"))
            pct = self._to_float(fac.get("retencion_pct"))
            return self._round2(-abs(base * pct / 100.0)) if pct else 0.0
        return self._round2(self._to_float(importe))

    def _negate_factura_lineas(self, lineas):
        out = []
        for ln in lineas or []:
            nl = dict(ln)
            if str(nl.get("tipo") or "").strip().lower() == "obs":
                out.append(nl)
                continue
            nl["base"] = self._negate_value(nl.get("base"))
            nl["cuota_iva"] = self._negate_value(nl.get("cuota_iva"))
            nl["cuota_re"] = self._negate_value(nl.get("cuota_re"))
            nl["cuota_irpf"] = self._negate_value(nl.get("cuota_irpf"))
            out.append(nl)
        return out

    def _negate_value(self, value):
        if value in (None, ""):
            return value
        try:
            val = self._to_float(value)
        except Exception:
            return value
        if val == 0:
            return 0.0
        return -abs(val)

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
