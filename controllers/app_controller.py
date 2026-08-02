from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from services.empresa_service import EmpresaService

if TYPE_CHECKING:
    from views.ui_dashboard_empresa import UIDashboardEmpresa


LOG = logging.getLogger(__name__)
MAIL_NOTIFICATION_INTERVAL_MS = 30_000


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
        self._mail_poll_running = False
        self._mail_poll_scheduled = False
        self._mail_poll_stopped = False
        self._mail_toast = None
        self._mail_status_callback = None
        self._content.bind("<Destroy>", self._on_content_destroy, add="+")

    @property
    def session(self):
        return self._session

    @property
    def authorization(self):
        return self._gestor.security

    def start(self):
        """Abre el listado de empresas, pantalla inicial de la aplicacion."""
        self._show(self.build_panel_general)
        self._schedule_mail_poll(1_500)

    def set_mail_status_callback(self, callback):
        self._mail_status_callback = callback

    def _schedule_mail_poll(self, delay_ms=MAIL_NOTIFICATION_INTERVAL_MS):
        role = str(getattr(self._session.role, "value", self._session.role)).lower()
        if (
            self._mail_poll_stopped
            or self._mail_poll_scheduled
            or role not in {"admin", "empleado"}
        ):
            return
        try:
            self._content.after(delay_ms, self._start_mail_poll)
            self._mail_poll_scheduled = True
        except tk.TclError:
            pass

    def _start_mail_poll(self):
        self._mail_poll_scheduled = False
        if self._mail_poll_stopped:
            return
        if self._mail_poll_running:
            self._schedule_mail_poll()
            return
        self._mail_poll_running = True
        mailbox = self._shared_mailbox()
        usuario_id = self._session.user.id

        def worker():
            try:
                rows = self._gestor.obtener_nuevos_avisos_correo(
                    usuario_id, mailbox,
                )
                summary = self._gestor.resumen_buzon_responsable(usuario_id)
                error = None
            except Exception as exc:
                rows, summary, error = [], None, exc
            try:
                self._content.after(
                    0, self._finish_mail_poll, rows, summary, error,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _shared_mailbox() -> str:
        from utils.utilidades import load_app_config

        return str(
            (load_app_config().get("microsoft_graph") or {}).get("shared_mailbox")
            or "Oficina@gestinem.es"
        ).strip().lower()

    def _finish_mail_poll(self, rows, summary, error):
        self._mail_poll_running = False
        if self._mail_poll_stopped:
            return
        if error is not None:
            LOG.warning("No se pudieron comprobar nuevos correos: %s", error)
        else:
            if self._mail_status_callback is not None and summary is not None:
                try:
                    self._mail_status_callback(summary)
                except tk.TclError:
                    pass
            if rows:
                self._show_mail_toast(rows)
        self._schedule_mail_poll()

    def _show_mail_toast(self, rows: list[dict]):
        try:
            if self._mail_toast is not None and self._mail_toast.winfo_exists():
                self._mail_toast.destroy()
            root = self._content.winfo_toplevel()
            toast = tk.Toplevel(root)
            self._mail_toast = toast
            toast.title("Nuevo correo")
            toast.attributes("-topmost", True)
            toast.resizable(False, False)
            toast.configure(bg="#eaf3fb")
            frame = tk.Frame(
                toast, bg="#eaf3fb", padx=16, pady=13,
                highlightbackground="#2b6ea6", highlightthickness=1,
            )
            frame.pack(fill="both", expand=True)
            count = len(rows)
            title = "Nuevo correo en Oficina" if count == 1 else f"{count} correos nuevos en Oficina"
            tk.Label(
                frame, text=title, bg="#eaf3fb", fg="#123b5d",
                font=("Segoe UI", 11, "bold"), anchor="w",
            ).pack(fill="x")
            details = []
            for row in rows[:3]:
                sender = str(row.get("remitente") or "Remitente desconocido")
                subject = str(row.get("asunto") or "(Sin asunto)")
                details.append(f"{sender}\n{subject}")
            if count > 3:
                details.append(f"Y {count - 3} mas...")
            tk.Label(
                frame, text="\n\n".join(details), bg="#eaf3fb", fg="#263746",
                font=("Segoe UI", 9), justify="left", anchor="w",
                wraplength=390,
            ).pack(fill="x", pady=(8, 10))
            actions = tk.Frame(frame, bg="#eaf3fb")
            actions.pack(fill="x")
            tk.Button(
                actions, text="Cerrar", command=toast.destroy,
                relief="flat", padx=10,
            ).pack(side="right")
            tk.Button(
                actions, text="Abrir buzon",
                command=lambda: self._open_mailbox_from_toast(toast),
                bg="#2b6ea6", fg="white", activebackground="#225985",
                activeforeground="white", relief="flat", padx=12,
            ).pack(side="right", padx=(0, 7))
            toast.update_idletasks()
            width, height = toast.winfo_reqwidth(), toast.winfo_reqheight()
            x = root.winfo_screenwidth() - width - 24
            y = root.winfo_screenheight() - height - 70
            toast.geometry(f"+{max(0, x)}+{max(0, y)}")
            toast.after(15_000, lambda: toast.winfo_exists() and toast.destroy())
            root.bell()
        except tk.TclError:
            pass

    def _open_mailbox_from_toast(self, toast):
        try:
            toast.destroy()
        except tk.TclError:
            pass
        self.open_buzon()

    def _on_content_destroy(self, event):
        if event.widget is self._content:
            self._mail_poll_stopped = True

    def open_buzon(self):
        """Abre el buzon global de comunicaciones bajo demanda."""
        self._show(self.build_comunicaciones_global)

    def open_empresas(self):
        """Vuelve al listado general de empresas desde cualquier modulo."""
        self._show(self.build_panel_general)

    def build_comunicaciones_global(self, parent):
        from views.ui_comunicaciones_global import UIComunicacionesGlobal

        return UIComunicacionesGlobal(parent, self._gestor, self._session)

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
        from views.ui_panel_general import UIPanelGeneral

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
        from views.ui_dashboard_empresa import UIDashboardEmpresa

        if (
            self._company_shell is not None
            and self._current_codigo == codigo
            and self._current_ejercicio == int(ejercicio)
        ):
            return self._company_shell

        # Destruir frame anterior (empresa distinta o primera vez)
        if self._current_frame is not None:
            self._current_frame.destroy()

        navigation = self._empresa_service.get_company_navigation(codigo)
        previous = navigation.get("previous")
        next_company = navigation.get("next")
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
            on_open_comunicaciones=lambda: self._open_module_in_shell(codigo, ejercicio, "comunicaciones"),
            on_previous_company=(
                (lambda: self._navigate_company(previous))
                if previous else None
            ),
            on_next_company=(
                (lambda: self._navigate_company(next_company))
                if next_company else None
            ),
            company_position=int(navigation.get("position") or 0),
            company_total=int(navigation.get("total") or 0),
            on_back=self.start,
        )
        shell.pack(fill="both", expand=True)
        self._company_shell = shell
        self._current_frame = shell
        self._current_codigo = codigo
        self._current_ejercicio = int(ejercicio)
        return shell

    def _navigate_company(self, target: dict):
        if not target:
            return
        module = (
            self._company_shell.current_nav_key
            if self._company_shell is not None else "inicio"
        )
        codigo = str(target.get("codigo") or "")
        ejercicio = int(target.get("ejercicio") or target.get("ultimo_ejercicio"))
        if module == "inicio":
            shell = self._get_or_create_shell(codigo, ejercicio)
            shell.show_dashboard()
            return
        self._open_module_in_shell(codigo, ejercicio, module)

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
        from views.ui_comunicaciones import UIComunicaciones
        from views.ui_configuracion_empresa import UIConfiguracionEmpresa
        from views.ui_contabilidad import UIContabilidad
        from views.ui_facturas_emitidas import UIFacturasEmitidas
        from views.ui_maestro_cuentas import UIMaestroCuentas
        from views.ui_plantillas import UIPlantillasEmpresa
        from views.ui_procesos import UIProcesos
        from views.ui_terceros_globales import UITercerosGlobales

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
        if modulo == "comunicaciones":
            return UIComunicaciones(parent, self._gestor, codigo, ejercicio, nombre, session=self._session)
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
        from views.ui_configuracion_empresa import UIConfiguracionEmpresa

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
        from views.ui_terceros_globales import UITercerosGlobales

        if self._company_shell is not None:
            self._open_module_in_shell(self._current_codigo, self._current_ejercicio, "terceros")
        else:
            self._show(lambda parent: UITercerosGlobales(parent, self._gestor, session=self._session))

    def open_notificaciones_global(self):
        from views.ui_notificaciones_global import UINotificacionesGlobal

        self._show(
            lambda parent: UINotificacionesGlobal(
                parent, self._gestor, session=self._session,
                on_open_empresa=self.open_company_dashboard,
            )
        )

    def open_tramites_dgt(self):
        from views.ui_tramites_dgt import UITramitesDgt

        try:
            self.authorization.ensure_tramites_dgt()
        except PermissionError as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self._content.winfo_toplevel())
            return
        self._show(lambda parent: UITramitesDgt(parent, self._gestor, session=self._session, on_back=self.start))

    def open_user_admin(self):
        from controllers.user_admin_controller import UserAdminController
        from views.ui_user_admin import UserAdminDialog

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
        from views.ui_facturas_recibidas_ocr import UIFacturasRecibidasOcr
        from views.ui_ocr_facturas import UIOcrFacturas

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
