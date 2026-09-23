from pathlib import Path

from services.auth_service import AuthService, PasswordHasher
from services.desktop_staff_auth_service import DesktopStaffAuthService


class _GestorUsuarios:
    def __init__(self):
        hasher = PasswordHasher()
        self.rows = {
            1: {
                "id": 1, "username": "admin", "nombre": "Administrador",
                "rol": "admin", "activo": 1,
                "password_hash": hasher.hash_password("emergencia-segura"),
                "must_change_password": 0, "email_corporativo": "",
                "entra_oid": "", "es_cuenta_emergencia": 1,
            },
            2: {
                "id": 2, "username": "ana", "nombre": "Ana",
                "rol": "empleado", "activo": 1,
                "password_hash": "!ENTRA_ONLY!", "must_change_password": 0,
                "email_corporativo": "ana@gestinem.es", "entra_oid": "",
                "es_cuenta_emergencia": 0,
            },
        }

    def get_usuario_by_username(self, username):
        return next((row for row in self.rows.values() if row["username"] == username), None)

    def get_usuario_by_entra_oid(self, entra_oid):
        return next((row for row in self.rows.values() if row["entra_oid"] == entra_oid), None)

    def get_usuario_by_email_corporativo(self, email):
        value = email.lower()
        return next((row for row in self.rows.values()
                     if row["email_corporativo"].lower() == value), None)

    def vincular_usuario_entra(self, user_id, entra_oid, email):
        self.rows[user_id]["entra_oid"] = entra_oid
        self.rows[user_id]["email_corporativo"] = email

    def get_usuario(self, user_id):
        return self.rows.get(user_id)

    def listar_permisos_usuario(self, _user_id):
        return []

    def listar_permisos_globales_usuario(self, _user_id):
        return []


def test_solo_admin_emergencia_puede_usar_password_local():
    service = AuthService(_GestorUsuarios())
    assert service.authenticate("admin", "emergencia-segura").ok
    employee = service.authenticate("ana", "cualquier-password")
    assert not employee.ok
    assert employee.code == "microsoft_required"


def test_entra_vincula_oid_y_conserva_staff_id_del_backend():
    gestor = _GestorUsuarios()
    service = AuthService(gestor)
    result = service.authenticate_entra(
        email="ANA@GESTINEM.ES",
        entra_oid="oid-ana",
        messaging_staff_id="staff-uuid-ana",
    )
    assert result.ok
    assert gestor.rows[2]["entra_oid"] == "oid-ana"
    assert result.session.user.messaging_staff_id == "staff-uuid-ana"


def test_login_principal_expone_acceso_microsoft():
    repo = Path(__file__).resolve().parents[1]
    login_source = (repo / "views" / "ui_auth.py").read_text(encoding="utf-8")
    main_source = (repo / "main.py").read_text(encoding="utf-8")

    assert 'text="Continuar con Microsoft"' in login_source
    assert "on_microsoft_login=_try_microsoft_login" in main_source
    assert "from services.desktop_staff_auth_service import DesktopStaffAuthService" in main_source


def test_servicio_desktop_microsoft_admite_backend_configurado():
    service = DesktopStaffAuthService(
        {"integrations_api_url": "https://api.gestinem.es"}
    )

    assert service.configured
    assert service.base_url == "https://api.gestinem.es"
