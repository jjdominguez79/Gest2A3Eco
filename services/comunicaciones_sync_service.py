from __future__ import annotations

from dataclasses import dataclass

from services.graph_mail_service import GraphMailService


def _address(value: dict | None) -> str:
    return str(((value or {}).get("emailAddress") or {}).get("address") or "").strip()


def _addresses(values: list[dict] | None) -> list[str]:
    return [address for item in values or [] if (address := _address(item))]


@dataclass(frozen=True)
class SyncSummary:
    recibidos: int = 0
    asignados: int = 0
    sin_asignar: int = 0
    duplicados: int = 0


class ComunicacionesSyncService:
    def __init__(self, gestor, graph: GraphMailService | None = None):
        self.gestor = gestor
        self.graph = graph or GraphMailService()

    def sync(self, mailbox: str) -> SyncSummary:
        key = str(mailbox or "me").strip().lower()
        delta = self.gestor.get_comunicaciones_delta(key)
        result = self.graph.sync_inbox(mailbox=mailbox, delta_link=delta)
        assigned = unmatched = duplicates = 0
        for raw in result.messages:
            data = self._normalize(raw, result.mailbox)
            empresa = self.gestor.buscar_empresa_por_email(data["remitente"])
            if empresa:
                data["codigo_empresa"] = empresa["codigo"]
                data["responsable_nombre"] = empresa.get("responsable")
                if self.gestor.registrar_entrada_comunicacion(data):
                    assigned += 1
                else:
                    duplicates += 1
            else:
                self.gestor.guardar_comunicacion_sin_asignar(data)
                unmatched += 1
        self.gestor.guardar_comunicaciones_delta(key, result.delta_link)
        return SyncSummary(len(result.messages), assigned, unmatched, duplicates)

    @staticmethod
    def _normalize(raw: dict, mailbox: str) -> dict:
        return {
            "graph_message_id": str(raw.get("id") or ""),
            "graph_conversation_id": str(raw.get("conversationId") or ""),
            "internet_message_id": str(raw.get("internetMessageId") or ""),
            "mailbox": mailbox,
            "remitente": _address(raw.get("from")),
            "destinatarios": _addresses(raw.get("toRecipients")),
            "cc": _addresses(raw.get("ccRecipients")),
            "asunto": str(raw.get("subject") or "(Sin asunto)"),
            "cuerpo_html": str((raw.get("body") or {}).get("content") or ""),
            "fecha": str(raw.get("receivedDateTime") or ""),
            "tiene_adjuntos": bool(raw.get("hasAttachments")),
            "leido": bool(raw.get("isRead")),
        }
