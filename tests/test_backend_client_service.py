from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.backend_client_service import BackendClientService


def _service(monkeypatch, session) -> BackendClientService:
    monkeypatch.setattr(
        "utils.credential_store.get_workstation_token",
        lambda: "g2a3_wks_test",
    )
    return BackendClientService(
        config={"integrations_api_url": "https://api.example.test"},
        session=session,
    )


def test_publish_document_uses_workstation_api_key(monkeypatch, tmp_path):
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    response = MagicMock()
    response.json.return_value = {"document_id": "doc-1"}
    session = MagicMock()
    session.post.return_value = response
    service = _service(monkeypatch, session)

    result = service.publish_document(
        source_type="factura_emitida",
        source_id="fac-1",
        display_name="Factura A1",
        pdf_path=str(pdf),
        company_code="E00006",
        previous_document_id="doc-anterior",
        customer_tax_id="B12345678",
    )

    assert result == {"document_id": "doc-1"}
    request = session.post.call_args
    assert request.kwargs["headers"] == {"X-API-Key": "g2a3_wks_test"}
    assert request.kwargs["data"]["company_code"] == "E00006"
    assert request.kwargs["data"]["previous_document_id"] == "doc-anterior"
    assert request.kwargs["data"]["customer_tax_id"] == "B12345678"
    assert request.kwargs["data"]["source_system"] == "desktop_invoice"
    response.raise_for_status.assert_called_once_with()


def test_publish_document_accepts_aapp_source_system(monkeypatch, tmp_path):
    pdf = tmp_path / "certificado.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    response = MagicMock()
    response.json.return_value = {"id": "doc-aapp"}
    session = MagicMock()
    session.post.return_value = response

    _service(monkeypatch, session).publish_document(
        source_type="certificado_aeat",
        source_system="desktop_aapp",
        source_id="sol-1",
        display_name="Estar al corriente",
        pdf_path=str(pdf),
        customer_tax_id="B12345678",
    )

    assert session.post.call_args.kwargs["data"]["source_system"] == "desktop_aapp"


def test_unconfigured_service_fails_before_http(monkeypatch):
    monkeypatch.setattr(
        "utils.credential_store.get_workstation_token",
        lambda: None,
    )
    session = MagicMock()
    service = BackendClientService(config={}, session=session)

    with pytest.raises(ValueError, match="no esta configurada"):
        service.sync_company_profile(company_code="E00001", profile={})

    session.put.assert_not_called()


def test_create_certificate_request_uses_internal_backend(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"id": "sol-1", "status": "queued"}
    session = MagicMock()
    session.post.return_value = response
    service = _service(monkeypatch, session)

    result = service.create_certificate_request(
        company_code="E00006",
        certificate_type="AEAT_CORRIENTE",
        idempotency_key="desktop-sol-1",
    )

    assert result["status"] == "queued"
    request = session.post.call_args
    assert request.kwargs["params"] == {"company_code": "E00006"}
    assert request.kwargs["json"]["certificate_type"] == "AEAT_CORRIENTE"
    assert request.kwargs["headers"] == {"X-API-Key": "g2a3_wks_test"}


def test_upload_client_certificate_uses_multipart(monkeypatch, tmp_path):
    pfx = tmp_path / "cliente.pfx"
    pfx.write_bytes(b"pfx-test")
    response = MagicMock()
    response.json.return_value = {"configured": True, "status": "valid"}
    session = MagicMock()
    session.post.return_value = response

    result = _service(monkeypatch, session).upload_client_certificate(
        company_code="E00006",
        pfx_path=str(pfx),
        password="secreto",
    )

    assert result["configured"] is True
    request = session.post.call_args
    assert request.kwargs["data"] == {
        "company_code": "E00006", "password": "secreto",
    }
    assert request.kwargs["files"]["file"][0] == "cliente.pfx"
    assert request.kwargs["headers"] == {"X-API-Key": "g2a3_wks_test"}
    response.raise_for_status.assert_called_once_with()


def test_list_certificate_requests_uses_internal_backend(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"items": [{"id": "sol-1"}]}
    session = MagicMock()
    session.get.return_value = response

    result = _service(monkeypatch, session).list_certificate_requests(
        company_code="E00006", limit=50,
    )

    assert result == [{"id": "sol-1"}]
    request = session.get.call_args
    assert request.kwargs["params"] == {"limit": 50, "company_code": "E00006"}
    assert request.kwargs["headers"] == {"X-API-Key": "g2a3_wks_test"}


def test_retry_certificate_request_uses_internal_backend(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"id": "sol-1", "status": "queued"}
    session = MagicMock()
    session.post.return_value = response

    result = _service(monkeypatch, session).retry_certificate_request("sol-1")

    assert result["status"] == "queued"
    assert session.post.call_args.args[0].endswith("/internal/requests/sol-1/retry")
    assert session.post.call_args.kwargs["headers"] == {"X-API-Key": "g2a3_wks_test"}
    response.raise_for_status.assert_called_once_with()


def test_download_certificate_request_document(monkeypatch):
    response = MagicMock()
    response.content = b"%PDF-1.7"
    response.headers = {
        "Content-Disposition": 'attachment; filename="corriente.pdf"',
        "Content-Type": "application/pdf",
    }
    session = MagicMock()
    session.get.return_value = response

    result = _service(monkeypatch, session).download_certificate_request_document("sol-1")

    assert result == (b"%PDF-1.7", "corriente.pdf", "application/pdf")
    assert session.get.call_args.args[0].endswith("/internal/requests/sol-1/document")


def test_sync_company_profile_uses_backend_route(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"organization_id": "org-1"}
    session = MagicMock()
    session.put.return_value = response
    service = _service(monkeypatch, session)

    result = service.sync_company_profile(
        company_code="E00001",
        profile={"tax_id": "B12345678"},
    )

    assert result == {"organization_id": "org-1"}
    assert session.put.call_args.args[0] == (
        "https://api.example.test/api/v1/messaging/client/internal/sync-profile"
    )
    response.raise_for_status.assert_called_once_with()


def test_review_profile_change_request_uses_internal_route(monkeypatch):
    response = MagicMock()
    response.json.return_value = {"id": "request-1", "status": "applied"}
    session = MagicMock()
    session.patch.return_value = response
    service = _service(monkeypatch, session)

    result = service.review_profile_change_request(
        "request-1", status="applied", note="Confirmado",
    )

    assert result["status"] == "applied"
    assert session.patch.call_args.args[0].endswith(
        "/internal/profile-change-requests/request-1"
    )
    assert session.patch.call_args.kwargs["json"] == {
        "status": "applied", "note": "Confirmado",
    }
    response.raise_for_status.assert_called_once_with()
