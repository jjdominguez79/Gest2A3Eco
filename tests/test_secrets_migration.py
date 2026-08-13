"""
Tests de migracion de secretos: backend config, OCR endpoint, workstation auth,
redaccion de secretos en logs y migracion de postgres_dsn.
"""
from __future__ import annotations

import os
import hashlib

import pytest

# ── Backend config ────────────────────────────────────────────────────────────

def test_backend_config_lee_variables_azure_ocr(monkeypatch):
    """get_settings() debe leer las variables AZURE_DOC_INTELLIGENCE_*."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.cognitiveservices.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "test-key-123")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_MODEL_ID", "mi-modelo-personalizado")
    monkeypatch.setenv("AZURE_OCR_TRAINING_CONNECTION_STRING", "DefaultEndpointsProtocol=https;...")
    monkeypatch.setenv("AZURE_OCR_TRAINING_CONTAINER", "mi-contenedor")

    from backend.api.config import get_settings
    cfg = get_settings()

    assert cfg.azure_doc_intelligence_endpoint == "https://test.cognitiveservices.azure.com/"
    assert cfg.azure_doc_intelligence_key == "test-key-123"
    assert cfg.azure_doc_intelligence_model_id == "mi-modelo-personalizado"
    assert cfg.azure_ocr_training_connection_string == "DefaultEndpointsProtocol=https;..."
    assert cfg.azure_ocr_training_container == "mi-contenedor"


def test_backend_config_sin_azure_key_ocr_no_disponible(monkeypatch):
    """Si AZURE_DOC_INTELLIGENCE_KEY esta vacio, ocr_available() devuelve False."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)

    from backend.api.ocr_service import ocr_available
    assert ocr_available() is False


def test_backend_config_con_azure_key_ocr_disponible(monkeypatch):
    """Con AZURE_DOC_INTELLIGENCE_KEY configurado, ocr_available() devuelve True."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://endpoint.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "mi-clave-secreta")

    from backend.api.ocr_service import ocr_available
    assert ocr_available() is True


# ── OCR endpoint ──────────────────────────────────────────────────────────────

def test_ocr_endpoint_sin_credenciales_devuelve_503(monkeypatch):
    """El endpoint OCR debe devolver 503 si Azure no esta configurado."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    pdf_bytes = b"%PDF-1.4 test"
    response = client.post(
        "/api/v1/ocr/invoices/analyze",
        headers={"X-API-Key": "test-internal-key"},
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"model_id": ""},
    )
    assert response.status_code == 503


def test_ocr_endpoint_sin_autenticacion_devuelve_401(monkeypatch):
    """El endpoint OCR debe requerir autenticacion."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/ocr/invoices/analyze",
        files={"file": ("test.pdf", b"%PDF test", "application/pdf")},
    )
    assert response.status_code == 401


def test_ocr_endpoint_tipo_no_permitido_devuelve_415(monkeypatch):
    """El endpoint OCR debe rechazar tipos de fichero no admitidos."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "cualquier-clave")

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/ocr/invoices/analyze",
        headers={"X-API-Key": "test-internal-key"},
        files={"file": ("virus.exe", b"\x4D\x5A ejecutable", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_ocr_endpoint_fichero_demasiado_grande(monkeypatch):
    """El endpoint OCR debe rechazar ficheros mayores de 20 MB."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "cualquier-clave")

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    big_content = b"A" * (21 * 1024 * 1024)
    response = client.post(
        "/api/v1/ocr/invoices/analyze",
        headers={"X-API-Key": "test-internal-key"},
        files={"file": ("grande.pdf", big_content, "application/pdf")},
    )
    assert response.status_code == 413


def test_ocr_endpoint_con_azure_mock_devuelve_resultado(monkeypatch):
    """El endpoint OCR con Azure simulado debe devolver estructura OcrInvoiceResult."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "test-key")

    expected_result = {
        "proveedor_nombre": "Empresa Test SL",
        "proveedor_nif": "B12345678",
        "numero_factura": "F-001",
        "fecha_factura": "2024-01-15",
        "fecha_vencimiento": "",
        "total": 121.0,
        "base_total": 100.0,
        "iva_total": 21.0,
        "retencion_total": 0.0,
        "bases_iva": [],
        "retenciones": [],
        "texto": "texto extraido",
        "raw_json": {},
        "confianza": 0.9,
        "motor": "azure_backend",
        "errores": [],
    }

    import backend.api.ocr_service as ocr_module
    monkeypatch.setattr(ocr_module, "analyze_invoice", lambda *a, **kw: expected_result)

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/ocr/invoices/analyze",
        headers={"X-API-Key": "test-internal-key"},
        files={"file": ("factura.pdf", b"%PDF-1.4", "application/pdf")},
        data={"model_id": ""},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["proveedor_nif"] == "B12345678"
    assert data["motor"] == "azure_backend"
    # Verificar que NO hay credenciales en la respuesta
    response_text = response.text
    assert "test-key" not in response_text
    assert "AZURE" not in response_text


def test_integrations_status_incluye_campo_ocr(monkeypatch):
    """GET /api/v1/integrations/status debe incluir el campo 'ocr'."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "cualquier-clave")

    from fastapi.testclient import TestClient
    from backend.api.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/api/v1/integrations/status",
        headers={"X-API-Key": "test-internal-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "ocr" in data
    assert data["ocr"] is True


# ── Workstation auth ──────────────────────────────────────────────────────────

def test_workstation_token_hash_es_sha256():
    """El hash de un token debe ser SHA-256."""
    from backend.api.security import hash_token, new_workstation_token
    token = new_workstation_token()
    assert token.startswith("g2a3_wks_")
    h = hash_token(token)
    expected = hashlib.sha256(token.encode()).hexdigest()
    assert h == expected
    assert len(h) == 64


def test_workstation_token_formato():
    """El token de puesto debe tener el prefijo correcto."""
    from backend.api.security import new_workstation_token
    for _ in range(5):
        token = new_workstation_token()
        assert token.startswith("g2a3_wks_")
        assert len(token) > 20


def test_require_internal_key_acepta_clave_correcta(monkeypatch):
    """require_internal_key debe aceptar la clave interna correcta."""
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "mi-clave-interna")

    from backend.api.security import require_internal_key
    result = require_internal_key("mi-clave-interna")
    assert result == "gest2a3eco"


def test_require_internal_key_rechaza_clave_incorrecta(monkeypatch):
    """require_internal_key debe rechazar una clave incorrecta."""
    from fastapi import HTTPException
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "mi-clave-interna")

    from backend.api.security import require_internal_key
    with pytest.raises(HTTPException) as exc_info:
        require_internal_key("clave-incorrecta")
    assert exc_info.value.status_code == 401


# ── Redaccion de secretos en logs ─────────────────────────────────────────────

def test_redact_config_oculta_claves_sensibles():
    """redact_config_for_logging debe ocultar passwords, keys, tokens, etc."""
    from utils.utilidades import redact_config_for_logging

    cfg = {
        "integrations_api_url": "https://mi-backend.es",
        "integrations_api_key": "super-secreto",
        "workstation_token": "g2a3_wks_abc123",
        "postgres_dsn": "postgresql://u:pass@host/db",
        "azure_doc_intelligence_key": "azure-key-xyz",
        "signrequest_token": "sr-token",
        "a3_base_path": "C:\\A3ECO",
        "firma_habilitada": True,
        "firma_max_mb": 15,
    }

    redacted = redact_config_for_logging(cfg)

    # Valores no sensibles deben permanecer
    assert redacted["integrations_api_url"] == "https://mi-backend.es"
    assert redacted["a3_base_path"] == "C:\\A3ECO"
    assert redacted["firma_habilitada"] is True
    assert redacted["firma_max_mb"] == 15

    # Valores sensibles deben ser '***'
    assert redacted["integrations_api_key"] == "***"
    assert redacted["workstation_token"] == "***"
    assert redacted["postgres_dsn"] == "***"
    assert redacted["azure_doc_intelligence_key"] == "***"
    assert redacted["signrequest_token"] == "***"


def test_redact_config_anida_dicts():
    """redact_config_for_logging debe procesar dicts anidados."""
    from utils.utilidades import redact_config_for_logging

    cfg = {
        "microsoft_graph": {
            "tenant_id": "abc-123",
            "client_secret": "muy-secreto",
        }
    }
    redacted = redact_config_for_logging(cfg)
    assert redacted["microsoft_graph"]["tenant_id"] == "abc-123"
    assert redacted["microsoft_graph"]["client_secret"] == "***"


def test_redact_dsn_oculta_password():
    """redact_dsn debe sustituir la password en el DSN."""
    from utils.utilidades import redact_dsn

    dsn = "postgresql://gest2a3eco:mi_password_secreta@192.168.0.18:5433/gest2a3eco"
    redacted = redact_dsn(dsn)
    assert "mi_password_secreta" not in redacted
    assert "***" in redacted
    assert "192.168.0.18" in redacted
    assert "gest2a3eco" in redacted


# ── Migracion de postgres_dsn ─────────────────────────────────────────────────

def test_migrate_from_dsn_extrae_credenciales(monkeypatch):
    """migrate_from_dsn debe extraer host/port/database/user y devolver config limpia."""
    stored = {}

    def mock_store(username: str, password: str) -> bool:
        stored["user"] = username
        stored["password"] = password
        return True

    monkeypatch.setattr("utils.credential_store.store_postgres_credentials", mock_store)

    from utils.credential_store import migrate_from_dsn
    dsn = "postgresql://miusuario:mipassword@192.168.0.18:5433/gest2a3eco"
    result = migrate_from_dsn(dsn)

    assert result["postgres_host"] == "192.168.0.18"
    assert result["postgres_port"] == 5433
    assert result["postgres_database"] == "gest2a3eco"
    assert result["postgres_user"] == "miusuario"
    assert result["database_engine"] == "postgres"
    # La password NO debe estar en el resultado
    assert "postgres_password" not in result
    assert "password" not in result
    # Debe haberse almacenado en keyring
    assert stored["user"] == "miusuario"
    assert stored["password"] == "mipassword"


def test_migrate_from_dsn_password_con_arroba(monkeypatch):
    """migrate_from_dsn debe extraer correctamente la password si contiene '@'."""
    stored = {}

    def _fake_set(service, username, value):
        stored[(service, username)] = value

    def _fake_get(service, username):
        return stored.get((service, username))

    import sys
    class _FakeKeyring:
        set_password = staticmethod(_fake_set)
        get_password = staticmethod(_fake_get)
        @staticmethod
        def delete_password(s, u): pass

    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    from utils import credential_store
    monkeypatch.setattr(credential_store, "_keyring_available", lambda: True)

    from utils.credential_store import migrate_from_dsn
    # Password contiene '@' sin URL-encodear
    dsn = "postgresql://gest2a3eco:M@rio05072011_@192.168.0.18:5433/gest2a3eco"
    result = migrate_from_dsn(dsn)

    assert result, "La migracion debe tener exito con password que contiene '@'"
    assert result["postgres_host"] == "192.168.0.18"
    assert result["postgres_port"] == 5433
    assert result["postgres_database"] == "gest2a3eco"
    assert result["postgres_user"] == "gest2a3eco"
    # Verificar que la password completa (con @) fue almacenada
    from utils.credential_store import SERVICE_POSTGRES, USERNAME_POSTGRES
    stored_value = stored.get((SERVICE_POSTGRES, USERNAME_POSTGRES), "")
    assert "M@rio05072011_" in stored_value, "La password con '@' debe almacenarse completa"


def test_migrate_from_dsn_sin_password_no_almacena(monkeypatch):
    """Si el DSN no tiene password, no debe guardar nada en keyring."""
    stored = {}

    def mock_store(username: str, password: str) -> bool:
        stored["called"] = True
        return True

    monkeypatch.setattr("utils.credential_store.store_postgres_credentials", mock_store)

    from utils.credential_store import migrate_from_dsn
    dsn = "postgresql://miusuario@192.168.0.18:5433/gest2a3eco"
    result = migrate_from_dsn(dsn)
    assert "called" not in stored


def test_credential_store_get_sin_keyring_devuelve_none(monkeypatch):
    """Si keyring no esta disponible, get_postgres_credentials devuelve None."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "keyring":
            raise ImportError("keyring no instalado")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from utils import credential_store
    monkeypatch.setattr(credential_store, "_keyring_available", lambda: False)

    result = credential_store.get_postgres_credentials()
    assert result is None


def test_config_ejemplo_no_contiene_secretos():
    """config.example.json no debe contener claves de secretos conocidos."""
    import json
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "config.example.json"
    if not config_path.exists():
        pytest.skip("config.example.json no encontrado")

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    forbidden_keys = {
        "azure_doc_intelligence_key",
        "azure_storage_connection_string",
        "dataprius_api_key",
        "dataprius_api_secret",
        "signrequest_token",
        "signrequest_from_email",
        "firma_permitir_cliente_local",
        "workstation_token",
        "integrations_api_key",
        "dgt_api_key",
        "messaging_api_key",
        "messaging_device_token",
        "admin_password",
        "initial_admin_password",
        "desmarcar_generadas_password",
    }
    present = forbidden_keys & set(cfg.keys())
    assert not present, f"Claves de secretos encontradas en config.example.json: {present}"


# ── Nuevos tests: credential store generico ───────────────────────────────────

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

    import sys
    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    from utils import credential_store
    monkeypatch.setattr(credential_store, "_keyring_available", lambda: True)
    return store


def test_store_get_workstation_token(monkeypatch):
    """Round-trip workstation token en almacen mock."""
    _mock_keyring(monkeypatch)
    from utils.credential_store import store_workstation_token, get_workstation_token

    assert get_workstation_token() is None
    ok = store_workstation_token("g2a3_wks_abc123")
    assert ok is True
    assert get_workstation_token() == "g2a3_wks_abc123"


def test_store_get_integrations_api_key(monkeypatch):
    """Round-trip integrations API key en almacen mock."""
    _mock_keyring(monkeypatch)
    from utils.credential_store import store_integrations_api_key, get_integrations_api_key

    assert get_integrations_api_key() is None
    ok = store_integrations_api_key("clave-api-integraciones")
    assert ok is True
    assert get_integrations_api_key() == "clave-api-integraciones"


def test_store_get_azure_doc_key(monkeypatch):
    """Round-trip Azure Doc Intelligence key en almacen mock."""
    _mock_keyring(monkeypatch)
    from utils.credential_store import store_azure_doc_key, get_azure_doc_key

    assert get_azure_doc_key() is None
    ok = store_azure_doc_key("azure-key-xyz")
    assert ok is True
    assert get_azure_doc_key() == "azure-key-xyz"


def test_store_get_desmarcar_password(monkeypatch):
    """Round-trip desmarcar password en almacen mock."""
    _mock_keyring(monkeypatch)
    from utils.credential_store import store_desmarcar_password, get_desmarcar_password

    assert get_desmarcar_password() is None
    ok = store_desmarcar_password("mipassword")
    assert ok is True
    assert get_desmarcar_password() == "mipassword"


def test_migrate_workstation_token_from_config(monkeypatch):
    """La migracion extrae workstation_token de config y lo guarda en Credential Manager."""
    _mock_keyring(monkeypatch)
    from utils.credential_store import store_workstation_token, get_workstation_token

    stored_calls = []
    original_store = store_workstation_token.__wrapped__ if hasattr(store_workstation_token, "__wrapped__") else None

    # Simular la logica de migracion de main.py directamente
    cfg = {"workstation_token": "g2a3_wks_test123", "other_key": "value"}

    token = str(cfg.get("workstation_token") or "").strip()
    assert token == "g2a3_wks_test123"

    ok = store_workstation_token(token)
    assert ok is True
    cfg.pop("workstation_token", None)

    assert "workstation_token" not in cfg
    assert get_workstation_token() == "g2a3_wks_test123"


def test_save_app_config_no_persists_secrets(monkeypatch):
    """save_app_config no debe escribir claves secretas en disco."""
    import json

    written_payload = {}

    def _fake_write(path, payload):
        written_payload.update(payload)

    monkeypatch.setattr("utils.utilidades._write_json_file", _fake_write)
    monkeypatch.setattr("utils.utilidades._load_json_file", lambda p: {})

    from utils.utilidades import save_app_config

    data = {
        "postgres_host": "192.168.0.18",
        "workstation_token": "g2a3_wks_secret",
        "integrations_api_key": "api-key-secret",
        "azure_doc_intelligence_key": "azure-key-secret",
        "azure_storage_connection_string": "DefaultEndpointsProtocol=...",
        "admin_password": "adminpass",
        "desmarcar_generadas_password": "desmarcar123",
        "messaging_device_token": "device-tok",
    }
    save_app_config(data)

    secret_keys = {
        "workstation_token", "integrations_api_key", "azure_doc_intelligence_key",
        "azure_storage_connection_string", "admin_password", "desmarcar_generadas_password",
        "messaging_device_token",
    }
    present = secret_keys & set(written_payload.keys())
    assert not present, f"Claves secretas encontradas en config guardado: {present}"
    # La clave no sensible si debe estar
    assert written_payload.get("postgres_host") == "192.168.0.18"


def test_dataprius_client_raises_on_direct_use():
    """DatapriusClient debe lanzar RuntimeError si se instancia sin _allow_legacy."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from services.dataprius_service import DatapriusClient

    with pytest.raises(RuntimeError, match="obsoleto"):
        DatapriusClient("key", "secret")


def test_signrequest_client_raises_on_direct_use():
    """SignRequestClient debe lanzar RuntimeError si se instancia sin _allow_legacy."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from services.signrequest_service import SignRequestClient

    with pytest.raises(RuntimeError, match="obsoleto"):
        SignRequestClient("token", "from@example.com")


def test_ocr_no_local_azure_fallback_with_backend(monkeypatch):
    """Con backend configurado, AzureInvoiceEngine local no debe anadirse a la cadena."""
    from unittest.mock import MagicMock, patch

    fake_cfg = {
        "motor_activo": "azure",
        "azure_endpoint": "https://test.azure.com",
        "azure_key": "local-key",
        "azure_model_id": "modelo",
        "integrations_api_url": "https://backend.example.com",
        "integrations_api_key": "api-key",
    }

    azure_local_instantiated = []

    class FakeBackendEngine:
        nombre = "azure_backend"
        def disponible(self): return True

    class FakeAzureLocal:
        nombre = "azure"
        def __init__(self, **kwargs):
            azure_local_instantiated.append(kwargs)
        def disponible(self): return True

    with patch("services.ocr.ocr_service.OcrService._leer_config_ocr", return_value=fake_cfg):
        with patch("services.ocr.engines.backend_ocr_engine.BackendOcrEngine", FakeBackendEngine):
            with patch("services.ocr.engines.azure_invoice_engine.AzureInvoiceEngine", FakeAzureLocal):
                from services.ocr.ocr_service import OcrService
                svc = OcrService.__new__(OcrService)
                svc._leer_config_ocr = lambda: fake_cfg
                # Forzar que BackendOcrEngine se importe desde el modulo correcto
                import services.ocr.engines.backend_ocr_engine as _bmod
                import services.ocr.engines.azure_invoice_engine as _amod
                _bmod.BackendOcrEngine = FakeBackendEngine
                _amod.AzureInvoiceEngine = FakeAzureLocal
                motores = svc._construir_cadena_motores()

    nombres = [type(m).__name__ for m in motores]
    assert "FakeAzureLocal" not in nombres, "AzureInvoiceEngine local no debe usarse con backend configurado"


def test_redact_covers_all_secret_types():
    """redact_config_for_logging debe ocultar todos los tipos de secretos conocidos."""
    from utils.utilidades import redact_config_for_logging

    cfg = {
        "workstation_token": "g2a3_wks_abc",
        "integrations_api_key": "key123",
        "dgt_api_key": "key456",
        "azure_doc_intelligence_key": "azure-key",
        "azure_storage_connection_string": "DefaultEndpoints...",
        "messaging_api_key": "msg-key",
        "messaging_device_token": "device-tok",
        "admin_password": "adminpass",
        "desmarcar_generadas_password": "desp",
        "postgres_host": "192.168.0.18",
    }
    redacted = redact_config_for_logging(cfg)

    for k in cfg:
        if k == "postgres_host":
            assert redacted[k] == "192.168.0.18"
        else:
            assert redacted[k] == "***", f"'{k}' no fue redactado"


def test_pyinstaller_spec_contiene_keyring_hiddenimports():
    """Gest2A3Eco.spec debe incluir keyring en hiddenimports."""
    from pathlib import Path
    spec_path = Path(__file__).parent.parent / "Gest2A3Eco.spec"
    if not spec_path.exists():
        pytest.skip("Gest2A3Eco.spec no encontrado")
    contenido = spec_path.read_text(encoding="utf-8")
    assert "keyring" in contenido, "keyring debe aparecer en hiddenimports del .spec"
    assert "keyring.backends.Windows" in contenido, "keyring.backends.Windows debe estar en hiddenimports"
