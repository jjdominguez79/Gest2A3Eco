import os
import traceback

import pandas as pd

from procesos.bancos import generar_bancos
from procesos.facturas_emitidas import generar_emitidas
from procesos.facturas_recibidas import generar_recibidas_suenlace
from services.excel_mapping import extract_rows_by_mapping
from utils.validaciones import normalizar_nif_cif


class ProcesosController:
    def __init__(self, gestor, codigo, ejercicio, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._view = view
        self._excel_path = None
        # Mejora 7: cache de filas extraidas y overrides de contrapartida por fila
        self._cached_rows: list[dict] | None = None
        self._cached_plantilla: dict | None = None
        self._cached_tipo: str = ""
        self._contrapartida_overrides: dict[int, str] = {}  # idx_fila -> subcuenta
        self._subcuenta_overrides: dict[int, str] = {}
        self._subcuenta_cached_rows: list[dict] | None = None
        self._subcuenta_cached_tipo: str = ""
        self._subcuenta_cached_plantilla: dict | None = None

    def _codigo_empresa_a3(self) -> str:
        digits = "".join(ch for ch in str(self._codigo or "") if ch.isdigit())
        digits = digits.zfill(5) if digits else "00000"
        return f"E{digits[:5]}"

    def refresh_plantillas(self):
        tipo = (self._view.get_tipo() or "").lower()
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
            return

        # Mejora 7: para Bancos, calcular contrapartidas y mostrar en preview
        self._cached_rows = None
        self._contrapartida_overrides = {}
        tipo = (self._view.get_tipo() or "").lower()
        if "bancos" in tipo:
            self._cargar_contrapartidas_preview()
        elif "emitidas" in tipo or "recibidas" in tipo:
            self._subcuenta_cached_rows = None
            self._subcuenta_overrides = {}
            nombre_pl = (self._view.get_selected_plantilla() or "").strip()
            if nombre_pl:
                if "emitidas" in tipo:
                    pl_prev = next((x for x in self._gestor.listar_emitidas(self._codigo, self._ejercicio) if x.get("nombre") == nombre_pl), None)
                else:
                    pl_prev = next((x for x in self._gestor.listar_recibidas(self._codigo, self._ejercicio) if x.get("nombre") == nombre_pl), None)
                if pl_prev:
                    self._cargar_subcuentas_preview(tipo, pl_prev)

    def _cargar_contrapartidas_preview(self):
        """Carga las filas mapeadas y calcula las contrapartidas por defecto para la preview."""
        import fnmatch
        try:
            nombre_pl = (self._view.get_selected_plantilla() or "").strip()
            if not nombre_pl:
                return
            pl = next(
                (x for x in self._gestor.listar_bancos(self._codigo, self._ejercicio) if x.get("banco") == nombre_pl),
                None,
            )
            if not pl:
                return
            excel_conf = pl.get("excel") or {}
            rows = extract_rows_by_mapping(self._excel_path, self._view.get_selected_sheet(), excel_conf)
            rows = [r for r in rows if self._row_has_data(r)]
            if not rows:
                return

            sub_def   = str(pl.get("subcuenta_por_defecto") or "").strip()
            conceptos = pl.get("conceptos") or []

            def _sub_por_concepto(txt: str) -> str:
                t = (str(txt) or "").lower()
                for cm in conceptos:
                    patron = (cm.get("patron", "*") or "*").lower()
                    if fnmatch.fnmatch(t, patron):
                        sub = (cm.get("subcuenta") or "").strip()
                        if sub:
                            return sub
                return sub_def

            # Calcular contrapartida por defecto para cada fila
            for row in rows:
                concepto = str(row.get("Concepto") or row.get("Descripcion Factura") or "")
                row["_contrapartida_defecto"] = _sub_por_concepto(concepto)

            self._cached_rows = rows
            self._cached_plantilla = pl
            self._cached_tipo = "bancos"

            # Notificar a la vista para mostrar la columna de contrapartida
            try:
                self._view.mostrar_contrapartidas_preview(rows)
            except AttributeError:
                pass  # Vista antigua, sin soporte para contrapartidas
        except Exception:
            pass

    def set_contrapartida_override(self, idx_fila: int, subcuenta: str):
        """Guarda el override de contrapartida para una fila especifica."""
        if subcuenta:
            self._contrapartida_overrides[idx_fila] = str(subcuenta).strip()
        elif idx_fila in self._contrapartida_overrides:
            del self._contrapartida_overrides[idx_fila]

    def set_subcuenta_override(self, idx_fila: int, subcuenta: str):
        if subcuenta:
            self._subcuenta_overrides[idx_fila] = str(subcuenta).strip()
        elif idx_fila in self._subcuenta_overrides:
            del self._subcuenta_overrides[idx_fila]

    def _cargar_subcuentas_preview(self, tipo: str, pl: dict):
        """Carga las filas mapeadas y calcula las subcuentas por defecto desde terceros para emitidas/recibidas."""
        try:
            excel_conf = pl.get("excel") or {}
            rows = extract_rows_by_mapping(self._excel_path, self._view.get_selected_sheet(), excel_conf)
            rows = [r for r in rows if self._row_has_data(r)]
            if not rows:
                return

            # Construir diccionario NIF -> tercero
            terceros = self._gestor.listar_terceros()
            terceros_by_nif = {
                self._norm_nif(t.get("nif")): t
                for t in terceros
                if self._norm_nif(t.get("nif"))
            }
            terceros_empresa = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
            for t in terceros_empresa:
                nif = self._norm_nif(t.get("nif"))
                if nif:
                    terceros_by_nif[nif] = t

            # Calcular subcuenta por defecto para cada fila
            es_emitidas = "emitidas" in tipo
            col_label = "Subcuenta cliente" if es_emitidas else "Subcuenta proveedor"
            sub_key = "subcuenta_cliente" if es_emitidas else "subcuenta_proveedor"
            for row in rows:
                nif = self._norm_nif(row.get("NIF Cliente Proveedor") or row.get("NIF"))
                tercero = terceros_by_nif.get(nif) if nif else None
                row["_subcuenta_defecto"] = str((tercero or {}).get(sub_key) or "")

            self._subcuenta_cached_rows = rows
            self._subcuenta_cached_tipo = tipo
            self._subcuenta_cached_plantilla = pl
            self._subcuenta_overrides = {}

            try:
                self._view.mostrar_subcuentas_preview(rows, col_label)
            except AttributeError:
                pass
        except Exception:
            pass

    def generar(self):
        try:
            if not self._excel_path or not self._view.get_selected_sheet():
                self._view.show_warning("Gest2A3Eco", "Selecciona un Excel y una hoja.")
                return

            tipo = (self._view.get_tipo() or "").lower()

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
            ndig = int(empresa_config.get("digitos_plan") or 8)
            codigo_empresa = str(self._codigo)

            excel_conf = pl.get("excel") or {}
            rows = extract_rows_by_mapping(self._excel_path, self._view.get_selected_sheet(), excel_conf)

            if "bancos" in tipo:
                req = ["Fecha Asiento", "Importe", "Concepto"]
                if not self._require_mapeo_or_warn(pl, "bancos", req):
                    return
                # Mejora 7: usar filas cacheadas con overrides de contrapartida si existen
                if (
                    self._cached_rows is not None
                    and self._cached_tipo == "bancos"
                    and self._cached_plantilla
                    and self._cached_plantilla.get("banco") == pl.get("banco")
                ):
                    rows = [dict(r) for r in self._cached_rows]
                    # Aplicar overrides de contrapartida
                    for idx, sub_override in self._contrapartida_overrides.items():
                        if 0 <= idx < len(rows):
                            rows[idx]["_subcuenta_override"] = sub_override
                else:
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
                save_path = self._view.ask_save_path(f"{self._codigo_empresa_a3()}.dat")
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
                if (
                    self._subcuenta_cached_rows is not None
                    and self._subcuenta_cached_tipo == "emitidas"
                    and self._subcuenta_cached_plantilla
                    and self._subcuenta_cached_plantilla.get("nombre") == pl.get("nombre")
                ):
                    rows = [dict(r) for r in self._subcuenta_cached_rows]
                    for idx, sub_override in self._subcuenta_overrides.items():
                        if 0 <= idx < len(rows):
                            rows[idx]["_subcuenta_cliente_override"] = sub_override
                else:
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
                    self._norm_nif(t.get("nif")): t
                    for t in terceros
                    if self._norm_nif(t.get("nif"))
                }
                terceros_empresa = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
                for t in terceros_empresa:
                    nif = self._norm_nif(t.get("nif"))
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
                    save_path = self._view.ask_save_path(f"{self._codigo_empresa_a3()}.dat")
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
            if (
                self._subcuenta_cached_rows is not None
                and self._subcuenta_cached_tipo == "recibidas"
                and self._subcuenta_cached_plantilla
                and self._subcuenta_cached_plantilla.get("nombre") == pl.get("nombre")
            ):
                rows = [dict(r) for r in self._subcuenta_cached_rows]
                for idx, sub_override in self._subcuenta_overrides.items():
                    if 0 <= idx < len(rows):
                        rows[idx]["_cuenta_tercero_override"] = sub_override
            else:
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
                self._norm_nif(t.get("nif")): t
                for t in terceros
                if self._norm_nif(t.get("nif"))
            }
            terceros_empresa = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
            for t in terceros_empresa:
                nif = self._norm_nif(t.get("nif"))
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
                save_path = self._view.ask_save_path(f"{self._codigo_empresa_a3()}.dat")
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

    def _norm_nif(self, value) -> str:
        return normalizar_nif_cif(value)

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
