"""Tests de la credencial exclusiva de billing_worker (Etapa 5).

Ver docs/adr/0001-facturacion-autonoma-cliente.md, seccion 4/12: a partir de
la Etapa 5 el pipeline fiscal/PDF/entrega exige una credencial de
billing_worker o la clave interna, nunca un token de puesto de escritorio.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import security


def _settings(**overrides):
    base = dict(
        billing_worker_api_key="billing-secret",
        internal_api_key="internal-secret",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_billing_worker_key_is_accepted(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    assert security.require_billing_worker_or_internal("billing-secret") == "billing-worker"


def test_internal_key_is_accepted_for_ops(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    assert security.require_billing_worker_or_internal("internal-secret") == "gest2a3eco"


def test_unknown_key_is_rejected(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as error:
        security.require_billing_worker_or_internal("something-else")
    assert error.value.status_code == 401


def test_workstation_token_is_never_accepted(monkeypatch):
    """Un token de puesto g2a3_wks_ no debe servir para reclamar trabajo cloud."""
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as error:
        security.require_billing_worker_or_internal("g2a3_wks_anything")
    assert error.value.status_code == 401
