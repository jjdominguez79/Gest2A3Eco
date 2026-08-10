from views.ui_firmas_global import UIFirmasGlobal


def test_resumen_entrega_distingue_enviado_y_espera_por_orden():
    resumen = UIFirmasGlobal._resumen_entrega([
        {"email": "segundo@example.com", "order": 2, "emailed": False},
        {"email": "primero@example.com", "order": 1, "emailed": True},
    ])

    assert "1. primero@example.com: correo enviado" in resumen
    assert "2. segundo@example.com: en espera del firmante anterior" in resumen


def test_firmante_desde_empresa_precarga_el_primer_email_de_la_ficha():
    firmante = UIFirmasGlobal._firmante_desde_empresa({
        "codigo": "E01071",
        "nombre": "Dometea",
        "email": "firma@dometea.es, administracion@dometea.es",
        "telefono": "600123123",
    })

    assert firmante == {
        "nombre": "Dometea",
        "email": "firma@dometea.es",
        "telefono": "600123123",
    }


def test_firmante_desde_empresa_no_precarga_sin_cliente():
    assert UIFirmasGlobal._firmante_desde_empresa({"codigo": ""}) is None


def test_cliente_visible_incluye_codigo_y_nombre():
    assert UIFirmasGlobal._cliente_visible("E01071", "Dometea") == "E01071 - Dometea"


def test_cliente_visible_conserva_codigo_si_no_hay_ficha():
    assert UIFirmasGlobal._cliente_visible("E00304") == "E00304"
    assert UIFirmasGlobal._cliente_visible("__GLOBAL__") == "Sin cliente"
