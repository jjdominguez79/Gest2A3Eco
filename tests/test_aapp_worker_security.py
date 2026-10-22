from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import security


def test_credencial_worker_es_independiente_de_la_interna(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            aapp_worker_api_key="legacy-secret",
            aapp_certificates_worker_api_key="certificates-secret",
            aapp_notifications_worker_api_key="notifications-secret",
            internal_api_key="internal-secret",
        ),
    )

    assert security.require_aapp_worker_key("certificates-secret") == "certificates"
    assert security.require_aapp_worker_key("notifications-secret") == "notifications"
    assert security.require_aapp_worker_key("legacy-secret") == "legacy"
    assert security.require_document_publisher(
        "certificates-secret"
    ) == "aapp-worker-certificates"
    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_key("internal-secret")
    assert error.value.status_code == 401


def test_protocolo_worker_rechaza_versiones_obsoletas():
    assert security.require_aapp_worker_claim_protocol("4") == "aapp-worker-protocol-4"

    for version in ("1", "2", "3"):
        with pytest.raises(HTTPException) as error:
            security.require_aapp_worker_claim_protocol(version)
        assert error.value.status_code == 426


def test_rol_worker_debe_coincidir_con_su_credencial():
    assert security.require_aapp_worker_claim_role(
        "certificates", "certificates"
    ) == "certificates"
    assert security.require_aapp_worker_claim_role(
        "notifications", "notifications"
    ) == "notifications"
    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_claim_role("notifications", "certificates")
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_claim_role("otro", "legacy")
    assert error.value.status_code == 422

    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_claim_role(None, "legacy")
    assert error.value.status_code == 422
