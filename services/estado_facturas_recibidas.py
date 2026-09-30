"""Estados canonicos del circuito de facturas recibidas.

El archivo documental es la fuente de verdad. Las tablas OCR y contables son
proyecciones tecnicas y deben conservar estos mismos estados cuando exista un
documento archivado vinculado.
"""
from __future__ import annotations


PENDIENTE = "pendiente"
PENDIENTE_CONTABILIZAR = "pendiente_contabilizar"
EXPORTADA_A3 = "exportada_a3"
CONTABILIZADA = "contabilizada"
CONTABILIZADA_MANUAL = "contabilizada_manual"

ESTADOS_VALIDOS = {
    PENDIENTE,
    PENDIENTE_CONTABILIZAR,
    EXPORTADA_A3,
    CONTABILIZADA,
    CONTABILIZADA_MANUAL,
}


def estado_efectivo(*, estado: str = "", generada=False, numero_asiento="") -> str:
    """Normaliza filas antiguas que usaban ``contabilizada`` al exportar.

    Una factura solo esta contabilizada cuando A3 ha devuelto un numero de
    asiento. ``generada`` sin asiento significa exclusivamente exportada.
    """
    value = str(estado or "").strip().lower()
    if value == CONTABILIZADA_MANUAL:
        return CONTABILIZADA_MANUAL
    if str(numero_asiento or "").strip():
        return CONTABILIZADA
    if bool(generada) or value in {"exportada", EXPORTADA_A3}:
        return EXPORTADA_A3
    if value == CONTABILIZADA:
        return EXPORTADA_A3
    if value in ESTADOS_VALIDOS:
        return value
    return PENDIENTE


def etiqueta_estado(estado: str, *, metodo: str = "") -> str:
    value = str(estado or "").strip().lower()
    method = str(metodo or "").strip().lower()
    if value == CONTABILIZADA_MANUAL or method == "manual_a3_papel":
        return "Manual en A3 (papel)"
    if value == CONTABILIZADA:
        return "OCR/SUENLACE · asiento confirmado en A3"
    if value == EXPORTADA_A3:
        return "OCR/SUENLACE · pendiente de asiento A3"
    if value == PENDIENTE_CONTABILIZAR:
        return "Pendiente de exportar a A3"
    return "Pendiente de revision"
