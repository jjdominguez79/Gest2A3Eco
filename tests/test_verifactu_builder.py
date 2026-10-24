"""Tests del constructor de XML Veri*FACTU (contrato estructural, no XSD).

No certifican validez contra el XSD oficial completo (no descargado en esta
sesion, ver services/verifactu/README.md). Verifican: XML bien formado,
UTF-8, jerarquia de elementos tal como aparece en los ejemplos reales del
documento 1, y que la huella incluida coincide con services/verifactu/hash.py.
"""

from decimal import Decimal
from xml.etree import ElementTree as ET

from services.verifactu.builder import (
    NS_SUM1,
    build_registro_alta,
    build_registro_anulacion,
)
from services.verifactu.hash import compute_alta_hash, compute_anulacion_hash
from services.verifactu.models import (
    AltaRegistroInput,
    AnulacionRegistroInput,
    DesgloseIva,
    SistemaInformatico,
)

SISTEMA = SistemaInformatico(
    nombre_razon="Gestinem Asesores SL", nif="B87654321",
    numero_instalacion="1",
)


def _q(tag: str) -> str:
    return f"{{{NS_SUM1}}}{tag}"


def test_first_record_uses_primer_registro_not_registro_anterior():
    data = AltaRegistroInput(
        id_emisor_factura="B87654321", num_serie_factura="APP-000001",
        fecha_expedicion_factura="05-03-2026", nombre_razon_emisor="Gestinem",
        tipo_factura="F1", descripcion_operacion="Servicios profesionales",
        destinatario_nombre_razon="Cliente SL", destinatario_nif="B12345678",
        desglose=[DesgloseIva(
            tipo_impositivo=Decimal("21.00"), base_imponible=Decimal("100.00"),
            cuota_repercutida=Decimal("21.00"),
        )],
        cuota_total=Decimal("21.00"), importe_total=Decimal("121.00"),
        sistema_informatico=SISTEMA,
        fecha_hora_huso_gen_registro="2026-03-05T10:00:00+01:00",
        huella_registro_anterior="",
    )
    huella, xml = build_registro_alta(data)

    root = ET.fromstring(xml)
    encadenamiento = root.find(_q("Encadenamiento"))
    assert encadenamiento.find(_q("PrimerRegistro")) is not None
    assert encadenamiento.find(_q("PrimerRegistro")).text == "S"
    assert encadenamiento.find(_q("RegistroAnterior")) is None
    assert root.find(_q("Huella")).text == huella


def test_subsequent_record_uses_registro_anterior():
    data = AltaRegistroInput(
        id_emisor_factura="B87654321", num_serie_factura="APP-000002",
        fecha_expedicion_factura="06-03-2026", nombre_razon_emisor="Gestinem",
        tipo_factura="F1", descripcion_operacion="Servicios profesionales",
        destinatario_nombre_razon="Cliente SL", destinatario_nif="B12345678",
        desglose=[DesgloseIva(
            tipo_impositivo=Decimal("21.00"), base_imponible=Decimal("50.00"),
            cuota_repercutida=Decimal("10.50"),
        )],
        cuota_total=Decimal("10.50"), importe_total=Decimal("60.50"),
        sistema_informatico=SISTEMA,
        fecha_hora_huso_gen_registro="2026-03-06T09:00:00+01:00",
        huella_registro_anterior="A" * 64,
        id_emisor_factura_anterior="B87654321",
        num_serie_factura_anterior="APP-000001",
        fecha_expedicion_factura_anterior="05-03-2026",
    )
    huella, xml = build_registro_alta(data)

    root = ET.fromstring(xml)
    encadenamiento = root.find(_q("Encadenamiento"))
    assert encadenamiento.find(_q("PrimerRegistro")) is None
    registro_anterior = encadenamiento.find(_q("RegistroAnterior"))
    assert registro_anterior.find(_q("Huella")).text == "A" * 64
    assert registro_anterior.find(_q("NumSerieFactura")).text == "APP-000001"


def test_alta_hash_matches_hash_module_independently():
    data = AltaRegistroInput(
        id_emisor_factura="B99999999", num_serie_factura="APP-000003",
        fecha_expedicion_factura="07-03-2026", nombre_razon_emisor="Gestinem",
        tipo_factura="F1", descripcion_operacion="Servicios",
        destinatario_nombre_razon="Cliente SL", destinatario_nif="B12345678",
        desglose=[DesgloseIva(
            tipo_impositivo=Decimal("21.00"), base_imponible=Decimal("200.00"),
            cuota_repercutida=Decimal("42.00"),
        )],
        cuota_total=Decimal("42.00"), importe_total=Decimal("242.00"),
        sistema_informatico=SISTEMA,
        fecha_hora_huso_gen_registro="2026-03-07T08:00:00+01:00",
        huella_registro_anterior="",
    )
    huella, _xml = build_registro_alta(data)

    expected = compute_alta_hash(
        id_emisor_factura="B99999999", num_serie_factura="APP-000003",
        fecha_expedicion_factura="07-03-2026", tipo_factura="F1",
        cuota_total="42.00", importe_total="242.00",
        huella_registro_anterior="",
        fecha_hora_huso_gen_registro="2026-03-07T08:00:00+01:00",
    )
    assert huella == expected


def test_xml_is_well_formed_and_utf8():
    data = AltaRegistroInput(
        id_emisor_factura="B99999999", num_serie_factura="APP-000004",
        fecha_expedicion_factura="08-03-2026", nombre_razon_emisor="Peña & Asociados",
        tipo_factura="F1", descripcion_operacion="Asesoría fiscal ñ",
        destinatario_nombre_razon="Clïente SL", destinatario_nif="B12345678",
        desglose=[DesgloseIva(
            tipo_impositivo=Decimal("21.00"), base_imponible=Decimal("10.00"),
            cuota_repercutida=Decimal("2.10"),
        )],
        cuota_total=Decimal("2.10"), importe_total=Decimal("12.10"),
        sistema_informatico=SISTEMA,
        fecha_hora_huso_gen_registro="2026-03-08T08:00:00+01:00",
        huella_registro_anterior="",
    )
    _huella, xml = build_registro_alta(data)
    assert xml.startswith("<?xml version='1.0' encoding='UTF-8'?>") or xml.startswith(
        '<?xml version="1.0" encoding="UTF-8"?>'
    )
    # Vuelve a parsear sin error: confirma que es XML bien formado.
    ET.fromstring(xml)
    assert "Peña" in xml
    assert "Asesoría" in xml


def test_anulacion_first_record_and_hash_consistency():
    data = AnulacionRegistroInput(
        id_emisor_factura_anulada="B87654321",
        num_serie_factura_anulada="APP-000001",
        fecha_expedicion_factura_anulada="05-03-2026",
        sistema_informatico=SISTEMA,
        fecha_hora_huso_gen_registro="2026-03-10T08:00:00+01:00",
        huella_registro_anterior="B" * 64,
        id_emisor_factura_anterior="B87654321",
        num_serie_factura_anterior="APP-000002",
        fecha_expedicion_factura_anterior="06-03-2026",
    )
    huella, xml = build_registro_anulacion(data)

    root = ET.fromstring(xml)
    assert root.tag == _q("RegistroAnulacion")
    id_factura = root.find(_q("IDFactura"))
    assert id_factura.find(_q("IDEmisorFacturaAnulada")).text == "B87654321"
    assert root.find(_q("Huella")).text == huella

    expected = compute_anulacion_hash(
        id_emisor_factura_anulada="B87654321",
        num_serie_factura_anulada="APP-000001",
        fecha_expedicion_factura_anulada="05-03-2026",
        huella_registro_anterior="B" * 64,
        fecha_hora_huso_gen_registro="2026-03-10T08:00:00+01:00",
    )
    assert huella == expected
