"""Tests del cliente HTTP real de billing_worker contra las rutas del backend.

Complementa tests/test_billing_worker.py (que usa un backend falso): aqui se
verifica que BillingBackendClient llama exactamente a las rutas, cabeceras y
payloads esperados por backend/api/client_invoices_api.py, usando
``responses`` para interceptar las llamadas HTTP (sin red real).
"""

from __future__ import annotations

import json

import responses

from billing_worker.backend_client import BillingBackendClient
from billing_worker.config import BillingWorkerConfig

BASE = "https://backend.test"
PREFIX = "/api/v1/messaging/client/invoicing"


def _config() -> BillingWorkerConfig:
    return BillingWorkerConfig(
        backend_url=BASE,
        api_key="billing-secret",
        instance_id="billing-1",
        poll_interval_seconds=5,
        lease_minutes=10,
        request_timeout_seconds=30,
        heartbeat_interval_seconds=60,
        max_backoff_seconds=300,
    )


@responses.activate
def test_claim_sends_worker_id_and_lease_and_returns_item():
    responses.add(
        responses.POST, f"{BASE}{PREFIX}/worker/claim",
        json={"claimed": True, "queue_id": "q1", "invoice_id": "inv-1"},
        status=200,
    )
    client = BillingBackendClient(_config())

    result = client.claim()

    assert result == {"claimed": True, "queue_id": "q1", "invoice_id": "inv-1"}
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"worker_id": "billing-1", "lease_minutes": 10}
    assert responses.calls[0].request.headers["X-API-Key"] == "billing-secret"


@responses.activate
def test_claim_returns_none_when_backend_reports_nothing_claimed():
    responses.add(
        responses.POST, f"{BASE}{PREFIX}/worker/claim",
        json={"claimed": False}, status=200,
    )
    client = BillingBackendClient(_config())
    assert client.claim() is None


@responses.activate
def test_upload_pdf_sends_multipart_with_sha256():
    responses.add(
        responses.POST, f"{BASE}{PREFIX}/worker/invoice/inv-1/pdf",
        json={"status": "ok", "sha256": "abc"}, status=200,
    )
    client = BillingBackendClient(_config())
    result = client.upload_pdf("inv-1", b"%PDF-1.4 fake", "abc")

    assert result["status"] == "ok"
    sent = responses.calls[0].request.body
    assert b"abc" in sent
    assert b"%PDF-1.4 fake" in sent


@responses.activate
def test_heartbeat_sends_instance_id_and_counts():
    responses.add(
        responses.POST, f"{BASE}{PREFIX}/worker/billing/heartbeat",
        json={"status": "ok"}, status=200,
    )
    client = BillingBackendClient(_config())
    client.heartbeat(jobs_processed_total=3, jobs_failed_total=1, status_detail="ok")

    sent = json.loads(responses.calls[0].request.body)
    assert sent["instance_id"] == "billing-1"
    assert sent["jobs_processed_total"] == 3
    assert sent["jobs_failed_total"] == 1


@responses.activate
def test_report_error_truncates_long_messages():
    responses.add(
        responses.POST, f"{BASE}{PREFIX}/worker/invoice/inv-1/error",
        json={"status": "ok", "retryable": True}, status=200,
    )
    client = BillingBackendClient(_config())
    client.report_error("inv-1", "x" * 5000)

    sent = json.loads(responses.calls[0].request.body)
    assert len(sent["error"]) == 4000


@responses.activate
def test_http_error_status_raises():
    responses.add(
        responses.GET, f"{BASE}{PREFIX}/worker/invoice/inv-1/status",
        json={"detail": "no encontrada"}, status=404,
    )
    client = BillingBackendClient(_config())
    import pytest
    import requests
    with pytest.raises(requests.HTTPError):
        client.get_status("inv-1")
