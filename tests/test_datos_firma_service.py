from services.firma.datos_firma_service import listar_terceros_para_firma


class _Gestor:
    def listar_terceros_por_empresa(self, codigo, ejercicio):
        assert codigo == "E00001"
        assert ejercicio == 2026
        return [
            {"id": "2", "nombre": "Vinculado", "email": "v@example.com"},
            {"id": "1", "nombre": "Primero actualizado", "email": "nuevo@example.com"},
        ]

    def listar_terceros(self):
        return [
            {"id": "1", "nombre": "Primero antiguo", "email": "viejo@example.com"},
            {"id": "3", "nombre": "Global", "email": ""},
            {"id": "4", "nombre": "Inactivo", "activo": 0},
        ]


def test_lista_vinculados_primero_y_completa_con_maestro_global():
    resultado = listar_terceros_para_firma(_Gestor(), "E00001", 2026)

    assert [item["id"] for item in resultado] == ["2", "1", "3"]
    assert resultado[1]["email"] == "nuevo@example.com"
    assert resultado[2]["email"] == ""


def test_sin_cliente_muestra_el_maestro_global():
    resultado = listar_terceros_para_firma(_Gestor())

    assert [item["id"] for item in resultado] == ["1", "3"]
