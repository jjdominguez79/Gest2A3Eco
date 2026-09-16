"""Estados DEHu compartidos por conector, backend e importacion local."""
from __future__ import annotations


def normalizar_estado_dehu(valor) -> str:
    estado = str(valor or "").strip().upper().replace("\u00cd", "I")
    # UNREAD / NOT_READ contienen READ, pero no significan leida.
    if estado in {
        "UNREAD", "NOT_READ", "NOT READ", "NO LEIDA", "NO_LEIDA",
        "SIN LEER", "PENDING", "PENDIENTE", "NOT_ACCEPTED", "NOT ACCEPTED",
    }:
        return "PENDIENTE"
    if "ACEPTAD" in estado or "ACCEPT" in estado:
        return "ACEPTADA"
    if "RECHAZ" in estado or "REJECT" in estado:
        return "RECHAZADA"
    if "VENCID" in estado or "EXPIR" in estado:
        return "VENCIDA"
    if "LEID" in estado or "READ" in estado:
        return "LEIDA"
    if "REALIZ" in estado or "DONE" in estado:
        return "REALIZADA"
    return "PENDIENTE"


def es_pendiente_dehu(estado, endpoint: str = "") -> bool:
    return (
        "realized_notifications" not in str(endpoint or "").lower()
        and normalizar_estado_dehu(estado) == "PENDIENTE"
    )
