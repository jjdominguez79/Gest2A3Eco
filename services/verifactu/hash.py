"""Calculo de la huella/hash de registros Veri*FACTU.

Formula verificada contra "Detalle de las especificaciones tecnicas para
generacion de la huella o hash de los registros de facturacion" (AEAT,
v0.1.2, 27/08/2024). Ver services/verifactu/README.md para la procedencia y
tests/test_verifactu_hash.py para los tres vectores de prueba oficiales
reproducidos exactamente.

Regla general (documento 2, apartado 3): los campos se concatenan, EN EL
ORDEN indicado para cada tipo de registro, como
``nombreCampo1=valorCampo1&nombreCampo2=valorCampo2&...``. Si un campo no
tiene valor (p.ej. ``Huella`` en el primer registro de la cadena), se
incluye el nombre y el ``=`` sin valor. La cadena resultante se codifica en
UTF-8 y se le aplica SHA-256; la salida es hexadecimal en mayusculas.
"""

from __future__ import annotations

import hashlib


def _concat(fields: list[tuple[str, str]]) -> str:
    return "&".join(f"{name}={value}" for name, value in fields)


def _sha256_upper(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def compute_alta_hash(
    *,
    id_emisor_factura: str,
    num_serie_factura: str,
    fecha_expedicion_factura: str,
    tipo_factura: str,
    cuota_total: str,
    importe_total: str,
    huella_registro_anterior: str,
    fecha_hora_huso_gen_registro: str,
) -> str:
    """Huella de un registro de alta.

    Orden de campos verificado (documento 2, apartado 3.a):
    IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura, TipoFactura,
    CuotaTotal, ImporteTotal, Huella (del registro anterior; vacio si es el
    primero de la cadena), FechaHoraHusoGenRegistro.

    Todos los parametros de fecha/importe deben venir ya formateados tal y
    como apareceran en el XML (``DD-MM-YYYY`` y 2 decimales
    respectivamente); esta funcion no los reformatea.
    """
    return _sha256_upper(_concat([
        ("IDEmisorFactura", id_emisor_factura),
        ("NumSerieFactura", num_serie_factura),
        ("FechaExpedicionFactura", fecha_expedicion_factura),
        ("TipoFactura", tipo_factura),
        ("CuotaTotal", cuota_total),
        ("ImporteTotal", importe_total),
        ("Huella", huella_registro_anterior),
        ("FechaHoraHusoGenRegistro", fecha_hora_huso_gen_registro),
    ]))


def compute_anulacion_hash(
    *,
    id_emisor_factura_anulada: str,
    num_serie_factura_anulada: str,
    fecha_expedicion_factura_anulada: str,
    huella_registro_anterior: str,
    fecha_hora_huso_gen_registro: str,
) -> str:
    """Huella de un registro de anulacion.

    Orden de campos verificado (documento 2, apartado 3.b):
    IDEmisorFacturaAnulada, NumSerieFacturaAnulada,
    FechaExpedicionFacturaAnulada, Huella (del registro anterior),
    FechaHoraHusoGenRegistro.
    """
    return _sha256_upper(_concat([
        ("IDEmisorFacturaAnulada", id_emisor_factura_anulada),
        ("NumSerieFacturaAnulada", num_serie_factura_anulada),
        ("FechaExpedicionFacturaAnulada", fecha_expedicion_factura_anulada),
        ("Huella", huella_registro_anterior),
        ("FechaHoraHusoGenRegistro", fecha_hora_huso_gen_registro),
    ]))
