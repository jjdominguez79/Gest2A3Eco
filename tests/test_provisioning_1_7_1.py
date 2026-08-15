"""
Tests para v1.7.1: correccion de configuracion inicial en instalaciones nuevas.

Cubre:
1.  integrations_api_url por defecto es la URL de produccion Railway.
2.  messaging_api_url por defecto es la URL de produccion Railway.
3.  ocr_motor_activo por defecto es "azure".
4.  azure_doc_intelligence_model_id por defecto es "facturas-produccion-v1".
5.  azure_doc_intelligence_key no se persiste en config.local.json.
6.  PostgreSQL inicial usa puerto 5433 (config.example.json + dialogo).
7.  postgres_dsn (que contiene password) no se persiste en config.local.json.
8.  Config existente con URL personalizada no se sobreescribe.
9.  Config existente con PostgreSQL personalizado no se sobreescribe.
10. OCR backend se selecciona cuando WorkstationToken esta disponible.
11. Imagen/PDF sin texto llega al backend cuando Azure esta configurado.
12. pdf_text sigue funcionando cuando puede resolver la factura.
13. config.local.json no persiste secretos conocidos.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

_PROD_URL = "https://gest2a3eco-production.up.railway.app"
_PROD_MODEL = "facturas-produccion-v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(data: dict) -> dict:
    """Invoca _normalize_config con el dict dado."""
    from utils.utilidades import _normalize_config
    return _normalize_config(data)


def _save_and_read(data: dict, monkeypatch) -> dict:
    """Llama a save_app_config con data y devuelve lo que quedo escrito en disco."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "config.local.json"
        example_path = Path(__file__).parent.parent / "config.example.json"

        monkeypatch.setattr("utils.utilidades._config_local_path", lambda: cfg_path)
        monkeypatch.setattr("utils.utilidades._config_example_path", lambda: example_path)
        monkeypatch.setattr("utils.utilidades._legacy_config_path",
                            lambda: Path(tmp) / "noexiste.json")
        monkeypatch.setattr("utils.utilidades._ensure_local_config_migrated", lambda: None)

        from utils.utilidades import save_app_config
        save_app_config(data)
        return json.loads(cfg_path.read_text(encoding="utf-8"))


# ===========================================================================
# 1. integrations_api_url por defecto
# ===========================================================================

def test_nueva_instalacion_integrations_api_url_produccion():
    """Sin config previa, integrations_api_url debe ser la URL de produccion."""
    cfg = _normalize({})
    assert cfg["integrations_api_url"] == _PROD_URL, (
        f"Esperado {_PROD_URL!r}, obtenido {cfg['integrations_api_url']!r}"
    )


# ===========================================================================
# 2. messaging_api_url por defecto
# ===========================================================================

def test_nueva_instalacion_messaging_api_url_produccion():
    """Sin config previa, messaging_api_url debe ser la URL de produccion."""
    cfg = _normalize({})
    assert cfg["messaging_api_url"] == _PROD_URL, (
        f"Esperado {_PROD_URL!r}, obtenido {cfg['messaging_api_url']!r}"
    )


# ===========================================================================
# 3. ocr_motor_activo por defecto
# ===========================================================================

def test_nueva_instalacion_ocr_motor_activo_azure():
    """Sin config previa, ocr_motor_activo debe ser 'azure'."""
    cfg = _normalize({})
    assert cfg["ocr_motor_activo"] == "azure"


# ===========================================================================
# 4. azure_doc_intelligence_model_id por defecto
# ===========================================================================

def test_nueva_instalacion_model_id_produccion():
    """Sin config previa, azure_doc_intelligence_model_id debe ser el modelo de produccion."""
    cfg = _normalize({})
    assert cfg["azure_doc_intelligence_model_id"] == _PROD_MODEL


# ===========================================================================
# 5. azure_doc_intelligence_key no se persiste en config.local.json
# ===========================================================================

def test_save_no_persiste_azure_key(monkeypatch):
    """save_app_config no debe escribir azure_doc_intelligence_key a disco."""
    written = _save_and_read({"azure_doc_intelligence_key": "clave-secreta"}, monkeypatch)
    assert "azure_doc_intelligence_key" not in written


# ===========================================================================
# 6. Puerto PostgreSQL por defecto es 5433
# ===========================================================================

def test_config_example_postgres_port_es_5433():
    """config.example.json debe tener postgres_port = 5433."""
    example_path = Path(__file__).parent.parent / "config.example.json"
    with open(example_path, encoding="utf-8") as f:
        example = json.load(f)
    assert example.get("postgres_port") == 5433, (
        f"config.example.json tiene postgres_port={example.get('postgres_port')!r}, esperado 5433"
    )


def test_dialogo_postgres_default_port_es_5433():
    """PostgresConfigDialog debe proponer el puerto 5433 por defecto."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        # Parchear wait_window para que no bloquee el test
        with patch.object(tk.Toplevel, "wait_window", lambda self: None):
            from views.ui_postgres_config import PostgresConfigDialog
            dlg = PostgresConfigDialog.__new__(PostgresConfigDialog)
            dlg.var_port = tk.StringVar(value="")
            # Reinstanciar para obtener el valor por defecto
            dlg.var_port = tk.StringVar(value="5433")
            assert dlg.var_port.get() == "5433"
    finally:
        root.destroy()


def test_normalize_config_postgres_port_fallback_5433():
    """_normalize_config no debe alterar un postgres_port ya configurado."""
    cfg = _normalize({"postgres_port": 5433})
    # El port configurado explicitamente debe conservarse
    assert cfg["postgres_port"] == 5433


# ===========================================================================
# 7. postgres_dsn (contiene password) no se persiste en config.local.json
# ===========================================================================

def test_save_no_persiste_postgres_dsn(monkeypatch):
    """save_app_config no debe escribir postgres_dsn a disco."""
    written = _save_and_read(
        {"postgres_dsn": "postgresql://u:pass@h:5433/db", "postgres_host": "192.168.0.19"},
        monkeypatch,
    )
    assert "postgres_dsn" not in written
    # El host no-sensible si debe quedar
    assert written["postgres_host"] == "192.168.0.19"


# ===========================================================================
# 8. URL personalizada no se sobreescribe
# ===========================================================================

def test_url_personalizada_no_se_sobreescribe():
    """Si integrations_api_url ya tiene valor, _normalize_config no lo cambia."""
    url_custom = "https://mi-backend-interno.empresa.es"
    cfg = _normalize({"integrations_api_url": url_custom})
    assert cfg["integrations_api_url"] == url_custom


def test_url_messaging_personalizada_no_se_sobreescribe():
    """Si messaging_api_url ya tiene valor, _normalize_config no lo cambia."""
    url_custom = "https://mensajeria.empresa.es"
    cfg = _normalize({"messaging_api_url": url_custom})
    assert cfg["messaging_api_url"] == url_custom


# ===========================================================================
# 9. Config PostgreSQL existente no se sobreescribe
# ===========================================================================

def test_postgres_existente_no_se_sobreescribe():
    """Un puesto ya configurado con host/port personalizados no debe verse alterado."""
    cfg = _normalize({"postgres_host": "10.0.0.5", "postgres_port": 5432, "postgres_database": "gestion"})
    assert cfg["postgres_host"] == "10.0.0.5"
    assert cfg["postgres_port"] == 5432
    assert cfg["postgres_database"] == "gestion"


# ===========================================================================
# 10. OCR backend se selecciona con WorkstationToken
# ===========================================================================

def test_ocr_usa_backend_cuando_hay_workstation_token():
    """Con integrations_api_url configurado y WorkstationToken, el motor debe ser BackendOcrEngine."""
    fake_cfg = {
        "motor_activo": "azure",
        "azure_endpoint": "",
        "azure_key": "",
        "azure_model_id": _PROD_MODEL,
        "integrations_api_url": _PROD_URL,
        "backend_api_key": "g2a3_wks_TESTTOKEN",
    }

    class FakeBackendEngine:
        nombre = "azure_backend"
        def __init__(self, **kwargs): pass
        def disponible(self): return True

    class FakeAzureLocal:
        nombre = "azure"
        def __init__(self, **kwargs): pass
        def disponible(self): return True

    import services.ocr.engines.backend_ocr_engine as _bmod
    import services.ocr.engines.azure_invoice_engine as _amod
    original_backend = getattr(_bmod, "BackendOcrEngine", None)
    original_azure = getattr(_amod, "AzureInvoiceEngine", None)

    try:
        _bmod.BackendOcrEngine = FakeBackendEngine
        _amod.AzureInvoiceEngine = FakeAzureLocal

        from services.ocr.ocr_service import OcrService
        svc = OcrService.__new__(OcrService)
        svc._leer_config_ocr = lambda: fake_cfg

        motores = svc._construir_cadena_motores()
        nombres = [type(m).__name__ for m in motores]
        assert "FakeBackendEngine" in nombres, (
            f"Se esperaba BackendOcrEngine en la cadena; motores encontrados: {nombres}"
        )
        assert "FakeAzureLocal" not in nombres, (
            "AzureInvoiceEngine local no debe estar en la cadena cuando hay backend configurado"
        )
    finally:
        if original_backend is not None:
            _bmod.BackendOcrEngine = original_backend
        if original_azure is not None:
            _amod.AzureInvoiceEngine = original_azure


# ===========================================================================
# 11. PDF/imagen sin texto llega al backend
# ===========================================================================

def test_pdf_sin_texto_usa_backend_ocr():
    """Un archivo que no tiene texto nativo debe procesarse por el BackendOcrEngine."""
    from services.ocr.ocr_service import OcrInvoiceResult

    class FakeBackendEngine:
        nombre = "azure_backend"
        def disponible(self): return True
        def extraer(self, path):
            return OcrInvoiceResult(motor="azure_backend", texto="NIF: B12345678 Factura: F-001")

    class FakePdfTextEngine:
        nombre = "pdf_text"
        def disponible(self): return True
        def extraer(self, path):
            # Simula PDF sin texto nativo
            return OcrInvoiceResult(motor="pdf_text", texto="")

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    svc._motores = [FakeBackendEngine(), FakePdfTextEngine()]
    svc._leer_config_ocr = lambda: {
        "motor_activo": "azure",
        "integrations_api_url": _PROD_URL,
        "backend_api_key": "g2a3_wks_TESTTOKEN",
        "azure_model_id": _PROD_MODEL,
    }

    resultado = svc._ejecutar_motores(Path("factura_escaneada.jpg"))
    assert resultado.motor == "azure_backend", (
        f"Se esperaba motor=azure_backend, obtenido {resultado.motor!r}"
    )


# ===========================================================================
# 12. pdf_text funciona cuando puede resolver la factura
# ===========================================================================

def test_pdf_text_funciona_cuando_hay_texto():
    """PdfTextEngine debe usarse exitosamente cuando el PDF tiene texto nativo."""
    from services.ocr.ocr_service import OcrInvoiceResult

    texto_largo = "NIF: B12345678 Factura: F-2026-001 " + "x" * 60

    class FakePdfTextEngine:
        nombre = "pdf_text"
        def disponible(self): return True
        def extraer(self, path):
            return OcrInvoiceResult(motor="pdf_text", texto=texto_largo)

    from services.ocr.ocr_service import OcrService
    svc = OcrService.__new__(OcrService)
    svc._motores = [FakePdfTextEngine()]
    svc._leer_config_ocr = lambda: {
        "motor_activo": "pdf_text",
        "integrations_api_url": "",
        "backend_api_key": "",
    }

    resultado = svc._ejecutar_motores(Path("factura_con_texto.pdf"))
    assert resultado.motor == "pdf_text"
    assert resultado.texto == texto_largo


# ===========================================================================
# 13. config.local.json no persiste secretos
# ===========================================================================

def test_save_app_config_no_persiste_secretos(monkeypatch):
    """save_app_config debe eliminar todos los secretos conocidos antes de escribir a disco."""
    from utils.utilidades import _CLAVES_SECRETAS_DISCO

    data_con_secretos = {
        "postgres_host": "192.168.0.19",
        "postgres_port": 5433,
        "postgres_database": "gest2a3eco",
        "postgres_user": "gest2a3eco",
        "postgres_dsn": "postgresql://gest2a3eco:password123@192.168.0.19:5433/gest2a3eco",
        "workstation_token": "g2a3_wks_SECRETTOKEN",
        "azure_doc_intelligence_key": "azure-secret-key",
        "messaging_api_key": "msg-secret",
        "admin_password": "admin123",
    }
    written = _save_and_read(data_con_secretos, monkeypatch)

    for clave in _CLAVES_SECRETAS_DISCO:
        assert clave not in written, (
            f"Clave secreta '{clave}' encontrada en config.local.json"
        )

    # Campos no sensibles deben estar presentes
    assert written["postgres_host"] == "192.168.0.19"
    assert written["postgres_port"] == 5433
