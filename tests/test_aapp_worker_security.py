from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import security


def test_credencial_worker_es_independiente_de_la_interna(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            aapp_worker_api_key="worker-secret",
            internal_api_key="internal-secret",
        ),
    )

    assert security.require_aapp_worker_key("worker-secret") == "aapp-worker"
    assert security.require_document_publisher("worker-secret") == "aapp-worker"
    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_key("internal-secret")
    assert error.value.status_code == 401


def test_protocolo_worker_rechaza_versiones_obsoletas():
    assert security.require_aapp_worker_claim_protocol("2") == "aapp-worker-protocol-2"

    with pytest.raises(HTTPException) as error:
        security.require_aapp_worker_claim_protocol("1")
    assert error.value.status_code == 426
