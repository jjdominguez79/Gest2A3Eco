from tkinter import messagebox, ttk

from controllers.user_admin_controller import UserAdminController
from services.empresa_service import EmpresaService
from views.ui_dashboard_empresa import UIDashboardEmpresa
from views.ui_facturas_emitidas import UIFacturasEmitidas
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

    @property
    def session(self):
        return self._session

    @property
    def authorization(self):
        return self._gestor.security

    def start(self):
        self.show(self.build_panel_general)

    def show(self, factory):
        if self._current_frame is not None:
            self._current_frame.destroy()
        frame = factory(self._content)
        if not frame.winfo_manager():
            frame.pack(fill="both", expand=True)
        self._current_frame = frame

    def build_panel_general(self, parent):
        return UIPanelGeneral(
            parent,
            self._empresa_service,
            self._session,
            on_open_dashboard=self.open_company_dashboard,
        )

    def on_empresa_ok(self, codigo, ejercicio, nombre, modulo="facturacion"):
        if modulo == "contabilidad":
            modulo = "importaciones"
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self.open_company_module(codigo, ejercicio, modulo=modulo, nombre=nombre)

    def open_company_dashboard(self, codigo, ejercicio):
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self.show(lambda parent: self.build_dashboard(parent, codigo, ejercicio))

    def open_company_module(self, codigo, ejercicio, modulo="dashboard", nombre=None):
        if modulo == "contabilidad":
            modulo = "importaciones"
        try:
            self.authorization.ensure_company_read(codigo)
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self.show(lambda parent: self.build_company_view(parent, codigo, ejercicio, modulo, nombre=nombre))

    def build_dashboard(self, parent, codigo, ejercicio):
        return UIDashboardEmpresa(
            parent,
            self._empresa_service,
            codigo,
            ejercicio,
            on_open_facturacion=lambda: self.open_company_module(codigo, ejercicio, "facturacion"),
            on_open_importaciones=lambda: self.open_company_module(codigo, ejercicio, "importaciones"),
            on_open_plantillas=lambda: self.open_company_module(codigo, ejercicio, "plantillas"),
            on_open_configuracion=lambda: self.open_company_config(codigo, ejercicio),
            on_open_ocr=self.open_company_ocr_placeholder,
            on_back=self.start,
        )

    def build_company_view(self, parent, codigo, ejercicio, modulo, nombre=None):
        empresa = self._gestor.get_empresa(codigo, ejercicio) or {}
        nombre = nombre or empresa.get("nombre") or codigo
        if modulo == "dashboard":
            return self.build_dashboard(parent, codigo, ejercicio)
        if modulo == "importaciones":
            return self._build_module_shell(
                parent,
                codigo,
                ejercicio,
                nombre,
                "Excel / Importaciones",
                lambda holder: UIProcesos(holder, self._gestor, codigo, ejercicio, nombre, session=self._session),
            )
        if modulo == "plantillas":
            return self._build_module_shell(
                parent,
                codigo,
                ejercicio,
                nombre,
                "Plantillas",
                lambda holder: UIPlantillasEmpresa(holder, self._gestor, codigo, ejercicio, nombre, session=self._session),
            )
        if modulo.startswith("importaciones::"):
            tipo = modulo.split("::", 1)[1]
            return self._build_module_shell(
                parent,
                codigo,
                ejercicio,
                nombre,
                "Excel / Importaciones",
                lambda holder: UIProcesos(
                    holder,
                    self._gestor,
                    codigo,
                    ejercicio,
                    nombre,
                    session=self._session,
                    initial_tipo=tipo,
                ),
            )
        if modulo.startswith("plantillas::"):
            tipo = modulo.split("::", 1)[1]
            return self._build_module_shell(
                parent,
                codigo,
                ejercicio,
                nombre,
                "Plantillas",
                lambda holder: UIPlantillasEmpresa(
                    holder,
                    self._gestor,
                    codigo,
                    ejercicio,
                    nombre,
                    session=self._session,
                    initial_tipo=tipo,
                ),
            )
        return self._build_module_shell(
            parent,
            codigo,
            ejercicio,
            nombre,
            "Facturacion",
            lambda holder: UIFacturasEmitidas(
                holder,
                self._gestor,
                codigo,
                ejercicio,
                nombre,
                allow_all_years=True,
                session=self._session,
                on_open_company_config=lambda: self.configure_company_in_place(codigo, ejercicio),
            ),
        )

    def _build_module_shell(self, parent, codigo, ejercicio, nombre, titulo, content_builder):
        shell = ttk.Frame(parent)
        top = ttk.Frame(shell, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text=f"{titulo} - {nombre} ({codigo})", font=("Segoe UI", 12, "bold")).pack(side="left")
        actions = ttk.Frame(top)
        actions.pack(side="right")
        buttons = (
            ("Dashboard", lambda: self.open_company_dashboard(codigo, ejercicio)),
            ("Facturacion", lambda: self.open_company_module(codigo, ejercicio, "facturacion")),
            ("Importaciones", lambda: self.open_company_module(codigo, ejercicio, "importaciones")),
            ("Plantillas", lambda: self.open_company_module(codigo, ejercicio, "plantillas")),
            ("Config. empresa", lambda: self.open_company_config(codigo, ejercicio)),
        )
        for text, command in buttons:
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=3)
        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        content = content_builder(body)
        if not content.winfo_manager():
            content.pack(fill="both", expand=True)
        return shell

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
        bank_records = [dict(row) for row in (result.get("_bank_records") or []) if isinstance(row, dict)]
        if bank_records:
            try:
                self._gestor.reemplazar_cuentas_bancarias(codigo, 0, bank_records)
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
                return False
        return True

    def open_company_ocr_placeholder(self):
        messagebox.showinfo(
            "Gest2A3Eco",
            "El modulo OCR se integrara en una fase posterior. Esta fase 1 deja preparado el acceso desde el dashboard.",
            parent=self._content.winfo_toplevel(),
        )

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
