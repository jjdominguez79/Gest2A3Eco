import os
from collections import defaultdict

import pandas as pd

from procesos.bancos import generar_bancos
from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_recibidas import generar_recibidas_suenlace
from services.excel_mapping import extract_rows_by_mapping


class ProcesosController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._excel_path = None

    def refresh_plantillas(self):
        tipo = (self._view.get_tipo() or "").lower()
        if "bancos" in tipo:
            pls = [p.get("banco") for p in self._gestor.listar_bancos(self._codigo, self._ejercicio)]
        elif "emitidas" in tipo:
            pls = [p.get("nombre") for p in self._gestor.listar_emitidas(self._codigo, self._ejercicio)]
        else:
            pls = [p.get("nombre") for p in self._gestor.listar_recibidas(self._codigo, self._ejercicio)]
        self._view.set_plantillas(pls)

    def cargar_excel(self):
        path = self._view.ask_open_excel_path()
        if not path:
            return
        self._excel_path = path
        self._view.set_excel_label(os.path.basename(path))
        try:
            xls = pd.ExcelFile(path)
            self._view.set_sheet_values(xls.sheet_names)
            self._view.clear_sheet_selection()
            self._view.clear_preview()
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"Error al abrir Excel:\n{e}")

    def preview_excel(self):
        hoja = self._view.get_selected_sheet()
        if not hoja or not self._excel_path:
            return
        try:
            df = pd.read_excel(self._excel_path, sheet_name=hoja, header=0)
            self._view.render_preview(df)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"Error al leer hoja:\n{e}")

    def generar(self):
        try:
            if not self._excel_path or not self._view.get_selected_sheet():
                self._view.show_warning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
                return

            nombre_pl = (self._view.get_selected_plantilla() or "").strip()
            if not nombre_pl:
                self._view.show_warning("Gest2A3Eco", "Selecciona una plantilla.")
                return

            tipo = (self._view.get_tipo() or "").lower()
            if "bancos" in tipo:
                pl = next((x for x in self._gestor.listar_bancos(self._codigo, self._ejercicio) if x.get("banco") == nombre_pl), None)
            elif "emitidas" in tipo:
                pl = next((x for x in self._gestor.listar_emitidas(self._codigo, self._ejercicio) if x.get("nombre") == nombre_pl), None)
            else:
                pl = next((x for x in self._gestor.listar_recibidas(self._codigo, self._ejercicio) if x.get("nombre") == nombre_pl), None)
            if not pl:
                self._view.show_error("Gest2A3Eco", "Plantilla no encontrada.")
                return

            empresa_config = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
            ndig = int(empresa_config.get("digitos_plan", 8))
            codigo_empresa = str(self._codigo)

            excel_conf = pl.get("excel") or {}
            rows = extract_rows_by_mapping(self._excel_path, self._view.get_selected_sheet(), excel_conf)

            if "bancos" in tipo:
                req = ["Fecha Asiento", "Importe", "Concepto"]
                if not self._require_mapeo_or_warn(pl, "bancos", req):
                    return
                try:
                    out_lines, avisos = generar_bancos(rows, pl, codigo_empresa, ndig)
                except ValueError as e:
                    self._view.show_error("Gest2A3Eco", str(e))
                    return
                if not out_lines:
                    msg = "No se generaron lineas para bancos."
                    if avisos:
                        msg += "\n\nSe han detectado problemas de fecha en algunas filas:\n"
                        preview = "\n".join(avisos[:10])
                        if len(avisos) > 10:
                            preview += f"\n... y {len(avisos)-10} filas mas con fecha invalida."
                        msg += preview
                    self._view.show_warning("Gest2A3Eco", msg)
                    return
                save_path = self._view.ask_save_path(f"E{self._codigo}.dat")
                if not save_path:
                    return
                with open(save_path, "w", encoding="latin-1", newline="") as f:
                    f.writelines(out_lines)
                msg = f"Fichero generado:\n{save_path}"
                if avisos:
                    msg += "\n\nATENCION: se han omitido movimientos por fecha invalida:\n"
                    preview = "\n".join(avisos[:10])
                    if len(avisos) > 10:
                        preview += f"\n... y {len(avisos)-10} filas mas."
                    msg += preview
                    self._view.show_warning("Gest2A3Eco - Bancos", msg)
                else:
                    self._view.show_info("Gest2A3Eco", msg)
                return

            if "emitidas" in tipo:
                req = ["Fecha Asiento", "Descripcion Factura", "Base", "Cuota IVA"]
                if not (self._has_letter(excel_conf, "Numero Factura") or self._has_letter(excel_conf, "Numero Factura Largo SII")):
                    req = [k for k in req if k != "Numero Factura"] + ["Numero Factura Largo SII"]
                else:
                    req = ["Numero Factura"] + req
                if not self._require_mapeo_or_warn(pl, "emitidas", req):
                    return
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
                    pl,
                    codigo_empresa,
                    ndig,
                    ejercicio=self._ejercicio,
                    terceros_by_nif=terceros_by_nif,
                )
                if registros:
                    save_path = self._view.ask_save_path(f"E{self._codigo}")
                    if not save_path:
                        return
                    with open(save_path, "w", encoding="latin-1", newline="") as f:
                        f.writelines(registros)
                    self._view.show_info("Gest2A3Eco", f"Fichero generado:\n{save_path}")
                else:
                    self._view.show_warning("Gest2A3Eco", "No se generaron registros para facturas emitidas.")
                return

            req = ["Fecha Asiento", "Descripcion Factura", "Base", "Cuota IVA"]
            if not (self._has_letter(excel_conf, "Numero Factura") or self._has_letter(excel_conf, "Numero Factura Largo SII")):
                req = [k for k in req if k != "Numero Factura"] + ["Numero Factura Largo SII"]
            else:
                req = ["Numero Factura"] + req
            if not self._require_mapeo_or_warn(pl, "recibidas", req):
                return
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
            out_lines = generar_recibidas_suenlace(
                rows,
                pl,
                codigo_empresa,
                ndig,
                ejercicio=self._ejercicio,
                terceros_by_nif=terceros_by_nif,
            )
            avisos = []
            if out_lines:
                save_path = self._view.ask_save_path(f"E{self._codigo}")
                if not save_path:
                    return
                with open(save_path, "w", encoding="latin-1", newline="") as f:
                    f.writelines(out_lines)
                msg = f"Fichero generado:\n{save_path}"
                if avisos:
                    preview = "\n".join(avisos[:10])
                    if len(avisos) > 10:
                        preview += f"\n... y {len(avisos)-10} descuadres mas."
                    msg += f"\n\nATENCION: se han detectado descuadres:\n{preview}"
                    self._view.show_warning("Gest2A3Eco - Descuadres", msg)
                else:
                    self._view.show_info("Gest2A3Eco", msg)
            else:
                self._view.show_warning("Gest2A3Eco", "No se generaron registros para facturas recibidas.")
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"Error en la generacion:\n{e}")

    def _has_letter(self, pl_excel, key):
        cols = (pl_excel or {}).get("columnas", {})
        val = cols.get(key, "")
        return bool(str(val).strip())

    def _require_mapeo_or_warn(self, pl, tipo, required_keys):
        pl_excel = pl.get("excel") or {}
        missing = [k for k in required_keys if not self._has_letter(pl_excel, k)]
        if missing:
            self._view.show_error(
                "Gest2A3Eco",
                "La plantilla de {} no tiene mapeadas estas columnas:\n- {}".format(
                    tipo, "\n- ".join(missing)
                ),
            )
            return False
        return True
