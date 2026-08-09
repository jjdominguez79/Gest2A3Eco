from views.ui_firmas_global import UIFirmasGlobal


def test_resumen_entrega_distingue_enviado_y_espera_por_orden():
    resumen = UIFirmasGlobal._resumen_entrega([
        {"email": "segundo@example.com", "order": 2, "emailed": False},
        {"email": "primero@example.com", "order": 1, "emailed": True},
    ])

    assert "1. primero@example.com: correo enviado" in resumen
    assert "2. segundo@example.com: en espera del firmante anterior" in resumen
