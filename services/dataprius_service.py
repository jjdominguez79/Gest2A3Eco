"""
OBSOLETO: Las credenciales Dataprius residen ahora exclusivamente en el backend.
El escritorio utiliza BackendDatapriusClient (services/dgt_remote_integrations.py).
Este modulo se conserva unicamente para tests y migracion controlada.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import requests

warnings.warn(
    "dataprius_service.DatapriusClient esta obsoleto. "
    "Usa BackendDatapriusClient de services.dgt_remote_integrations.",
    DeprecationWarning,
    stacklevel=2,
)


class DatapriusClient:
    """Cliente minimo para almacenar documentos en Dataprius API REST v2."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://api.v2.dataprius.com",
        timeout: int = 60,
        session=None,
        _allow_legacy: bool = False,
    ):
        if not _allow_legacy:
            raise RuntimeError(
                "DatapriusClient esta obsoleto y no puede usarse en produccion. "
                "Usa BackendDatapriusClient de services.dgt_remote_integrations."
            )
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = int(timeout)
        self._http = session or requests.Session()
        self._access_token = ""
        if not self.client_id or not self.client_secret:
            raise ValueError("Configura dataprius_api_key y dataprius_api_secret.")

    def obtener_carpeta(self, ruta: str) -> dict | None:
        try:
            data = self._request("POST", "/folders/getpath", json={"Path": ruta})
        except ValueError as exc:
            if "404" in str(exc) or "PATH_NOT_EXISTS" in str(exc):
                return None
            raise
        items = data.get("data") or []
        return dict(items[0]) if items else None

    def asegurar_carpeta(self, ruta: str) -> dict:
        existente = self.obtener_carpeta(ruta)
        if existente:
            return existente
        data = self._request("POST", "/folders/createpath", json={"Path": ruta})
        items = data.get("data") or []
        if not items:
            raise ValueError("Dataprius no devolvio la carpeta creada.")
        return dict(items[-1])

    def subir_archivo(self, ruta_carpeta: str, ruta_archivo: str) -> dict:
        path = Path(ruta_archivo)
        if not path.is_file():
            raise FileNotFoundError(f"No se encuentra el archivo para Dataprius: {path}")
        carpeta = self.asegurar_carpeta(ruta_carpeta)
        with path.open("rb") as fh:
            data = self._request(
                "POST",
                "/files/upload",
                data={"IDFolder": carpeta["ID"]},
                files={"file": (path.name, fh)},
            )
        archivo = dict(data.get("data") or {})
        if not archivo.get("ID"):
            raise ValueError("Dataprius no devolvio el identificador del archivo.")
        return {
            "provider": "dataprius",
            "id": archivo["ID"],
            "folder_id": archivo.get("Folder") or carpeta["ID"],
            "nombre": archivo.get("Name") or path.name,
            "ruta": ruta_carpeta,
            "tamano": archivo.get("Size"),
        }

    def _token(self, renovar: bool = False) -> str:
        if self._access_token and not renovar:
            return self._access_token
        response = self._http.request(
            "GET",
            f"{self.base_url}/oauth/token",
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_status(response)
        self._access_token = str(response.json().get("access_token") or "")
        if not self._access_token:
            raise ValueError("Dataprius no devolvio un token de acceso.")
        return self._access_token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = dict(kwargs.pop("headers", {}))
        headers["Accept"] = "application/json"
        headers["Authorization"] = f"Bearer {self._token()}"
        response = self._http.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self._token(renovar=True)}"
            response = self._http.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        self._raise_for_status(response)
        return response.json() if response.content else {}

    @staticmethod
    def _raise_for_status(response) -> None:
        if response.status_code < 400:
            return
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise ValueError(f"Dataprius rechazo la operacion ({response.status_code}): {detail}")
