import pytest

from models.auth import CompanyPermission, UserRecord, UserRole, UserSession
from services.auth_service import AuthorizationService
from services.empresa_service import EmpresaService
from services.secured_gestor import SecuredGestor


class _BaseEtiquetas:
    def __init__(self):
        self.actualizaciones = []

    def listar_etiquetas_clientes(self, incluir_inactivas=False):
        return [{"id": "tag-1", "nombre": "Cuota pendiente", "activo": True}]

    def listar_empresas(self):
        return [{
            "codigo": "E00001", "ejercicio": 2026,
            "nombre": "Cliente", "activo": True,
        }]

    def listar_asignaciones_etiquetas_clientes(self):
        return [
            {"codigo_empresa": "E00001", "etiqueta_id": "tag-1"},
            {"codigo_empresa": "E00002", "etiqueta_id": "tag-1"},
        ]

    def listar_etiquetas_empresa(self, codigo_empresa):
        return [{"codigo_empresa": codigo_empresa, "etiqueta_id": "tag-1"}]

    def guardar_etiqueta_cliente(self, datos, usuario=""):
        return "tag-1"

    def desactivar_etiqueta_cliente(self, etiqueta_id, usuario=""):
        return None

    def actualizar_etiquetas_empresas(
        self, codigos_empresa, etiqueta_ids, modo="reemplazar", usuario="",
    ):
        self.actualizaciones.append((codigos_empresa, etiqueta_ids, modo, usuario))
        return len(codigos_empresa)


def _gestor(role, permissions=None):
    session = UserSession(
        user=UserRecord(
            id=1, username="test", nombre="Prueba", rol=role, activo=True,
        ),
        company_permissions=permissions or {},
    )
    base = _BaseEtiquetas()
    return SecuredGestor(base, AuthorizationService(session)), base


def test_empleado_solo_lee_etiquetas_de_empresas_autorizadas():
    gestor, _ = _gestor(
        UserRole.EMPLEADO,
        {"E00001": CompanyPermission.READ},
    )

    assert gestor.listar_etiquetas_clientes()[0]["id"] == "tag-1"
    assert gestor.listar_asignaciones_etiquetas_clientes() == [{
        "codigo_empresa": "E00001", "etiqueta_id": "tag-1",
    }]
    with pytest.raises(PermissionError):
        gestor.guardar_etiqueta_cliente({"nombre": "Nueva"})
    with pytest.raises(PermissionError):
        gestor.actualizar_etiquetas_empresas(["E00001"], ["tag-1"])


def test_cliente_no_puede_leer_etiquetas_internas():
    gestor, _ = _gestor(
        UserRole.CLIENTE,
        {"E00001": CompanyPermission.READ},
    )

    with pytest.raises(PermissionError):
        gestor.listar_etiquetas_clientes()
    with pytest.raises(PermissionError):
        gestor.listar_asignaciones_etiquetas_clientes()
    with pytest.raises(PermissionError):
        gestor.listar_etiquetas_empresa("E00001")
    assert EmpresaService(gestor).listar_empresas_panel()[0]["etiquetas"] == []


def test_administrador_puede_asignar_varias_etiquetas_a_varias_empresas():
    gestor, base = _gestor(UserRole.ADMIN)

    assert gestor.actualizar_etiquetas_empresas(
        ["E00001", "E00002"], ["tag-1", "tag-2"], "agregar", "Admin",
    ) == 2
    assert base.actualizaciones == [(
        ["E00001", "E00002"], ["tag-1", "tag-2"], "agregar", "Admin",
    )]
