import sqlite3
import shutil
import sys
import json
from datetime import datetime
from pathlib import Path

from services.import_empresas_csv import import_empresas_csv
from utils.utilidades import aplicar_descuento_total_lineas


class SeleccionEmpresaController:
    def __init__(self, gestor, on_ok, view):
        self._gestor = gestor
        self._on_ok = on_ok
        self._view = view
        self._empresas_cache = []
        self._facturas_cache = []
        self._empresas_by_key = {}
        self._admin_password = self._load_admin_password()

    def refresh(self):
        self._empresas_cache = self._gestor.listar_empresas()
        ejercicios = sorted({e.get("ejercicio") for e in self._empresas_cache if e.get("ejercicio") is not None})
        self._view.set_ejercicios(ejercicios)
        self.apply_filter()
        self._build_empresas_index()
        self._load_facturas_global()

    def apply_filter(self):
        filtro = (self._view.get_filter_text() or "").strip().lower()
        eje_filter = self._view.get_ejercicio_filter()
        self._view.clear_empresas()
        for e in self._empresas_cache:
            if eje_filter is not None and e.get("ejercicio") != eje_filter:
                continue
            texto = " ".join([
                str(e.get("codigo", "")),
                str(e.get("nombre", "")),
                str(e.get("cif", "")),
                str(e.get("ejercicio", "")),
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
        self._view.clear_facturas()
        for fac in self._facturas_cache:
            if eje_filter is not None and fac.get("ejercicio") != eje_filter:
                continue
            if empresa_txt:
                codigo = str(fac.get("codigo_empresa", "")).lower()
                nombre_emp = self._empresa_nombre(fac).lower()
                if empresa_txt not in codigo and empresa_txt not in nombre_emp:
                    continue
            total = self._compute_total(fac)
            self._view.insert_factura_row(fac, total, empresa_nombre=self._empresa_nombre(fac))

    def _sel_empresa(self):
        return self._view.get_selected_empresa_key()

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
        base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        cfg_path = base_dir / "config.json"
        try:
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pwd = data.get("admin_password")
                if pwd is not None and str(pwd).strip():
                    return str(pwd)
        except Exception:
            pass
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
