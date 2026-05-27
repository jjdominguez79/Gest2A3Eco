from controllers.terceros_global_controller import TercerosGlobalController


class _FakeGestor:
    def listar_terceros(self):
        return []

    def listar_empresas(self):
        return [
            {"codigo": "E00001", "nombre": "Empresa Uno", "ejercicio": 2025},
            {"codigo": "E00001", "nombre": "Empresa Uno", "ejercicio": 2026},
            {"codigo": "E00002", "nombre": "Empresa Dos", "ejercicio": 2026},
        ]


class _FakeView:
    def __init__(self):
        self.terceros = None
        self.empresas = None
        self.empresas_asignadas = None

    def set_terceros(self, rows):
        self.terceros = rows

    def set_empresas(self, rows):
        self.empresas = rows

    def set_empresas_asignadas(self, rows):
        self.empresas_asignadas = rows


def test_refresh_deduplica_empresas_por_codigo():
    view = _FakeView()
    controller = TercerosGlobalController(_FakeGestor(), view)

    controller.refresh()

    assert view.empresas == [
        {"codigo": "E00001", "nombre": "Empresa Uno"},
        {"codigo": "E00002", "nombre": "Empresa Dos"},
    ]
