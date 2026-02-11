import os
import traceback
from collections import defaultdict
import unicodedata

import pandas as pd

from procesos.bancos import generar_bancos
from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_recibidas import generar_recibidas_suenlace
from services.excel_mapping import extract_rows_by_mapping
from utils.utilidades import validar_subcuenta_longitud


class ProcesosController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._excel_path = None

    def refresh_plantillas(self):
        tipo = (self._view.get_tipo() or "").lower()
        if "terceros" in tipo:
            self._view.set_plantillas([])
            self._view.set_plantilla_enabled(False)
            self._view.set_generar_text("Importar terceros")
            return
        if "bancos" in tipo:
            pls = [p.get("banco") for p in self._gestor.listar_bancos(self._codigo, self._ejercicio)]
        elif "emitidas" in tipo:
            pls = [p.get("nombre") for p in self._gestor.listar_emitidas(self._codigo, self._ejercicio)]
        else:
            pls = [p.get("nombre") for p in self._gestor.listar_recibidas(self._codigo, self._ejercicio)]
        self._view.set_plantillas(pls)
        self._view.set_plantilla_enabled(True)
        self._view.set_generar_text("Generar Suenlace.dat")

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

            tipo = (self._view.get_tipo() or "").lower()
            if "terceros" in tipo:
                self._importar_terceros()
                return

            nombre_pl = (self._view.get_selected_plantilla() or "").strip()
            if not nombre_pl:
                self._view.show_warning("Gest2A3Eco", "Selecciona una plantilla.")
                return
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
                rows = [r for r in rows if self._row_has_data(r)]
                if not rows:
                    self._view.show_warning(
                        "Gest2A3Eco",
                        "No se encontraron filas con datos en el Excel.\n"
                        "Revisa la hoja seleccionada, 'Primera fila procesar' y el mapeo de columnas.",
                    )
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
                rows = [r for r in rows if self._row_has_data(r)]
                if not rows:
                    self._view.show_warning(
                        "Gest2A3Eco",
                        "No se encontraron filas con datos en el Excel.\n"
                        "Revisa la hoja seleccionada, 'Primera fila procesar' y el mapeo de columnas.",
                    )
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
            rows = [r for r in rows if self._row_has_data(r)]
            if not rows:
                self._view.show_warning(
                    "Gest2A3Eco",
                    "No se encontraron filas con datos en el Excel.\n"
                    "Revisa la hoja seleccionada, 'Primera fila procesar' y el mapeo de columnas.",
                )
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
            self._log_error("Error en la generacion", e)
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

    def _row_has_data(self, row):
        for k, v in (row or {}).items():
            if str(k).startswith("_"):
                continue
            if v is None:
                continue
            try:
                if isinstance(v, float) and (v != v):
                    continue
            except Exception:
                pass
            s = str(v).strip()
            if not s or s.lower() == "nan":
                continue
            return True
        return False

    def _importar_terceros(self):
        hoja = self._view.get_selected_sheet()
        if not hoja or not self._excel_path:
            self._view.show_warning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
            return

        try:
            df = pd.read_excel(self._excel_path, sheet_name=hoja, header=0, dtype=object)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"Error al leer hoja:\n{e}")
            return

        col_map = self._map_terceros_columns(df.columns)
        if not col_map.get("nif") and not col_map.get("nombre"):
            self._view.show_error(
                "Gest2A3Eco",
                "No se encontraron columnas 'NIF' o 'Nombre' en el Excel.",
            )
            return

        empresa_config = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa_config.get("digitos_plan", 8))

        terceros = self._gestor.listar_terceros()
        terceros_by_nif = {
            self._norm_nif(t.get("nif")): t
            for t in terceros
            if self._norm_nif(t.get("nif"))
        }

        creados = 0
        actualizados = 0
        vinculados = 0
        omitidos = 0
        avisos = []

        for idx, row in enumerate(df.to_dict(orient="records"), start=2):
            rec = self._row_to_tercero_dict(row, col_map)
            if not self._row_has_data(rec):
                omitidos += 1
                continue

            nif = self._norm_nif(rec.get("nif"))
            nombre = self._norm_text(rec.get("nombre"))
            if not nif and not nombre:
                omitidos += 1
                continue
            if not nif:
                avisos.append(f"Fila {idx}: NIF vacío, se creó/actualizó por nombre.")

            existing = terceros_by_nif.get(nif) if nif else None
            if existing:
                tercero = self._merge_tercero(existing, rec)
                actualizados += 1
            else:
                tercero = self._build_tercero(rec)
                creados += 1

            self._gestor.upsert_tercero(tercero)
            if nif:
                terceros_by_nif[nif] = tercero

            tercero_id = tercero.get("id")
            if tercero_id:
                merged = self._merge_subcuentas(
                    tercero_id,
                    rec,
                    ndig,
                    avisos,
                    idx,
                )
                self._gestor.upsert_tercero_empresa(merged)
                vinculados += 1

        msg = (
            f"Importación finalizada.\n\n"
            f"Filas procesadas: {len(df)}\n"
            f"Creados: {creados}\n"
            f"Actualizados: {actualizados}\n"
            f"Vinculados a empresa: {vinculados}\n"
            f"Omitidos: {omitidos}"
        )
        if avisos:
            preview = "\n".join(avisos[:10])
            if len(avisos) > 10:
                preview += f"\n... y {len(avisos)-10} avisos mas."
            msg += f"\n\nAvisos:\n{preview}"
            self._view.show_warning("Gest2A3Eco", msg)
        else:
            self._view.show_info("Gest2A3Eco", msg)

    def _map_terceros_columns(self, columns):
        mapping = {}
        aliases = {
            "nif": [
                "nif", "cif", "dni", "vat", "taxid", "tax_id", "identificacion",
                "nifclienteproveedor", "nifcliente", "nifproveedor",
            ],
            "nombre": [
                "nombre", "razonsocial", "razon_social", "razon",
                "nombreclienteproveedor", "nombrecliente", "nombreproveedor",
            ],
            "direccion": ["direccion", "direccion1", "domicilio", "dir", "address"],
            "cp": ["cp", "codigo_postal", "codigopostal", "postal"],
            "poblacion": ["poblacion", "ciudad", "localidad", "municipio"],
            "provincia": ["provincia", "prov"],
            "telefono": ["telefono", "tel", "movil", "phone"],
            "email": ["email", "correo", "mail"],
            "contacto": ["contacto", "persona_contacto"],
            "subcuenta_cliente": ["subcuenta_cliente", "subcuenta_cliente_proveedor", "cta_cliente", "cuenta_cliente"],
            "subcuenta_proveedor": ["subcuenta_proveedor", "cta_proveedor", "cuenta_proveedor"],
            "subcuenta_ingreso": ["subcuenta_ingreso", "cta_ingreso", "cuenta_ingreso"],
            "subcuenta_gasto": ["subcuenta_gasto", "cta_gasto", "cuenta_gasto"],
        }
        normalized = {self._norm_col(c): c for c in columns}
        for key, names in aliases.items():
            for n in names:
                col = normalized.get(self._norm_col(n))
                if col and key not in mapping:
                    mapping[key] = col
        return mapping

    def _row_to_tercero_dict(self, row, col_map):
        out = {}
        for key, col in col_map.items():
            try:
                out[key] = row.get(col)
            except Exception:
                out[key] = None
        return out

    def _build_tercero(self, rec: dict):
        return {
            "nif": self._norm_nif(rec.get("nif")),
            "nombre": self._norm_text(rec.get("nombre")),
            "direccion": self._norm_text(rec.get("direccion")),
            "cp": self._norm_text(rec.get("cp")),
            "poblacion": self._norm_text(rec.get("poblacion")),
            "provincia": self._norm_text(rec.get("provincia")),
            "telefono": self._norm_text(rec.get("telefono")),
            "email": self._norm_text(rec.get("email")),
            "contacto": self._norm_text(rec.get("contacto")),
        }

    def _merge_tercero(self, existing: dict, rec: dict):
        tercero = dict(existing)
        for k in ("nif", "nombre", "direccion", "cp", "poblacion", "provincia", "telefono", "email", "contacto"):
            val = self._norm_text(rec.get(k))
            if k == "nif":
                val = self._norm_nif(rec.get(k))
            if val:
                tercero[k] = val
        return tercero

    def _merge_subcuentas(self, tercero_id, rec, ndig, avisos, idx):
        existing = self._gestor.get_tercero_empresa(self._codigo, tercero_id, self._ejercicio) or {}
        def pick(field, label):
            val = self._norm_text(rec.get(field))
            if not val:
                return existing.get(field)
            try:
                validar_subcuenta_longitud(val, ndig, label)
            except Exception as e:
                avisos.append(f"Fila {idx}: {e}")
                return existing.get(field)
            return val

        return {
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "tercero_id": tercero_id,
            "subcuenta_cliente": pick("subcuenta_cliente", "subcuenta cliente"),
            "subcuenta_proveedor": pick("subcuenta_proveedor", "subcuenta proveedor"),
            "subcuenta_ingreso": pick("subcuenta_ingreso", "subcuenta ingreso"),
            "subcuenta_gasto": pick("subcuenta_gasto", "subcuenta gasto"),
        }

    def _norm_col(self, name):
        s = "" if name is None else str(name)
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = s.strip().lower()
        for ch in (" ", "-", "_", ".", "/", "\\"):
            s = s.replace(ch, "")
        return s

    def _norm_nif(self, val):
        s = self._norm_text(val)
        return s.upper() if s else ""

    def _norm_text(self, val):
        if val is None:
            return ""
        if isinstance(val, float):
            if val != val:
                return ""
            if val.is_integer():
                return str(int(val))
        s = str(val).strip()
        if s.lower() == "nan":
            return ""
        return s

    def _log_error(self, msg: str, exc: Exception) -> None:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "procesos_error.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n---- PROCESOS ERROR ----\n")
                f.write(f"Message: {msg}\n")
                f.write("Exception:\n")
                f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            pass
