"""Construccion del contenido del QR fiscal de la factura.

Formato oficial del QR de validacion AEAT (Real Decreto 1007/2023; Orden
HAC/1177/2024, articulos 20-21): URL de la sede electronica con cuatro
parametros (``nif``, ``numserie``, ``fecha``, ``importe``). Verificado contra
multiples fuentes publicas que citan la norma; no se ha podido contrastar
contra el texto integro de la Orden en esta sesion (sin acceso a un entorno
AEAT real), por lo que ``build_aeat_validation_url`` se trata como pendiente
de validacion final (ver docs/adr/0001, seccion 9/14).

IMPORTANTE: esta URL solo debe imprimirse cuando el registro se ha remitido
de verdad a la AEAT (Etapa 7, flag ``VERIFACTU_SUBMISSION_ENABLED``). Antes
de eso, apuntar al validador de la AEAT para un registro que nunca se envio
seria mas enganoso que no tener QR: el escaneo mostraria "no encontrado" para
una factura legitima. Mientras el flag este desactivado se usa
``build_pending_reference_payload``, que nunca pretende ser una validacion
AEAT.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import quote

AEAT_VALIDATION_BASE_URL = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR"

# Frase legal obligatoria (Orden HAC/1177/2024) cuando el sistema esta
# efectivamente acogido a VERI*FACTU. No debe imprimirse mientras el envio
# fiscal real no exista (ADR 0001, seccion 9).
VERIFACTU_LEGAL_PHRASE = "Factura verificable en la sede electronica de la AEAT - VERI*FACTU"

PENDING_LEGAL_PHRASE = (
    "Documento emitido por un sistema no acogido todavia a VERI*FACTU. "
    "Referencia interna, no es una validacion de la AEAT."
)


def _format_importe(total: Decimal) -> str:
    try:
        value = Decimal(total)
    except (InvalidOperation, TypeError):
        raise ValueError("Importe no valido para el QR fiscal")
    return f"{value:.2f}"


def build_aeat_validation_url(
    *, nif: str, numserie: str, fecha: str, importe: Decimal,
) -> str:
    """Construye la URL oficial de validacion AEAT. Solo usar con flag activo.

    ``fecha`` debe venir ya en formato ``DD-MM-YYYY``. ``numserie`` se
    url-codifica en UTF-8 (incluido un posible ``&`` dentro del propio
    numero de serie, que se codifica como ``%26``).
    """
    if not nif:
        raise ValueError("nif es obligatorio para el QR fiscal")
    if not numserie:
        raise ValueError("numserie es obligatorio para el QR fiscal")
    if not fecha:
        raise ValueError("fecha es obligatoria para el QR fiscal")

    params = "&".join([
        f"nif={quote(nif, safe='')}",
        f"numserie={quote(numserie, safe='')}",
        f"fecha={quote(fecha, safe='')}",
        f"importe={quote(_format_importe(importe), safe='')}",
    ])
    return f"{AEAT_VALIDATION_BASE_URL}?{params}"


def build_pending_reference_payload(
    *, organization_code: str, series_code: str, invoice_number: int,
) -> str:
    """Contenido neutral del QR mientras no hay remision fiscal real.

    No es una URL de validacion de nada: es solo una referencia de la propia
    factura, para que el QR exista estructuralmente en el PDF sin insinuar
    una conformidad VERI*FACTU que todavia no existe.
    """
    return (
        f"GEST2A3ECO-REF:{organization_code}:{series_code}-"
        f"{invoice_number:06d}"
    )
