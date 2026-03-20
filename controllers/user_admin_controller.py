from __future__ import annotations


class UserAdminController:
    def __init__(self, gestor, auth_service, view):
        self._gestor = gestor
        self._auth_service = auth_service
        self._view = view
        self._users_cache: list[dict] = []
        self._companies_cache: list[dict] = []

    def refresh(self):
        self._users_cache = self._auth_service.list_users()
        self._companies_cache = self._listar_empresas_unicas()
        self._view.set_users(self._users_cache)
        self.nuevo()

    def nuevo(self):
        self._view.load_user(None, self._companies_cache, {})

    def seleccionar_usuario(self):
        user_id = self._view.get_selected_user_id()
        if not user_id:
            return
        user = self._auth_service.get_user(user_id)
        assigned = {
            str(row.get("empresa_codigo") or ""): str(row.get("permiso") or "")
            for row in self._gestor.listar_permisos_usuario(user_id)
        }
        self._view.load_user(user, self._companies_cache, assigned)

    def guardar(self):
        data = self._view.get_form_data()
        password = data.get("password") or None
        try:
            user_id = self._auth_service.save_user(
                user_id=data.get("id"),
                username=data.get("username"),
                nombre=data.get("nombre"),
                rol=data.get("rol"),
                activo=data.get("activo"),
                company_permissions=data.get("company_permissions") or {},
                password=password,
                must_change_password=bool(data.get("must_change_password")),
            )
        except Exception as exc:
            self._view.show_error(str(exc))
            return
        self.refresh()
        if self._view.tv_users.exists(str(user_id)):
            self._view.tv_users.selection_set(str(user_id))
            self.seleccionar_usuario()
        self._view.show_info("Usuario guardado.")

    def cambiar_password(self):
        user_id = self._view.get_selected_user_id()
        if not user_id:
            self._view.show_error("Selecciona un usuario.")
            return
        payload = self._view.ask_new_password()
        if not payload:
            return
        try:
            self._auth_service.change_password(
                user_id,
                payload["password"],
                must_change_password=bool(payload.get("must_change_password")),
            )
        except Exception as exc:
            self._view.show_error(str(exc))
            return
        self.refresh()
        self._view.show_info("Contraseña actualizada.")

    def _listar_empresas_unicas(self) -> list[dict]:
        rows = self._gestor.listar_empresas()
        by_code = {}
        for row in rows:
            codigo = str(row.get("codigo") or "")
            if not codigo:
                continue
            current = by_code.get(codigo)
            if current is None:
                by_code[codigo] = {
                    "codigo": codigo,
                    "nombre": row.get("nombre", ""),
                }
                continue
            if not current.get("nombre") and row.get("nombre"):
                current["nombre"] = row.get("nombre")
        return sorted(by_code.values(), key=lambda item: (item["codigo"], str(item.get("nombre") or "")))
