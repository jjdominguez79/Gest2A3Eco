"""
Tipos y enumeraciones del modulo Notificaciones Electronicas.
Sin dependencias de Tkinter ni de la capa de datos: apto para reutilizar en GestinemAppFull.
"""
from __future__ import annotations

from enum import Enum


class TipoDocumento(str, Enum):
    """Tipo de documento origen que genera la notificacion."""
    FACTURA_EMITIDA = "FACTURA_EMITIDA"
    ALBARAN         = "ALBARAN"
    VENCIMIENTO     = "VENCIMIENTO"
    RECORDATORIO    = "RECORDATORIO"
    MANUAL          = "MANUAL"


class TipoNotificacion(str, Enum):
    """Proposito de la notificacion."""
    ENVIO_FACTURA       = "ENVIO_FACTURA"
    RECORDATORIO_COBRO  = "RECORDATORIO_COBRO"
    AVISO_VENCIMIENTO   = "AVISO_VENCIMIENTO"
    COMUNICADO_GENERAL  = "COMUNICADO_GENERAL"


class Canal(str, Enum):
    """Canal de envio disponible."""
    EMAIL     = "EMAIL"
    SMS       = "SMS"
    WHATSAPP  = "WHATSAPP"


class EstadoNotificacion(str, Enum):
    """Estado del ciclo de vida de una notificacion."""
    PENDIENTE  = "PENDIENTE"
    ENVIADA    = "ENVIADA"
    ERROR      = "ERROR"
    CANCELADA  = "CANCELADA"


# Etiquetas legibles para la interfaz
LABELS_TIPO_NOTIF: dict[str, str] = {
    TipoNotificacion.ENVIO_FACTURA:      "Envio de factura",
    TipoNotificacion.RECORDATORIO_COBRO: "Recordatorio de cobro",
    TipoNotificacion.AVISO_VENCIMIENTO:  "Aviso de vencimiento",
    TipoNotificacion.COMUNICADO_GENERAL: "Comunicado general",
}

LABELS_CANAL: dict[str, str] = {
    Canal.EMAIL:    "Correo electronico",
    Canal.SMS:      "SMS",
    Canal.WHATSAPP: "WhatsApp",
}

LABELS_ESTADO: dict[str, str] = {
    EstadoNotificacion.PENDIENTE:  "Pendiente",
    EstadoNotificacion.ENVIADA:    "Enviada",
    EstadoNotificacion.ERROR:      "Error",
    EstadoNotificacion.CANCELADA:  "Cancelada",
}
