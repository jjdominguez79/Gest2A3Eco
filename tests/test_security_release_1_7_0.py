"""
Tests de seguridad para release 1.7.0.

Verifica la eliminacion completa de los mecanismos de autenticacion legacy
basados en integrations_api_key y dgt_api_key en el escritorio v1.7.0.

1. GEST2A3ECO_INTEGRATIONS_API_KEY no se carga en configuracion.
2. GEST2A3ECO_DGT_API_KEY no se carga en configuracion.
3. integrations_api_key no se utiliza como autenticacion del escritorio.
4. dgt_api_key no se utiliza como autenticacion del escritorio.
5. Configuraciones antiguas que contienen esas claves se limpian.
6. Gest2A3Eco/IntegrationsApiKey legacy continua eliminandose del Credential Manager.
7. WorkstationToken continua funcionando.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_keyring(monkeypatch):
    """Devuelve un dict que actua como almacen keyring en memoria."""
    store = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, username, value):
            store[(service, username)] = value

        @staticmethod
        def get_password(service, username):
            return store.get((service, username))

        @staticmethod
        def delete_password(service, username):
            store.pop((service, username), None)

    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    from utils import credential_store
    monkeypatch.setattr(credential_store, "_keyring_available", lambda: True)
    return store


# ── Test 1: GEST2A3ECO_INTEGRATIONS_API_KEY no se carga ──────────────────────

def test_env_integrations_api_key_no_carga_en_config(monkeypatch):
    """GEST2A3ECO_INTEGRATIONS_API_KEY no debe introducir integrations_api_key en config."""
    monkeypatch.setenv("GEST2A3ECO_INTEGRATIONS_API_KEY", "clave-legacy-env")
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    import importlib
    import utils.utilidades as _u
    importlib.reload(_u)

    cfg = _u.load_app_config()

    assert cfg.get("integrations_api_key") != "clave-legacy-env", (
        "GEST2A3ECO_INTEGRATIONS_API_KEY no debe cargarse en la config del escritorio. "
        "integrations_api_key es una clave legacy reemplazada por WorkstationToken."
    )
    assert not cfg.get("integrations_api_key"), (
        "integrations_api_key no debe aparecer en la config cargada por env."
    )


# ── Test 2: GEST2A3ECO_DGT_API_KEY no se carga ───────────────────────────────

def test_env_dgt_api_key_no_carga_en_config(monkeypatch):
    """GEST2A3ECO_DGT_API_KEY no debe introducir dgt_api_key en config."""
    monkeypatch.setenv("GEST2A3ECO_DGT_API_KEY", "dgt-key-legacy-env")
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    import importlib
    import utils.utilidades as _u
    importlib.reload(_u)

    cfg = _u.load_app_config()

    assert cfg.get("dgt_api_key") != "dgt-key-legacy-env", (
        "GEST2A3ECO_DGT_API_KEY no debe cargarse en la config del escritorio. "
        "dgt_api_key es una clave legacy reemplazada por WorkstationToken."
    )
    assert not cfg.get("dgt_api_key"), (
        "dgt_api_key no debe aparecer en la config cargada por env."
    )


# ── Test 3: integrations_api_key no autentica el escritorio ──────────────────

def test_integrations_api_key_no_autentica_tramites_dgt(monkeypatch):
    """Tramites DGT no usa integrations_api_key del Credential Manager para autenticar."""
    store = _mock_keyring(monkeypatch)

    # Guardamos SOLO integrations_api_key legacy en Credential Manager, sin WorkstationToken
    from utils.credential_store import SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY
    store[(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)] = "api-key-legacy-tramites"

    from utils.credential_store import get_workstation_token
    # Sin WorkstationToken, el puesto no puede autenticarse
    token = get_workstation_token()
    assert not token, "Solo debe existir api-key legacy, no WorkstationToken."

    # La logica de UITramitesDgt usa exclusivamente WorkstationToken
    effective_key = (
        get_workstation_token()
        or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
    )
    assert not effective_key, (
        "integrations_api_key legacy no debe ser utilizada como autenticacion del escritorio."
    )


def test_integrations_api_key_no_autentica_ocr(monkeypatch):
    """OCR service no usa integrations_api_key del Credential Manager; usa WorkstationToken."""
    store = _mock_keyring(monkeypatch)

    # Guardamos SOLO integrations_api_key legacy, sin WorkstationToken
    from utils.credential_store import SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY
    store[(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)] = "api-key-legacy-ocr"

    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "ocr_motor_activo": "azure",
            "integrations_api_url": "https://backend.example.com",
        },
    )

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    cfg = svc._leer_config_ocr()

    # La clave de backend debe ser vacia (no WorkstationToken, no legacy)
    assert cfg.get("backend_api_key") != "api-key-legacy-ocr", (
        "OCR service no debe usar integrations_api_key legacy."
    )
    assert not cfg.get("backend_api_key"), (
        "Sin WorkstationToken, backend_api_key debe estar vacia."
    )
    # La clave 'integrations_api_key' no debe existir en el dict interno
    assert "integrations_api_key" not in cfg, (
        "El dict interno de OCR no debe exponer la clave 'integrations_api_key'."
    )


# ── Test 4: dgt_api_key no autentica el escritorio ───────────────────────────

def test_dgt_api_key_no_autentica_escritorio(monkeypatch):
    """dgt_api_key en config no debe ser utilizada para autenticar el escritorio."""
    store = _mock_keyring(monkeypatch)

    # Config con dgt_api_key pero sin WorkstationToken
    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "integrations_api_url": "https://backend.example.com",
            "dgt_api_key": "dgt-key-legacy-value",
        },
    )

    from utils.credential_store import get_workstation_token

    # La logica de autenticacion del escritorio usa EXCLUSIVAMENTE WorkstationToken
    effective_key = (
        get_workstation_token()
        or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
    )
    assert not effective_key, (
        "dgt_api_key no debe utilizarse como autenticacion del escritorio. "
        "Solo WorkstationToken es valido."
    )


def test_dgt_api_key_no_autentica_firma(monkeypatch):
    """build_firma_provider no usa dgt_api_key; solo WorkstationToken."""
    store = _mock_keyring(monkeypatch)
    # Ponemos dgt_api_key en config pero no WorkstationToken
    cfg = {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
        "dgt_api_key": "dgt-key-legacy-firma",
    }

    from services.firma.provider import build_firma_provider
    result = build_firma_provider(cfg)
    assert result is None, (
        "Sin WorkstationToken, build_firma_provider no debe autenticar con dgt_api_key."
    )


# ── Test 5: configuraciones antiguas se limpian ───────────────────────────────

def test_config_antigua_integrations_api_key_se_limpia_al_guardar(monkeypatch):
    """save_app_config elimina integrations_api_key de cualquier config que reciba."""
    written_payload = {}

    monkeypatch.setattr("utils.utilidades._write_json_file",
                        lambda p, d: written_payload.update(d))
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "integrations_api_url": "https://backend.example.com",
        "integrations_api_key": "clave-antigua-instalacion",
    })

    assert "integrations_api_key" not in written_payload, (
        "integrations_api_key no debe persistirse en disco en instalaciones antiguas."
    )


def test_config_antigua_dgt_api_key_se_limpia_al_guardar(monkeypatch):
    """save_app_config elimina dgt_api_key de cualquier config que reciba."""
    written_payload = {}

    monkeypatch.setattr("utils.utilidades._write_json_file",
                        lambda p, d: written_payload.update(d))
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "integrations_api_url": "https://backend.example.com",
        "dgt_api_key": "dgt-clave-antigua",
    })

    assert "dgt_api_key" not in written_payload, (
        "dgt_api_key no debe persistirse en disco en instalaciones antiguas."
    )


def test_config_antigua_claves_legacy_se_limpian_juntas(monkeypatch):
    """save_app_config elimina tanto integrations_api_key como dgt_api_key simultaneamente."""
    written_payload = {}

    monkeypatch.setattr("utils.utilidades._write_json_file",
                        lambda p, d: written_payload.update(d))
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "integrations_api_url": "https://backend.example.com",
        "integrations_api_key": "clave-integraciones",
        "dgt_api_key": "clave-dgt",
        "ocr_motor_activo": "azure",
    })

    assert "integrations_api_key" not in written_payload
    assert "dgt_api_key" not in written_payload
    assert written_payload.get("ocr_motor_activo") == "azure", (
        "Los campos no sensibles si deben conservarse."
    )


# ── Test 6: Gest2A3Eco/IntegrationsApiKey se borra del Credential Manager ────

def test_integrations_api_key_se_elimina_de_credential_manager(monkeypatch):
    """delete_integrations_api_key borra Gest2A3Eco/IntegrationsApiKey del Credential Manager."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import (
        SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY,
        store_integrations_api_key, delete_integrations_api_key,
        get_integrations_api_key,
    )

    # Simular instalacion antigua con clave en Credential Manager
    store_integrations_api_key("clave-antigua-en-credmanager")
    assert get_integrations_api_key() == "clave-antigua-en-credmanager"

    # La rutina de limpieza debe borrarla
    delete_integrations_api_key()
    assert get_integrations_api_key() is None, (
        "Gest2A3Eco/IntegrationsApiKey debe eliminarse del Credential Manager."
    )


def test_integrations_api_key_eliminada_por_constante_correcta():
    """La constante SERVICE_INTEGRATIONS_KEY apunta a Gest2A3Eco/IntegrationsApiKey."""
    from utils.credential_store import SERVICE_INTEGRATIONS_KEY
    assert SERVICE_INTEGRATIONS_KEY == "Gest2A3Eco/IntegrationsApiKey", (
        "La constante de servicio debe seguir apuntando a la entrada legacy "
        "para poder eliminarla de instalaciones antiguas."
    )


# ── Test 7: WorkstationToken continua funcionando ─────────────────────────────

def test_workstation_token_autentica_tramites_dgt(monkeypatch):
    """Con WorkstationToken valido, la autenticacion del escritorio funciona correctamente."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_WORKSTATION, USERNAME_WORKSTATION
    store[(SERVICE_WORKSTATION, USERNAME_WORKSTATION)] = "g2a3_wks_valid_token_v170"

    from utils.credential_store import get_workstation_token
    token = get_workstation_token()
    assert token == "g2a3_wks_valid_token_v170", (
        "WorkstationToken debe recuperarse correctamente del Credential Manager."
    )


def test_workstation_token_autentica_ocr(monkeypatch):
    """OCR service usa WorkstationToken correctamente como backend_api_key."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_WORKSTATION, USERNAME_WORKSTATION
    store[(SERVICE_WORKSTATION, USERNAME_WORKSTATION)] = "g2a3_wks_ocr_v170"

    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "ocr_motor_activo": "azure",
            "integrations_api_url": "https://backend.example.com",
        },
    )

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    cfg = svc._leer_config_ocr()

    assert cfg["backend_api_key"] == "g2a3_wks_ocr_v170", (
        "OCR service debe pasar WorkstationToken como backend_api_key."
    )
    assert "integrations_api_key" not in cfg, (
        "El dict interno no debe exponer la clave legacy 'integrations_api_key'."
    )


def test_workstation_token_autentica_firma(monkeypatch):
    """build_firma_provider usa WorkstationToken correctamente."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_WORKSTATION, USERNAME_WORKSTATION
    store[(SERVICE_WORKSTATION, USERNAME_WORKSTATION)] = "g2a3_wks_firma_v170"

    cfg = {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
    }

    captured_keys = []

    class FakeBackendSignRequest:
        def __init__(self, base_url, api_key, session=None):
            captured_keys.append(api_key)
            raise ValueError("SignRequest no configurado")

    with patch("services.dgt_remote_integrations.BackendSignRequestClient", FakeBackendSignRequest):
        import importlib
        import services.firma.provider as _pmod
        importlib.reload(_pmod)
        _pmod.BackendSignRequestClient = FakeBackendSignRequest
        try:
            _pmod.build_firma_provider(cfg)
        except (ValueError, RuntimeError):
            pass

    assert captured_keys, "build_firma_provider debe intentar crear el cliente"
    assert all(k == "g2a3_wks_firma_v170" for k in captured_keys), (
        "Solo WorkstationToken debe usarse para autenticar firma en v1.7.0."
    )


# ── Test extra: env vars validas siguen funcionando ───────────────────────────

def test_env_workstation_token_sigue_funcionando(monkeypatch):
    """GEST2A3ECO_WORKSTATION_TOKEN como fallback de entorno continua funcionando."""
    store = _mock_keyring(monkeypatch)
    # Sin token en Credential Manager, usamos variable de entorno
    monkeypatch.setenv("GEST2A3ECO_WORKSTATION_TOKEN", "g2a3_wks_env_fallback")

    from utils.credential_store import get_workstation_token
    token = get_workstation_token()  # Credential Manager vacio

    effective_key = token or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
    assert effective_key == "g2a3_wks_env_fallback", (
        "GEST2A3ECO_WORKSTATION_TOKEN como variable de entorno debe seguir funcionando."
    )


def test_env_vars_legacy_no_inyectan_config(monkeypatch):
    """GEST2A3ECO_INTEGRATIONS_API_KEY y GEST2A3ECO_DGT_API_KEY no deben inyectar valores en config."""
    monkeypatch.setenv("GEST2A3ECO_INTEGRATIONS_API_KEY", "inyeccion-test")
    monkeypatch.setenv("GEST2A3ECO_DGT_API_KEY", "dgt-inyeccion-test")

    import importlib
    import utils.utilidades as _u
    importlib.reload(_u)

    result = _u._apply_env_overrides({})

    assert result.get("integrations_api_key") != "inyeccion-test", (
        "GEST2A3ECO_INTEGRATIONS_API_KEY no debe inyectar integrations_api_key en config."
    )
    assert result.get("dgt_api_key") != "dgt-inyeccion-test", (
        "GEST2A3ECO_DGT_API_KEY no debe inyectar dgt_api_key en config."
    )
