from controllers.ui_facturas_emitidas_controller import FacturasEmitidasController
from controllers import ui_facturas_emitidas_controller as module


def test_numero_factura_contable_concatena_serie_y_numero():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._numero_factura_contable({"serie": "A", "numero": "123"}) == "A123"


def test_numero_factura_contable_tolera_campos_vacios():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._numero_factura_contable({"serie": "", "numero": "123"}) == "123"
    assert controller._numero_factura_contable({"serie": "A", "numero": ""}) == "A"


def test_observacion_rectificativa_referencia_factura_y_fecha_originales():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._observacion_rectificativa({
        "serie": "A", "numero": "000123", "fecha_expedicion": "2026-05-08",
    }) == "Rectifica la factura A000123 con fecha 08/05/2026."


def test_totales_separan_suplidos_de_base_imponible():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    factura = {
        "lineas": [
            {"base": 100, "cuota_iva": 21, "cuota_re": 0, "tipo": "honorario"},
            {"base": 55.70, "cuota_iva": 0, "cuota_re": 0, "tipo": "suplido"},
        ],
        "retencion_aplica": False,
    }

    totales = controller._totales_factura(factura)

    assert totales == {
        "base": 100.0,
        "iva": 21.0,
        "re": 0.0,
        "suplidos": 55.7,
        "ret": 0.0,
        "total": 176.7,
    }


def test_resuelve_facturas_y_albaranes_en_subcarpetas_distintas(monkeypatch, tmp_path):
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    monkeypatch.setattr(module, "get_word_templates_subdir", lambda tipo: tmp_path / tipo)

    factura = controller._docx_template_path(default_filename="factura_emitida_template.docx")
    albaran = controller._docx_template_path(default_filename="albaran_template.docx")

    assert factura == str(tmp_path / "facturas" / "factura_emitida_template.docx")
    assert albaran == str(tmp_path / "albaranes" / "albaran_template.docx")
