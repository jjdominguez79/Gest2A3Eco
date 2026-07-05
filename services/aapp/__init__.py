"""
Paquete de conectores con Administraciones Publicas (notificaciones y
certificados) para Gest2A3Eco.

Modelo "Opcion A": cada cliente aporta su certificado digital (.pfx/.p12) en
una ruta local; la app se autentica como ese cliente contra el portal del
organismo (DEHu, Seguridad Social, ...) y sincroniza sus notificaciones.

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
