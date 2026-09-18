from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import requests

from aapp_worker.config import AappWorkerConfig


class AappBackendClient:
    def __init__(self, config: AappWorkerConfig, session=None):
        self.config = config
        self.http = session or requests.Session()

    @property
    def _headers(self) -> dict:
        return {
            "X-API-Key": self.config.api_key,
            "X-AAPP-Worker-Protocol": "3",
        }

    def claim(self) -> dict | None:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/internal/worker/claim",
            headers=self._headers,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json().get("item")

    def certificate_material(self, item: dict) -> dict:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/internal/worker/certificate-material",
            headers=self._headers,
            json={"request_id": item["id"], "claim_token": item["claim_token"]},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def publish_pdf(self, item: dict, pdf_path: Path) -> dict:
        certificate_type = str(item["certificate_type"])
        organization = "AEAT" if certificate_type.startswith("AEAT_") else "TGSS"
        clase = item.get("_document_kind") or "certificado"
        resguardo = clase != "certificado"
        obtained_at = datetime.now(timezone.utc)
        content = pdf_path.read_bytes()
        with pdf_path.open("rb") as stream:
            response = self.http.post(
                f"{self.config.backend_url}/api/v1/messaging/client/documents/internal/publish",
                headers=self._headers,
                data={
                    "organization_id": item["organization_id"],
                    "document_type": f"{clase}_{organization.lower()}",
                    "source_system": "aapp_worker",
                    "source_id": f"{item['id']}:{clase}" if resguardo else item["id"],
                    "source_version": "1",
                    "display_name": (
                        ("Resguardo - " if clase == "resguardo" else "Documento en revision - ")
                        if resguardo else ""
                    ) + (item.get("certificate_name") or certificate_type),
                    "description": (
                        "Documento de la solicitud AEAT; no es el certificado definitivo"
                        if resguardo else f"Certificado obtenido de {organization}"
                    ),
                    "document_date": obtained_at.date().isoformat(),
                    "fiscal_year": str(obtained_at.year),
                    "expected_sha256": hashlib.sha256(content).hexdigest(),
                    # Solo las solicitudes creadas por el propio cliente se
                    # publican automaticamente en Flutter.
                    "publish_to_client": str(
                        item.get("requester_type") == "client"
                    ).lower(),
                },
                files={"file": (pdf_path.name, stream, "application/pdf")},
                timeout=self.config.request_timeout_seconds,
            )
        response.raise_for_status()
        return response.json()

    def receipt_pdf(self, item: dict) -> bytes:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/internal/worker/receipt-document",
            headers=self._headers,
            json={"request_id": item["id"], "claim_token": item["claim_token"]},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.content

    def publish_notification_pdf(self, item: dict, notification, pdf_path: Path) -> dict:
        content = pdf_path.read_bytes()
        source_id = hashlib.sha256(
            f"{item['organization_id']}|{notification.dedup_key()}".encode("utf-8")
        ).hexdigest()[:40]
        with pdf_path.open("rb") as stream:
            response = self.http.post(
                f"{self.config.backend_url}/api/v1/messaging/client/documents/internal/publish",
                headers=self._headers,
                data={
                    "organization_id": item["organization_id"],
                    "document_type": "notificacion_dehu",
                    "source_system": "aapp_worker",
                    "source_id": source_id,
                    "source_version": "1",
                    "display_name": notification.asunto or "Notificacion DEHu",
                    "description": notification.descripcion or "Notificacion electronica recibida en DEHu",
                    "expected_sha256": hashlib.sha256(content).hexdigest(),
                },
                files={"file": (pdf_path.name, stream, "application/pdf")},
                timeout=self.config.request_timeout_seconds,
            )
        response.raise_for_status()
        return response.json()

    def upsert_dehu_notifications(self, item: dict, notifications: list[dict]) -> dict:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/"
            f"internal/worker/requests/{item['id']}/dehu-notifications",
            headers=self._headers,
            json={
                "claim_token": item["claim_token"],
                "notifications": notifications,
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def complete(self, item: dict, document_id: str | None, summary: str = "") -> None:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/complete",
            headers=self._headers,
            json={
                "claim_token": item["claim_token"],
                "document_id": document_id,
                "result_summary": summary,
                "certificate_result": summary if summary in {"POSITIVO", "NEGATIVO"} else "",
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()

    def pending_issuance(
        self, item: dict, *, receipt_document_id=None, reference="",
        requires_review=False, message="La AEAT sigue tramitando el certificado.",
    ) -> None:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/"
            f"internal/worker/requests/{item['id']}/pending-issuance",
            headers=self._headers,
            json={
                "claim_token": item["claim_token"],
                "receipt_document_id": receipt_document_id,
                "external_reference": reference or "",
                "requires_review": requires_review,
                "message": message,
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()

    def fail(
        self,
        item: dict,
        message: str,
        *,
        code: str = "worker_error",
        needs_action: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        response = self.http.post(
            f"{self.config.backend_url}/api/v1/messaging/client/certificates/internal/worker/requests/{item['id']}/fail",
            headers=self._headers,
            json={
                "claim_token": item["claim_token"],
                "error_code": code,
                "error_message": message[:4000],
                "needs_action": needs_action,
                "retry_after_seconds": retry_after_seconds,
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
