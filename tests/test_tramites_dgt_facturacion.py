from datetime import date

import pytest

from models.gestor_sqlite import GestorSQLite
from services.tramites_dgt_facturacion_service import (
    CUENTA_SUPLIDOS,
    EMPRESA_DGT,
    SERIE_DGT,
    TramitesDgtFacturacionService,
)
import procesos.facturas_emitidas as exportador_emitidas


@pytest.fixture()
def gestor(tmp_path):
    db = GestorSQLite(tmp_path / "test.db")
    db.upsert_empresa({
        "codigo": EMPRESA_DGT,
        "ejercicio": date.today().year,
        "nombre": "Empresa emisora",
        "cif": "72044071K",
        "digitos_plan": 8,
        "serie_emitidas": "A",
        "siguiente_num_emitidas": 1,
        "serie_emitidas_rect": "R",
        "siguiente_num_emitidas_rect": 1,
    })
    yield db
    db.conn.close()


def _expediente():
    return {
        "id": "exp-1",
        "referencia": "DGT-2026-0001",
        "vehiculo_matricula": "1234ABC",
        "comprador_payload": {
            "nombre": "Cliente Comprador",
            "nif": "12345678Z",
            "email": "cliente@example.com",
            "direccion": "Calle Uno 1",
            "codigo_postal": "06001",
            "poblacion": "Badajoz",
            "provincia": "Badajoz",
        },
        "vendedor_payload": {"nombre": "Cliente Vendedor", "nif": "B12345678"},
    }


def test_crea_borrador_tr_con_honorarios_y_suplidos(gestor):
    factura = TramitesDgtFacturacionService(gestor).crear_borrador(
        _expediente(),
        destinatario="comprador",
        honorarios="100,00",
        tasa_dgt="55,70",
        impuesto_620="40",
    )

    assert factura["codigo_empresa"] == EMPRESA_DGT
    assert factura["serie"] == SERIE_DGT
    assert factura["borrador"] == 1
    assert factura["numero"] == ""
    assert factura["nombre"] == "Cliente Comprador"
    assert factura["lineas"][0]["base"] == 100.0
    assert factura["lineas"][0]["pct_iva"] == 21.0
    assert factura["lineas"][0]["cuota_iva"] == 21.0
    suplidos = factura["lineas"][1:]
    assert [linea["base"] for linea in suplidos] == [55.7, 40.0]
    assert all(linea["tipo"] == "suplido" for linea in suplidos)
    assert all(linea["cuenta_ingreso"] == CUENTA_SUPLIDOS for linea in suplidos)
    assert all(linea["cuota_iva"] == 0 for linea in suplidos)

    guardadas = gestor.listar_facturas_emitidas(EMPRESA_DGT, date.today().year)
    assert len(guardadas) == 1
    assert gestor.get_dgt_factura("exp-1")["factura_id"] == factura["id"]
    assert any(s["nombre"] == SERIE_DGT for s in gestor.listar_series_emitidas(EMPRESA_DGT, date.today().year))


def test_no_duplica_factura_ni_reinicia_contador_serie(gestor):
    servicio = TramitesDgtFacturacionService(gestor)
    servicio.crear_borrador(_expediente(), destinatario="vendedor", honorarios=80)
    gestor.incrementar_serie_num(EMPRESA_DGT, date.today().year, SERIE_DGT)

    with pytest.raises(ValueError, match="ya tiene una factura"):
        servicio.crear_borrador(_expediente(), destinatario="comprador", honorarios=90)

    assert gestor.get_siguiente_serie_num(EMPRESA_DGT, date.today().year, SERIE_DGT) == 2


def test_exportacion_separa_honorarios_y_suplidos(monkeypatch):
    detalles = []
    monkeypatch.setattr(exportador_emitidas, "render_emitidas_cabecera_256", lambda **_kwargs: "CAB")
    monkeypatch.setattr(
        exportador_emitidas,
        "render_emitidas_detalle_256",
        lambda **kwargs: detalles.append(kwargs) or "DET",
    )
    rows = [
        {
            "Serie": "TR", "Numero Factura": "TR000001", "Fecha Asiento": "2026-01-15",
            "NIF Cliente Proveedor": "12345678Z", "Nombre Cliente Proveedor": "Cliente",
            "Cuenta Cliente Proveedor": "43000001", "Cuenta Compras Ventas": "70000000",
            "Base": 100, "Porcentaje IVA": 21, "Cuota IVA": 21,
        },
        {
            "Serie": "TR", "Numero Factura": "TR000001", "Fecha Asiento": "2026-01-15",
            "NIF Cliente Proveedor": "12345678Z", "Nombre Cliente Proveedor": "Cliente",
            "Cuenta Cliente Proveedor": "43000001", "Cuenta Compras Ventas": CUENTA_SUPLIDOS,
            "Base": 55.70, "Porcentaje IVA": 0, "Cuota IVA": 0, "Es Suplido": True,
        },
    ]

    exportador_emitidas.generar_emitidas(rows, {}, EMPRESA_DGT, 8)

    assert len(detalles) == 2
    honorarios = next(d for d in detalles if d["cuenta_base_iva"] == "70000000")
    suplido = next(d for d in detalles if d["cuenta_base_iva"] == CUENTA_SUPLIDOS)
    assert honorarios["operacion_sujeta_iva"] is True
    assert suplido["operacion_sujeta_iva"] is False
    assert suplido["base"] == 55.7
