from __future__ import annotations

import base64
from pathlib import Path

import requests

from backend.dgt_api.config import get_settings


class ProviderError(RuntimeError):
    pass


class SignRequestBackend:
    def __init__(self, session=None):
        cfg = get_settings()
        self.token = cfg.signrequest_token
        self.from_email = cfg.signrequest_from_email
        self.base_url = cfg.signrequest_base_url
        self.http = session or requests.Session()
        if not self.token or not self.from_email:
            raise ProviderError("SignRequest no esta configurado en el backend.")

    def _json(self, method: str, url: str, **kwargs) -> dict:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Token {self.token}"
        response = self.http.request(method, url, headers=headers, timeout=60, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(f"SignRequest rechazo la operacion ({response.status_code}).")
        return response.json() if response.content else {}

    def enviar(self, contenido: bytes, nombre: str, firmantes: list[dict], asunto: str, mensaje: str,
               external_id: str, callback_url: str = "", usar_sms: bool = False) -> dict:
        signers = []
        for firmante in firmantes:
            email = str(firmante.get("email") or "").strip()
            if not email:
                raise ProviderError("Todos los firmantes deben tener email.")
            item = {"email": email, "needs_to_sign": True, "order": int(firmante.get("order") or 0)}
            telefono = str(firmante.get("telefono") or "").strip()
            if usar_sms and telefono:
                item["verify_phone_number"] = telefono
            signers.append(item)
        payload = {
            "file_from_content": base64.b64encode(contenido).decode("ascii"),
            "file_from_content_name": Path(nombre).name,
            "name": asunto,
            "external_id": external_id,
            "from_email": self.from_email,
            "message": mensaje,
            "signers": signers,
            "send_reminders": True,
        }
        if callback_url:
            payload["events_callback_url"] = callback_url
        result = self._json("POST", f"{self.base_url}/signrequest-quick-create/", json=payload)
        return {
            "uuid": result.get("uuid") or result.get("signrequest_uuid") or "",
            "document": result.get("document") or "",
            "status": result.get("status") or "sent",
        }

    def consultar(self, request_id: str) -> dict:
        solicitud = self._json("GET", f"{self.base_url}/signrequests/{request_id}/")
        document_url = str(solicitud.get("document") or "")
        if not document_url:
            return {"status": "desconocido"}
        documento = self._json("GET", document_url)
        log = documento.get("signing_log") or {}
        estado = "signed" if documento.get("pdf") and log.get("pdf") else str(documento.get("status") or "sent")
        return {
            "status": estado,
            "document_uuid": documento.get("uuid") or "",
            "security_hash": documento.get("security_hash") or "",
            "signing_log_security_hash": log.get("security_hash") or "",
            "signed_pdf_url": documento.get("pdf") or "",
            "signing_log_url": log.get("pdf") or "",
        }

    def cancelar(self, request_id: str) -> dict:
        estado = self.consultar(request_id)
        if str(estado.get("status") or "").lower() in {"signed", "completed"}:
            raise ProviderError("La solicitud ya esta firmada y no se puede anular.")
        return self._json(
            "POST", f"{self.base_url}/signrequests/{request_id}/cancel_signrequest/"
        )

    def evidencia(self, request_id: str, tipo: str) -> bytes:
        estado = self.consultar(request_id)
        if estado.get("status") != "signed":
            raise ProviderError("La solicitud todavia no esta completamente firmada.")
        url = estado["signed_pdf_url"] if tipo == "documento" else estado["signing_log_url"]
        response = self.http.get(url, timeout=60)
        if response.status_code >= 400:
            raise ProviderError(f"No se pudo descargar la evidencia ({response.status_code}).")
        return response.content


class DatapriusBackend:
    def __init__(self, session=None):
        cfg = get_settings()
        self.client_id = cfg.dataprius_api_key
        self.client_secret = cfg.dataprius_api_secret
        self.base_url = cfg.dataprius_base_url
        self.base_path = cfg.dataprius_base_path
        self.http = session or requests.Session()
        self.access_token = ""
        if not self.client_id or not self.client_secret:
            raise ProviderError("Dataprius no esta configurado en el backend.")

    def _token(self, renovar=False) -> str:
        if self.access_token and not renovar:
            return self.access_token
        response = self.http.get(
            f"{self.base_url}/oauth/token", auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"}, timeout=60,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Dataprius rechazo la autenticacion ({response.status_code}).")
        self.access_token = str(response.json().get("access_token") or "")
        if not self.access_token:
            raise ProviderError("Dataprius no devolvio un token de acceso.")
        return self.access_token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token()}"}
        response = self.http.request(method, f"{self.base_url}{path}", headers=headers, timeout=60, **kwargs)
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self._token(True)}"
            response = self.http.request(method, f"{self.base_url}{path}", headers=headers, timeout=60, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(f"Dataprius rechazo la operacion ({response.status_code}).")
        return response.json() if response.content else {}

    def subir(self, ruta: str, nombre: str, contenido: bytes) -> dict:
        ruta_final = str(ruta or "").strip().strip("/")
        if self.base_path and not ruta_final.upper().startswith(self.base_path.upper()):
            ruta_final = f"{self.base_path}/{ruta_final}" if ruta_final else self.base_path
        data = self._request("POST", "/folders/getpath", json={"Path": ruta_final})
        items = data.get("data") or []
        if not items:
            data = self._request("POST", "/folders/createpath", json={"Path": ruta_final})
            items = data.get("data") or []
        if not items:
            raise ProviderError("Dataprius no devolvio la carpeta de destino.")
        carpeta = items[-1]
        data = self._request(
            "POST", "/files/upload", data={"IDFolder": carpeta["ID"]},
            files={"file": (Path(nombre).name, contenido)},
        )
        archivo = dict(data.get("data") or {})
        if not archivo.get("ID"):
            raise ProviderError("Dataprius no devolvio el identificador del archivo.")
        return {
            "provider": "dataprius", "id": archivo["ID"],
            "folder_id": archivo.get("Folder") or carpeta["ID"],
            "nombre": archivo.get("Name") or Path(nombre).name,
            "ruta": ruta_final, "tamano": archivo.get("Size"),
        }
