from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    EMPLEADO = "empleado"
    CLIENTE = "cliente"


class CompanyPermission(str, Enum):
    NONE = "ninguno"
    READ = "lectura"
    WRITE = "escritura"


@dataclass(slots=True)
class UserRecord:
    id: int
    username: str
    nombre: str
    rol: UserRole
    activo: bool
    must_change_password: bool = False


@dataclass(slots=True)
class UserSession:
    user: UserRecord
    company_permissions: dict[str, CompanyPermission] = field(default_factory=dict)

    @property
    def role(self) -> UserRole:
        return self.user.rol

    def is_admin(self) -> bool:
        return self.user.rol == UserRole.ADMIN

    def allowed_company_codes(self) -> set[str]:
        if self.is_admin():
            return set()
        return {
            code
            for code, permission in self.company_permissions.items()
            if permission in (CompanyPermission.READ, CompanyPermission.WRITE)
        }

    def permission_for_company(self, codigo_empresa: str) -> CompanyPermission:
        if self.is_admin():
            return CompanyPermission.WRITE
        return self.company_permissions.get(str(codigo_empresa), CompanyPermission.NONE)

    def can_read_company(self, codigo_empresa: str) -> bool:
        return self.permission_for_company(codigo_empresa) in (
            CompanyPermission.READ,
            CompanyPermission.WRITE,
        )

    def can_write_company(self, codigo_empresa: str) -> bool:
        return self.permission_for_company(codigo_empresa) == CompanyPermission.WRITE
