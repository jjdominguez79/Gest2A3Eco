from views.ui_facturas_recibidas_ocr import (
    IVA_TIPOS_CATALOGO,
    RETENCION_TIPOS_CATALOGO,
    UIFacturasRecibidasOcr,
    _codigo_selector,
    _calcular_cuota_porcentaje,
    _filtrar_valores,
    _formatear_fecha_editor,
    _normalizar_confianza,
    _parse_fecha_editor,
    _resumen_fiscal,
    _totales_coherentes,
    _campos_aprendizaje,
    _zoom_para_ajustar,
)
from services.ocr_contabilidad_service import (
    modelo_retencion_para_clase,
    normalizar_clase_retencion,
)
from datetime import date
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


def test_campos_aprendizaje_cambian_segun_tipo_factura():
    recibida = _campos_aprendizaje("factura_recibida")
    emitida = _campos_aprendizaje("factura_emitida")
    assert recibida[:2] == ("ProveedorNif", "ProveedorNombre")
    assert emitida[:4] == (
        "EmisorNif", "EmisorNombre", "ClienteNif", "ClienteNombre",
    )
    assert "ProveedorNif" not in emitida
    assert {
        "FechaOperacion", "RetencionTotal", "Suplidos", "TipoIva", "BaseIva",
        "CuotaIva", "TipoRecargo", "CuotaRecargo", "BaseRetencion",
        "TipoRetencion", "ImporteRetencion", "ClaseRetencion",
    }.issubset(recibida)


def test_texto_marcado_rellena_cabecera_iva_y_retencion():
    class Variable:
        def __init__(self):
            self.valor = ""

        def set(self, valor):
            self.valor = valor

    vista = SimpleNamespace(
        _entries={"fecha_operacion": Variable()},
        _iva_vars={"base": Variable()},
        _ret_vars={"importe_retencion": Variable()},
    )

    UIFacturasRecibidasOcr._aplicar_texto_marca(
        vista, "FechaOperacion", "21/10/2026",
    )
    UIFacturasRecibidasOcr._aplicar_texto_marca(vista, "BaseIva", "100,00")
    UIFacturasRecibidasOcr._aplicar_texto_marca(
        vista, "ImporteRetencion", "15,00",
    )

    assert vista._entries["fecha_operacion"].valor == "21/10/2026"
    assert vista._iva_vars["base"].valor == "100,00"
    assert vista._ret_vars["importe_retencion"].valor == "15,00"


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


def test_filtro_selectores_admite_acentos_mayusculas_y_varias_palabras():
    valores = (
        "40000008 - ELISA DE GREGORIO GARCIA",
        "41000002 - Proveedor genérico",
    )

    assert _filtrar_valores(valores, "elisa garcía") == (valores[0],)
    assert _filtrar_valores(valores, "410 generico") == (valores[1],)
    assert _filtrar_valores(valores, "") == valores


def test_desplegable_filtrable_muestra_todo_si_hay_una_opcion_seleccionada():
    class ComboboxPrueba:
        def __init__(self):
            self.texto = "ProveedorNif"
            self.configuracion = {}
            self.eventos = {}

        def get(self):
            return self.texto

        def set(self, valor):
            self.texto = valor

        def configure(self, **kwargs):
            self.configuracion.update(kwargs)

        def bind(self, evento, callback, **_kwargs):
            self.eventos[evento] = callback

    campos = ("ProveedorNif", "ProveedorNombre", "NumeroFactura", "TipoIva")
    widget = ComboboxPrueba()

    UIFacturasRecibidasOcr._hacer_combobox_filtrable(
        SimpleNamespace(), widget, lambda: campos,
    )
    widget.configuracion["postcommand"]()

    assert widget.configuracion["values"] == campos

    widget.texto = "iva"
    widget.eventos["<KeyRelease>"]()
    assert widget.configuracion["values"] == ("TipoIva",)


def test_codigo_selector_acepta_etiqueta_o_codigo_escrito():
    opciones = {"40000008 - ELISA DE GREGORIO GARCIA": "40000008"}

    assert _codigo_selector(next(iter(opciones)), opciones) == "40000008"
    assert _codigo_selector("40000008", opciones) == "40000008"
    assert _codigo_selector("4000", opciones) == ""


def test_cuota_iva_se_calcula_con_redondeo_comercial_y_sigue_siendo_editable():
    assert _calcular_cuota_porcentaje("100,00", "21") == 21.0
    assert _calcular_cuota_porcentaje("0.50", "5") == 0.03


def test_fecha_factura_rellena_fechas_contable_y_operacion():
    class Variable:
        def __init__(self, valor=""):
            self.valor = valor

        def get(self):
            return self.valor

        def set(self, valor):
            self.valor = valor

    vista = SimpleNamespace(
        _cargando_editor=False,
        _formato_fecha_var=Variable("DD/MM/AAAA"),
        _entries={
            "fecha_factura": Variable("21/10/2026"),
            "fecha_contable": Variable(""),
            "fecha_operacion": Variable(""),
        },
    )

    UIFacturasRecibidasOcr._sincronizar_fechas_factura(vista)

    assert vista._entries["fecha_contable"].get() == "21/10/2026"
    assert vista._entries["fecha_operacion"].get() == "21/10/2026"


def test_retencion_usa_catalogo_cerrado_y_calcula_importe_automaticamente():
    class Variable:
        def __init__(self, valor=""):
            self.valor = valor

        def get(self):
            return self.valor

        def set(self, valor):
            self.valor = valor

    assert RETENCION_TIPOS_CATALOGO == (1.0, 7.0, 15.0, 19.0)
    vista = SimpleNamespace(
        _actualizando_retencion=False,
        _cargando_editor=False,
        _ret_vars={
            "base_retencion": Variable("100,50"),
            "tipo_retencion": Variable("15"),
            "importe_retencion": Variable(""),
        },
    )

    UIFacturasRecibidasOcr._recalcular_importe_retencion_editor(vista)

    assert vista._ret_vars["importe_retencion"].get() == "15.08"


def test_selector_fecha_admite_los_dos_formatos_de_la_revision():
    esperada = date(2026, 10, 21)
    assert _parse_fecha_editor("21/10/2026") == esperada
    assert _parse_fecha_editor("2026-10-21") == esperada
    assert _formatear_fecha_editor(esperada, "DD/MM/AAAA") == "21/10/2026"
    assert _formatear_fecha_editor(esperada, "AAAA-MM-DD") == "2026-10-21"


def test_clase_retencion_determina_el_modelo_fiscal():
    assert normalizar_clase_retencion("PROFESIONAL (Modelo 111)") == "PROFESIONAL"
    assert modelo_retencion_para_clase("PROFESIONAL") == "111"
    assert modelo_retencion_para_clase("ARRENDAMIENTO") == "115"
    assert modelo_retencion_para_clase("CAPITAL") == "123"


def test_cambiar_subcuenta_gasto_reemplaza_la_antigua_en_las_lineas():
    class Variable:
        def __init__(self):
            self.valor = "62100001"

        def get(self):
            return self.valor

        def set(self, valor):
            self.valor = valor

    class Tabla:
        def __init__(self):
            self.filas = {"iva_21": ["21", "100", "21", "61000001", "0", "0"]}

        def item(self, item, opcion=None, **kwargs):
            if "values" in kwargs:
                self.filas[item] = list(kwargs["values"])
            return self.filas[item] if opcion == "values" else {"values": self.filas[item]}

    variable = Variable()
    vista = SimpleNamespace(
        _tv_iva=Tabla(),
        _iva_catalog_items=["iva_21"],
        _iva_vars={"cuenta_gasto": variable},
        _subcuenta_gasto_seleccionada=lambda: "62100001",
    )

    UIFacturasRecibidasOcr._al_cambiar_subcuenta_gasto(vista)

    assert vista._tv_iva.filas["iva_21"][3] == "62100001"
    assert variable.get() == "62100001"
