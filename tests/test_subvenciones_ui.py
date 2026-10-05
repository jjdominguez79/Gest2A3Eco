"""Pruebas de la operativa masiva del panel de subvenciones."""

from views.ui_subvenciones_global import filtrar_organizaciones


ORGANIZACIONES = [
    {
        "codigo_empresa": "E00000",
        "empresa": "Empresa de pruebas",
        "activa": True,
        "usuarios_activos": 1,
        "territorio": {
            "municipio": "Santander",
            "provincia_nombre": "Cantabria",
            "ccaa_nombre": "Cantabria",
        },
    },
    {
        "codigo_empresa": "E00001",
        "empresa": "Cliente sin acceso",
        "activa": False,
        "usuarios_activos": 0,
        "territorio": {"municipio": "Camargo"},
    },
]


def test_filtra_empresas_por_texto_codigo_y_territorio():
    assert [x["codigo_empresa"] for x in filtrar_organizaciones(
        ORGANIZACIONES, "pruebas",
    )] == ["E00000"]
    assert [x["codigo_empresa"] for x in filtrar_organizaciones(
        ORGANIZACIONES, "camargo",
    )] == ["E00001"]


def test_filtra_empresas_por_estado_y_usuarios():
    assert [x["codigo_empresa"] for x in filtrar_organizaciones(
        ORGANIZACIONES, status="Activadas",
    )] == ["E00000"]
    assert [x["codigo_empresa"] for x in filtrar_organizaciones(
        ORGANIZACIONES, status="Sin usuarios",
    )] == ["E00001"]
