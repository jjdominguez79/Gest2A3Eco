from __future__ import annotations

import hashlib
import hmac
import os
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
        if not self._hasher.verify_password(password, str(user.get("password_hash") or "")):
            return AuthenticationResult(False, "invalid_password", "Contraseña incorrecta.")
        session = self._build_session(user)
        return AuthenticationResult(True, "ok", "", session=session)

    def _build_session(self, user_row: dict) -> UserSession:
        user = UserRecord(
            id=int(user_row["id"]),
            username=str(user_row["username"]),
            nombre=str(user_row.get("nombre") or user_row["username"]),
            rol=UserRole(str(user_row["rol"])),
            activo=bool(user_row.get("activo")),
            must_change_password=bool(user_row.get("must_change_password")),
        )
        permissions: dict[str, CompanyPermission] = {}
        for row in self._gestor.listar_permisos_usuario(user.id):
            permiso_raw = str(row.get("permiso") or CompanyPermission.NONE.value)
            try:
                permiso = CompanyPermission(permiso_raw)
            except Exception:
                permiso = CompanyPermission.NONE
            permissions[str(row.get("empresa_codigo") or "")] = permiso
        return UserSession(user=user, company_permissions=permissions)

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
        password: str | None = None,
        must_change_password: bool = False,
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

        existing = self._gestor.get_usuario_by_username(username)
        if existing and (user_id is None or int(existing["id"]) != int(user_id)):
            raise ValueError("Ya existe un usuario con ese nombre.")

        password_hash = None
        if password is not None:
            plain = str(password).strip()
            if not plain:
                raise ValueError("La contraseña no puede estar vacia.")
            password_hash = self._hasher.hash_password(plain)

        stored_id = self._gestor.upsert_usuario(
            {
                "id": user_id,
                "username": username,
                "nombre": nombre,
                "rol": user_role.value,
                "activo": 1 if activo else 0,
                "must_change_password": 1 if must_change_password else 0,
                "password_hash": password_hash,
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
        return stored_id

    def change_password(self, user_id: int, new_password: str, *, must_change_password: bool = False) -> None:
        plain = str(new_password or "").strip()
        if not plain:
            raise ValueError("La contraseña no puede estar vacia.")
        password_hash = self._hasher.hash_password(plain)
        self._gestor.actualizar_password_usuario(user_id, password_hash, must_change_password=must_change_password)
