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
    response.raise_for_status.assert_called_once_with()


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
