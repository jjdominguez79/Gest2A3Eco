import sqlite3
import shutil
import sys
from datetime import datetime
from pathlib import Path

from services.import_empresas_csv import import_empresas_csv
from utils.utilidades import aplicar_descuento_total_lineas, load_app_config, save_app_config


class SeleccionEmpresaController:
    def __init__(self, gestor, on_ok, view):
        self._gestor = gestor
        self._on_ok = on_ok
        self._view = view
        self._empresas_cache = []
        self._empresas_grouped = []
        self._empresa_default_ej = {}
        self._facturas_cache = []
        self._empresas_by_key = {}
        self._admin_password = self._load_admin_password()

    def refresh(self):
        self._empresas_cache = self._gestor.listar_empresas()
        self._group_empresas()
        self.apply_filter()
        self._build_empresas_index()
        self._load_facturas_global()

    def apply_filter(self):
        filtro = (self._view.get_filter_text() or "").strip().lower()
        ver_bajas = self._view.get_ver_bajas()
        self._view.clear_empresas()
        for e in self._empresas_grouped:
            if not ver_bajas and not bool(e.get("activo", True)):
                continue
            texto = " ".join([
                str(e.get("codigo", "")),
                str(e.get("nombre", "")),
                str(e.get("cif", "")),
                str(e.get("ejercicios_txt", "")),
            ]).lower()
            if filtro and filtro not in texto:
                continue
            self._view.insert_empresa(e)

    def importar_csv(self):
        csv_path = self._view.ask_csv_path()
        if not csv_path:
            return
        try:
            backup_path = self._backup_db()
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"No se pudo crear la copia de seguridad:\n{e}")
            return
        try:
            n = import_empresas_csv(str(self._gestor.db_path), csv_path)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", f"Error al importar el CSV:\n{e}")
            return
        self.refresh()
        self._view.show_info(
            "Gest2A3Eco",
            f"Importacion completada.\nFilas procesadas: {n}.\nCopia: {backup_path.name}",
        )

    def nueva(self):
        result = self._view.open_empresa_dialog("Nueva empresa")
        if result:
            result["logo_path"] = self._store_logo(result.get("logo_path"))
            self._gestor.upsert_empresa(result)
            self.refresh()
            self._view.show_info("Gest2A3Eco", "Empresa guardada.")

    def editar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_info("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self._gestor.get_empresa(codigo, eje)
        result = self._view.open_empresa_dialog("Editar empresa", emp)
        if result:
            result["logo_path"] = self._store_logo(result.get("logo_path"))
            self._gestor.upsert_empresa(result)
            self.refresh()
            self._view.show_info("Gest2A3Eco", "Cambios guardados.")

    def copiar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_info("Gest2A3Eco", "Selecciona una empresa para copiar.")
            return
        emp = self._gestor.get_empresa(codigo, eje)
        if not emp:
            self._view.show_warning("Gest2A3Eco", "No se encontro la empresa seleccionada.")
            return
        base = dict(emp)
        base["codigo"] = ""
        try:
            base["ejercicio"] = int(emp.get("ejercicio", 0)) + 1
        except Exception:
            pass
        base["siguiente_num_emitidas"] = 1
        result = self._view.open_empresa_dialog(f"Copiar {codigo}", base)
        if not result:
            return
        if not result.get("codigo"):
            self._view.show_warning("Gest2A3Eco", "Introduce un codigo para la nueva empresa.")
            return
        result["logo_path"] = self._store_logo(result.get("logo_path"))
        if self._gestor.get_empresa(result["codigo"], result.get("ejercicio")):
            self._view.show_warning("Gest2A3Eco", "Ya existe una empresa con ese codigo y ejercicio.")
            return
        try:
            self._gestor.copiar_empresa(codigo, eje, result)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", str(e))
            return
        self.refresh()
        self._view.select_empresa_by_codigo(result["codigo"])
        self._view.show_info("Gest2A3Eco", "Empresa copiada con plantillas y terceros.")

    def terceros(self):
        self._view.open_terceros_dialog(self._gestor)

    def continuar_facturacion(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_warning("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self._gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre", "")
        self._on_ok(codigo, eje, nombre, "facturacion")

    def continuar_contabilidad(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_warning("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self._gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre", "")
        self._on_ok(codigo, eje, nombre, "contabilidad")

    def eliminar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_info("Gest2A3Eco", "Selecciona una empresa para eliminar.")
            return
        pwd = self._view.ask_admin_password()
        if pwd is None:
            return
        if str(pwd) != str(self._admin_password):
            self._view.show_error("Gest2A3Eco", "Contraseña de administrador incorrecta.")
            return
        emp = self._gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre", codigo)
        if not self._view.ask_yes_no(
            "Gest2A3Eco",
            f"IMPORTANTE:\nVas a eliminar {nombre} (codigo {codigo}, ejercicio {eje}).\n"
            "Se borraran sus plantillas, facturas y subcuentas de terceros de este ejercicio.\nContinuar?",
        ):
            return
        try:
            self._gestor.eliminar_empresa(codigo, eje)
        except Exception as e:
            self._view.show_error("Gest2A3Eco", str(e))
            return
        self.refresh()
        self._view.show_info("Gest2A3Eco", "Empresa eliminada.")

    def apply_facturas_filter(self):
        eje_filter, empresa_txt = self._view.get_facturas_filters()
        ver_bajas = self._view.get_ver_bajas()
        self._view.clear_facturas()
        for fac in self._facturas_cache:
            if eje_filter is not None and fac.get("ejercicio") != eje_filter:
                continue
            if empresa_txt:
                codigo = str(fac.get("codigo_empresa", "")).lower()
                nombre_emp = self._empresa_nombre(fac).lower()
                if empresa_txt not in codigo and empresa_txt not in nombre_emp:
                    continue
            if not ver_bajas:
                key = (str(fac.get("codigo_empresa")), fac.get("ejercicio"))
                emp = self._empresas_by_key.get(key)
                if emp and not bool(emp.get("activo", True)):
                    continue
            total = self._compute_total(fac)
            self._view.insert_factura_row(fac, total, empresa_nombre=self._empresa_nombre(fac))

    def _sel_empresa(self):
        return self._view.get_selected_empresa_key()

    def _group_empresas(self):
        grouped = {}
        for e in self._empresas_cache:
            codigo = str(e.get("codigo") or "")
            if not codigo:
                continue
            grouped.setdefault(codigo, []).append(e)

        self._empresas_grouped = []
        self._empresa_default_ej = {}
        for codigo, items in grouped.items():
            ejercicios = []
            for it in items:
                ejercicios.append(it.get("ejercicio"))
            def_ej = self._pick_default_ejercicio(ejercicios)
            base = next((it for it in items if it.get("ejercicio") == def_ej), items[0])
            ejercicios_txt = ", ".join(str(ej) for ej in sorted({x for x in ejercicios if x is not None}))
            activo = any(bool(it.get("activo", True)) for it in items)
            row = {
                "codigo": codigo,
                "nombre": base.get("nombre", ""),
                "cif": base.get("cif", ""),
                "digitos_plan": base.get("digitos_plan", 8),
                "ejercicios_txt": ejercicios_txt,
                "serie_emitidas": base.get("serie_emitidas", "A"),
                "siguiente_num_emitidas": base.get("siguiente_num_emitidas", 1),
                "ejercicio_default": def_ej,
                "activo": activo,
            }
            self._empresa_default_ej[codigo] = def_ej
            self._empresas_grouped.append(row)
        self._empresas_grouped.sort(key=lambda r: (str(r.get("codigo") or ""), str(r.get("nombre") or "")))

    def _pick_default_ejercicio(self, ejercicios):
        nums = []
        others = []
        for ej in ejercicios:
            if ej is None:
                continue
            try:
                nums.append(int(ej))
            except Exception:
                others.append(str(ej))
        if nums:
            return max(nums)
        if others:
            return sorted(others)[-1]
        return None

    def _backup_db(self) -> Path:
        db_path = Path(self._gestor.db_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = db_path.suffix or ".db"
        backup_path = db_path.with_name(f"{stamp}_copy{suffix}")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._gestor.conn.commit()
        except Exception:
            pass
        with sqlite3.connect(backup_path) as dst:
            self._gestor.conn.backup(dst)
        return backup_path

    def _store_logo(self, logo_path: str | None) -> str:
        raw = str(logo_path or "").strip()
        if not raw:
            return ""
        try:
            p = Path(raw)
        except Exception:
            return raw
        if not p.exists():
            return raw
        base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        dest_dir = base_dir / "assets" / "logos"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / p.name
        if dest_path.exists() and dest_path.samefile(p):
            return str(dest_path)
        try:
            shutil.copy2(p, dest_path)
            return str(dest_path)
        except Exception:
            return str(p)

    def _load_facturas_global(self):
        self._facturas_cache = self._gestor.listar_facturas_emitidas_todas()
        ejercicios = sorted({f.get("ejercicio") for f in self._facturas_cache if f.get("ejercicio") is not None})
        self._view.set_facturas_filters(ejercicios)
        self.apply_facturas_filter()

    def refresh_facturas_global(self):
        self._build_empresas_index()
        self._load_facturas_global()

    def copiar_factura_global(self):
        codigo, eje, fid = self._view.get_selected_factura_key()
        if not codigo or not fid:
            self._view.show_info("Gest2A3Eco", "Selecciona una factura.")
            return
        fac = next(
            (
                f
                for f in self._facturas_cache
                if str(f.get("id")) == str(fid)
                and str(f.get("codigo_empresa")) == str(codigo)
                and str(f.get("ejercicio")) == str(eje)
            ),
            None,
        )
        if not fac:
            self._view.show_warning("Gest2A3Eco", "No se encontro la factura seleccionada.")
            return

        empresas = [e for e in self._gestor.listar_empresas() if e.get("ejercicio") is not None]
        if not empresas:
            self._view.show_warning("Gest2A3Eco", "No hay empresas disponibles.")
            return
        destino = self._view.ask_copiar_factura_destino(empresas)
        if not destino:
            return
        dest_codigo, dest_eje = destino
        emp_dest = self._gestor.get_empresa(dest_codigo, dest_eje)
        if not emp_dest:
            self._view.show_warning("Gest2A3Eco", "Empresa destino no encontrada.")
            return

        serie = str(emp_dest.get("serie_emitidas", "A") or "A")
        try:
            siguiente = int(emp_dest.get("siguiente_num_emitidas", 1))
        except Exception:
            siguiente = 1
        numero = f"{serie}{siguiente:06d}"

        nuevo = dict(fac)
        nuevo.pop("id", None)
        nuevo["codigo_empresa"] = dest_codigo
        nuevo["ejercicio"] = dest_eje
        nuevo["serie"] = serie
        nuevo["numero"] = numero
        nuevo["generada"] = False
        nuevo["fecha_generacion"] = ""
        nuevo["enviado"] = False
        nuevo["fecha_envio"] = ""
        nuevo["canal_envio"] = ""
        nuevo["pdf_ref"] = ""
        nuevo["pdf_path"] = ""
        nuevo["pdf_path_a3"] = ""

        self._gestor.upsert_factura_emitida(nuevo)
        emp_dest["siguiente_num_emitidas"] = siguiente + 1
        self._gestor.upsert_empresa(emp_dest)
        self.refresh_facturas_global()
        self._view.show_info("Gest2A3Eco", "Factura copiada.")

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
        return round(total, 2)

    def _retencion_importe(self, fac: dict) -> float:
        if not fac:
            return 0.0
        if not bool(fac.get("retencion_aplica")):
            ret_lineas = 0.0
            for ln in fac.get("lineas", []):
                ret_lineas += self._to_float(ln.get("cuota_irpf"))
            return round(ret_lineas, 2)
        importe = fac.get("retencion_importe")
        if importe is None or importe == "":
            base = self._to_float(fac.get("retencion_base"))
            pct = self._to_float(fac.get("retencion_pct"))
            return round(-abs(base * pct / 100.0), 2) if pct else 0.0
        return round(self._to_float(importe), 2)

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

    def _load_admin_password(self):
        data = load_app_config()
        pwd = data.get("admin_password")
        if pwd is not None and str(pwd).strip():
            return str(pwd)
        return "admin"


    def _build_empresas_index(self):
        self._empresas_by_key = {}
        for e in self._empresas_cache:
            key = (str(e.get("codigo")), e.get("ejercicio"))
            self._empresas_by_key[key] = e

    def _empresa_nombre(self, fac: dict) -> str:
        key = (str(fac.get("codigo_empresa")), fac.get("ejercicio"))
        emp = self._empresas_by_key.get(key)
        if emp and emp.get("nombre"):
            return str(emp.get("nombre"))
        emp2 = self._gestor.get_empresa(fac.get("codigo_empresa"), fac.get("ejercicio")) or {}
        return str(emp2.get("nombre") or "")
