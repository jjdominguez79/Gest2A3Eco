"""
Canal SMS - STUB fase 1.

Implementacion pendiente: requiere credenciales de proveedor SMS (Twilio,
Vonage, etc.) almacenadas en notificaciones_config para la empresa.
Por ahora eleva NotImplementedError al intentar enviar.
"""
from __future__ import annotations

import re

from services.notificaciones.canales.base import ChannelResult, ChannelSender

# Acepta formatos: +34600000000, 600000000, +1 (555) 000-0000 (simplificado)
_RE_TELEFONO = re.compile(r"^\+?[\d\s\-\(\)]{7,20}$")


class SmsChannel(ChannelSender):
    """
    Conector SMS.

    Parametros de configuracion esperados (config_json):
        {
            "api_key":    "...",
            "api_secret": "...",
            "remitente":  "MiEmpresa"
        }
    """

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def nombre_canal(self) -> str:
        return "SMS"

    def validar_destinatario(self, destinatario: str) -> bool:
        return bool(_RE_TELEFONO.match(destinatario.strip()))

    def send(self, payload: dict) -> ChannelResult:
        # STUB: conector real pendiente de implementacion
        raise NotImplementedError("SmsChannel.send() no implementado en fase 1.")
