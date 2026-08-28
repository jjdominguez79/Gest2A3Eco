"""Pantalla de administracion de puestos de trabajo.

Accesible desde Configuracion > Administracion > Puestos de trabajo.
Solo para usuarios con rol admin.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk

from services.workstation_admin_service import (
    STATUS_ACTIVATED,
    STATUS_BACKEND_UNAVAILABLE,
    STATUS_DEACTIVATED,
    STATUS_NOT_ACTIVATED,
    STATUS_TOKEN_INVALID,
    WorkstationAdminService,
    get_hostname,
)

logger = logging.getLogger(__name__)

COLOR_PRIMARY = "#002C57"
COLOR_WHITE = "#ffffff"
COLOR_BG = "#f5f5f7"
COLOR_SURFACE = "#ffffff"
COLOR_BORDER = "#d0d0d0"
COLOR_SUCCESS = "#27ae60"
COLOR_WARNING = "#e67e22"
COLOR_DANGER = "#D64545"
COLOR_MUTED = "#6c757d"

STATUS_LABELS = {
    STATUS_ACTIVATED: ("Activado", COLOR_SUCCESS),
    STATUS_NOT_ACTIVATED: ("Sin activar", COLOR_MUTED),
    STATUS_TOKEN_INVALID: ("Token invalido", COLOR_DANGER),
    STATUS_DEACTIVATED: ("Puesto desactivado", COLOR_WARNING),
    STATUS_BACKEND_UNAVAILABLE: ("Backend no disponible", COLOR_WARNING),
}


def _format_datetime(iso_str: str | None) -> str:
    if not iso_str:
        return "Nunca"
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        if dt.date() == now.date():
            return f"Hoy {dt.strftime('%H:%M')}"
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso_str)[:16]


class WorkstationAdminDialog(tk.Toplevel):
    """Dialogo de administracion de puestos de trabajo."""

    def __init__(self, parent, session):
        super().__init__(parent)
        self.title("Puestos de trabajo")
        self.geometry("780x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._session = session
        self._service = WorkstationAdminService()
        self._hostname = get_hostname()
        self._workstations: list[dict] = []
        self._admin_logged_in = False

        self._build_ui()
        self._check_current_status()

    def _build_ui(self):
        self.configure(bg=COLOR_BG)

        # Header
        header = tk.Frame(self, bg=COLOR_PRIMARY, padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(
            header, text="Puestos de trabajo",
            bg=COLOR_PRIMARY, fg=COLOR_WHITE,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        # Estado del equipo actual
        status_frame = tk.Frame(self, bg=COLOR_SURFACE, padx=16, pady=12)
        status_frame.pack(fill="x", padx=12, pady=(12, 0))

        row = tk.Frame(status_frame, bg=COLOR_SURFACE)
        row.pack(fill="x")
        tk.Label(
            row, text=f"Equipo actual:  {self._hostname}",
            bg=COLOR_SURFACE, fg="#222222",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self._status_label = tk.Label(
            row, text="Comprobando...",
            bg=COLOR_SURFACE, fg=COLOR_MUTED,
            font=("Segoe UI", 10),
        )
        self._status_label.pack(side="left", padx=(16, 0))

        btn_row = tk.Frame(status_frame, bg=COLOR_SURFACE)
        btn_row.pack(fill="x", pady=(8, 0))

        self._btn_activate = tk.Button(
            btn_row, text="Activar este equipo",
            bg=COLOR_PRIMARY, fg=COLOR_WHITE,
            font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._on_activate_current,
            state="disabled",
        )
        self._btn_activate.pack(side="left")

        self._btn_refresh = tk.Button(
            btn_row, text="Actualizar",
            bg="#e0e0e0", fg="#333333",
            font=("Segoe UI", 9),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._on_refresh,
        )
        self._btn_refresh.pack(side="left", padx=(8, 0))

        # Separador
        tk.Frame(self, bg=COLOR_BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # Tabla de puestos
        table_frame = tk.Frame(self, bg=COLOR_SURFACE, padx=12, pady=8)
        table_frame.pack(fill="both", expand=True, padx=12)

        tk.Label(
            table_frame, text="Puestos registrados",
            bg=COLOR_SURFACE, fg="#222222",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        cols = ("name", "status", "last_seen", "created")
        self._tree = ttk.Treeview(
            table_frame, columns=cols, show="headings",
            height=10, selectmode="browse",
        )
        self._tree.heading("name", text="Puesto")
        self._tree.heading("status", text="Estado")
        self._tree.heading("last_seen", text="Ultimo acceso")
        self._tree.heading("created", text="Creado")
        self._tree.column("name", width=200, minwidth=120)
        self._tree.column("status", width=100, minwidth=80)
        self._tree.column("last_seen", width=180, minwidth=120)
        self._tree.column("created", width=150, minwidth=100)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.tag_configure("current", background="#e8f4e8")
        self._tree.tag_configure("inactive", foreground=COLOR_MUTED)

        # Botones de accion
        action_frame = tk.Frame(self, bg=COLOR_BG, padx=12, pady=10)
        action_frame.pack(fill="x")

        self._btn_toggle = tk.Button(
            action_frame, text="Activar",
            bg="#e0e0e0", fg="#333333",
            font=("Segoe UI", 9),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._on_toggle_selected,
            state="disabled",
        )
        self._btn_toggle.pack(side="left")

        self._btn_regen = tk.Button(
            action_frame, text="Regenerar token",
            bg="#e0e0e0", fg="#333333",
            font=("Segoe UI", 9),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._on_regenerate_selected,
            state="disabled",
        )
        self._btn_regen.pack(side="left", padx=(8, 0))

        self._tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        # Login frame (oculto hasta que se necesite autenticacion admin)
        self._login_frame = tk.Frame(self, bg=COLOR_BG)
        self._info_label = tk.Label(
            action_frame, text="",
            bg=COLOR_BG, fg=COLOR_MUTED,
            font=("Segoe UI", 9),
        )
        self._info_label.pack(side="right")

    def _check_current_status(self):
        """Comprueba el estado del equipo actual (no requiere login admin)."""
        def _do():
            try:
                result = self._service.check_current_workstation_status()
                self.after(0, lambda: self._update_status(result))
            except Exception as exc:
                self.after(0, lambda: self._update_status(
                    {"status": STATUS_BACKEND_UNAVAILABLE, "name": self._hostname}
                ))
        threading.Thread(target=_do, daemon=True).start()

    def _update_status(self, result: dict):
        st = result.get("status", STATUS_BACKEND_UNAVAILABLE)
        label_text, color = STATUS_LABELS.get(st, ("Desconocido", COLOR_MUTED))
        self._status_label.configure(text=f"Estado: {label_text}", fg=color)

        if st in (STATUS_NOT_ACTIVATED, STATUS_TOKEN_INVALID, STATUS_DEACTIVATED):
            self._btn_activate.configure(state="normal")
        elif st == STATUS_ACTIVATED:
            self._btn_activate.configure(state="disabled")

    def _ensure_admin_login(self) -> bool:
        """Asegura que el admin esta autenticado en el backend via Microsoft."""
        if self._admin_logged_in:
            return True

        if not self._service.configured:
            messagebox.showerror(
                "Gestinem Suite",
                "No hay URL de backend configurada.\n\n"
                "Revisa integrations_api_url en la configuracion.",
                parent=self,
            )
            return False

        confirm = messagebox.askyesno(
            "Gestinem Suite",
            "Para administrar los puestos debes identificarte como administrador.\n\n"
            "Se abrira el navegador para iniciar sesion con tu cuenta Microsoft corporativa.\n\n"
            "Continuar?",
            parent=self,
        )
        if not confirm:
            return False

        self._info_label.configure(text="Esperando autenticacion Microsoft...")

        result_holder = {}
        error_holder = {}
        done_event = threading.Event()

        def _do_login():
            try:
                data = self._service.login_microsoft()
                result_holder["data"] = data
            except Exception as exc:
                detail = ""
                try:
                    import json as _json
                    resp = getattr(exc, "response", None)
                    if resp is not None:
                        detail = _json.loads(resp.text).get("detail", "")
                except Exception:
                    pass
                error_holder["detail"] = detail or str(exc)
            finally:
                done_event.set()
                self.after(0, _on_login_done)

        def _on_login_done():
            if result_holder.get("data"):
                self._admin_logged_in = True
                name = result_holder["data"].get("username", "")
                self._info_label.configure(text=f"Admin: {name}")
            elif error_holder.get("detail"):
                self._info_label.configure(text="")
                messagebox.showerror(
                    "Gestinem Suite",
                    f"Error de autenticacion:\n{error_holder['detail']}",
                    parent=self,
                )

        threading.Thread(target=_do_login, daemon=True).start()
        done_event.wait(timeout=320)
        return self._admin_logged_in

    def _on_activate_current(self):
        if not self._ensure_admin_login():
            return

        def _do():
            try:
                result = self._service.activate_current_workstation()
                self.after(0, lambda: self._handle_activation_result(result))
            except Exception as exc:
                msg = str(exc)
                try:
                    import json
                    msg = json.loads(exc.response.text).get("detail", msg)
                except Exception:
                    pass
                self.after(0, lambda: messagebox.showerror(
                    "Gestinem Suite", f"Error al activar:\n{msg}", parent=self,
                ))

        self._btn_activate.configure(state="disabled", text="Activando...")
        threading.Thread(target=_do, daemon=True).start()

    def _handle_activation_result(self, result: dict):
        self._btn_activate.configure(text="Activar este equipo")
        if result.get("success"):
            messagebox.showinfo("Gestinem Suite", result["message"], parent=self)
            self._check_current_status()
            self._load_workstations()
        else:
            messagebox.showerror("Gestinem Suite", result.get("message", "Error desconocido."), parent=self)

    def _on_refresh(self):
        self._check_current_status()
        if self._admin_logged_in:
            self._load_workstations()

        if not self._admin_logged_in:
            if self._ensure_admin_login():
                self._load_workstations()

    def _load_workstations(self):
        def _do():
            try:
                ws_list = self._service.list_workstations()
                self.after(0, lambda: self._populate_tree(ws_list))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._info_label.configure(text=f"Error: {msg}"))
        threading.Thread(target=_do, daemon=True).start()

    def _populate_tree(self, workstations: list[dict]):
        self._workstations = workstations
        self._tree.delete(*self._tree.get_children())
        for ws in workstations:
            status_text = "Activo" if ws["active"] else "Inactivo"
            tags = ()
            if ws["name"] == self._hostname:
                tags = ("current",)
            elif not ws["active"]:
                tags = ("inactive",)
            name_display = ws["name"]
            if ws["name"] == self._hostname:
                name_display = f"{ws['name']}  (este equipo)"
            self._tree.insert(
                "", "end",
                iid=ws["id"],
                values=(
                    name_display,
                    status_text,
                    _format_datetime(ws.get("last_seen_at")),
                    _format_datetime(ws.get("created_at")),
                ),
                tags=tags,
            )
        self._info_label.configure(text=f"{len(workstations)} puesto(s) registrado(s)")

    def _on_selection_changed(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            self._btn_toggle.configure(state="disabled", text="Activar")
            self._btn_regen.configure(state="disabled")
            return
        ws = self._get_selected_ws()
        if not ws:
            return
        if ws["active"]:
            self._btn_toggle.configure(state="normal", text="Desactivar")
        else:
            self._btn_toggle.configure(state="normal", text="Activar")
        self._btn_regen.configure(state="normal")

    def _get_selected_ws(self) -> dict | None:
        sel = self._tree.selection()
        if not sel:
            return None
        ws_id = sel[0]
        return next((ws for ws in self._workstations if ws["id"] == ws_id), None)

    def _on_toggle_selected(self):
        ws = self._get_selected_ws()
        if not ws:
            return
        if not self._ensure_admin_login():
            return
        new_active = not ws["active"]
        action = "activar" if new_active else "desactivar"
        msg = (
            f"Quieres {action} el puesto {ws['name']}?\n\n"
        )
        if not new_active:
            msg += "Este ordenador dejara de poder utilizar los servicios del backend."
        else:
            msg += "El puesto podra utilizar los servicios del backend."

        if not messagebox.askyesno("Gestinem Suite", msg, parent=self):
            return

        def _do():
            try:
                self._service.set_active(ws["id"], new_active)
                self.after(0, self._load_workstations)
                self.after(0, self._check_current_status)
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: messagebox.showerror(
                    "Gestinem Suite", f"Error: {msg}", parent=self,
                ))
        threading.Thread(target=_do, daemon=True).start()

    def _on_regenerate_selected(self):
        ws = self._get_selected_ws()
        if not ws:
            return
        if not self._ensure_admin_login():
            return

        is_current = ws["name"] == self._hostname
        msg = f"Se invalidara el token anterior de {ws['name']}.\n\n"
        if is_current:
            msg += "Se generara un nuevo token y se guardara automaticamente en este equipo."
        else:
            msg += (
                "El ordenador necesitara volver a activarse para obtener el nuevo token.\n"
                "No se puede transportar el token de forma segura a otro equipo."
            )

        if not messagebox.askyesno("Gestinem Suite", msg, parent=self):
            return

        def _do():
            try:
                result = self._service.regenerate_token(ws["id"])
                if is_current:
                    from utils.credential_store import store_workstation_token
                    new_token = result.get("token", "")
                    if new_token:
                        store_workstation_token(new_token)
                        logger.info("Token regenerado y almacenado para equipo actual.")
                self.after(0, lambda: self._handle_regen_result(ws, is_current))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: messagebox.showerror(
                    "Gestinem Suite", f"Error: {msg}", parent=self,
                ))
        threading.Thread(target=_do, daemon=True).start()

    def _handle_regen_result(self, ws: dict, is_current: bool):
        if is_current:
            messagebox.showinfo(
                "Gestinem Suite",
                "Token regenerado y almacenado correctamente.",
                parent=self,
            )
            self._check_current_status()
        else:
            messagebox.showinfo(
                "Gestinem Suite",
                f"Token de {ws['name']} regenerado.\n\n"
                f"El equipo {ws['name']} debera volver a activarse.",
                parent=self,
            )
        self._load_workstations()


