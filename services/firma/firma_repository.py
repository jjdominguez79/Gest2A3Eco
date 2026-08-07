from __future__ import annotations


class FirmaRepository:
    """Adaptador pequeno para que el servicio no dependa del SQL de la UI."""

    def __init__(self, gestor):
        self.gestor = gestor

    def crear(self, datos, firmantes, zonas):
        return self.gestor.crear_firma_solicitud(datos, firmantes, zonas)

    def get(self, solicitud_id):
        return self.gestor.get_firma_solicitud(solicitud_id)

    def listar(self, codigo_empresa, ejercicio, estado="", texto=""):
        return self.gestor.listar_firma_solicitudes(codigo_empresa, ejercicio, estado, texto)

    def actualizar(self, solicitud_id, cambios):
        return self.gestor.actualizar_firma_solicitud(solicitud_id, cambios)

    def actualizar_participantes(self, solicitud_id, firmantes, zonas):
        return self.gestor.actualizar_firma_participantes(solicitud_id, firmantes, zonas)

    def eliminar(self, solicitud_id):
        return self.gestor.eliminar_firma_solicitud(solicitud_id)

    def evento(self, solicitud_id, tipo, detalle_json="", usuario=""):
        return self.gestor.registrar_firma_evento(solicitud_id, tipo, detalle_json, usuario)

