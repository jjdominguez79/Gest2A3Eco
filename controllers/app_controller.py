from tkinter import messagebox, ttk

from controllers.user_admin_controller import UserAdminController
from services.empresa_service import EmpresaService
from views.ui_contabilidad import UIContabilidad
from views.ui_dashboard_empresa import UIDashboardEmpresa
from views.ui_facturas_emitidas import UIFacturasEmitidas
from views.ui_ocr_facturas import UIOcrFacturas
from views.ui_empresa_dialog import EmpresaDialog
from views.ui_panel_general import UIPanelGeneral
from views.ui_plantillas import UIPlantillasEmpresa
from views.ui_procesos import UIProcesos
from views.ui_user_admin import UserAdminDialog


class AppController:
    """
    Controlador principal de navegacion y puntos de entrada protegidos.
    """

    def __init__(self, content_frame: ttk.Frame, gestor, auth_service, session):
        self._content = content_frame
        self._gestor = gestor
        self._auth_service = auth_service
        self._session = session
        self._current_frame = None
        self._empresa_service = EmpresaService(gestor)
        # Shell persistente por empresa
        self._company_shell: UIDashboardEmpresa | None = None
        self._current_codigo: str | None = None
        self._current_ejercicio: int | None = None

    @property
    def session(self):
        return self._session

    @property
    def authorization(self):
        return self._gestor.security

    def start(self):
        self._show(self.build_panel_general)

    def _show(self, factory):
        """Reemplaza el contenido principal destruyendo el frame actual."""
        if self._current_frame is not None:
            self._current_frame.destroy()
        # Al salir de la empresa, resetear el shell guardado
        self._company_shell = None
        self._current_codigo = None
        self._current_ejercicio = None
        frame = factory(self._content)
        if not frame.winfo_manager():
            frame.pack(fill="both", expand=True)
        self._current_frame = frame

    # Alias publico para compatibilidad con llamadas externas (header, etc.)
    def show(self, factory):
        self._show(factory)

    def build_panel_general(self, parent):
        return UIPanelGeneral(
            parent,
            self._empresa_service,
            self._session,
            on_open_dashboard=self.open_company_dashboard,
        )

    # ------------------------------------------------------------------ empresa

    def open_company_dashboard(self, codigo, ejercicio):
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        shell = self._get_or_create_shell(codigo, ejercicio)
        shell.show_dashboard()

    def open_company_module(self, codigo, ejercicio, modulo="dashboard", nombre=None):
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        if modulo == "dashboard":
            self.open_company_dashboard(codigo, ejercicio)
            return
        self._open_module_in_shell(codigo, ejercicio, modulo, nombre)

    def on_empresa_ok(self, codigo, ejercicio, nombre, modulo="facturacion"):
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self.open_company_module(codigo, ejercicio, modulo=modulo, nombre=nombre)

    # ------------------------------------------------------------------ shell

    def _get_or_create_shell(self, codigo, ejercicio) -> UIDashboardEmpresa:
        """Devuelve el shell existente si es la misma empresa/ejercicio, o crea uno nuevo."""
        if (
            self._company_shell is not None
            and self._current_codigo == codigo
            and self._current_ejercicio == int(ejercicio)
        ):
            return self._company_shell

        # Destruir frame anterior (empresa distinta o primera vez)
        if self._current_frame is not None:
            self._current_frame.destroy()

        shell = UIDashboardEmpresa(
            self._content,
            self._empresa_service,
            codigo,
            ejercicio,
            on_open_facturacion=lambda: self._open_module_in_shell(codigo, ejercicio, "facturacion"),
            on_open_contabilidad=lambda: self._open_module_in_shell(codigo, ejercicio, "contabilidad"),
            on_open_importaciones=lambda: self._open_module_in_shell(codigo, ejercicio, "importaciones"),
            on_open_plantillas=lambda: self._open_module_in_shell(codigo, ejercicio, "plantillas"),
            on_open_configuracion=lambda: self.open_company_config(codigo, ejercicio),
            on_open_ocr=lambda: self._open_module_in_shell(codigo, ejercicio, "ocr"),
            on_back=self.start,
        )
        shell.pack(fill="both", expand=True)
        self._company_shell = shell
        self._current_frame = shell
        self._current_codigo = codigo
        self._current_ejercicio = int(ejercicio)
        return shell

    def _open_module_in_shell(self, codigo, ejercicio, modulo, nombre=None):
        """Muestra un modulo dentro del shell persistente."""
        shell = self._get_or_create_shell(codigo, ejercicio)
        empresa = self._gestor.get_empresa(codigo, ejercicio) or {}
        nombre = nombre or empresa.get("nombre") or codigo

        nav_key = modulo.split("::")[0] if "::" in modulo else modulo
        content = self._build_module_content(shell.get_content_holder(), codigo, ejercicio, modulo, nombre)
        shell.show_module(content, nav_key=nav_key)

    def _build_module_content(self, parent, codigo, ejercicio, modulo, nombre):
        """Construye y devuelve el widget del modulo sin empaquetarlo."""
        if modulo == "importaciones":
            return UIProcesos(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "ocr":
            return UIOcrFacturas(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "contabilidad":
            return UIContabilidad(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "plantillas":
            return UIPlantillasEmpresa(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo.startswith("importaciones::"):
            tipo = modulo.split("::", 1)[1]
            return UIProcesos(parent, self._gestor, codigo, ejercicio, nombre, session=self._session, initial_tipo=tipo)
        if modulo.startswith("plantillas::"):
            tipo = modulo.split("::", 1)[1]
            return UIPlantillasEmpresa(parent, self._gestor, codigo, ejercicio, nombre, session=self._session, initial_tipo=tipo)
        # default: facturacion
        return UIFacturasEmitidas(
            parent,
            self._gestor,
            codigo,
            ejercicio,
            nombre,
            allow_all_years=True,
            session=self._session,
            on_open_company_config=lambda: self.configure_company_in_place(codigo, ejercicio),
        )

    # ------------------------------------------------------------------ config

    def open_company_config(self, codigo, ejercicio):
        changed = self.configure_company_in_place(codigo, ejercicio)
        if changed:
            self.open_company_dashboard(codigo, ejercicio)

    def configure_company_in_place(self, codigo, ejercicio):
        empresa = self._gestor.get_empresa(codigo, ejercicio)
        if not empresa:
            messagebox.showerror("Gest2A3Eco", "Empresa no encontrada.", parent=self._content.winfo_toplevel())
            return False
        if self._session.role.value not in ("admin", "empleado"):
            messagebox.showerror("Gest2A3Eco", "Solo administradores y empleados pueden configurar empresas.", parent=self._content.winfo_toplevel())
            return False
        dialog = EmpresaDialog(self._content.winfo_toplevel(), f"Configurar {codigo}", empresa, gestor=self._gestor)
        result = dialog.result
        if not result:
            return False
        if result.get("_action") == "delete_company":
            try:
                for eje in self._gestor.listar_ejercicios_empresa(codigo):
                    self._gestor.eliminar_empresa(codigo, eje)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
                return False
            self.start()
            return True
        if result.get("_action") != "save_company":
            return False
        for item in result.get("_exercise_configs") or []:
            self._gestor.upsert_empresa(item)
        series_por_ejercicio = result.get("_series_por_ejercicio") or {}
        for eje_str, series in series_por_ejercicio.items():
            try:
                eje = int(eje_str)
            except Exception:
                continue
            for s in (series or []):
                try:
                    self._gestor.upsert_serie_emitida(
                        codigo, eje,
                        s["nombre"],
                        int(s.get("siguiente_num") or 1),
                        int(s.get("es_rectificativa") or 0),
                    )
                except Exception:
                    pass
        bank_records = [dict(row) for row in (result.get("_bank_records") or []) if isinstance(row, dict)]
        if bank_records:
            try:
                self._gestor.reemplazar_cuentas_bancarias(codigo, 0, bank_records)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
                return False
        return True

    # ------------------------------------------------------------------ otros

    def open_user_admin(self):
        try:
            self.authorization.ensure_admin()
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        dialog = UserAdminDialog(self._content.winfo_toplevel(), None)
        controller = UserAdminController(self._gestor, self._auth_service, dialog)
        dialog.controller = controller
        controller.refresh()
