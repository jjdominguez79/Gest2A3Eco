from services.empresa_service import EmpresaService
from models.gestor_base import GestorBase


class _Gestor:
    def __init__(self):
        self.calls = []

    def actualizar_estado_empresas(self, codigos, activo):
        self.calls.append((codigos, activo))
        return len(codigos)


def test_empresa_service_actualiza_estado_masivo():
    gestor = _Gestor()
    service = EmpresaService(gestor)

    result = service.actualizar_estado_empresas(["E00001", "E00006"], False)

    assert result == 2
    assert gestor.calls == [(["E00001", "E00006"], False)]


class _Cursor:
    rowcount = 3


class _Connection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return _Cursor()

    def commit(self):
        self.commits += 1


def test_gestor_actualiza_todos_los_ejercicios_una_vez_por_empresa():
    connection = _Connection()
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = connection

    result = gestor.actualizar_estado_empresas(
        ["e00001", "E00001", " E00006 "],
        False,
    )

    assert result == 2
    assert connection.executed == [
        ("UPDATE empresas SET activo=? WHERE codigo=?", (0, "E00001")),
        ("UPDATE empresas SET activo=? WHERE codigo=?", (0, "E00006")),
    ]
    assert connection.commits == 1


def test_gestor_aplica_solicitud_y_logo_a_todos_los_ejercicios():
    connection = _Connection()
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = connection

    result = gestor.aplicar_cambios_empresa_solicitados(
        " e00006 ",
        {
            "legal_name": " Empresa Demo SL ",
            "tax_id": " b-123 45678 ",
            "bank_accounts": [" ES12 1234 ", "", "ES98 7654"],
        },
        r"\\servidor\documentos\E00006\logotipo_empresa.png",
    )

    assert result == 1
    sql, params = connection.executed[0]
    assert sql == (
        "UPDATE empresas SET nombre=?, cif=?, cuentas_bancarias=?, logo_path=? "
        "WHERE codigo=?"
    )
    assert params == (
        "Empresa Demo SL",
        "B12345678",
        "ES12 1234\nES98 7654",
        r"\\servidor\documentos\E00006\logotipo_empresa.png",
        "E00006",
    )
    assert connection.commits == 1
