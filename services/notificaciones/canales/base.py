"""
Interfaz base para canales de envio de notificaciones.

Cada canal (email, SMS, WhatsApp) debe heredar de ChannelSender e implementar
el metodo send(). Esto permite sustituir implementaciones sin cambiar el servicio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelResult:
    """Resultado estandar de un intento de envio."""
    ok:        bool
    mensaje:   str         = ""
    codigo:    str         = ""
    respuesta: dict        = field(default_factory=dict)


class ChannelSender:
    """
    Clase base abstracta para conectores de canal.

    Implementaciones concretas (fase posterior):
        EmailChannel(ChannelSender)
        SmsChannel(ChannelSender)
        WhatsAppChannel(ChannelSender)
    """

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        """
        Envia el payload por el canal especifico.
        Lanza NotImplementedError hasta que se implemente el conector real.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.send() no esta implementado todavia."
        )

    def validar_destinatario(self, destinatario: str) -> bool:
        """
        Valida el formato del destinatario para este canal.
        Devuelve True si el formato es correcto.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.validar_destinatario() no esta implementado."
        )

    def nombre_canal(self) -> str:
        """Nombre legible del canal para mostrar en la UI."""
        return self.__class__.__name__
