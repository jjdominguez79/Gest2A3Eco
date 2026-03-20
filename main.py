import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controllers.app_controller import AppController
from models.gestor_sqlite import GestorSQLite
from services.auth_service import AuthService, AuthorizationService
from services.secured_gestor import SecuredGestorSQLite
from utils.utilidades import get_word_templates_dir, load_app_config, save_app_config, set_word_templates_dir
from views.ui_auth import ChangePasswordDialog, UILogin
from views.ui_config_monedas import MonedasDialog
from views.ui_theme import aplicar_tema


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


def app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_base_dir()
PLANTILLAS_DIR = os.path.join(BASE_DIR, "plantillas")
os.makedirs(PLANTILLAS_DIR, exist_ok=True)
RUTA_JSON = os.path.join(PLANTILLAS_DIR, "plantillas.json")
RUTA_DB = os.path.join(PLANTILLAS_DIR, "gest2a3eco.db")


def _build_header(
    root: tk.Tk,
    session,
    on_cambiar_empresa,
    on_open_users=None,
    on_logout=None,
    db_path: str | None = None,
    word_tpl_dir: str | None = None,
) -> ttk.Frame:
    header = ttk.Frame(root, padding=10, style="TFrame")
    header.pack(side="top", fill="x")

    try:
        logo_img = tk.PhotoImage(file=resource_path("logo.png"))
        max_h = 72
        if logo_img.height() > max_h:
            factor = max(1, logo_img.height() // max_h)
            logo_img = logo_img.subsample(factor, factor)
        root._logo_img = logo_img
        ttk.Label(header, image=logo_img, style="TLabel").grid(row=0, column=0, rowspan=4, sticky="w", padx=(0, 10))
    except Exception:
        pass

    ttk.Label(header, text=EMPRESA_NOMBRE, style="Header.TLabel").grid(row=0, column=1, sticky="w")
    ttk.Label(
        header,
        text=f"CIF: {EMPRESA_CIF}  ·  {EMPRESA_DIRECCION}",
        style="SubHeader.TLabel",
    ).grid(row=1, column=1, sticky="w")
    ttk.Label(
        header,
        text=f"Email: {EMPRESA_EMAIL}  ·  {EMPRESA_TELEFONO}",
        style="SubHeader.TLabel",
    ).grid(row=2, column=1, sticky="w")

    role_label = str(getattr(session, "role", "")).replace("UserRole.", "")
    ttk.Label(
        header,
        text=f"Usuario: {session.user.nombre} ({role_label})",
        style="SubHeader.TLabel",
    ).grid(row=3, column=1, sticky="w")

    botones_frame = ttk.Frame(header, style="TFrame")
    botones_frame.grid(row=0, column=2, rowspan=4, sticky="e", padx=(20, 0))

    ttk.Button(botones_frame, text="Empresas", style="Primary.TButton", command=on_cambiar_empresa).grid(row=0, column=0, sticky="ew", pady=(0, 6))
    if on_open_users and session.is_admin():
        ttk.Button(botones_frame, text="Usuarios", style="Primary.TButton", command=on_open_users).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        logout_row = 2
    else:
        logout_row = 1
    if on_logout:
        ttk.Button(botones_frame, text="Cerrar sesion", command=on_logout).grid(row=logout_row, column=0, sticky="ew", pady=(0, 6))
        close_row = logout_row + 1
    else:
        close_row = logout_row
    ttk.Button(botones_frame, text="Cerrar", style="Danger.TButton", command=root.destroy).grid(row=close_row, column=0, sticky="ew")
    botones_frame.columnconfigure(0, weight=1)

    if db_path:
        ttk.Label(header, text=f"Base de datos: {db_path}", style="SubHeader.TLabel", foreground="#3f3f3f").grid(row=4, column=1, sticky="w")
    if word_tpl_dir:
        ttk.Label(header, text=f"Plantillas Word: {word_tpl_dir}", style="SubHeader.TLabel", foreground="#3f3f3f").grid(row=5, column=1, sticky="w")
    header.columnconfigure(1, weight=1)
    return header


def _select_db_path(default_path: str) -> str:
    path = filedialog.askopenfilename(
        title="Selecciona base de datos",
        initialdir=os.path.dirname(default_path),
        initialfile=os.path.basename(default_path),
        filetypes=[("SQLite DB", "*.db"), ("Todos", "*.*")],
    )
    return path or default_path


def _select_word_templates_dir(default_dir: str) -> str:
    path = filedialog.askdirectory(
        title="Selecciona carpeta de plantillas Word",
        initialdir=default_dir if os.path.isdir(default_dir) else "",
        mustexist=True,
    )
    return path or default_dir


def _get_last_db_path(default_path: str) -> str:
    cfg = load_app_config()
    last = str(cfg.get("last_db_path") or "").strip()
    if last and os.path.exists(last):
        return last
    return default_path


def _set_last_db_path(path: str) -> None:
    cfg = load_app_config()
    cfg["last_db_path"] = path
    save_app_config(cfg)


def _restart_app():
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass


def _clear_root(root: tk.Tk):
    for child in root.winfo_children():
        child.destroy()


def main():
    root = tk.Tk()
    root.title("Gest2A3Eco")
    root.geometry("1850x1100+60+30")
    root.resizable(True, True)
    try:
        root.iconbitmap(resource_path("icono.ico"))
    except Exception:
        pass
    aplicar_tema(root)

    db_path = _get_last_db_path(RUTA_DB)
    if not db_path:
        db_path = RUTA_DB
    _set_last_db_path(db_path)

    default_tpl_dir = os.path.join(BASE_DIR, "plantillas")
    word_tpl_dir = get_word_templates_dir(default_tpl_dir)
    if not word_tpl_dir:
        word_tpl_dir = default_tpl_dir
    os.makedirs(word_tpl_dir, exist_ok=True)
    set_word_templates_dir(word_tpl_dir)

    gestor_base = GestorSQLite(db_path, json_seed=RUTA_JSON)
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
            _set_last_db_path(new_path)
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
        if state["session"] and state["session"].is_admin():
            ctx.add_command(label="Usuarios", command=controller.open_user_admin)
            cfg_menu = tk.Menu(ctx, tearoff=0)
            cfg_menu.add_command(label="Seleccionar base de datos", command=_on_cambiar_db)
            cfg_menu.add_command(label="Seleccionar plantillas Word", command=_on_cambiar_plantillas_word)
            cfg_menu.add_command(label="Configurar monedas", command=_on_config_monedas)
            ctx.add_cascade(label="Configuracion", menu=cfg_menu)
        ctx.add_separator()
        ctx.add_command(label="Cerrar sesion", command=_logout)
        ctx.add_command(label="Cerrar", command=root.destroy)
        return ctx

    def _launch_authenticated_ui(session):
        _clear_root(root)
        state["session"] = session
        secured_gestor = SecuredGestorSQLite(gestor_base, AuthorizationService(session))
        content = ttk.Frame(root, padding=10, style="TFrame")
        controller = AppController(content, secured_gestor, auth_service, session)
        state["controller"] = controller
        _build_header(
            root,
            session=session,
            on_cambiar_empresa=controller.start,
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
        login = UILogin(root, _try_login)
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

    _show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
