"""
Motor OCR: proxy hacia el backend Gest2A3Eco (Azure Document Intelligence).

Cuando el backend esta configurado (integrations_api_url), el escritorio
delega el OCR al backend en lugar de llamar a Azure directamente.
Las credenciales Azure residen exclusivamente en el backend.
"""
from __future__ import annotations
import logging
from pathlib import Path
from services.ocr.base import OcrEngineBase
from services.ocr.types import OcrInvoiceResult

logger = logging.getLogger(__name__)


class BackendOcrEngine(OcrEngineBase):
    """Motor OCR que delega en el backend FastAPI."""

    def __init__(self, base_url: str, api_key: str, model_id: str = "", timeout: int = 120):
        self._base_url = str(base_url or "").rstrip("/")
        self._api_key = str(api_key or "")
        self._model_id = str(model_id or "")
        self._timeout = timeout
        self._disponible: bool | None = None  # cache

    @property
    def nombre(self) -> str:
        return "azure_backend"

    def disponible(self) -> bool:
        if not self._base_url or not self._api_key:
            return False
        if self._disponible is not None:
            return self._disponible
        try:
            import requests
            resp = requests.get(
                f"{self._base_url}/api/v1/integrations/status",
                headers={"X-API-Key": self._api_key},
                timeout=10,
            )
            data = resp.json() if resp.status_code == 200 else {}
            self._disponible = bool(data.get("ocr"))
        except Exception:
            self._disponible = False
        return self._disponible

    def extraer(self, path: Path) -> OcrInvoiceResult:
        if not path.exists():
            return self._error_result(f"Fichero no encontrado: {path}")
        try:
            import requests
            with path.open("rb") as fh:
                resp = requests.post(
                    f"{self._base_url}/api/v1/ocr/invoices/analyze",
                    headers={"X-API-Key": self._api_key},
                    data={"model_id": self._model_id},
                    files={"file": (path.name, fh)},
                    timeout=self._timeout,
                )
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                return self._error_result(f"Backend OCR error {resp.status_code}: {detail}")
            return OcrInvoiceResult.from_dict(resp.json())
        except Exception as exc:
            return self._error_result(f"Error llamando al backend OCR: {exc}")
