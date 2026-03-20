from tkinter import messagebox, ttk

from controllers.user_admin_controller import UserAdminController
from views.ui_facturas_emitidas import UIFacturasEmitidas
from views.ui_plantillas import UIPlantillasEmpresa
from views.ui_procesos import UIProcesos
from views.ui_seleccion_empresa import UISeleccionEmpresa
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

    @property
    def session(self):
        return self._session

    @property
    def authorization(self):
        return self._gestor.security

    def start(self):
        self.show(self.build_seleccion)

    def show(self, factory):
        if self._current_frame is not None:
            self._current_frame.destroy()
        frame = factory(self._content)
        frame.pack(fill="both", expand=True)
        self._current_frame = frame

    def build_seleccion(self, parent):
        return UISeleccionEmpresa(parent, self._gestor, self.on_empresa_ok, session=self._session)

    def on_empresa_ok(self, codigo, ejercicio, nombre, modulo="facturacion"):
        try:
            self.authorization.ensure_company_read(codigo)
            if modulo == "contabilidad" and self._session.role.value == "cliente":
                raise PermissionError("El rol cliente no puede acceder a contabilidad.")
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self.show(lambda parent: self.build_dashboard(parent, codigo, ejercicio, nombre, modulo))

    def build_dashboard(self, parent, codigo, ejercicio, nombre, modulo):
        if modulo == "contabilidad":
            nb = ttk.Notebook(parent)
            nb.add(
                UIPlantillasEmpresa(nb, self._gestor, codigo, ejercicio, nombre, session=self._session),
                text="Plantillas",
            )
            nb.add(
                UIProcesos(nb, self._gestor, codigo, ejercicio, nombre, session=self._session),
                text="Generar ficheros",
            )
            return nb
        nb = ttk.Notebook(parent)
        nb.add(
            UIFacturasEmitidas(nb, self._gestor, codigo, ejercicio, nombre, allow_all_years=True, session=self._session),
            text="Facturas emitidas",
        )
        return nb

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
