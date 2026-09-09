from controllers.ui_control_facturas_global_controller import (
    ControlFacturasGlobalController,
)
from services.empresa_service import EmpresaService
from views.ui_control_facturas_global import UIControlFacturasGlobal


class _EmpresaService:
    def listar_empresas_panel(self):
        return [
            {"codigo": "E00001", "nombre": "Alfa", "responsable": "Ana"},
            {"codigo": "E00002", "nombre": "Beta", "responsable": ""},
        ]


class _Gestor:
    def listar_control_facturas_global(self, codigos):
        assert codigos == ["E00001", "E00002"]
        return [
            {
                "codigo_empresa": "E00001",
                "ejercicio": 2026,
                "tipo": "emitida",
                "generada": 0,
                "estado_contable": "",
                "lineas_json": "[]",
            },
            {
                "codigo_empresa": "E00002",
                "ejercicio": 2025,
                "tipo": "recibida",
                "generada": 1,
                "estado_contable": "contabilizada",
                "total": 125,
            },
        ]


class _GestorEmpresas:
    security = None

    def listar_empresas(self):
        return [
            {
                "codigo": "E00001",
                "ejercicio": 2025,
                "nombre": "Alfa",
                "responsable": "Responsable anterior",
                "activo": True,
            },
            {
                "codigo": "E00001",
                "ejercicio": 2026,
                "nombre": "Alfa",
                "responsable": "Ana",
                "activo": True,
            },
        ]


def test_panel_empresas_expone_el_responsable_del_ultimo_ejercicio():
    empresas = EmpresaService(_GestorEmpresas()).listar_empresas_panel()

    assert empresas[0]["responsable"] == "Ana"


def test_control_incorpora_responsable_de_la_empresa():
    rows, nombres = ControlFacturasGlobalController(
        _Gestor(), _EmpresaService(),
    ).cargar()

    assert nombres == {"E00001": "Alfa", "E00002": "Beta"}
    assert rows[0]["responsable"] == "Ana"
    assert rows[1]["responsable"] == ""


def _row(codigo, ejercicio, responsable, tipo="emitida", **extra):
    row = {
        "codigo_empresa": codigo,
        "empresa_nombre": codigo,
        "ejercicio": ejercicio,
        "responsable": responsable,
        "tipo": tipo,
        "generada": False,
        "estado_contable": "",
        "numero_asiento": "",
        "numero_factura": "A1",
        "tercero": "Cliente",
        "nif": "B123",
        "descripcion": "Servicio",
    }
    row.update(extra)
    return row


def test_filtra_por_responsable_y_ejercicio_a_la_vez():
    rows = [
        _row("E00001", 2026, "Ana"),
        _row("E00001", 2025, "Ana"),
        _row("E00002", 2026, "Luis"),
    ]

    result = UIControlFacturasGlobal.filter_rows(
        rows,
        responsable="Ana",
        ejercicio="2026",
    )

    assert result == [rows[0]]


def test_permite_filtrar_empresas_sin_responsable():
    rows = [
        _row("E00001", 2026, "Ana"),
        _row("E00002", 2026, ""),
    ]

    result = UIControlFacturasGlobal.filter_rows(
        rows,
        responsable="Sin asignar",
    )

    assert result == [rows[1]]


def test_busqueda_incluye_el_nombre_del_responsable():
    rows = [_row("E00001", 2026, "Analía Pérez")]

    result = UIControlFacturasGlobal.filter_rows(rows, text="analia")

    assert result == rows


def test_formatea_importes_con_convencion_espanola():
    assert UIControlFacturasGlobal._format_amount(1234567.8) == "1.234.567,80"
