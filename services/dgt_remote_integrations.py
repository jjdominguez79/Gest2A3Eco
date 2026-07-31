from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests


class _BackendClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 90, session=None):
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "")
        self.timeout = timeout
        self.http = session or requests.Session()

    def request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["X-API-Key"] = self.api_key
        response = self.http.request(method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text
            raise ValueError(f"El backend rechazo la operacion: {detail or response.status_code}")
        return response


class BackendSignRequestClient:
    def __init__(self, base_url: str, api_key: str, session=None):
        self.backend = _BackendClient(base_url, api_key, session=session)
        status = self.backend.request("GET", "/api/v1/integrations/status").json()
        if not status.get("signrequest"):
            raise ValueError("SignRequest no esta configurado en el backend.")
        self.from_email = str(status.get("firma_gestor_email") or "")
        self.gestor_email = self.from_email
        self.gestor_telefono = str(status.get("firma_gestor_telefono") or "")

    def enviar_documento(self, ruta: str, firmantes: list[dict], asunto: str, mensaje: str,
                         external_id: str, callback_url: str = "", usar_sms: bool = False) -> dict:
        path = Path(ruta)
        with path.open("rb") as fh:
            response = self.backend.request(
                "POST", "/api/v1/integrations/signrequest/send",
                data={"firmantes": json.dumps(firmantes), "asunto": asunto, "mensaje": mensaje,
                      "external_id": external_id, "callback_url": callback_url,
                      "usar_sms": "true" if usar_sms else "false"},
                files={"file": (path.name, fh, "application/pdf")},
            )
        return response.json()

    def consultar(self, request_id: str) -> dict:
        return self.backend.request("GET", f"/api/v1/integrations/signrequest/{request_id}").json()

    def descargar_evidencias(self, request_id: str, destino: str, nombre_base: str) -> dict:
        estado = self.consultar(request_id)
        if estado.get("status") != "signed":
            raise ValueError("La solicitud todavia no esta completamente firmada.")
        output = Path(destino)
        output.mkdir(parents=True, exist_ok=True)
        firmado = output / f"{nombre_base}_firmado.pdf"
        registro = output / f"{nombre_base}_registro_firma.pdf"
        firmado.write_bytes(self.backend.request(
            "GET", f"/api/v1/integrations/signrequest/{request_id}/evidence/documento"
        ).content)
        registro.write_bytes(self.backend.request(
            "GET", f"/api/v1/integrations/signrequest/{request_id}/evidence/registro"
        ).content)
        return {
            "ruta_firmado": str(firmado), "ruta_registro_firma": str(registro),
            "sha256_firmado": self._sha(firmado), "sha256_registro_firma": self._sha(registro),
            "security_hash": estado.get("security_hash") or "",
            "signing_log_security_hash": estado.get("signing_log_security_hash") or "",
            "document_uuid": estado.get("document_uuid") or "",
        }

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


class BackendDatapriusClient:
    def __init__(self, base_url: str, api_key: str, session=None):
        self.backend = _BackendClient(base_url, api_key, session=session)
        status = self.backend.request("GET", "/api/v1/integrations/status").json()
        if not status.get("dataprius"):
            raise ValueError("Dataprius no esta configurado en el backend.")

    def subir_archivo(self, ruta_carpeta: str, ruta_archivo: str) -> dict:
        path = Path(ruta_archivo)
        with path.open("rb") as fh:
            response = self.backend.request(
                "POST", "/api/v1/integrations/dataprius/upload",
                data={"ruta": ruta_carpeta}, files={"file": (path.name, fh)},
            )
        return response.json()
