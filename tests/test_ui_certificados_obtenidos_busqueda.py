from views.ui_certificados_obtenidos import _label_cliente, _normalizar_busqueda


def test_label_cliente_prioriza_nombre_y_permite_identificarlo():
    empresa = {"codigo": "E00006", "nombre": "Dominguez Barrero", "cif": "72044071K"}

    assert _label_cliente(empresa) == "Dominguez Barrero - 72044071K - E00006"


def test_busqueda_ignora_mayusculas_y_acentos():
    label = "Álvarez Gestión - B12345678 - E00001"

    assert "alvarez" in _normalizar_busqueda(label)
    assert "b12345678" in _normalizar_busqueda(label)
