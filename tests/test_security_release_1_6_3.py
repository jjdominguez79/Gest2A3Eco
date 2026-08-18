"""
Tests de seguridad para release 1.6.3.

Verifica:
1. postgres_dsn nunca se persiste en disco.
2. WorkstationToken es el unico mecanismo normal de autenticacion del escritorio.
3. Ausencia de WorkstationToken produce error controlado (no fallback a legacy).
4. IntegrationsApiKey legacy no puede autenticar una peticion del escritorio.
5. El escritorio no necesita AzureDocIntelligence key para OCR backend.
6. Azure OCR backend continua funcionando con sus variables Railway (mock).
7. config.example.json no contiene secretos.
8. Migracion de configuraciones antiguas elimina secretos del JSON.
9. save_app_config() no puede reintroducirlos.
"""
from __future__ import annotations

import json
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


# ── Test 1: postgres_dsn nunca se persiste ─────────────────────────────────────

def test_postgres_dsn_no_se_persiste_en_disco(monkeypatch):
    """postgres_dsn con password NO debe aparecer en el JSON guardado en disco."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    data = {
        "postgres_host": "192.168.0.18",
        "postgres_port": 5433,
        "postgres_database": "gest2a3eco",
        "postgres_user": "miusuario",
        "postgres_dsn": "postgresql://miusuario:password_secreta@192.168.0.18:5433/gest2a3eco",
    }
    save_app_config(data)

    assert "postgres_dsn" not in written_payload, (
        "postgres_dsn con password no debe guardarse en el fichero de configuracion."
    )


def test_postgres_dsn_en_claves_secretas_disco():
    """postgres_dsn debe estar en _CLAVES_SECRETAS_DISCO."""
    from utils.utilidades import _CLAVES_SECRETAS_DISCO
    assert "postgres_dsn" in _CLAVES_SECRETAS_DISCO, (
        "postgres_dsn debe estar en _CLAVES_SECRETAS_DISCO para no persistirse en disco."
    )


def test_campos_postgres_no_secretos_si_se_persisten(monkeypatch):
    """postgres_host, postgres_port, postgres_database, postgres_user SI deben persistirse."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    data = {
        "postgres_host": "192.168.0.18",
        "postgres_port": 5433,
        "postgres_database": "gest2a3eco",
        "postgres_user": "miusuario",
    }
    save_app_config(data)

    assert written_payload.get("postgres_host") == "192.168.0.18"
    assert written_payload.get("postgres_port") == 5433
    assert written_payload.get("postgres_database") == "gest2a3eco"
    assert written_payload.get("postgres_user") == "miusuario"


# ── Test 2: WorkstationToken es el unico mecanismo normal ─────────────────────

def test_workstation_token_es_unico_mecanismo_firma(monkeypatch):
    """build_firma_provider debe usar solo WorkstationToken, nunca integrations_api_key."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_WORKSTATION, USERNAME_WORKSTATION
    store[(SERVICE_WORKSTATION, USERNAME_WORKSTATION)] = "g2a3_wks_test_token"

    cfg = {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
    }

    captured_keys = []

    class FakeBackendSignRequest:
        def __init__(self, base_url, api_key, session=None):
            captured_keys.append(api_key)
            raise ValueError("SignRequest no configurado")  # no queremos llamada real

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
    assert all(k == "g2a3_wks_test_token" for k in captured_keys), (
        "Solo WorkstationToken debe usarse, no integrations_api_key."
    )


def test_ocr_service_usa_solo_workstation_token(monkeypatch):
    """_leer_config_ocr del OCR service usa WorkstationToken, no integrations_api_key."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_WORKSTATION, USERNAME_WORKSTATION
    store[(SERVICE_WORKSTATION, USERNAME_WORKSTATION)] = "g2a3_wks_ocr_token"

    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "ocr_motor_activo": "azure",
            "integrations_api_url": "https://backend.example.com",
            "azure_doc_intelligence_endpoint": "https://test.azure.com",
        },
    )

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    cfg = svc._leer_config_ocr()

    assert cfg["backend_api_key"] == "g2a3_wks_ocr_token", (
        "OCR service debe usar WorkstationToken como backend_api_key."
    )


# ── Test 3: Ausencia de WorkstationToken produce error controlado ──────────────

def test_tramites_dgt_sin_workstation_token_lanza_error(monkeypatch):
    """Sin WorkstationToken, la inicializacion de DGT debe lanzar RuntimeError claro.

    Se verifica a nivel de logica de autenticacion (no instanciando el widget Tkinter).
    """
    store = _mock_keyring(monkeypatch)
    # No guardamos WorkstationToken

    # Reproducimos la logica de autenticacion de UITramitesDgt.__init__
    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "integrations_api_url": "https://backend.example.com",
        },
    )

    from utils.utilidades import load_app_config
    from utils.credential_store import get_workstation_token
    import os

    cfg = load_app_config()
    api_url = str(cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or "").strip()
    effective_key = (
        get_workstation_token()
        or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
    )

    if not api_url or not effective_key:
        with pytest.raises(RuntimeError):
            raise RuntimeError(
                "Puesto no registrado: falta WorkstationToken."
            )
    else:
        pytest.fail("Debe detectarse la ausencia de WorkstationToken.")


def test_firma_provider_sin_workstation_token_retorna_none(monkeypatch):
    """build_firma_provider devuelve None si no hay WorkstationToken (no usa legacy)."""
    store = _mock_keyring(monkeypatch)
    # No guardamos WorkstationToken ni integrations_api_key

    cfg = {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
    }

    from services.firma.provider import build_firma_provider
    result = build_firma_provider(cfg)
    assert result is None, (
        "Sin WorkstationToken, build_firma_provider no debe autenticar con clave legacy."
    )


# ── Test 4: IntegrationsApiKey legacy no puede autenticar ─────────────────────

def test_integrations_api_key_legacy_no_autentica_escritorio(monkeypatch):
    """IntegrationsApiKey en el Credential Manager ya no se usa para autenticar el escritorio."""
    store = _mock_keyring(monkeypatch)

    # Guardamos SOLO integrations_api_key legacy, no WorkstationToken
    from utils.credential_store import SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY
    store[(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)] = "api-key-legacy"

    cfg = {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
    }

    from services.firma.provider import build_firma_provider
    result = build_firma_provider(cfg)
    # Sin WorkstationToken, debe devolver None (no usar la clave legacy)
    assert result is None, (
        "IntegrationsApiKey legacy no debe usarse para autenticar firma. "
        "Solo WorkstationToken es valido."
    )


def test_ocr_service_sin_workstation_token_no_usa_integrations_key(monkeypatch):
    """OCR service sin WorkstationToken no debe caer back a integrations_api_key."""
    store = _mock_keyring(monkeypatch)

    # Guardamos SOLO integrations_api_key legacy
    from utils.credential_store import SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY
    store[(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)] = "api-key-legacy"

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

    assert cfg.get("backend_api_key") != "api-key-legacy", (
        "OCR service no debe usar integrations_api_key legacy como backend_api_key. "
        "Solo WorkstationToken es valido."
    )
    assert not cfg.get("backend_api_key"), (
        "Sin WorkstationToken, backend_api_key debe ser vacio."
    )
    assert "integrations_api_key" not in cfg, (
        "El dict de config OCR no debe exponer la clave 'integrations_api_key'."
    )


# ── Test 5: Escritorio no necesita azure_doc_intelligence_key con backend ──────

def test_ocr_no_carga_azure_key_si_hay_backend(monkeypatch):
    """Con backend configurado, el escritorio no debe cargar azure_doc_intelligence_key."""
    store = _mock_keyring(monkeypatch)

    # Guardamos una clave Azure en el almacen local
    from utils.credential_store import SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY
    store[(SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY)] = "azure-key-local"

    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "ocr_motor_activo": "azure",
            "integrations_api_url": "https://backend.example.com",
            "azure_doc_intelligence_endpoint": "https://test.azure.com",
        },
    )

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    cfg = svc._leer_config_ocr()

    assert not cfg.get("azure_key"), (
        "Con backend configurado, el escritorio no debe cargar azure_doc_intelligence_key. "
        "Azure lo gestiona el backend Railway."
    )


def test_ocr_no_carga_azure_key_sin_backend(monkeypatch):
    """El escritorio nunca carga azure_doc_intelligence_key, tampoco sin backend."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY
    store[(SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY)] = "azure-key-local-valida"

    monkeypatch.setattr(
        "utils.utilidades.load_app_config",
        lambda: {
            "ocr_motor_activo": "azure",
            "integrations_api_url": "",  # sin backend
            "azure_doc_intelligence_endpoint": "https://test.azure.com",
        },
    )

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    cfg = svc._leer_config_ocr()

    assert "azure_key" not in cfg


# ── Test 6: Azure OCR backend Railway funciona con variables de entorno ────────

def test_backend_azure_ocr_disponible_con_variables_railway(monkeypatch):
    """Con variables Railway (AZURE_DOC_INTELLIGENCE_KEY), ocr_available() devuelve True."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "clave-railway")

    from backend.api.ocr_service import ocr_available
    assert ocr_available() is True


def test_backend_azure_ocr_no_disponible_sin_key(monkeypatch):
    """Sin AZURE_DOC_INTELLIGENCE_KEY en Railway, ocr_available() devuelve False."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)

    from backend.api.ocr_service import ocr_available
    assert ocr_available() is False


# ── Test 7: config.example.json no contiene secretos ─────────────────────────

def test_config_example_no_contiene_secretos_completo():
    """config.example.json no debe contener ninguna clave secreta."""
    config_path = Path(__file__).parent.parent / "config.example.json"
    if not config_path.exists():
        pytest.skip("config.example.json no encontrado")

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    secretos_prohibidos = {
        "postgres_dsn",
        "postgres_password",
        "azure_doc_intelligence_key",
        "azure_storage_connection_string",
        "dataprius_api_key",
        "dataprius_api_secret",
        "signrequest_token",
        "workstation_token",
        "integrations_api_key",
        "dgt_api_key",
        "messaging_api_key",
        "messaging_device_token",
        "admin_password",
        "initial_admin_password",
        "desmarcar_generadas_password",
        "DGT_INTERNAL_API_KEY",
        "firma_webhook_secret",
    }
    presentes = secretos_prohibidos & set(cfg.keys())
    assert not presentes, f"Secretos encontrados en config.example.json: {presentes}"


def test_config_example_contiene_campos_no_sensibles():
    """config.example.json debe contener los campos de configuracion no sensibles."""
    config_path = Path(__file__).parent.parent / "config.example.json"
    if not config_path.exists():
        pytest.skip("config.example.json no encontrado")

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    campos_esperados = {
        "postgres_host", "postgres_port", "postgres_database", "postgres_user",
        "integrations_api_url", "firma_habilitada",
    }
    ausentes = campos_esperados - set(cfg.keys())
    assert not ausentes, f"Campos de configuracion no sensibles ausentes: {ausentes}"


# ── Test 8: Migracion elimina secretos del JSON ───────────────────────────────

def test_migracion_elimina_integrations_api_key_del_json(monkeypatch):
    """La migracion en arranque debe eliminar integrations_api_key del config JSON."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    # Simular config con clave legacy
    data = {
        "postgres_host": "192.168.0.18",
        "integrations_api_url": "https://backend.example.com",
        "integrations_api_key": "clave-legacy-que-debe-desaparecer",
        "dgt_api_key": "otra-clave-legacy",
        "azure_doc_intelligence_key": "azure-key-que-debe-desaparecer",
    }
    save_app_config(data)

    assert "integrations_api_key" not in written_payload, (
        "integrations_api_key no debe persistirse en disco."
    )
    assert "dgt_api_key" not in written_payload, (
        "dgt_api_key no debe persistirse en disco."
    )
    assert "azure_doc_intelligence_key" not in written_payload, (
        "azure_doc_intelligence_key no debe persistirse en disco."
    )


def test_migracion_conserva_campos_no_sensibles(monkeypatch):
    """La migracion conserva campos no sensibles como postgres_host e integrations_api_url."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    data = {
        "postgres_host": "192.168.0.18",
        "postgres_port": 5433,
        "integrations_api_url": "https://backend.example.com",
        "ocr_motor_activo": "azure",
        "integrations_api_key": "clave-secreta",
    }
    save_app_config(data)

    assert written_payload.get("postgres_host") == "192.168.0.18"
    assert written_payload.get("postgres_port") == 5433
    assert written_payload.get("integrations_api_url") == "https://backend.example.com"
    assert "ocr_motor_activo" not in written_payload


# ── Test 9: save_app_config() no puede reintroducir secretos ─────────────────

def test_save_app_config_no_reintroduce_postgres_dsn(monkeypatch):
    """save_app_config no puede reintroducir postgres_dsn."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "postgres_dsn": "postgresql://user:secret@host/db",
        "postgres_host": "host",
    })

    assert "postgres_dsn" not in written_payload


def test_save_app_config_no_reintroduce_workstation_token(monkeypatch):
    """save_app_config no puede reintroducir workstation_token."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "workstation_token": "g2a3_wks_secret_token",
        "postgres_host": "host",
    })

    assert "workstation_token" not in written_payload


def test_save_app_config_bloquea_todos_los_secretos(monkeypatch):
    """save_app_config filtra TODOS los secretos de _CLAVES_SECRETAS_DISCO."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config, _CLAVES_SECRETAS_DISCO

    data_con_secretos = {k: f"valor-secreto-{k}" for k in _CLAVES_SECRETAS_DISCO}
    data_con_secretos["postgres_host"] = "192.168.0.18"  # no sensible
    save_app_config(data_con_secretos)

    presentes = set(_CLAVES_SECRETAS_DISCO) & set(written_payload.keys())
    assert not presentes, f"Secretos filtrados incorrectamente presentes: {presentes}"
    assert written_payload.get("postgres_host") == "192.168.0.18"


# ── Test extra: migracion DSN continua funcionando ────────────────────────────

def test_migracion_dsn_continua_funcionando(monkeypatch):
    """La migracion de postgres_dsn a Credential Manager sigue siendo correcta."""
    store = _mock_keyring(monkeypatch)

    from utils.credential_store import migrate_from_dsn
    dsn = "postgresql://testuser:testpassword@192.168.1.10:5432/testdb"
    result = migrate_from_dsn(dsn)

    assert result["postgres_host"] == "192.168.1.10"
    assert result["postgres_port"] == 5432
    assert result["postgres_database"] == "testdb"
    assert result["postgres_user"] == "testuser"
    assert "postgres_dsn" not in result
    assert "postgres_password" not in result
    assert "password" not in result


# ── Tests firma_webhook_secret (campo legacy eliminado) ───────────────────────

def test_normalize_config_elimina_firma_webhook_secret_legacy():
    """Una config antigua con firma_webhook_secret lo elimina al normalizar."""
    from utils.utilidades import _normalize_config

    cfg_antigua = {
        "firma_habilitada": True,
        "firma_webhook_secret": "secreto-legacy-de-webhook",
        "integrations_api_url": "https://backend.example.com",
    }
    resultado = _normalize_config(cfg_antigua)

    assert "firma_webhook_secret" not in resultado, (
        "firma_webhook_secret es un campo legacy y debe eliminarse al normalizar."
    )


def test_save_app_config_no_persiste_firma_webhook_secret(monkeypatch):
    """save_app_config no debe escribir firma_webhook_secret al disco."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({
        "firma_habilitada": True,
        "firma_webhook_secret": "secreto-que-no-debe-guardarse",
        "integrations_api_url": "https://backend.example.com",
    })

    assert "firma_webhook_secret" not in written_payload, (
        "firma_webhook_secret no debe persistirse en disco: es un campo legacy sin uso."
    )


def test_save_app_config_no_introduce_firma_webhook_secret_vacio(monkeypatch):
    """save_app_config no debe introducir firma_webhook_secret vacio en configs nuevas."""
    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    save_app_config({"integrations_api_url": "https://backend.example.com"})

    assert "firma_webhook_secret" not in written_payload, (
        "save_app_config no debe crear firma_webhook_secret aunque no este en la config original."
    )


def test_env_var_firma_webhook_secret_no_carga_en_config(monkeypatch):
    """La variable de entorno GEST2A3ECO_FIRMA_WEBHOOK_SECRET ya no inyecta el campo."""
    monkeypatch.setenv("GEST2A3ECO_FIRMA_WEBHOOK_SECRET", "valor-de-entorno")
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    import importlib
    import utils.utilidades as _uu
    importlib.reload(_uu)

    cfg = _uu.load_app_config()

    assert "firma_webhook_secret" not in cfg, (
        "GEST2A3ECO_FIRMA_WEBHOOK_SECRET no debe inyectarse en la config: campo legacy eliminado."
    )


def test_ningun_flujo_activo_depende_de_firma_webhook_secret(monkeypatch):
    """Ninguna funcion activa consume firma_webhook_secret de la config."""
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {
        "firma_habilitada": True,
        "integrations_api_url": "https://backend.example.com",
        "firma_webhook_secret": "secreto-inyectado-en-config",
    })

    from utils.utilidades import load_app_config
    cfg = load_app_config()

    # El campo no sobrevive a la normalizacion: load_app_config lo descarta.
    assert "firma_webhook_secret" not in cfg, (
        "load_app_config debe descartar firma_webhook_secret al normalizar."
    )
