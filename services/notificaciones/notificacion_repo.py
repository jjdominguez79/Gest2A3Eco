"""
Repositorio de Notificaciones Electronicas.

Abstrae el acceso a datos para que NotificacionService no dependa directamente
de GestorSQLite. En GestinemAppFull se puede sustituir por una implementacion
sobre SQLAlchemy o una API REST sin modificar el servicio.
"""
from __future__ import annotations

from typing import Any


class NotificacionRepo:
    """
    Repositorio sobre GestorSQLite.
    Delega en los metodos listar/get/upsert/eliminar_notificacion del gestor.
    """

    def __init__(self, gestor: Any):
        self._gestor = gestor

    # ----------------------------------------------------------------- lectura

    def listar(
        self,
        codigo_empresa: str,
        ejercicio: int,
        estado: str | None = None,
        canal: str | None = None,
    ) -> list[dict]:
        return self._gestor.listar_notificaciones(
            codigo_empresa, ejercicio, estado=estado, canal=canal
        )

    def get(self, notificacion_id: str) -> dict | None:
        return self._gestor.get_notificacion(notificacion_id)

    def get_config(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        return self._gestor.get_notificaciones_config(codigo_empresa, ejercicio)

    # ---------------------------------------------------------------- escritura

    def guardar(self, notif: dict) -> str:
        """Inserta o actualiza una notificacion. Devuelve el id."""
        return self._gestor.upsert_notificacion(notif)

    def eliminar(self, codigo_empresa: str, notificacion_id: str) -> None:
        self._gestor.eliminar_notificacion(codigo_empresa, notificacion_id)

    def guardar_config(self, config: dict) -> None:
        self._gestor.upsert_notificaciones_config(config)
