from datetime import datetime
from tkinter import messagebox, ttk

from controllers.user_admin_controller import UserAdminController
from services.empresa_service import EmpresaService
from views.ui_configuracion_empresa import UIConfiguracionEmpresa
from views.ui_contabilidad import UIContabilidad
from views.ui_dashboard_empresa import UIDashboardEmpresa
from views.ui_facturas_emitidas import UIFacturasEmitidas
from views.ui_maestro_cuentas import UIMaestroCuentas
from views.ui_ocr_facturas import UIOcrFacturas
from views.ui_facturas_recibidas_ocr import UIFacturasRecibidasOcr
from views.ui_notificaciones_global import UINotificacionesGlobal
from views.ui_panel_general import UIPanelGeneral
from views.ui_plantillas import UIPlantillasEmpresa
from views.ui_procesos import UIProcesos
from views.ui_terceros_globales import UITercerosGlobales
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
        on_create_company = self.open_new_company_config if self.authorization.can_manage_company_catalog() else None
        return UIPanelGeneral(
            parent,
            self._empresa_service,
            self._session,
            on_open_dashboard=self.open_company_dashboard,
            on_create_company=on_create_company,
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
        self._content.after(400, lambda: self._avisar_cuotas_pendientes(codigo, ejercicio))

    def _avisar_cuotas_pendientes(self, codigo, ejercicio):
        """Comprueba cuotas pendientes de generar para la empresa y muestra aviso si las hay."""
        try:
            from datetime import date
            from controllers.ui_cuotas_controller import CuotasController
            empresa_conf = self._gestor.get_empresa(codigo, ejercicio) or {}
            ctrl = CuotasController(self._gestor, codigo, int(ejercicio), empresa_conf)
            pendientes = ctrl.calcular_cuotas_pendientes(hasta=date.today())
            if not pendientes:
                return
            total_periodos = sum(len(p["periodos"]) for p in pendientes)
            nombres = [p["cuota"].get("nombre") or p["cuota"].get("nif") or "?" for p in pendientes[:5]]
            detalle = "\n".join(f"  - {n}" for n in nombres)
            if len(pendientes) > 5:
                detalle += f"\n  ... y {len(pendientes) - 5} mas"
            msg = (
                f"Hay {total_periodos} periodo(s) pendiente(s) de facturar "
                f"en {len(pendientes)} cuota(s):\n\n{detalle}\n\n"
                "Puedes generarlas desde Facturacion > Cuotas periodicas > Generar pendientes."
            )
            messagebox.showinfo("Cuotas pendientes", msg,
                                parent=self._content.winfo_toplevel())
        except Exception:
            pass

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
            on_open_configuracion=lambda: self._open_module_in_shell(codigo, ejercicio, "configuracion"),
            on_open_ocr=lambda: self._open_module_in_shell(codigo, ejercicio, "ocr"),
            on_open_terceros=lambda: self._open_module_in_shell(codigo, ejercicio, "terceros"),
            on_open_maestro_cuentas=lambda: self._open_module_in_shell(codigo, ejercicio, "maestro_cuentas"),
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
        if modulo == "configuracion":
            shell = self._company_shell
            def _back_to_dashboard():
                if shell is not None:
                    shell.refresh()
                    shell.show_dashboard()
                else:
                    self.start()
            return UIConfiguracionEmpresa(
                parent, self._gestor, codigo, ejercicio, nombre,
                on_back=_back_to_dashboard,
                on_deleted=self.start,
                session=self._session,
            )
        if modulo == "importaciones":
            return UIProcesos(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "ocr":
            return _OcrModuleContainer(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "contabilidad":
            return UIContabilidad(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "plantillas":
            return UIPlantillasEmpresa(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
        if modulo == "terceros":
            return UITercerosGlobales(parent, self._gestor, session=self._session)
        if modulo == "maestro_cuentas":
            return UIMaestroCuentas(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
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
        )

    # ------------------------------------------------------------------ config

    def open_company_config(self, codigo, ejercicio):
        self.open_company_module(codigo, ejercicio, modulo="configuracion")

    def configure_company_in_place(self, codigo, ejercicio):
        self.open_company_module(codigo, ejercicio, modulo="configuracion")
        return True

    def open_new_company_config(self):
        try:
            if not self.authorization.can_manage_company_catalog():
                raise PermissionError("No tienes permisos para crear empresas.")
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        current_year = datetime.now().year
        self._show(
            lambda parent: UIConfiguracionEmpresa(
                parent,
                self._gestor,
                "",
                current_year,
                "",
                on_back=self.start,
                on_deleted=self.start,
                session=self._session,
            )
        )

    # ------------------------------------------------------------------ otros

    def open_terceros(self):
        if self._company_shell is not None:
            self._open_module_in_shell(self._current_codigo, self._current_ejercicio, "terceros")
        else:
            self._show(lambda parent: UITercerosGlobales(parent, self._gestor, session=self._session))

    def open_notificaciones_global(self):
        self._show(
            lambda parent: UINotificacionesGlobal(
                parent, self._gestor, session=self._session,
                on_open_empresa=self.open_company_dashboard,
            )
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


# ── Contenedor OCR: pestana nueva (tipada) + pestana legado ──────────────────

class _OcrModuleContainer(ttk.Frame):
    """
    Contenedor del modulo OCR con dos pestanas:
      - "Nuevo OCR"   — UIFacturasRecibidasOcr (services/ocr/ tipado, nuevas tablas)
      - "Importaciones anteriores" — UIOcrFacturas (flujo legado facturas_recibidas_docs)

    Permite usar el nuevo modulo sin perder acceso a documentos existentes.
    """

    def __init__(self, master, gestor, codigo, ejercicio, nombre, session=None):
        super().__init__(master)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # Pestana 1: nuevo modulo OCR tipado
        tab_nuevo = ttk.Frame(nb)
        nb.add(tab_nuevo, text="Captura documental")
        UIFacturasRecibidasOcr(
            tab_nuevo, gestor, codigo, ejercicio, nombre, session=session
        ).pack(fill="both", expand=True)

        # Pestana 2: flujo legado (documentos ya procesados con sistema anterior)
        tab_legado = ttk.Frame(nb)
        nb.add(tab_legado, text="Importaciones anteriores")
        UIOcrFacturas(
            tab_legado, gestor, codigo, ejercicio, nombre, session=session
        ).pack(fill="both", expand=True)
