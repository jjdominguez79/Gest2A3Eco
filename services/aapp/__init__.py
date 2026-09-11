"""
Paquete de conectores con Administraciones Publicas (notificaciones y
certificados) para Gest2A3Eco.

Modelo "Opcion A": cada cliente aporta su certificado digital (.pfx/.p12). En
produccion se custodia cifrado exclusivamente en Azure; el worker lo materializa
de forma temporal para autenticarse como ese cliente y lo elimina al terminar.
Las rutas locales solo pertenecen al flujo directo historico y a desarrollo.

Puntos de entrada tipicos:
    from services.aapp.sync_service import sincronizar_buzon, sincronizar_buzones
    from services.aapp.base import OpcionesSync
    from services.aapp.cert_store import CertStore
"""
from .base import (
    NotificacionDTO,
    OpcionesSync,
    ResultadoSync,
    ConectorOrganismo,
    obtener_conector,
    conectores_disponibles,
)

__all__ = [
    "NotificacionDTO",
    "OpcionesSync",
    "ResultadoSync",
    "ConectorOrganismo",
    "obtener_conector",
    "conectores_disponibles",
]
