"""
Servicio de Notificaciones Electronicas.

Fachada principal del modulo. Coordina el repositorio de datos y los canales
de envio. No contiene logica de UI ni referencias a Tkinter.

Uso en Gest2A3Eco:
    repo    = NotificacionRepo(gestor)
    service = NotificacionService(repo)
    service.programar(...)

Uso futuro en GestinemAppFull:
    repo    = NotificacionRepoSqlAlchemy(session)   # implementacion alternativa
    service = NotificacionService(repo)              # mismo servicio
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from services.notificaciones.notificacion_repo import NotificacionRepo
from services.notificaciones.tipos import (
    Canal,
    EstadoNotificacion,
    TipoDocumento,
    TipoNotificacion,
)


class NotificacionService:
    """
    Servicio principal de notificaciones.

    canales: dict[Canal, ChannelSender] con los conectores activos.
             Si el dict esta vacio no se puede enviar, solo programar.
    """

    def __init__(self, repo: NotificacionRepo, canales: dict | None = None):
        self._repo = repo
        self._canales: dict[str, Any] = canales or {}

    # ----------------------------------------------------------- programacion

    def programar(
        self,
        codigo_empresa: str,
        ejercicio: int,
        tipo_notif: str | TipoNotificacion,
        canal: str | Canal,
        destinatario: str,
        *,
        tipo_documento: str | TipoDocumento = TipoDocumento.MANUAL,
        documento_id: str | None = None,
        asunto: str | None = None,
    ) -> str:
        """
        Registra una notificacion en estado PENDIENTE.
        Devuelve el id generado.
        """
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        notif = {
            "id":             str(uuid.uuid4()),
            "codigo_empresa": codigo_empresa,
            "ejercicio":      int(ejercicio),
            "tipo_documento": str(tipo_documento),
            "documento_id":   documento_id,
            "tipo_notif":     str(tipo_notif),
            "canal":          str(canal),
            "destinatario":   destinatario,
            "asunto":         asunto,
            "estado":         EstadoNotificacion.PENDIENTE,
            "intentos":       0,
            "created_at":     now,
            "updated_at":     now,
        }
        return self._repo.guardar(notif)

    def cancelar(self, codigo_empresa: str, notificacion_id: str) -> None:
        """Marca una notificacion como CANCELADA."""
        notif = self._repo.get(notificacion_id)
        if not notif:
            return
        notif["estado"]     = EstadoNotificacion.CANCELADA
        notif["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat()
        self._repo.guardar(notif)

    def eliminar(self, codigo_empresa: str, notificacion_id: str) -> None:
        """Elimina definitivamente una notificacion."""
        self._repo.eliminar(codigo_empresa, notificacion_id)

    # ----------------------------------------------------------- consulta

    def listar(
        self,
        codigo_empresa: str,
        ejercicio: int,
        estado: str | None = None,
        canal: str | None = None,
    ) -> list[dict]:
        return self._repo.listar(codigo_empresa, ejercicio, estado=estado, canal=canal)

    def get(self, notificacion_id: str) -> dict | None:
        return self._repo.get(notificacion_id)

    # ----------------------------------------------------------- configuracion

    def listar_config(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        return self._repo.get_config(codigo_empresa, ejercicio)

    def guardar_config(
        self,
        codigo_empresa: str,
        ejercicio: int,
        canal: str | Canal,
        activo: bool,
        config_json: str | None = None,
    ) -> None:
        self._repo.guardar_config({
            "codigo_empresa": codigo_empresa,
            "ejercicio":      int(ejercicio),
            "canal":          str(canal),
            "activo":         1 if activo else 0,
            "config_json":    config_json,
        })

    # ----------------------------------------------------------- envio (stub)

    def enviar(self, notificacion_id: str) -> bool:
        """
        Intenta enviar una notificacion pendiente.

        STUB: en fase 1 siempre devuelve False (sin conectores reales).
        Los conectores se inyectaran via self._canales en fases posteriores.
        """
        notif = self._repo.get(notificacion_id)
        if not notif:
            return False

        canal_key = str(notif.get("canal", ""))
        sender    = self._canales.get(canal_key)

        if sender is None:
            # Sin conector configurado: registrar intento fallido
            self._registrar_intento(notif, ok=False, detalle="Conector no configurado")
            return False

        # Cuando existan conectores reales, se llamara aqui a sender.send(payload)
        return False

    def _registrar_intento(self, notif: dict, ok: bool, detalle: str = "") -> None:
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        notif["fecha_intento"] = now
        notif["intentos"]      = int(notif.get("intentos") or 0) + 1
        notif["estado"]        = EstadoNotificacion.ENVIADA if ok else EstadoNotificacion.ERROR
        notif["error_detalle"] = None if ok else detalle
        notif["updated_at"]    = now
        self._repo.guardar(notif)
