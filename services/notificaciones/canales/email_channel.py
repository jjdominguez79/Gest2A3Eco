"""
Canal Email - STUB fase 1.

Implementacion pendiente: reutilizara services/email_service.py cuando se
active el conector real. Por ahora eleva NotImplementedError al intentar enviar.
"""
from __future__ import annotations

import re

from services.notificaciones.canales.base import ChannelResult, ChannelSender

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailChannel(ChannelSender):
    """
    Conector de correo electronico.

    Parametros de configuracion esperados (config_json):
        {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password": "...",
            "remitente": "Empresa S.L. <facturacion@example.com>"
        }
    """

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def nombre_canal(self) -> str:
        return "Correo electronico"

    def validar_destinatario(self, destinatario: str) -> bool:
        return bool(_RE_EMAIL.match(destinatario.strip()))

    def send(self, payload: dict) -> ChannelResult:
        # STUB: conector real pendiente de implementacion
        raise NotImplementedError("EmailChannel.send() no implementado en fase 1.")
