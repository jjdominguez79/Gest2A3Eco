from services.empresa_service import EmpresaService


class Gestor:
    def listar_empresas(self):
        return [
            {"codigo": "E00002", "ejercicio": 2025, "nombre": "Beta", "activo": 1},
            {"codigo": "E00001", "ejercicio": 2024, "nombre": "Alfa", "activo": 1},
            {"codigo": "E00001", "ejercicio": 2026, "nombre": "Alfa", "activo": 1},
            {"codigo": "E00003", "ejercicio": 2026, "nombre": "Gamma", "activo": 1},
        ]


def test_navegacion_empresas_ordenada_y_usa_ultimo_ejercicio():
    service = EmpresaService(Gestor())

    navigation = service.get_company_navigation("E00002")

    assert navigation["position"] == 2
    assert navigation["total"] == 3
    assert navigation["previous"]["codigo"] == "E00001"
    assert navigation["previous"]["ejercicio"] == 2026
    assert navigation["next"]["codigo"] == "E00003"


def test_navegacion_desactiva_flecha_en_extremos():
    service = EmpresaService(Gestor())

    first = service.get_company_navigation("E00001")
    last = service.get_company_navigation("E00003")

    assert first["previous"] is None
    assert last["next"] is None
