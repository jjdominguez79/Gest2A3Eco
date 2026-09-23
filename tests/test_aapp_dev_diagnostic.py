from services.aapp.dev_playwright import _clasificar_estado, _url_sin_secretos


def test_diagnostico_dev_distingue_cliente_sin_alta():
    assert _clasificar_estado(
        "El titular no se encuentra dado de alta en la Direccion Electronica Vial",
        "https://sedeapl.dgt.gob.es:9443/WEB_NTRA_CONSULTA/error.faces",
        200,
    ) == "NO_ALTA"


def test_diagnostico_dev_reconoce_acceso_autenticado():
    assert _clasificar_estado(
        "Direccion Electronica Vial - Listado de notificaciones",
        "https://sedeapl.dgt.gob.es:9443/WEB_NTRA_CONSULTA/listado.faces",
        200,
    ) == "AUTENTICADO"


def test_diagnostico_dev_no_conserva_parametros_de_sesion():
    assert _url_sin_secretos(
        "https://sedeapl.dgt.gob.es:9443/WEB_NTRA_CONSULTA/listado.faces;jsessionid=abc?ticket=secret#x"
    ) == "https://sedeapl.dgt.gob.es:9443/WEB_NTRA_CONSULTA/listado.faces"
