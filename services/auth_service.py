from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass

from models.auth import CompanyPermission, UserRecord, UserRole, UserSession


DEFAULT_INITIAL_ADMIN_PASSWORD = "admin1234"


@dataclass(slots=True)
class AuthenticationResult:
    ok: bool
    code: str
    message: str
    session: UserSession | None = None


class PasswordHasher:
    """
    Usa scrypt del stdlib con sal aleatoria. No depende de librerias externas.
    """

    _PREFIX = "scrypt"
    _N = 2**14
    _R = 8
    _P = 1
    _DKLEN = 64

    def hash_password(self, plain_password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.scrypt(
            plain_password.encode("utf-8"),
            salt=salt,
            n=self._N,
            r=self._R,
            p=self._P,
            dklen=self._DKLEN,
        )
        return f"{self._PREFIX}${self._N}${self._R}${self._P}${salt.hex()}${digest.hex()}"

    def verify_password(self, plain_password: str, stored_hash: str) -> bool:
        try:
            prefix, n_raw, r_raw, p_raw, salt_hex, digest_hex = str(stored_hash).split("$", 5)
            if prefix != self._PREFIX:
                return False
            digest = hashlib.scrypt(
                plain_password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n_raw),
                r=int(r_raw),
                p=int(p_raw),
                dklen=len(bytes.fromhex(digest_hex)),
            )
            return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
        except Exception:
            return False


class AuthorizationService:
    def __init__(self, session: UserSession):
        self._session = session

    @property
    def session(self) -> UserSession:
        return self._session

    def can_manage_users(self) -> bool:
        return self._session.is_admin()

    def can_manage_global_config(self) -> bool:
        return self._session.is_admin()

    def can_manage_companies(self) -> bool:
        return self._session.is_admin()

    def can_manage_company_catalog(self) -> bool:
        return self._session.role in (UserRole.ADMIN, UserRole.EMPLEADO)

    def can_manage_global_third_parties(self) -> bool:
        return self._session.role in (UserRole.ADMIN, UserRole.EMPLEADO)

    def can_view_control_facturas(self) -> bool:
        """El control es comun; sus filas se limitan por permisos de empresa."""
        return True

    def can_manage_tramites_dgt(self) -> bool:
        return self._session.has_global_permission("tramites_dgt")

    def can_manage_firmas(self) -> bool:
        return self._session.has_global_permission("firmas")

    def permission_for_company(self, codigo_empresa: str) -> CompanyPermission:
        return self._session.permission_for_company(codigo_empresa)

    def can_read_company(self, codigo_empresa: str) -> bool:
        return self._session.can_read_company(codigo_empresa)

    def can_write_company(self, codigo_empresa: str) -> bool:
        return self._session.can_write_company(codigo_empresa)

    def is_company_read_only(self, codigo_empresa: str) -> bool:
        return self.permission_for_company(codigo_empresa) == CompanyPermission.READ

    def ensure_admin(self, message: str | None = None) -> None:
        if self.can_manage_users():
            return
        raise PermissionError(message or "Acceso restringido a administradores.")

    def ensure_tramites_dgt(self, message: str | None = None) -> None:
        if self.can_manage_tramites_dgt():
            return
        raise PermissionError(message or "Acceso restringido al modulo Trámites DGT.")

    def ensure_firmas(self, message: str | None = None) -> None:
        if self.can_manage_firmas():
            return
        raise PermissionError(message or "Acceso restringido al modulo Firmas.")

    def ensure_control_facturas(self, message: str | None = None) -> None:
        if self.can_view_control_facturas():
            return
        raise PermissionError(
            message or "Acceso restringido al control global de facturas."
        )

    def ensure_company_read(self, codigo_empresa: str, message: str | None = None) -> None:
        if self.can_read_company(codigo_empresa):
            return
        raise PermissionError(message or f"Sin acceso a la empresa {codigo_empresa}.")

    def ensure_company_write(self, codigo_empresa: str, message: str | None = None) -> None:
        if self.can_write_company(codigo_empresa):
            return
        raise PermissionError(message or f"Sin permisos de escritura en la empresa {codigo_empresa}.")


class AuthService:
    def __init__(self, gestor, hasher: PasswordHasher | None = None):
        self._gestor = gestor
        self._hasher = hasher or PasswordHasher()

    @property
    def hasher(self) -> PasswordHasher:
        return self._hasher

    def ensure_initial_admin(self, password: str | None = None) -> dict | None:
        if self._gestor.hay_usuarios():
            return None
        initial_password = str(password or "").strip() or DEFAULT_INITIAL_ADMIN_PASSWORD
        password_hash = self._hasher.hash_password(initial_password)
        return self._gestor.crear_usuario_inicial_admin(password_hash)

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        user = self._gestor.get_usuario_by_username(username)
        if not user:
            return AuthenticationResult(False, "user_not_found", "Usuario inexistente.")
        if not bool(user.get("activo")):
            return AuthenticationResult(False, "inactive", "Usuario inactivo.")
        if not bool(user.get("es_cuenta_emergencia")):
            return AuthenticationResult(
                False,
                "microsoft_required",
                "Esta cuenta debe acceder con Microsoft Entra.",
            )
        if not self._hasher.verify_password(password, str(user.get("password_hash") or "")):
            return AuthenticationResult(False, "invalid_password", "Contraseña incorrecta.")
        session = self._build_session(user)
        return AuthenticationResult(True, "ok", "", session=session)

    def authenticate_entra(
        self,
        *,
        email: str,
        entra_oid: str,
        messaging_staff_id: str,
    ) -> AuthenticationResult:
        """Vincula la identidad validada por Entra con el usuario local."""
        email_norm = str(email or "").strip().lower()
        oid = str(entra_oid or "").strip()
        if not email_norm or not oid:
            return AuthenticationResult(
                False, "invalid_entra_identity", "Microsoft no devolvio una identidad valida."
            )
        user = self._gestor.get_usuario_by_entra_oid(oid)
        if not user:
            user = self._gestor.get_usuario_by_email_corporativo(email_norm)
        if not user:
            return AuthenticationResult(
                False,
                "user_not_authorized",
                "La cuenta Microsoft no esta dada de alta en Gestinem.",
            )
        if not bool(user.get("activo")):
            return AuthenticationResult(False, "inactive", "Usuario inactivo.")
        stored_oid = str(user.get("entra_oid") or "").strip()
        if stored_oid and stored_oid != oid:
            return AuthenticationResult(
                False,
                "entra_identity_conflict",
                "El correo esta vinculado a otra identidad de Microsoft.",
            )
        if bool(user.get("es_cuenta_emergencia")):
            return AuthenticationResult(
                False,
                "emergency_local_only",
                "La cuenta de emergencia solo admite acceso local.",
            )
        self._gestor.vincular_usuario_entra(int(user["id"]), oid, email_norm)
        user = self._gestor.get_usuario(int(user["id"])) or user
        session = self._build_session(user)
        session.user.messaging_staff_id = str(messaging_staff_id or "").strip()
        return AuthenticationResult(True, "ok", "", session=session)

    def _build_session(self, user_row: dict) -> UserSession:
        user = UserRecord(
            id=int(user_row["id"]),
            username=str(user_row["username"]),
            nombre=str(user_row.get("nombre") or user_row["username"]),
            rol=UserRole(str(user_row["rol"])),
            activo=bool(user_row.get("activo")),
            must_change_password=bool(user_row.get("must_change_password")),
            email_corporativo=str(user_row.get("email_corporativo") or ""),
            entra_oid=str(user_row.get("entra_oid") or ""),
            es_cuenta_emergencia=bool(user_row.get("es_cuenta_emergencia")),
        )
        permissions: dict[str, CompanyPermission] = {}
        for row in self._gestor.listar_permisos_usuario(user.id):
            permiso_raw = str(row.get("permiso") or CompanyPermission.NONE.value)
            try:
                permiso = CompanyPermission(permiso_raw)
            except Exception:
                permiso = CompanyPermission.NONE
            permissions[str(row.get("empresa_codigo") or "")] = permiso
        global_permissions = {
            str(row.get("permiso") or "").strip()
            for row in self._gestor.listar_permisos_globales_usuario(user.id)
            if bool(row.get("activo", 1)) and str(row.get("permiso") or "").strip()
        }
        return UserSession(user=user, company_permissions=permissions, global_permissions=global_permissions)

    def list_users(self) -> list[dict]:
        return self._gestor.listar_usuarios()

    def get_user(self, user_id: int) -> dict | None:
        return self._gestor.get_usuario(user_id)

    def save_user(
        self,
        *,
        user_id: int | None,
        username: str,
        nombre: str,
        rol: str,
        activo: bool,
        company_permissions: dict[str, str],
        global_permissions: set[str] | list[str] | tuple[str, ...] | None = None,
        password: str | None = None,
        must_change_password: bool = False,
        email_corporativo: str = "",
        es_cuenta_emergencia: bool = False,
    ) -> int:
        username = str(username or "").strip()
        nombre = str(nombre or "").strip()
        if not username:
            raise ValueError("El usuario es obligatorio.")
        if not nombre:
            raise ValueError("El nombre es obligatorio.")
        try:
            user_role = UserRole(str(rol))
        except Exception as exc:
            raise ValueError("Rol de usuario no valido.") from exc

        email_norm = str(email_corporativo or "").strip().lower()
        emergency = bool(es_cuenta_emergencia)
        if emergency and user_role != UserRole.ADMIN:
            raise ValueError("Solo un administrador puede ser cuenta de emergencia.")
        if emergency:
            if username.lower() != "admin":
                raise ValueError("La cuenta local de emergencia debe ser el usuario admin.")
            duplicate_emergency = next((
                row for row in self._gestor.listar_usuarios()
                if bool(row.get("es_cuenta_emergencia"))
                and (user_id is None or int(row["id"]) != int(user_id))
            ), None)
            if duplicate_emergency:
                raise ValueError("Ya existe una cuenta local de emergencia.")
            email_norm = ""
        elif user_role in {UserRole.ADMIN, UserRole.EMPLEADO}:
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_norm):
                raise ValueError("El correo corporativo es obligatorio para acceder con Microsoft.")
            duplicate_email = self._gestor.get_usuario_by_email_corporativo(email_norm)
            if duplicate_email and (
                user_id is None or int(duplicate_email["id"]) != int(user_id)
            ):
                raise ValueError("Ya existe un usuario con ese correo corporativo.")

        existing = self._gestor.get_usuario_by_username(username)
        if existing and (user_id is None or int(existing["id"]) != int(user_id)):
            raise ValueError("Ya existe un usuario con ese nombre.")

        password_hash = None
        if password is not None:
            plain = str(password).strip()
            if not plain:
                raise ValueError("La contraseña no puede estar vacia.")
            password_hash = self._hasher.hash_password(plain)
        elif user_id is None and not emergency and user_role in {UserRole.ADMIN, UserRole.EMPLEADO}:
            password_hash = "!ENTRA_ONLY!"

        stored_id = self._gestor.upsert_usuario(
            {
                "id": user_id,
                "username": username,
                "nombre": nombre,
                "rol": user_role.value,
                "activo": 1 if activo else 0,
                "must_change_password": 1 if must_change_password else 0,
                "password_hash": password_hash,
                "email_corporativo": email_norm,
                "es_cuenta_emergencia": 1 if emergency else 0,
            }
        )

        normalized_permissions: dict[str, str] = {}
        if user_role != UserRole.ADMIN:
            for codigo, permiso_raw in (company_permissions or {}).items():
                codigo_norm = str(codigo or "").strip()
                if not codigo_norm:
                    continue
                try:
                    permiso = CompanyPermission(str(permiso_raw))
                except Exception:
                    permiso = CompanyPermission.NONE
                if permiso == CompanyPermission.NONE:
                    continue
                normalized_permissions[codigo_norm] = permiso.value
        self._gestor.reemplazar_permisos_usuario(stored_id, normalized_permissions)
        requested_global = {
            str(perm or "").strip()
            for perm in (global_permissions or [])
            if str(perm or "").strip()
        }
        existing_global = {
            str(row.get("permiso") or "").strip()
            for row in self._gestor.listar_permisos_globales_usuario(stored_id)
            if str(row.get("permiso") or "").strip()
        }
        for permiso in sorted(requested_global | existing_global):
            self._gestor.upsert_permiso_global_usuario(stored_id, permiso, permiso in requested_global)
        return stored_id

    def change_password(self, user_id: int, new_password: str, *, must_change_password: bool = False) -> None:
        plain = str(new_password or "").strip()
        if not plain:
            raise ValueError("La contraseña no puede estar vacia.")
        password_hash = self._hasher.hash_password(plain)
        self._gestor.actualizar_password_usuario(user_id, password_hash, must_change_password=must_change_password)
