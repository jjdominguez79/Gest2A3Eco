import os
import sys
import threading
import warnings
import tkinter as tk

warnings.filterwarnings("ignore", message="Data Validation extension is not supported", category=UserWarning, module="openpyxl")
from tkinter import filedialog, messagebox, ttk

from controllers.app_controller import AppController
from services.email_service import ensure_template_file
from models.gestor_postgres import GestorPostgres, crear_dsn_postgres
from services.auth_service import AuthService, AuthorizationService
from services.desktop_staff_auth_service import DesktopStaffAuthService
from services.secured_gestor import SecuredGestor
from utils.utilidades import (
    get_default_templates_dir,
    get_word_templates_dir,
    load_app_config,
    log_exception,
    save_app_config,
    set_word_templates_dir,
)
from views.ui_auth import ChangePasswordDialog, UILogin
from views.ui_config_monedas import MonedasDialog
from views.ui_postgres_config import PostgresConfigDialog
from views.ui_tramites_dgt_public import UITramitesDgtPublicForm
from views.ui_theme import aplicar_icono_ventana, aplicar_tema
from update_checker import check_for_updates


EMPRESA_NOMBRE = "Asesoria Gestinem S.L."
EMPRESA_CIF = "B16916967"
EMPRESA_DIRECCION = "CL Atilano Rodriguez 4, Entlo. 7, 39002 Santander (Cantabria)"
EMPRESA_EMAIL = "jjdominguez@gestinem.es"
EMPRESA_TELEFONO = "Tel.: 942 791 404"


def resource_path(relpath: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relpath)


def find_login_logo_path() -> str:
    project_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        resource_path("icono.ico"),
        resource_path("logo.png"),
        resource_path("logo.jpg"),
        os.path.join(project_dir, "dist", "Gest2A3Eco", "_internal", "logo.png"),
        resource_path("icono.ico"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _posicion_menu_contextual(root: tk.Tk, margen: int = 8) -> tuple[int, int]:
    """Situa un menu secundario junto al punto que origino la accion."""
    return (
        int(root.winfo_pointerx()) + int(margen),
        int(root.winfo_pointery()) + int(margen),
    )


def _deshabilitar_boton_secundario(root: tk.Tk) -> None:
    """Impide que el boton derecho abra acciones dentro de la aplicacion."""

    def _bloquear(_event):
        return "break"

    root.bind_all("<Button-3>", _bloquear)
    root.bind_all("<ButtonRelease-3>", _bloquear)


def _restaurar_boton_secundario(root: tk.Tk) -> None:
    root.unbind_all("<Button-3>")
    root.unbind_all("<ButtonRelease-3>")


def _build_header(
    root: tk.Tk,
    session,
    on_cambiar_empresa,
    on_open_empresas=None,
    on_open_config=None,
    on_open_users=None,
    on_open_terceros=None,
    on_open_control_facturas=None,
    on_open_firmas=None,
    on_open_adjuntos_mensajeria=None,
    on_open_notificaciones=None,
    on_open_tramites_dgt=None,
    on_logout=None,
    db_label: str | None = None,
    word_tpl_dir: str | None = None,
) -> tk.Frame:
    COLOR_PRIMARY = "#002C57"
    COLOR_PRIMARY_HOV = "#164B7A"
    COLOR_DANGER = "#B4322A"
    COLOR_DANGER_HOV = "#922820"
    COLOR_WHITE = "#FFFFFF"
    COLOR_ACCENT = "#BFD3E7"
    COLOR_NAV = "#F7F9FC"
    COLOR_NAV_TEXT = "#24364B"
    COLOR_NAV_HOV = "#E4EDF6"
    COLOR_SEPARATOR = "#D8E0E8"
    COLOR_INFOBAR = "#EEF2F6"
    COLOR_MUTED = "#647284"

    # ── Franja principal ────────────────────────────────────────────────
    header = tk.Frame(root, bg=COLOR_PRIMARY)
    header.pack(side="top", fill="x")

    inner = tk.Frame(header, bg=COLOR_PRIMARY, padx=18, pady=9)
    inner.pack(fill="x")

    # ── Lado izquierdo: logo + datos empresa ────────────────────────────
    left = tk.Frame(inner, bg=COLOR_PRIMARY)
    left.pack(side="left", fill="y")

    try:
        logo_img = tk.PhotoImage(file=resource_path("logo.png"))
        max_h = 52
        if logo_img.height() > max_h:
            factor = max(1, logo_img.height() // max_h)
            logo_img = logo_img.subsample(factor, factor)
        root._logo_img = logo_img
        tk.Label(left, image=logo_img, bg=COLOR_PRIMARY).pack(side="left", padx=(0, 14), anchor="center")
    except Exception:
        pass

    company = tk.Frame(left, bg=COLOR_PRIMARY)
    company.pack(side="left", fill="y", anchor="center")

    tk.Label(
        company, text=EMPRESA_NOMBRE,
        bg=COLOR_PRIMARY, fg=COLOR_WHITE,
        font=("Segoe UI", 14, "bold"), anchor="w",
    ).pack(anchor="w")
    tk.Label(
        company, text=f"CIF: {EMPRESA_CIF}  ·  {EMPRESA_DIRECCION}",
        bg=COLOR_PRIMARY, fg=COLOR_ACCENT,
        font=("Segoe UI", 9), anchor="w",
    ).pack(anchor="w")
    tk.Label(
        company, text=f"{EMPRESA_EMAIL}  ·  {EMPRESA_TELEFONO}",
        bg=COLOR_PRIMARY, fg=COLOR_ACCENT,
        font=("Segoe UI", 9), anchor="w",
    ).pack(anchor="w")

    # ── Lado derecho: usuario + botones ─────────────────────────────────
    right = tk.Frame(inner, bg=COLOR_PRIMARY)
    right.pack(side="right", fill="y", anchor="center")

    role_label = (
        str(getattr(session, "role", "")).replace("UserRole.", "").title()
    )
    user_badge = tk.Frame(
        right,
        bg=COLOR_PRIMARY_HOV,
        padx=10,
        pady=4,
        highlightbackground="#3C648B",
        highlightthickness=1,
    )
    user_badge.pack(anchor="e", pady=(0, 6))
    tk.Label(
        user_badge,
        text=f"\u25cf  {session.user.nombre}  ·  {role_label}",
        bg=COLOR_PRIMARY_HOV,
        fg=COLOR_WHITE,
        font=("Segoe UI", 9, "bold"),
        anchor="e",
    ).pack()

    mail_status = tk.Frame(right, bg=COLOR_PRIMARY, cursor="hand2")
    mail_status.pack(anchor="e")
    tk.Label(
        mail_status, text="Correo", bg=COLOR_PRIMARY, fg=COLOR_ACCENT,
        font=("Segoe UI", 9, "bold"), cursor="hand2",
    ).pack(side="left", padx=(0, 5))
    mail_labels = {}
    for key, title, color in (
        ("pendiente", "Pendientes", "#f8c471"),
        ("respondido", "Respondidos", "#85c1e9"),
        ("gestionado", "Gestionados", "#82e0aa"),
    ):
        label = tk.Label(
            mail_status, text=f"{title} 0", bg=COLOR_PRIMARY, fg=color,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        label.pack(side="left", padx=(0, 9))
        label.bind("<Button-1>", lambda _event: on_cambiar_empresa())
        mail_labels[key] = label
    mail_status.bind("<Button-1>", lambda _event: on_cambiar_empresa())

    def _set_mail_counts(counts):
        mail_labels["pendiente"].configure(
            text=f"Pendientes {int(counts.get('pendiente', 0))}"
        )
        mail_labels["respondido"].configure(
            text=f"Respondidos {int(counts.get('respondido', 0))}"
        )
        mail_labels["gestionado"].configure(
            text=f"Gestionados {int(counts.get('gestionado', 0))}"
        )

    attachment_button = None
    attachment_menu = None
    attachment_menu_index = None

    def _set_attachment_count(count):
        if (
            attachment_button is None
            or attachment_menu is None
            or attachment_menu_index is None
        ):
            return
        count = int(count or 0)
        attachment_menu.entryconfigure(
            attachment_menu_index,
            label=f"Documentos recibidos ({count})",
        )
        attachment_button.configure(
            text=(
                f"Comunicaciones ({count})  ⌄"
                if count else "Comunicaciones  ⌄"
            ),
            bg="#C87800" if count else COLOR_NAV,
            fg=COLOR_WHITE if count else COLOR_NAV_TEXT,
            activebackground="#A96300" if count else COLOR_NAV_HOV,
            activeforeground=COLOR_WHITE if count else COLOR_NAV_TEXT,
        )
        attachment_button.bind(
            "<Enter>",
            lambda _event: attachment_button.configure(
                bg="#A96300" if count else COLOR_NAV_HOV,
            ),
        )
        attachment_button.bind(
            "<Leave>",
            lambda _event: attachment_button.configure(
                bg="#C87800" if count else COLOR_NAV,
            ),
        )

    # La navegacion ocupa su propia fila: conserva espacio y permite agrupar
    # opciones relacionadas sin convertir la cabecera en una lista de botones.
    btn_row = tk.Frame(
        header,
        bg=COLOR_NAV,
        padx=14,
        pady=6,
        highlightbackground=COLOR_SEPARATOR,
        highlightthickness=1,
    )
    btn_row.pack(fill="x")
    nav_left = tk.Frame(btn_row, bg=COLOR_NAV)
    nav_left.pack(side="left")
    nav_right = tk.Frame(btn_row, bg=COLOR_NAV)
    nav_right.pack(side="right")

    def _hbtn(text, command, danger=False, parent=nav_left):
        bg = COLOR_DANGER if danger else COLOR_NAV
        fg = COLOR_WHITE if danger else COLOR_NAV_TEXT
        hov = COLOR_DANGER_HOV if danger else COLOR_NAV_HOV
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=13,
            pady=6,
            cursor="hand2",
            activebackground=hov,
            activeforeground=fg,
            borderwidth=0,
        )
        button.pack(side="left", padx=(0, 4))
        button.bind("<Enter>", lambda _event: button.configure(bg=hov))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg))
        return button

    def _hmenu(text, commands):
        button = tk.Menubutton(
            nav_left,
            text=f"{text}  ⌄",
            bg=COLOR_NAV,
            fg=COLOR_NAV_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=13,
            pady=6,
            cursor="hand2",
            activebackground=COLOR_NAV_HOV,
            activeforeground=COLOR_NAV_TEXT,
            borderwidth=0,
            direction="below",
        )
        menu = tk.Menu(
            button,
            tearoff=0,
            font=("Segoe UI", 9),
            bg=COLOR_WHITE,
            fg=COLOR_NAV_TEXT,
            activebackground=COLOR_PRIMARY,
            activeforeground=COLOR_WHITE,
            relief="solid",
            borderwidth=1,
        )
        for label, command in commands:
            menu.add_command(label=label, command=command)
        button.configure(menu=menu)
        button.pack(side="left", padx=(0, 4))
        button.bind(
            "<Enter>", lambda _event: button.configure(bg=COLOR_NAV_HOV),
        )
        button.bind(
            "<Leave>", lambda _event: button.configure(bg=COLOR_NAV),
        )
        return button, menu

    if on_open_empresas:
        _hbtn("Empresas", on_open_empresas)

    comunicaciones_menu = [("Buzón de comunicaciones", on_cambiar_empresa)]
    if on_open_adjuntos_mensajeria:
        comunicaciones_menu.append(
            ("Documentos recibidos (0)", on_open_adjuntos_mensajeria),
        )
    attachment_button, attachment_menu = _hmenu(
        "Comunicaciones", comunicaciones_menu,
    )
    if on_open_adjuntos_mensajeria:
        attachment_menu_index = len(comunicaciones_menu) - 1

    if on_open_terceros:
        _hbtn("Terceros", on_open_terceros)

    documentos_menu = []
    if on_open_control_facturas:
        documentos_menu.append(
            ("Control global de facturas", on_open_control_facturas),
        )
    if on_open_firmas:
        documentos_menu.append(("Firma documental", on_open_firmas))
    if documentos_menu:
        _hmenu("Documentos", documentos_menu)

    gestiones_menu = []
    if on_open_notificaciones:
        gestiones_menu.append(
            ("Notificaciones y certificados", on_open_notificaciones),
        )
    if on_open_tramites_dgt:
        gestiones_menu.append(("Trámites DGT", on_open_tramites_dgt))
    if gestiones_menu:
        _hmenu("Gestiones", gestiones_menu)

    admin_menu = []
    if on_open_config and session.is_admin():
        admin_menu.append(("Configuración", on_open_config))
    if on_open_users and session.is_admin():
        admin_menu.append(("Gestión de usuarios", on_open_users))
    if admin_menu:
        _hmenu("Administración", admin_menu)

    if on_logout:
        _hbtn("Cerrar sesión", on_logout, parent=nav_right)
    _hbtn("Salir", root.destroy, danger=True, parent=nav_right)

    # ── Separador ───────────────────────────────────────────────────────
    tk.Frame(root, bg=COLOR_SEPARATOR, height=1).pack(side="top", fill="x")

    # ── Barra de información secundaria ─────────────────────────────────
    parts = []
    if db_label:
        parts.append(f"BD: {db_label}")
    if word_tpl_dir:
        parts.append(f"Plantillas Word: {word_tpl_dir}")
    if parts:
        info_bar = tk.Frame(root, bg=COLOR_INFOBAR, pady=2)
        info_bar.pack(side="top", fill="x")
        tk.Label(
            info_bar, text="  ·  ".join(parts),
            bg=COLOR_INFOBAR, fg=COLOR_MUTED,
            font=("Segoe UI", 8), padx=12,
        ).pack(anchor="w")
        tk.Frame(root, bg=COLOR_SEPARATOR, height=1).pack(side="top", fill="x")

    header.set_mail_counts = _set_mail_counts
    header.set_attachment_count = _set_attachment_count
    return header


def _select_word_templates_dir(default_dir: str) -> str:
    path = filedialog.askdirectory(
        title="Selecciona carpeta de plantillas Word",
        initialdir=default_dir if os.path.isdir(default_dir) else "",
        mustexist=True,
    )
    return path or default_dir


def _restart_app():
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass


def _clear_root(root: tk.Tk):
    for child in root.winfo_children():
        child.destroy()


def _set_window_geometry(root: tk.Tk, width: int, height: int, *, resizable: bool) -> None:
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    pos_x = max(20, int((screen_w - width) / 2))
    pos_y = max(20, int((screen_h - height) / 2))
    root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
    root.resizable(resizable, resizable)


def main():
    ensure_template_file()  # Crea plantillas/email_factura.html si no existe
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
        root._dnd_available = True
        root._dnd_error = ""
    except Exception as exc:
        root = tk.Tk()
        root._dnd_available = False
        root._dnd_error = str(exc)
        log_exception("No se pudo inicializar el arrastre de archivos.", exc)
    root.withdraw()  # ocultar ventana vacia durante inicializacion y comprobacion de actualizaciones
    root.title("Gestinem Suite")
    _set_window_geometry(root, 980, 600, resizable=False)
    aplicar_icono_ventana(root)
    aplicar_tema(root)

    cfg = load_app_config()
    word_tpl_dir = get_word_templates_dir(str(get_default_templates_dir()))
    if not str(cfg.get("word_templates_dir") or "").strip():
        cfg["word_templates_dir"] = word_tpl_dir

    # Migracion automatica: si el DSN contiene password, moverla al almacen seguro
    postgres_dsn = str(cfg.get("postgres_dsn") or "").strip()
    if postgres_dsn:
        from utils.credential_store import migrate_from_dsn
        migrated = migrate_from_dsn(postgres_dsn)
        if migrated:
            # Guardar solo config no sensible; eliminar DSN con password
            cfg.pop("postgres_dsn", None)
            cfg.update(migrated)
            postgres_dsn = ""  # Se reconstruira desde almacen

    # Migracion automatica: mover secretos de config.local.json a Credential Manager
    import logging as _log_module
    _log_migration = _log_module.getLogger(__name__)

    from utils.credential_store import (
        store_workstation_token,
        store_azure_storage_conn,
        store_messaging_device_token,
        store_admin_password, store_desmarcar_password,
        delete_integrations_api_key, delete_azure_doc_key,
        delete_messaging_api_key,
    )

    def _migrar_secreto(config_key: str, store_fn, label: str) -> bool:
        value = str(cfg.get(config_key) or "").strip()
        if not value:
            return False
        ok = store_fn(value)
        if ok:
            cfg.pop(config_key, None)
            _log_migration.info("Secreto '%s' migrado a Windows Credential Manager.", label)
            return True
        _log_migration.warning(
            "No se pudo migrar '%s' al almacen seguro. Se conserva en config local.", label
        )
        return False

    def _limpiar_secreto_legacy(config_key: str, label: str) -> bool:
        """Elimina un secreto legacy del config JSON sin migrarlo al almacen.

        Usado para claves que ya no son necesarias en el escritorio:
        - integrations_api_key / dgt_api_key: sustituidas por WorkstationToken.
        - azure_doc_intelligence_key: el escritorio no debe conectarse a Azure directamente.
        """
        value = str(cfg.get(config_key) or "").strip()
        if not value:
            return False
        cfg.pop(config_key, None)
        _log_migration.info(
            "Secreto legacy '%s' eliminado de la configuracion local (ya no necesario en escritorio).",
            label,
        )
        return True

    # Eliminar credencial legacy MessagingApiKey del Credential Manager y del JSON.
    # Desde 1.6.3 el puesto autentica mensajeria con WorkstationToken.
    delete_messaging_api_key()
    cfg.pop("messaging_api_key", None)

    _any_migrated = False
    for _cfg_key, _store_fn, _label in [
        ("workstation_token",               store_workstation_token,     "workstation_token"),
        ("azure_storage_connection_string", store_azure_storage_conn,    "azure_storage_connection_string"),
        ("messaging_device_token",         store_messaging_device_token, "messaging_device_token"),
        ("admin_password",                 store_admin_password,         "admin_password"),
        ("initial_admin_password",         store_admin_password,         "initial_admin_password"),
        ("desmarcar_generadas_password",   store_desmarcar_password,     "desmarcar_generadas_password"),
    ]:
        if _migrar_secreto(_cfg_key, _store_fn, _label):
            _any_migrated = True

    # Secretos legacy que ya no son necesarios en el escritorio: eliminar del JSON
    # y del Credential Manager si existiesen. El escritorio autentica exclusivamente
    # con WorkstationToken; Azure lo gestiona el backend Railway.
    for _legacy_key, _legacy_label in [
        ("integrations_api_key",       "integrations_api_key"),
        ("dgt_api_key",                "dgt_api_key"),
        ("azure_doc_intelligence_key", "azure_doc_intelligence_key"),
    ]:
        if _limpiar_secreto_legacy(_legacy_key, _legacy_label):
            _any_migrated = True

    # Eliminar tambien del Credential Manager si quedaron de instalaciones anteriores
    try:
        delete_integrations_api_key()
    except Exception:
        pass
    try:
        delete_azure_doc_key()
    except Exception:
        pass

    save_app_config(cfg)

    # Intentar reconstruir DSN desde almacen seguro o campos individuales
    if not postgres_dsn:
        _host = str(cfg.get("postgres_host") or "").strip()
        _port = cfg.get("postgres_port") or 5433
        _db = str(cfg.get("postgres_database") or "").strip()
        _user = str(cfg.get("postgres_user") or "").strip()
        if _host and _db:
            from utils.credential_store import build_dsn_from_store
            postgres_dsn = build_dsn_from_store(_host, _port, _db, _user) or ""

    db_label = "PostgreSQL"

    try:
        while True:
            if not postgres_dsn:
                root.deiconify()
                dialog = PostgresConfigDialog(root)
                root.withdraw()
                if not dialog.result:
                    root.destroy()
                    return
                from utils.credential_store import store_postgres_credentials
                _r = dialog.result
                store_postgres_credentials(_r.get("user", ""), _r.get("password", ""))
                cfg.update({
                    "database_engine": "postgres",
                    "postgres_host": _r.get("host", ""),
                    "postgres_port": _r.get("port", 5432),
                    "postgres_database": _r.get("database", ""),
                    "postgres_user": _r.get("user", ""),
                })
                cfg.pop("postgres_dsn", None)
                save_app_config(cfg)
                postgres_dsn = crear_dsn_postgres(**_r)
            try:
                gestor_base = GestorPostgres(postgres_dsn)
                break
            except Exception as exc:
                log_exception("Error conectando con PostgreSQL.", exc)
                reconfigurar = messagebox.askretrycancel(
                    "Gest2A3Eco",
                    "No se ha podido conectar con PostgreSQL.\n\n"
                    f"Detalle: {exc}\n\n"
                    "Pulsa Reintentar para revisar servidor, usuario y contrasena.",
                    parent=root,
                )
                if not reconfigurar:
                    root.destroy()
                    return
                postgres_dsn = ""
    except Exception as exc:
        log_exception("Error abriendo PostgreSQL.", exc)
        messagebox.showerror(
            "Gest2A3Eco",
            f"No se ha podido abrir PostgreSQL:\n\nDetalle: {exc}",
            parent=root,
        )
        root.destroy()
        return
    from services.tramites_dgt_service import get_protocol_url_from_argv

    protocol_url = get_protocol_url_from_argv(sys.argv)
    if protocol_url:
        try:
            from services.tramites_dgt_service import TramitesDgtService

            service = TramitesDgtService(gestor_base)
            parsed = service.parse_link_seguro(protocol_url)
            root.deiconify()
            _set_window_geometry(root, 780, 680, resizable=True)
            UITramitesDgtPublicForm(
                root,
                service,
                referencia=parsed["referencia"],
                rol=parsed["rol"],
                token=parsed["token"],
            )
            root.mainloop()
        except Exception as exc:
            log_exception("Error abriendo formulario DGT desde enlace.", exc, extra={"url": protocol_url})
            messagebox.showerror("Gest2A3Eco", f"No se pudo abrir el enlace DGT:\n{exc}", parent=root)
            root.destroy()
        return
    auth_service = AuthService(gestor_base)
    _bootstrap_cfg = load_app_config()
    from utils.credential_store import get_admin_password, delete_admin_password
    _bootstrap_password = (
        os.getenv("GEST2A3ECO_ADMIN_PASSWORD")
        or get_admin_password()
        or str(_bootstrap_cfg.get("initial_admin_password") or "").strip()
        or str(_bootstrap_cfg.get("admin_password") or "").strip()
    )
    initial_admin_info = auth_service.ensure_initial_admin(_bootstrap_password)
    # Si el admin ya existe, eliminar la password del almacen seguro (ya no es necesaria)
    if initial_admin_info is None and get_admin_password():
        delete_admin_password()
        import logging as _logging
        _logging.getLogger(__name__).info(
            "Admin inicial ya existe; contrasena de bootstrap eliminada del almacen seguro."
        )

    state = {"controller": None, "session": None, "login_view": None}

    def _on_config_postgres():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede cambiar la conexion PostgreSQL.", parent=root)
            return
        dialog = PostgresConfigDialog(root)
        if not dialog.result:
            return
        _r = dialog.result
        from utils.credential_store import store_postgres_credentials
        store_postgres_credentials(_r.get("user", ""), _r.get("password", ""))
        cfg = load_app_config()
        cfg.pop("postgres_dsn", None)
        cfg.update({
            "database_engine": "postgres",
            "postgres_host": _r.get("host", ""),
            "postgres_port": _r.get("port", 5432),
            "postgres_database": _r.get("database", ""),
            "postgres_user": _r.get("user", ""),
        })
        save_app_config(cfg)
        messagebox.showinfo("Gest2A3Eco", "Conexion PostgreSQL actualizada. La aplicacion se reiniciara.", parent=root)
        root.destroy()
        _restart_app()

    def _on_cambiar_plantillas_word():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede cambiar la carpeta de plantillas.", parent=root)
            return
        new_dir = _select_word_templates_dir(word_tpl_dir)
        if new_dir and new_dir != word_tpl_dir:
            set_word_templates_dir(new_dir)
            messagebox.showinfo("Gest2A3Eco", "Carpeta de plantillas Word cambiada. La aplicacion se reiniciara.", parent=root)
            root.destroy()
            _restart_app()

    def _on_config_monedas():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede modificar la configuracion global.", parent=root)
            return
        MonedasDialog(root)

    def _on_workstation_admin():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede gestionar puestos de trabajo.", parent=root)
            return
        from views.ui_workstation_admin import WorkstationAdminDialog
        WorkstationAdminDialog(root, state["session"])

    def _show_config_menu():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede modificar la configuracion global.", parent=root)
            return
        menu = tk.Menu(root, tearoff=0)
        menu.add_command(label="Configurar PostgreSQL", command=_on_config_postgres)
        menu.add_command(label="Seleccionar plantillas Word", command=_on_cambiar_plantillas_word)
        menu.add_command(label="Configurar monedas y clave desmarcar", command=_on_config_monedas)
        menu.add_separator()
        admin_menu = tk.Menu(menu, tearoff=0)
        admin_menu.add_command(label="Puestos de trabajo", command=_on_workstation_admin)
        menu.add_cascade(label="Administracion", menu=admin_menu)
        try:
            x, y = _posicion_menu_contextual(root)
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _launch_authenticated_ui(session):
        _clear_root(root)
        _set_window_geometry(root, 1850, 1100, resizable=True)
        state["session"] = session
        secured_gestor = SecuredGestor(gestor_base, AuthorizationService(session))
        content = ttk.Frame(root, padding=10, style="TFrame")
        controller = AppController(content, secured_gestor, auth_service, session)
        state["controller"] = controller
        header = _build_header(
            root,
            session=session,
            on_cambiar_empresa=controller.open_buzon,
            on_open_empresas=controller.open_empresas,
            on_open_terceros=controller.open_terceros,
            on_open_control_facturas=(
                controller.open_control_facturas_global
                if controller.authorization.can_view_control_facturas()
                else None
            ),
            on_open_firmas=(
                controller.open_firmas_global
                if controller.authorization.can_manage_firmas()
                else None
            ),
            on_open_adjuntos_mensajeria=controller.open_adjuntos_mensajeria,
            on_open_notificaciones=controller.open_notificaciones_global,
            on_open_tramites_dgt=(
                controller.open_tramites_dgt
                if controller.authorization.can_manage_tramites_dgt()
                else None
            ),
            on_open_config=_show_config_menu,
            on_open_users=controller.open_user_admin,
            on_logout=_logout,
            db_label=db_label,
            word_tpl_dir=word_tpl_dir,
        )
        controller.set_mail_status_callback(header.set_mail_counts)
        controller.set_attachment_status_callback(header.set_attachment_count)
        content.pack(side="top", fill="both", expand=True)
        _deshabilitar_boton_secundario(root)
        controller.start()

    def _force_password_change(username: str, current_password: str, user_id: int) -> str | None:
        dialog = ChangePasswordDialog(root, title="Debes cambiar la contraseña", username=username)
        root.wait_window(dialog)
        if not dialog.result:
            return None
        if dialog.result["current_password"] != current_password:
            messagebox.showerror("Gest2A3Eco", "La contraseña actual no coincide.", parent=root)
            return None
        try:
            auth_service.change_password(user_id, dialog.result["new_password"], must_change_password=False)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=root)
            return None
        return dialog.result["new_password"]

    def _try_login(username: str, password: str):
        result = auth_service.authenticate(username, password)
        if not result.ok:
            state["login_view"].show_error(result.message)
            return
        session = result.session
        if session.user.must_change_password:
            new_password = _force_password_change(session.user.username, password, session.user.id)
            if not new_password:
                state["login_view"].show_error("Debes actualizar la contraseña temporal para continuar.")
                return
            result = auth_service.authenticate(username, new_password)
            session = result.session if result.ok else session
            if session.user.must_change_password:
                session.user.must_change_password = False
        _launch_authenticated_ui(session)

    def _try_microsoft_login():
        login_view = state.get("login_view")
        if login_view:
            login_view.show_error("Esperando autenticacion de Microsoft...")

        def worker():
            try:
                data = DesktopStaffAuthService().login_microsoft()
                error = None
            except Exception as exc:
                data, error = None, exc
            root.after(0, lambda: finish(data, error))

        def finish(data, error):
            current_login = state.get("login_view")
            if error:
                if current_login:
                    current_login.show_error(f"No se pudo iniciar sesion con Microsoft: {error}")
                return
            result = auth_service.authenticate_entra(
                email=str(data.get("email") or ""),
                entra_oid=str(data.get("entra_oid") or ""),
                messaging_staff_id=str(data.get("staff_id") or ""),
            )
            if not result.ok:
                if current_login:
                    current_login.show_error(result.message)
                return
            _launch_authenticated_ui(result.session)

        threading.Thread(target=worker, daemon=True).start()

    def _show_login():
        nonlocal initial_admin_info
        _clear_root(root)
        _set_window_geometry(root, 980, 600, resizable=False)
        login = UILogin(
            root,
            _try_login,
            logo_path=find_login_logo_path(),
            on_microsoft_login=_try_microsoft_login,
        )
        login.pack(fill="both", expand=True)
        state["login_view"] = login
        state["controller"] = None
        state["session"] = None
        if initial_admin_info:
            login.show_error("Usuario inicial: admin. Contraseña temporal pendiente de cambio.")
            initial_admin_info = None

    def _logout():
        _restaurar_boton_secundario(root)
        _show_login()

    if not check_for_updates(root):
        root.destroy()
        return
    root.deiconify()
    _show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
