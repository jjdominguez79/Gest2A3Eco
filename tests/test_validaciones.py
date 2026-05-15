from utils.validaciones import normalizar_nif_cif, validar_nif_cif_nie


def test_normalizar_nif_cif_elimina_separadores_y_mayusculiza():
    assert normalizar_nif_cif(" 12.345.678-z ") == "12345678Z"
    assert normalizar_nif_cif("b-12345678") == "B12345678"


def test_validar_dni_nie_y_cif_validos():
    assert validar_nif_cif_nie("12345678Z") is True
    assert validar_nif_cif_nie("X2482300W") is True
    assert validar_nif_cif_nie("A58818501") is True


def test_validar_nif_cif_nie_rechaza_valores_invalidos():
    assert validar_nif_cif_nie("") is False
    assert validar_nif_cif_nie("12345678A") is False
    assert validar_nif_cif_nie("A58818502") is False

