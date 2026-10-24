"""Modelos de entrada para el motor Veri*FACTU.

Ver services/verifactu/README.md para la procedencia de los nombres de
campo (documento 1, ejemplos de XML de alta/anulacion).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class DesgloseIva:
    """Una linea del bloque ``Desglose/DetalleDesglose``."""

    tipo_impositivo: Decimal
    base_imponible: Decimal
    cuota_repercutida: Decimal
    clave_regimen: str = "01"
    calificacion_operacion: str = "S1"


@dataclass(frozen=True)
class SistemaInformatico:
    """Identificacion del software, igual para todos los registros."""

    nombre_razon: str
    nif: str
    nombre_sistema_informatico: str = "Gest2A3Eco"
    id_sistema_informatico: str = "01"
    version: str = "1.0"
    numero_instalacion: str = "1"
    # N = el sistema puede usarse fuera de VERI*FACTU; aqui siempre "S":
    # este software solo opera en modalidad VERI*FACTU.
    tipo_uso_posible_solo_verifactu: str = "S"
    tipo_uso_posible_multi_ot: str = "N"
    indicador_multiples_ot: str = "N"


@dataclass(frozen=True)
class AltaRegistroInput:
    """Datos de un registro de alta, antes de calcular su huella."""

    id_emisor_factura: str
    num_serie_factura: str
    fecha_expedicion_factura: str  # DD-MM-YYYY
    nombre_razon_emisor: str
    tipo_factura: str  # "F1" (normal) | "R1" (rectificativa); ver README
    descripcion_operacion: str
    destinatario_nombre_razon: str
    destinatario_nif: str
    desglose: list[DesgloseIva]
    cuota_total: Decimal
    importe_total: Decimal
    sistema_informatico: SistemaInformatico
    fecha_hora_huso_gen_registro: str  # ISO 8601 con offset
    huella_registro_anterior: str = ""  # "" solo si es el primer registro
    id_emisor_factura_anterior: str = ""
    num_serie_factura_anterior: str = ""
    fecha_expedicion_factura_anterior: str = ""
    factura_rectificada_num_serie: str = ""
    factura_rectificada_fecha: str = ""


@dataclass(frozen=True)
class AnulacionRegistroInput:
    """Datos de un registro de anulacion, antes de calcular su huella."""

    id_emisor_factura_anulada: str
    num_serie_factura_anulada: str
    fecha_expedicion_factura_anulada: str  # DD-MM-YYYY
    sistema_informatico: SistemaInformatico
    fecha_hora_huso_gen_registro: str  # ISO 8601 con offset
    huella_registro_anterior: str = ""
    id_emisor_factura_anterior: str = ""
    num_serie_factura_anterior: str = ""
    fecha_expedicion_factura_anterior: str = ""
