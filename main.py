import os
import sys
import warnings
import tkinter as tk

warnings.filterwarnings("ignore", message="Data Validation extension is not supported", category=UserWarning, module="openpyxl")
from tkinter import filedialog, messagebox, ttk

from controllers.app_controller import AppController
from services.email_service import ensure_template_file
from models.gestor_sqlite import GestorSQLite
from services.auth_service import AuthService, AuthorizationService
from services.secured_gestor import SecuredGestorSQLite
from utils.utilidades import (
    get_default_db_path,
    get_default_templates_dir,
    get_seed_json_path,
    get_word_templates_dir,
    load_app_config,
    log_exception,
    save_app_config,
    set_configured_db_path,
    set_word_templates_dir,
    validate_sqlite_db_path,
)
from views.ui_auth import ChangePasswordDialog, UILogin
from views.ui_config_monedas import MonedasDialog
from views.ui_theme import aplicar_tema
from update_checker import check_for_updates


EMPRESA_NOMBRE = "Asesoria Gestinem S.L."
EMPRESA_CIF = "B16916967"
EMPRESA_DIRECCION = "CL Atilano Rodriguez 4, Entlo. 7, 39002 Santander (Cantabria)"
EMPRESA_EMAIL = "jjdominguez@gestinem.es"
EMPRESA_TELEFONO = "Tel.: 691 474 519"


def resource_path(relpath: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relpath)


def find_login_logo_path() -> str:
    project_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        resource_path("logo.png"),
        resource_path("logo.jpg"),
        os.path.join(project_dir, "dist", "Gest2A3Eco", "_internal", "logo.png"),
        resource_path("icono.ico"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _build_header(
    root: tk.Tk,
    session,
    on_cambiar_empresa,
    on_open_config=None,
    on_open_users=None,
    on_open_terceros=None,
    on_open_notificaciones=None,
    on_logout=None,
    db_path: str | None = None,
    word_tpl_dir: str | None = None,
) -> tk.Frame:
    COLOR_PRIMARY      = "#002C57"
    COLOR_PRIMARY_HOV  = "#1a4a7a"
    COLOR_DANGER       = "#c0392b"
    COLOR_DANGER_HOV   = "#a93226"
    COLOR_WHITE        = "#ffffff"
    COLOR_ACCENT       = "#a8c4e0"
    COLOR_SEPARATOR    = "#d0d0d0"
    COLOR_INFOBAR      = "#e8ecf0"
    COLOR_MUTED        = "#6c757d"

    # ── Franja principal ────────────────────────────────────────────────
    header = tk.Frame(root, bg=COLOR_PRIMARY)
    header.pack(side="top", fill="x")

    inner = tk.Frame(header, bg=COLOR_PRIMARY, padx=16, pady=10)
    inner.pack(fill="x")

    # ── Lado izquierdo: logo + datos empresa ────────────────────────────
    left = tk.Frame(inner, bg=COLOR_PRIMARY)
    left.pack(side="left", fill="y")

    try:
        logo_img = tk.PhotoImage(file=resource_path("logo.png"))
        max_h = 64
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
        font=("Segoe UI", 15, "bold"), anchor="w",
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

    role_label = str(getattr(session, "role", "")).replace("UserRole.", "")
    tk.Label(
        right, text=f"\u25cf  {session.user.nombre}  \u2014  {role_label}",
        bg=COLOR_PRIMARY, fg=COLOR_ACCENT,
        font=("Segoe UI", 9), anchor="e",
    ).pack(anchor="e", pady=(0, 8))

    btn_row = tk.Frame(right, bg=COLOR_PRIMARY)
    btn_row.pack(anchor="e")

    def _hbtn(text, command, danger=False):
        bg  = COLOR_DANGER      if danger else COLOR_PRIMARY_HOV
        hov = COLOR_DANGER_HOV  if danger else "#1e5999"
        b = tk.Button(
            btn_row, text=text, command=command,
            bg=bg, fg=COLOR_WHITE,
            font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=5,
            cursor="hand2",
            activebackground=hov, activeforeground=COLOR_WHITE,
            borderwidth=0,
        )
        b.pack(side="left", padx=(0, 6))
        return b

    _hbtn("Empresas", on_cambiar_empresa)
    if on_open_terceros:
        _hbtn("Terceros", on_open_terceros)
    if on_open_notificaciones:
        _hbtn("Notificaciones/Certificados", on_open_notificaciones)
    if on_open_config and session.is_admin():
        _hbtn("Configuracion", on_open_config)
    if on_open_users and session.is_admin():
        _hbtn("Usuarios", on_open_users)
    if on_logout:
        _hbtn("Cerrar sesion", on_logout)
    _hbtn("Cerrar", root.destroy, danger=True)

    # ── Separador ───────────────────────────────────────────────────────
    tk.Frame(root, bg=COLOR_SEPARATOR, height=1).pack(side="top", fill="x")

    # ── Barra de información secundaria ─────────────────────────────────
    parts = []
    if db_path:
        parts.append(f"BD: {db_path}")
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

    return header


def _select_db_path(default_path: str) -> str:
    path = filedialog.asksaveasfilename(
        title="Selecciona o crea base de datos",
        initialdir=os.path.dirname(default_path),
        initialfile=os.path.basename(default_path),
        filetypes=[("SQLite DB", "*.db"), ("Todos", "*.*")],
        defaultextension=".db",
    )
    return path or default_path


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
    root = tk.Tk()
    root.withdraw()  # ocultar ventana vacia durante inicializacion y comprobacion de actualizaciones
    root.title("Gest2A3Eco")
    _set_window_geometry(root, 520, 480, resizable=False)
    try:
        root.iconbitmap(resource_path("icono.ico"))
    except Exception:
        pass
    aplicar_tema(root)

    cfg = load_app_config()
    db_path = str(cfg.get("db_path") or cfg.get("last_db_path") or "").strip() or str(get_default_db_path())
    word_tpl_dir = get_word_templates_dir(str(get_default_templates_dir()))
    if not str(cfg.get("db_path") or "").strip():
        cfg["db_path"] = db_path
    if not str(cfg.get("last_db_path") or "").strip():
        cfg["last_db_path"] = db_path
    if not str(cfg.get("word_templates_dir") or "").strip():
        cfg["word_templates_dir"] = word_tpl_dir
    save_app_config(cfg)

    try:
        db_path = validate_sqlite_db_path(db_path, allow_create=True)
    except Exception as exc:
        log_exception("Error validando la base de datos SQLite al iniciar.", exc, extra={"db_path": db_path})
        messagebox.showerror(
            "Gest2A3Eco",
            f"No se puede usar la base de datos SQLite configurada:\n{db_path}\n\nDetalle: {exc}",
            parent=root,
        )
        root.destroy()
        return

    try:
        gestor_base = GestorSQLite(db_path, json_seed=get_seed_json_path())
    except Exception as exc:
        log_exception("Error abriendo la base de datos SQLite.", exc, extra={"db_path": db_path})
        messagebox.showerror(
            "Gest2A3Eco",
            f"No se ha podido abrir la base de datos SQLite:\n{db_path}\n\nDetalle: {exc}",
            parent=root,
        )
        root.destroy()
        return
    auth_service = AuthService(gestor_base)
    initial_admin_info = auth_service.ensure_initial_admin(
        os.getenv("GEST2A3ECO_ADMIN_PASSWORD")
        or str(load_app_config().get("initial_admin_password") or "").strip()
        or str(load_app_config().get("admin_password") or "").strip()
    )

    state = {"controller": None, "session": None, "login_view": None}

    def _on_cambiar_db():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede cambiar la base de datos.", parent=root)
            return
        new_path = _select_db_path(db_path)
        if new_path and new_path != db_path:
            try:
                validated = validate_sqlite_db_path(new_path, allow_create=True)
            except Exception as exc:
                log_exception("Error validando una base de datos seleccionada manualmente.", exc, extra={"db_path": new_path})
                messagebox.showerror(
                    "Gest2A3Eco",
                    f"No se puede usar la base de datos seleccionada:\n{new_path}\n\nDetalle: {exc}",
                    parent=root,
                )
                return
            set_configured_db_path(validated)
            messagebox.showinfo("Gest2A3Eco", "Base de datos cambiada. La aplicacion se reiniciara.", parent=root)
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

    def _build_context_menu(controller):
        ctx = tk.Menu(root, tearoff=0)
        ctx.add_command(label="Menu principal", command=controller.start)
        ctx.add_separator()
        ctx.add_command(label="Cerrar sesion", command=_logout)
        ctx.add_command(label="Cerrar", command=root.destroy)
        return ctx

    def _show_config_menu():
        if not state["session"] or not state["session"].is_admin():
            messagebox.showerror("Gest2A3Eco", "Solo el administrador puede modificar la configuracion global.", parent=root)
            return
        menu = tk.Menu(root, tearoff=0)
        menu.add_command(label="Seleccionar base de datos", command=_on_cambiar_db)
        menu.add_command(label="Seleccionar plantillas Word", command=_on_cambiar_plantillas_word)
        menu.add_command(label="Configurar monedas y clave desmarcar", command=_on_config_monedas)
        try:
            x = root.winfo_rootx() + root.winfo_width() - 220
            y = root.winfo_rooty() + 110
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _launch_authenticated_ui(session):
        _clear_root(root)
        _set_window_geometry(root, 1850, 1100, resizable=True)
        state["session"] = session
        secured_gestor = SecuredGestorSQLite(gestor_base, AuthorizationService(session))
        content = ttk.Frame(root, padding=10, style="TFrame")
        controller = AppController(content, secured_gestor, auth_service, session)
        state["controller"] = controller
        _build_header(
            root,
            session=session,
            on_cambiar_empresa=controller.start,
            on_open_terceros=controller.open_terceros,
            on_open_notificaciones=controller.open_notificaciones_global,
            on_open_config=_show_config_menu,
            on_open_users=controller.open_user_admin,
            on_logout=_logout,
            db_path=db_path,
            word_tpl_dir=word_tpl_dir,
        )
        content.pack(side="top", fill="both", expand=True)
        ctx = _build_context_menu(controller)

        def _show_ctx(event):
            try:
                ctx.tk_popup(event.x_root, event.y_root)
            finally:
                ctx.grab_release()

        root.bind("<Button-3>", _show_ctx)
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

    def _show_login():
        nonlocal initial_admin_info
        _clear_root(root)
        _set_window_geometry(root, 520, 480, resizable=False)
        login = UILogin(root, _try_login, logo_path=find_login_logo_path())
        login.pack(fill="both", expand=True)
        state["login_view"] = login
        state["controller"] = None
        state["session"] = None
        if initial_admin_info:
            login.show_error("Usuario inicial: admin. Contraseña temporal pendiente de cambio.")
            initial_admin_info = None

    def _logout():
        root.unbind("<Button-3>")
        _show_login()

    if not check_for_updates(root):
        root.destroy()
        return
    root.deiconify()
    _show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
