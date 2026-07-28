from services.comunicaciones_sync_service import ComunicacionesSyncService
from services.graph_mail_service import GraphSyncResult


MESSAGE = {
    "id": "graph-1",
    "conversationId": "conversation-1",
    "internetMessageId": "<one@example.com>",
    "subject": "Documentacion",
    "body": {"content": "<p>Hola</p>"},
    "from": {"emailAddress": {"address": "cliente@example.com"}},
    "toRecipients": [{"emailAddress": {"address": "oficina@gestinem.es"}}],
    "ccRecipients": [],
    "receivedDateTime": "2026-07-28T10:00:00Z",
    "hasAttachments": False,
    "isRead": False,
}


class Graph:
    def sync_inbox(self, **kwargs):
        return GraphSyncResult([MESSAGE], "delta-1", "oficina@gestinem.es")


class Gestor:
    def __init__(self, empresa=None):
        self.empresa = empresa
        self.entradas = []
        self.pendientes = []
        self.delta = None

    def get_comunicaciones_delta(self, mailbox):
        return ""

    def buscar_empresa_por_email(self, email):
        return self.empresa

    def registrar_entrada_comunicacion(self, data):
        self.entradas.append(data)
        return ("com-1", "msg-1")

    def guardar_comunicacion_sin_asignar(self, data):
        self.pendientes.append(data)

    def guardar_comunicaciones_delta(self, mailbox, delta_link):
        self.delta = (mailbox, delta_link)


def test_sync_asigna_por_email_y_responsable():
    gestor = Gestor({
        "codigo": "E00001", "responsable": "ANA",
    })

    summary = ComunicacionesSyncService(gestor, Graph()).sync("oficina@gestinem.es")

    assert summary.asignados == 1
    assert gestor.entradas[0]["codigo_empresa"] == "E00001"
    assert gestor.entradas[0]["responsable_nombre"] == "ANA"
    assert gestor.delta == ("oficina@gestinem.es", "delta-1")


def test_sync_conserva_sin_asignar():
    gestor = Gestor()

    summary = ComunicacionesSyncService(gestor, Graph()).sync("oficina@gestinem.es")

    assert summary.sin_asignar == 1
    assert gestor.pendientes[0]["graph_message_id"] == "graph-1"
