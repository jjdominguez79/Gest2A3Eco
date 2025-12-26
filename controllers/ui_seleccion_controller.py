import sqlite3
from datetime import datetime
from pathlib import Path

from services.import_empresas_csv import import_empresas_csv


class SeleccionEmpresaController:
    def __init__(self, gestor, on_ok, view):
        self._gestor = gestor
        self._on_ok = on_ok
        self._view = view
        self._empresas_cache = []

    def refresh(self):
        self._empresas_cache = self._gestor.listar_empresas()
        ejercicios = sorted({e.get("ejercicio") for e in self._empresas_cache if e.get("ejercicio") is not None})
        self._view.set_ejercicios(ejercicios)
        self.apply_filter()

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

    def continuar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_warning("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self._gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre", "")
        self._on_ok(codigo, eje, nombre)

    def eliminar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            self._view.show_info("Gest2A3Eco", "Selecciona una empresa para eliminar.")
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
