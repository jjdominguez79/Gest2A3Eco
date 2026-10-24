"""Cliente HTTP de billing_worker contra el backend.

billing_worker nunca abre una conexion SQL (ni al backend ni, mucho menos,
al PostgreSQL interno del escritorio): todo pasa por esta API autenticada,
igual que aapp_worker/backend_client.py. Ver ADR 0001, seccion 4.
"""

from __future__ import annotations

import requests

from billing_worker.config import BillingWorkerConfig

_PREFIX = "/api/v1/messaging/client/invoicing"


class BillingBackendClient:
    def __init__(self, config: BillingWorkerConfig, session: requests.Session | None = None):
        self.config = config
        self.http = session or requests.Session()

    @property
    def _headers(self) -> dict:
        return {"X-API-Key": self.config.api_key}

    def _url(self, path: str) -> str:
        return f"{self.config.backend_url}{_PREFIX}{path}"

    def claim(self) -> dict | None:
        response = self.http.post(
            self._url("/worker/claim"),
            headers=self._headers,
            json={
                "worker_id": self.config.instance_id,
                "lease_minutes": self.config.lease_minutes,
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("claimed"):
            return None
        return data

    def get_payload(self, invoice_id: str) -> dict:
        response = self.http.get(
            self._url(f"/worker/invoice/{invoice_id}/payload"),
            headers=self._headers,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def upload_pdf(self, invoice_id: str, content: bytes, sha256: str) -> dict:
        response = self.http.post(
            self._url(f"/worker/invoice/{invoice_id}/pdf"),
            headers=self._headers,
            data={"sha256": sha256},
            files={"file": ("factura.pdf", content, "application/pdf")},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def publish_document(self, invoice_id: str, description: str = "") -> dict:
        response = self.http.post(
            self._url(f"/worker/invoice/{invoice_id}/publish-document"),
            headers=self._headers,
            json={"description": description},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def send_email(self, invoice_id: str) -> dict:
        response = self.http.post(
            self._url(f"/worker/invoice/{invoice_id}/send-email"),
            headers=self._headers,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def send_fcm(self, invoice_id: str) -> dict:
        response = self.http.post(
            self._url(f"/worker/invoice/{invoice_id}/send-fcm"),
            headers=self._headers,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def report_error(self, invoice_id: str, message: str) -> dict:
        response = self.http.post(
            self._url(f"/worker/invoice/{invoice_id}/error"),
            headers=self._headers,
            json={"error": message[:4000]},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_status(self, invoice_id: str) -> dict:
        response = self.http.get(
            self._url(f"/worker/invoice/{invoice_id}/status"),
            headers=self._headers,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(
        self, *, jobs_processed_total: int, jobs_failed_total: int, status_detail: str = "",
    ) -> None:
        response = self.http.post(
            self._url("/worker/billing/heartbeat"),
            headers=self._headers,
            json={
                "instance_id": self.config.instance_id,
                "jobs_processed_total": jobs_processed_total,
                "jobs_failed_total": jobs_failed_total,
                "status_detail": status_detail[:2000],
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
