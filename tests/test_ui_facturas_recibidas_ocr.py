from views.ui_facturas_recibidas_ocr import (
    IVA_TIPOS_CATALOGO,
    UIFacturasRecibidasOcr,
    _normalizar_confianza,
    _resumen_fiscal,
    _totales_coherentes,
    _campos_aprendizaje,
    _zoom_para_ajustar,
)
from types import SimpleNamespace


def test_normalizar_confianza_acepta_valores_de_azure_y_porcentaje():
    assert _normalizar_confianza("0.87") == 0.87
    assert _normalizar_confianza("87%") == 0.87
    assert _normalizar_confianza("87,5") == 0.875
    assert _normalizar_confianza("invalido") == 0.0


def test_catalogo_iva_y_resumen_fiscal_incluyen_suplidos_y_retenciones():
    assert IVA_TIPOS_CATALOGO == (21.0, 10.0, 7.5, 5.0, 4.0, 2.0, 0.0)
    resumen = _resumen_fiscal(
        [{"base": 100, "cuota_iva": 21, "cuota_recargo": 0}],
        [{"importe_retencion": 15}],
        suplidos=12,
    )
    assert resumen == {
        "base": 100.0,
        "iva": 21.0,
        "recargo": 0.0,
        "retencion": 15.0,
        "suplidos": 12.0,
        "total_esperado": 118.0,
    }
    assert _totales_coherentes(118.04, resumen)
    assert not _totales_coherentes(118.06, resumen)


def test_drag_enter_y_leave_aceptan_la_accion_de_windows():
    class Zona:
        def configure(self, **_kwargs):
            pass

    vista = SimpleNamespace(zona=Zona())
    vista._zona_arrastre = vista.zona
    vista._restaurar_texto_arrastre = lambda: None
    evento = SimpleNamespace(action="copy")

    assert UIFacturasRecibidasOcr._on_dnd_enter(vista, evento) == "copy"
    assert UIFacturasRecibidasOcr._on_dnd_leave(vista, evento) == "copy"


def test_campos_aprendizaje_cambian_segun_tipo_factura():
    recibida = _campos_aprendizaje("factura_recibida")
    emitida = _campos_aprendizaje("factura_emitida")
    assert recibida[:2] == ("ProveedorNif", "ProveedorNombre")
    assert emitida[:4] == (
        "EmisorNif", "EmisorNombre", "ClienteNif", "ClienteNombre",
    )
    assert "ProveedorNif" not in emitida


def test_cabecera_listado_muestra_cliente_en_facturas_emitidas():
    class Tabla:
        def __init__(self):
            self.titulo = ""

        def heading(self, _columna, *, text):
            self.titulo = text

    tabla = Tabla()
    vista = SimpleNamespace(_tvs={"pendiente_revision": tabla})
    UIFacturasRecibidasOcr._actualizar_cabeceras_listado(
        vista, "factura_emitida",
    )
    assert tabla.titulo == "Cliente"


def test_zoom_para_ajustar_muestra_pagina_completa():
    zoom = _zoom_para_ajustar(1200, 1800, 600, 900)
    assert 0.49 < zoom < 0.5
    assert 1200 * zoom <= 590
    assert 1800 * zoom <= 890


def test_zoom_para_ajustar_no_amplia_mas_del_limite():
    assert _zoom_para_ajustar(100, 100, 2000, 2000) == 3.0
