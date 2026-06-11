"""
Controlador del modulo Notificaciones Electronicas.

Orquesta la vista UINotificaciones con el servicio NotificacionService.
Sigue el patron del resto de controladores del proyecto:
  - recibe la vista y el gestor en el constructor
  - expone metodos publicos que la vista llama en respuesta a eventos
  - actualiza la vista via callbacks (set_rows, set_estado, etc.)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from services.notificaciones.notificacion_repo import NotificacionRepo
from services.notificaciones.notificacion_service import NotificacionService
from services.notificaciones.tipos import EstadoNotificacion, LABELS_CANAL, LABELS_ESTADO, LABELS_TIPO_NOTIF

if TYPE_CHECKING:
    from views.ui_notificaciones import UINotificaciones


class UINotificacionesController:
    """
    Controlador para UINotificaciones.

    La vista pasa su referencia (self) en el constructor. El controlador
    llama de vuelta a self._view.set_rows() / self._view.set_status() etc.
    """

    def __init__(self, view: "UINotificaciones", gestor, codigo: str, ejercicio: int, session=None):
        self._view      = view
        self._gestor    = gestor
        self._codigo    = codigo
        self._ejercicio = int(ejercicio)
        self._session   = session

        repo = NotificacionRepo(gestor)
        self._service = NotificacionService(repo)

        # Cache local para evitar consultas repetidas
        self._cache: list[dict] = []

    # ------------------------------------------------------------------ refresh

    def refresh(self) -> None:
        """Recarga la lista de notificaciones desde la base de datos."""
        self._cache = self._service.listar(self._codigo, self._ejercicio)
        self._render_cache()

    def apply_filter(self, estado: str = "", canal: str = "") -> None:
        """Filtra la cache en memoria y actualiza la vista."""
        rows = self._cache
        if estado:
            rows = [r for r in rows if r.get("estado") == estado]
        if canal:
            rows = [r for r in rows if r.get("canal") == canal]
        if self._view is not None and hasattr(self._view, "set_rows"):
            self._view.set_rows(self._format_rows(rows))

    # ------------------------------------------------------------------ acciones

    def cancelar_seleccionada(self, notificacion_id: str) -> None:
        """Cancela la notificacion indicada y refresca."""
        self._service.cancelar(self._codigo, notificacion_id)
        self.refresh()

    def eliminar_seleccionada(self, notificacion_id: str) -> None:
        """Elimina definitivamente la notificacion indicada y refresca."""
        self._service.eliminar(self._codigo, notificacion_id)
        self.refresh()

    # ------------------------------------------------------------------ bandeja

    def listar_bandeja(self) -> list[dict]:
        """Devuelve todas las notificaciones de la bandeja de entrada."""
        return self._gestor.listar_notif_bandeja(self._codigo, self._ejercicio)

    def get_bandeja_item(self, item_id: str) -> dict | None:
        """Devuelve el detalle de una notificacion de la bandeja."""
        return self._gestor.get_notif_bandeja_item(item_id)

    def cambiar_estado_bandeja(self, item_id: str, estado: str, fecha: str) -> None:
        """Cambia el estado de una notificacion de la bandeja (ACEPTADA/RECHAZADA)."""
        self._gestor.cambiar_estado_notif_bandeja(self._codigo, item_id, estado, fecha)

    def eliminar_bandeja_item(self, item_id: str) -> None:
        """Elimina definitivamente un item de la bandeja."""
        self._gestor.eliminar_notif_bandeja_item(self._codigo, item_id)

    # ------------------------------------------------------------------ helpers

    def _render_cache(self) -> None:
        if self._view is not None and hasattr(self._view, "set_rows"):
            self._view.set_rows(self._format_rows(self._cache))

    def _format_rows(self, rows: list[dict]) -> list[tuple]:
        """Convierte dicts de DB a tuplas de columnas para el Treeview."""
        result = []
        for r in rows:
            tipo_label  = LABELS_TIPO_NOTIF.get(r.get("tipo_notif", ""), r.get("tipo_notif", ""))
            canal_label = LABELS_CANAL.get(r.get("canal", ""), r.get("canal", ""))
            estado_label = LABELS_ESTADO.get(r.get("estado", ""), r.get("estado", ""))
            result.append((
                r.get("id", ""),
                tipo_label,
                canal_label,
                r.get("destinatario", ""),
                estado_label,
                r.get("fecha_intento", "") or "",
                r.get("intentos", 0),
                r.get("error_detalle", "") or "",
            ))
        return result
