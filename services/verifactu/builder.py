"""Construccion del XML del registro de facturacion (RegistroAlta/Anulacion).

Genera el fragmento ``RegistroAlta``/``RegistroAnulacion`` (no el sobre SOAP
completo: esa capa de transporte depende de un adaptador real que todavia no
existe, ver ``adapter.py``). Estructura y namespaces verificados contra
ejemplos reales del documento 1 citado en README.md.

ADVERTENCIA: no se ha validado este XML contra el XSD oficial completo
(``SuministroLR.xsd`` / ``SuministroInformacion.xsd``); no se ha descargado
en esta sesion. Ver README.md, seccion "Lo que NO esta verificado".
"""

from __future__ import annotations

from decimal import Decimal
from xml.etree import ElementTree as ET

from services.verifactu.hash import compute_alta_hash, compute_anulacion_hash
from services.verifactu.models import AltaRegistroInput, AnulacionRegistroInput

NS_SUM = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd"
NS_SUM1 = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"

ET.register_namespace("sum", NS_SUM)
ET.register_namespace("sum1", NS_SUM1)


def _el(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    e = ET.SubElement(parent, f"{{{NS_SUM1}}}{tag}")
    if text is not None:
        e.text = text
    return e


def _fmt_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def build_registro_alta(data: AltaRegistroInput) -> tuple[str, str]:
    """Devuelve ``(huella, xml_utf8)`` del registro de alta.

    La huella se calcula primero (sobre los campos, no sobre el XML) y
    despues se incluye en el elemento ``Huella`` del propio registro,
    conforme al documento 2 (la huella de un registro siempre se informa en
    el propio registro, incluso el primero de la cadena).
    """
    cuota_str = _fmt_decimal(data.cuota_total)
    importe_str = _fmt_decimal(data.importe_total)

    huella = compute_alta_hash(
        id_emisor_factura=data.id_emisor_factura,
        num_serie_factura=data.num_serie_factura,
        fecha_expedicion_factura=data.fecha_expedicion_factura,
        tipo_factura=data.tipo_factura,
        cuota_total=cuota_str,
        importe_total=importe_str,
        huella_registro_anterior=data.huella_registro_anterior,
        fecha_hora_huso_gen_registro=data.fecha_hora_huso_gen_registro,
    )

    root = ET.Element(f"{{{NS_SUM1}}}RegistroAlta")
    _el(root, "IDVersion", "1.0")

    id_factura = _el(root, "IDFactura")
    _el(id_factura, "IDEmisorFactura", data.id_emisor_factura)
    _el(id_factura, "NumSerieFactura", data.num_serie_factura)
    _el(id_factura, "FechaExpedicionFactura", data.fecha_expedicion_factura)

    _el(root, "NombreRazonEmisor", data.nombre_razon_emisor)
    _el(root, "TipoFactura", data.tipo_factura)
    _el(root, "DescripcionOperacion", data.descripcion_operacion)

    destinatarios = _el(root, "Destinatarios")
    id_destinatario = _el(destinatarios, "IDDestinatario")
    _el(id_destinatario, "NombreRazon", data.destinatario_nombre_razon)
    _el(id_destinatario, "NIF", data.destinatario_nif)

    desglose = _el(root, "Desglose")
    for linea in data.desglose:
        detalle = _el(desglose, "DetalleDesglose")
        _el(detalle, "ClaveRegimen", linea.clave_regimen)
        _el(detalle, "CalificacionOperacion", linea.calificacion_operacion)
        _el(detalle, "TipoImpositivo", _fmt_decimal(linea.tipo_impositivo))
        _el(detalle, "BaseImponibleOimporteNoSujeto", _fmt_decimal(linea.base_imponible))
        _el(detalle, "CuotaRepercutida", _fmt_decimal(linea.cuota_repercutida))

    _el(root, "CuotaTotal", cuota_str)
    _el(root, "ImporteTotal", importe_str)

    encadenamiento = _el(root, "Encadenamiento")
    if data.huella_registro_anterior:
        registro_anterior = _el(encadenamiento, "RegistroAnterior")
        _el(registro_anterior, "IDEmisorFactura", data.id_emisor_factura_anterior)
        _el(registro_anterior, "NumSerieFactura", data.num_serie_factura_anterior)
        _el(registro_anterior, "FechaExpedicionFactura", data.fecha_expedicion_factura_anterior)
        _el(registro_anterior, "Huella", data.huella_registro_anterior)
    else:
        # Primer registro de la cadena de este obligado tributario/SIF
        # (documento 2, apartado 5): se declara con PrimerRegistro="S" y no
        # se informa RegistroAnterior.
        _el(encadenamiento, "PrimerRegistro", "S")

    si = data.sistema_informatico
    sistema = _el(root, "SistemaInformatico")
    _el(sistema, "NombreRazon", si.nombre_razon)
    _el(sistema, "NIF", si.nif)
    _el(sistema, "NombreSistemaInformatico", si.nombre_sistema_informatico)
    _el(sistema, "IdSistemaInformatico", si.id_sistema_informatico)
    _el(sistema, "Version", si.version)
    _el(sistema, "NumeroInstalacion", si.numero_instalacion)
    _el(sistema, "TipoUsoPosibleSoloVerifactu", si.tipo_uso_posible_solo_verifactu)
    _el(sistema, "TipoUsoPosibleMultiOT", si.tipo_uso_posible_multi_ot)
    _el(sistema, "IndicadorMultiplesOT", si.indicador_multiples_ot)

    _el(root, "FechaHoraHusoGenRegistro", data.fecha_hora_huso_gen_registro)
    _el(root, "TipoHuella", "01")
    _el(root, "Huella", huella)

    xml_bytes = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    return huella, xml_bytes.decode("utf-8")


def build_registro_anulacion(data: AnulacionRegistroInput) -> tuple[str, str]:
    """Devuelve ``(huella, xml_utf8)`` del registro de anulacion."""
    huella = compute_anulacion_hash(
        id_emisor_factura_anulada=data.id_emisor_factura_anulada,
        num_serie_factura_anulada=data.num_serie_factura_anulada,
        fecha_expedicion_factura_anulada=data.fecha_expedicion_factura_anulada,
        huella_registro_anterior=data.huella_registro_anterior,
        fecha_hora_huso_gen_registro=data.fecha_hora_huso_gen_registro,
    )

    root = ET.Element(f"{{{NS_SUM1}}}RegistroAnulacion")
    _el(root, "IDVersion", "1.0")

    id_factura = _el(root, "IDFactura")
    _el(id_factura, "IDEmisorFacturaAnulada", data.id_emisor_factura_anulada)
    _el(id_factura, "NumSerieFacturaAnulada", data.num_serie_factura_anulada)
    _el(id_factura, "FechaExpedicionFacturaAnulada", data.fecha_expedicion_factura_anulada)

    encadenamiento = _el(root, "Encadenamiento")
    if data.huella_registro_anterior:
        registro_anterior = _el(encadenamiento, "RegistroAnterior")
        _el(registro_anterior, "IDEmisorFactura", data.id_emisor_factura_anterior)
        _el(registro_anterior, "NumSerieFactura", data.num_serie_factura_anterior)
        _el(registro_anterior, "FechaExpedicionFactura", data.fecha_expedicion_factura_anterior)
        _el(registro_anterior, "Huella", data.huella_registro_anterior)
    else:
        _el(encadenamiento, "PrimerRegistro", "S")

    si = data.sistema_informatico
    sistema = _el(root, "SistemaInformatico")
    _el(sistema, "NombreRazon", si.nombre_razon)
    _el(sistema, "NIF", si.nif)
    _el(sistema, "NombreSistemaInformatico", si.nombre_sistema_informatico)
    _el(sistema, "IdSistemaInformatico", si.id_sistema_informatico)
    _el(sistema, "Version", si.version)
    _el(sistema, "NumeroInstalacion", si.numero_instalacion)
    _el(sistema, "TipoUsoPosibleSoloVerifactu", si.tipo_uso_posible_solo_verifactu)
    _el(sistema, "TipoUsoPosibleMultiOT", si.tipo_uso_posible_multi_ot)
    _el(sistema, "IndicadorMultiplesOT", si.indicador_multiples_ot)

    _el(root, "FechaHoraHusoGenRegistro", data.fecha_hora_huso_gen_registro)
    _el(root, "TipoHuella", "01")
    _el(root, "Huella", huella)

    xml_bytes = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    return huella, xml_bytes.decode("utf-8")
